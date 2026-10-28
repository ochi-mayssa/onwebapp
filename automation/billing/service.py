"""Billing orchestration shared by all providers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import BillingEvent, Plan, Subscription
from ..security.redaction import redact_mapping, redact_text
from .base import (
    BillingAdapter,
    BillingError,
    BillingNotConfigured,
    ProviderEvent,
    WebhookVerificationError,
)
from .stripe_adapter import StripeBillingAdapter

logger = logging.getLogger('automation')

_STRIPE_STATUS_MAP = {
    'active': 'active',
    'trialing': 'trialing',
    'past_due': 'past_due',
    'canceled': 'cancelled',
    'cancelled': 'cancelled',
    'unpaid': 'past_due',
    'incomplete': 'pending_payment',
    'incomplete_expired': 'pending_payment',
    'paused': 'suspended',
}


@dataclass(frozen=True)
class EventOutcome:
    status: str
    subscription: Subscription | None = None


def get_billing_adapter(provider: str = 'stripe') -> BillingAdapter:
    if provider == 'stripe':
        return StripeBillingAdapter()
    raise BillingNotConfigured('Unsupported billing provider.')


def _timestamp(value: Any) -> datetime | None:
    if value in (None, ''):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _object_id(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get('id')
    return str(value) if value else ''


def _safe_event_payload(event: ProviderEvent) -> dict[str, Any]:
    return redact_mapping({
        'id': event.event_id,
        'type': event.event_type,
        'data': event.data,
    })


def start_checkout(
    *,
    customer,
    plan: Plan,
    success_url: str,
    cancel_url: str,
    provider: str = 'stripe',
):
    """Create a local pending subscription and a provider checkout session.

    The redirect back from the provider never activates the subscription; only a
    signature-verified webhook can do that.
    """
    if not plan.is_active:
        raise BillingError('Plan is not available.')
    if Decimal(plan.price or 0) <= 0:
        raise BillingError('Plan price must be greater than zero.')

    existing = (
        Subscription.objects.filter(customer=customer, plan=plan, provider=provider)
        .order_by('-created_at')
        .first()
    )
    if existing and existing.is_currently_active:
        raise BillingError('An active subscription already exists for this plan.')

    adapter = get_billing_adapter(provider)
    created = False
    if existing is None:
        existing = Subscription.objects.create(
            customer=customer,
            plan=plan,
            provider=provider,
            status='pending_payment',
            is_active=False,
            payment_status='pending',
        )
        created = True
    else:
        existing.status = 'pending_payment'
        existing.is_active = False
        existing.payment_status = 'pending'
        existing.save(update_fields=['status', 'is_active', 'payment_status', 'updated_at'])

    try:
        return adapter.create_checkout_session(
            customer=customer,
            plan=plan,
            local_subscription=existing,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except Exception:
        if created:
            existing.delete()
        raise


def process_webhook(payload: bytes, signature: str | None, *, provider: str = 'stripe') -> str:
    adapter = get_billing_adapter(provider)
    event = adapter.parse_webhook(payload, signature)
    return handle_provider_event(adapter, event)


def _resolve_subscription(event: ProviderEvent) -> Subscription | None:
    data = event.data or {}
    metadata = data.get('metadata') or {}

    local_id = metadata.get('local_subscription_id') or metadata.get('automation_subscription_id')
    if local_id:
        subscription = Subscription.objects.filter(pk=local_id, provider=event.provider).first()
        if subscription:
            _assert_tenant(subscription, metadata, data)
            return subscription

    provider_subscription_id = _object_id(data.get('subscription'))
    if not provider_subscription_id and event.event_type.startswith('customer.subscription.'):
        provider_subscription_id = _object_id(data.get('id'))
    if provider_subscription_id:
        subscription = (
            Subscription.objects.filter(
                provider=event.provider,
                provider_subscription_id=provider_subscription_id,
            )
            .order_by('-created_at')
            .first()
        )
        if subscription:
            _assert_tenant(subscription, metadata, data)
            return subscription

    customer_id = metadata.get('customer_id') or data.get('client_reference_id')
    plan_id = metadata.get('plan_id')
    if customer_id and plan_id:
        subscription = (
            Subscription.objects.filter(
                customer_id=customer_id,
                plan_id=plan_id,
                provider=event.provider,
            )
            .order_by('-created_at')
            .first()
        )
        if subscription:
            _assert_tenant(subscription, metadata, data)
            return subscription
    return None


def _assert_tenant(subscription: Subscription, metadata: dict, data: dict) -> None:
    claimed_customer = metadata.get('customer_id') or data.get('client_reference_id')
    if claimed_customer and str(claimed_customer) != str(subscription.customer_id):
        raise BillingError('Provider event customer does not match the subscription tenant.')


def _apply_subscription_object(subscription: Subscription, data: dict) -> Subscription:
    metadata = data.get('metadata') or {}
    _assert_tenant(subscription, metadata, data)

    provider_status = str(data.get('status') or '').lower()
    local_status = _STRIPE_STATUS_MAP.get(provider_status, 'pending_payment')
    subscription.provider_subscription_id = _object_id(data.get('id')) or subscription.provider_subscription_id
    subscription.provider_customer_id = _object_id(data.get('customer')) or subscription.provider_customer_id
    subscription.status = local_status
    subscription.is_active = local_status == 'active'
    subscription.cancel_at_period_end = bool(data.get('cancel_at_period_end'))
    subscription.billing_period_start = _timestamp(data.get('current_period_start')) or subscription.billing_period_start
    subscription.billing_period_end = _timestamp(data.get('current_period_end')) or subscription.billing_period_end

    cancelled_at = _timestamp(data.get('canceled_at'))
    if cancelled_at:
        subscription.cancelled_at = cancelled_at
    if local_status == 'cancelled':
        subscription.cancelled_at = subscription.cancelled_at or timezone.now()

    if local_status == 'active':
        subscription.payment_status = 'paid'
    elif local_status == 'past_due':
        subscription.payment_status = 'failed'
    elif local_status == 'cancelled':
        subscription.payment_status = 'pending'
    subscription.save()
    return subscription


def _invoice_period(data: dict) -> tuple[datetime | None, datetime | None]:
    period_start = _timestamp(data.get('period_start'))
    period_end = _timestamp(data.get('period_end'))
    for line in data.get('lines', {}).get('data', []) if isinstance(data.get('lines'), dict) else []:
        period = (line or {}).get('period') or {}
        period_start = _timestamp(period.get('start')) or period_start
        period_end = _timestamp(period.get('end')) or period_end
    return period_start, period_end


def _apply_event(adapter: BillingAdapter, event: ProviderEvent, subscription: Subscription | None) -> EventOutcome:
    if subscription is None:
        return EventOutcome(status='ignored')

    data = event.data or {}
    event_type = event.event_type

    if event_type == 'checkout.session.completed':
        subscription.provider_customer_id = _object_id(data.get('customer')) or subscription.provider_customer_id
        provider_subscription_id = _object_id(data.get('subscription'))
        if provider_subscription_id:
            subscription.provider_subscription_id = provider_subscription_id
            # Do not infer paid access from the redirect; retrieve authoritative state.
            remote = adapter.retrieve_subscription(provider_subscription_id)
            if remote:
                _apply_subscription_object(subscription, remote)
                return EventOutcome(status='processed', subscription=subscription)
        subscription.status = 'pending_payment'
        subscription.is_active = False
        subscription.payment_status = 'pending'
        subscription.save()
        return EventOutcome(status='processed', subscription=subscription)

    if event_type in {
        'customer.subscription.created',
        'customer.subscription.updated',
        'customer.subscription.deleted',
    }:
        _apply_subscription_object(subscription, data)
        return EventOutcome(status='processed', subscription=subscription)

    if event_type in {'invoice.paid', 'invoice.payment_succeeded'}:
        period_start, period_end = _invoice_period(data)
        subscription.provider_customer_id = _object_id(data.get('customer')) or subscription.provider_customer_id
        subscription.provider_subscription_id = _object_id(data.get('subscription')) or subscription.provider_subscription_id
        subscription.activate(period_start=period_start, period_end=period_end)
        return EventOutcome(status='processed', subscription=subscription)

    if event_type in {'invoice.payment_failed', 'invoice.payment_action_required'}:
        subscription.mark_past_due()
        return EventOutcome(status='processed', subscription=subscription)

    if event_type == 'customer.subscription.paused':
        _apply_subscription_object(subscription, {**data, 'status': 'paused'})
        return EventOutcome(status='processed', subscription=subscription)

    if event_type == 'customer.subscription.resumed':
        _apply_subscription_object(subscription, {**data, 'status': 'active'})
        return EventOutcome(status='processed', subscription=subscription)

    return EventOutcome(status='ignored', subscription=subscription)


def handle_provider_event(adapter: BillingAdapter, event: ProviderEvent) -> str:
    """Verify/dedupe/apply one provider event. Returns a short status string."""
    if not event.event_id or not event.event_type:
        raise WebhookVerificationError('Provider event is missing an id or type.')

    try:
        with transaction.atomic():
            record, created = BillingEvent.objects.select_for_update().get_or_create(
                provider=event.provider,
                provider_event_id=event.event_id,
                defaults={
                    'event_type': event.event_type,
                    'payload': _safe_event_payload(event),
                    'processed': False,
                },
            )
            if not created and record.processed:
                return 'duplicate'

            subscription = _resolve_subscription(event)
            if subscription is not None:
                record.subscription = subscription
            outcome = _apply_event(adapter, event, subscription)

            record.event_type = event.event_type
            record.payload = _safe_event_payload(event)
            record.processed = True
            record.processed_at = timezone.now()
            record.failure_reason = '' if outcome.status == 'processed' else outcome.status
            record.save()
            return outcome.status
    except IntegrityError:
        # Concurrent delivery of the same event; the unique constraint wins.
        duplicate = BillingEvent.objects.filter(
            provider=event.provider,
            provider_event_id=event.event_id,
            processed=True,
        ).exists()
        if duplicate:
            return 'duplicate'
        raise
    except Exception as exc:
        redacted = redact_text(str(exc))[:1000]
        BillingEvent.objects.filter(
            provider=event.provider,
            provider_event_id=event.event_id,
        ).update(processed=False, failure_reason=redacted)
        logger.warning('Billing event %s failed: %s', event.event_id, redacted)
        raise
