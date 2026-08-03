"""Webhook dispatcher — sends signed POST requests to registered endpoints.

Features:
- HMAC-SHA256 signature in ``X-Webhook-Signature`` header.
- Exponential backoff retry (3 attempts).
- Delivery logging via ``WebhookDelivery`` model.
- Non-blocking: uses Django's ``on_commit`` to avoid blocking transactions.
"""
import hashlib
import hmac
import json
import logging
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    BrandingWebhook,
    WebhookDelivery,
    WEBHOOK_EVENT_TYPES,
)

logger = logging.getLogger('branding.webhooks')

# Maximum delivery attempts
MAX_ATTEMPTS = 3

# Delay between retries (seconds) — exponential backoff
RETRY_DELAYS = [2, 10, 30]


def _sign_payload(payload_bytes, secret):
    """Compute HMAC-SHA256 signature of the payload."""
    if not secret:
        return ''
    return hmac.new(
        secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


def _build_payload(event_type, instance):
    """Build the JSON payload for a webhook event."""
    data = {
        'event': event_type,
        'timestamp': timezone.now().isoformat(),
        'data': {},
    }

    if hasattr(instance, 'pk'):
        data['data']['id'] = instance.pk

    # BrandingRequest
    if hasattr(instance, 'request_number'):
        data['data'].update({
            'request_number': instance.request_number,
            'company_name': instance.company_name,
            'status': instance.status,
            'status_display': instance.get_status_display(),
            'priority': instance.priority,
            'industry': instance.industry,
            'user_id': instance.user_id,
            'designer_id': instance.designer_id,
            'collection_id': instance.collection_id,
            'created_at': instance.created_at.isoformat() if instance.created_at else None,
            'updated_at': instance.updated_at.isoformat() if instance.updated_at else None,
        })
        if instance.designer_id:
            data['data']['designer_name'] = (
                instance.designer.get_full_name() or instance.designer.username
            )

    # BrandingAsset
    if hasattr(instance, 'original_name') and hasattr(instance, 'asset_type'):
        data['data'].update({
            'request_id': instance.request_id,
            'original_name': instance.original_name,
            'asset_type': instance.asset_type,
            'content_type': instance.content_type,
            'size': instance.size,
            'uploaded_at': instance.uploaded_at.isoformat() if instance.uploaded_at else None,
        })

    # BrandingFeedback
    if hasattr(instance, 'rating') and hasattr(instance, 'would_recommend'):
        data['data'].update({
            'request_id': instance.request_id,
            'request_number': instance.request.request_number if instance.request else None,
            'rating': instance.rating,
            'comment': instance.comment,
            'would_recommend': instance.would_recommend,
            'created_at': instance.created_at.isoformat() if instance.created_at else None,
        })

    return data


def dispatch_webhook(event_type, instance):
    """Dispatch a webhook event to all subscribed, active endpoints.

    This is designed to be called from signal receivers.
    Uses ``transaction.on_commit`` to ensure the payload reflects
    committed data.
    """
    def _send():
        webhooks = BrandingWebhook.objects.filter(is_active=True)
        for wh in webhooks:
            if not wh.accepts_event(event_type):
                continue
            _deliver(wh, event_type, instance)

    transaction.on_commit(_send)


def _deliver(webhook, event_type, instance, attempt=1):
    """Deliver a single webhook payload with retry logic."""
    payload = _build_payload(event_type, instance)
    payload_bytes = json.dumps(payload, default=str).encode('utf-8')
    signature = _sign_payload(payload_bytes, webhook.secret)

    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Event': event_type,
        'X-Webhook-ID': str(webhook.pk),
        'User-Agent': 'OnWebApp-Branding-Webhook/1.0',
    }
    if signature:
        headers['X-Webhook-Signature'] = signature

    # Create delivery log entry
    delivery = WebhookDelivery.objects.create(
        webhook=webhook,
        event_type=event_type,
        payload=payload,
        status='pending' if attempt == 1 else 'retrying',
        attempt=attempt,
    )

    try:
        resp = requests.post(
            webhook.url,
            data=payload_bytes,
            headers=headers,
            timeout=10,
        )
        delivery.status_code = resp.status_code
        delivery.response_body = resp.text[:2000]
        delivery.completed_at = timezone.now()

        if 200 <= resp.status_code < 300:
            delivery.status = 'success'
            webhook.last_triggered_at = timezone.now()
            webhook.failure_count = 0
            webhook.save(update_fields=['last_triggered_at', 'failure_count'])
            logger.info(
                '[Webhook] Delivered %s to %s — %d (attempt %d)',
                event_type, webhook.url, resp.status_code, attempt,
            )
        else:
            _handle_failure(delivery, webhook, event_type, instance, attempt, resp.status_code)
    except requests.RequestException as exc:
        delivery.response_body = str(exc)[:2000]
        delivery.completed_at = timezone.now()
        _handle_failure(delivery, webhook, event_type, instance, attempt, None)

    delivery.save()


def _handle_failure(delivery, webhook, event_type, instance, attempt, status_code):
    """Handle a failed delivery — retry or mark as failed."""
    delivery.status = 'failed'
    delivery.save()

    webhook.failure_count += 1
    webhook.save(update_fields=['failure_count'])

    logger.warning(
        '[Webhook] Failed delivery of %s to %s (attempt %d, status=%s)',
        event_type, webhook.url, attempt, status_code,
    )

    if attempt < MAX_ATTEMPTS:
        delay = RETRY_DELAYS[attempt - 1] if attempt <= len(RETRY_DELAYS) else RETRY_DELAYS[-1]
        # Schedule retry using threading (non-blocking)
        import threading
        timer = threading.Timer(
            delay,
            _deliver,
            args=(webhook, event_type, instance),
            kwargs={'attempt': attempt + 1},
        )
        timer.daemon = True
        timer.start()
        logger.info(
            '[Webhook] Scheduled retry %d for %s to %s in %ds',
            attempt + 1, event_type, webhook.url, delay,
        )


# ---------------------------------------------------------------------------
# Signal receivers — fire webhooks on model events
# ---------------------------------------------------------------------------

@receiver(post_save, sender='branding.BrandingRequest')
def webhook_status_change(sender, instance, created, **kwargs):
    """Fire webhooks when a branding request status changes."""
    if created:
        dispatch_webhook('request_created', instance)
    else:
        # Only fire status_change if status actually changed
        if instance.status != getattr(instance, '_original_status', None):
            dispatch_webhook('status_change', instance)
            if instance.status == 'COMPLETED':
                dispatch_webhook('completion', instance)


@receiver(post_save, sender='branding.BrandingAsset')
def webhook_asset_upload(sender, instance, created, **kwargs):
    """Fire webhook when an asset is uploaded."""
    if created:
        dispatch_webhook('asset_upload', instance)


@receiver(post_save, sender='branding.BrandingFeedback')
def webhook_feedback_submitted(sender, instance, created, **kwargs):
    """Fire webhook when feedback is submitted."""
    if created:
        dispatch_webhook('feedback_submitted', instance)


# Track original status for change detection
def _capture_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._original_status = sender.objects.filter(pk=instance.pk).values_list('status', flat=True).get()
        except sender.DoesNotExist:
            instance._original_status = None
    else:
        instance._original_status = None


from django.db.models.signals import pre_save
pre_save.connect(_capture_status, sender='branding.BrandingRequest')
