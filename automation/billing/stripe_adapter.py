"""Stripe implementation of the billing adapter."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import stripe
from django.conf import settings

from .base import (
    BillingAdapter,
    BillingError,
    BillingNotConfigured,
    CheckoutSession,
    ProviderEvent,
    WebhookVerificationError,
)


def stripe_object_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    to_dict = getattr(value, 'to_dict_recursive', None)
    if callable(to_dict):
        return dict(to_dict())
    try:
        return dict(value)
    except (TypeError, ValueError):
        return {}


class StripeBillingAdapter(BillingAdapter):
    provider = 'stripe'

    def __init__(self, *, api_key: str | None = None, webhook_secret: str | None = None):
        self.api_key = api_key if api_key is not None else getattr(settings, 'STRIPE_SECRET_KEY', '')
        self.webhook_secret = (
            webhook_secret
            if webhook_secret is not None
            else getattr(
                settings,
                'AUTOMATION_STRIPE_WEBHOOK_SECRET',
                getattr(settings, 'STRIPE_WEBHOOK_SECRET', ''),
            )
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.webhook_secret)

    def create_checkout_session(
        self,
        *,
        customer,
        plan,
        local_subscription,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession:
        if not self.api_key:
            raise BillingNotConfigured('Stripe is not configured.')
        amount = int((Decimal(plan.price) * 100).to_integral_value())
        if amount <= 0:
            raise BillingError('Plan price must be greater than zero.')

        metadata = {
            'local_subscription_id': str(local_subscription.pk),
            'customer_id': str(customer.pk),
            'plan_id': str(plan.pk),
        }
        try:
            session = stripe.checkout.Session.create(
                api_key=self.api_key,
                mode='subscription',
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': (plan.currency or 'usd').lower(),
                        'product_data': {
                            'name': plan.name,
                            'description': (plan.description or '')[:500],
                        },
                        'recurring': {'interval': 'month'},
                        'unit_amount': amount,
                    },
                    'quantity': 1,
                }],
                success_url=success_url,
                cancel_url=cancel_url,
                client_reference_id=str(customer.pk),
                metadata=metadata,
                subscription_data={'metadata': metadata},
            )
        except Exception as exc:
            raise BillingError('Could not create a Stripe checkout session.') from exc

        if not getattr(session, 'url', None) or not getattr(session, 'id', None):
            raise BillingError('Stripe returned an incomplete checkout session.')
        return CheckoutSession(provider=self.provider, session_id=str(session.id), url=str(session.url))

    def parse_webhook(self, payload: bytes, signature: str | None) -> ProviderEvent:
        if not self.webhook_secret:
            raise WebhookVerificationError('Stripe webhook secret is not configured.')
        if not signature:
            raise WebhookVerificationError('Missing Stripe signature.')
        try:
            event = stripe.Webhook.construct_event(payload, signature, self.webhook_secret)
        except Exception as exc:
            raise WebhookVerificationError('Invalid Stripe webhook signature or payload.') from exc

        event_dict = stripe_object_to_dict(event)
        event_id = event_dict.get('id')
        event_type = event_dict.get('type')
        data = (event_dict.get('data') or {}).get('object')
        if not event_id or not event_type or not isinstance(data, dict):
            raise WebhookVerificationError('Stripe event is missing required fields.')
        return ProviderEvent(
            provider=self.provider,
            event_id=str(event_id),
            event_type=str(event_type),
            data=data,
        )

    def retrieve_subscription(self, provider_subscription_id: str) -> dict[str, Any]:
        if not self.api_key:
            raise BillingNotConfigured('Stripe is not configured.')
        try:
            subscription = stripe.Subscription.retrieve(provider_subscription_id, api_key=self.api_key)
        except Exception as exc:
            raise BillingError('Could not retrieve the Stripe subscription.') from exc
        return stripe_object_to_dict(subscription)
