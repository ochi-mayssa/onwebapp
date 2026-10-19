"""Bounded, resumable campaign delivery.

There is no Celery worker in this deployment, so campaigns are delivered by a
daemon thread started from the web request, using small batches with a
configurable delay between them (safe for Resend's rate limits). The request
itself returns immediately. Limitations are documented in
docs/EMAIL_CAMPAIGNS.md.

``CampaignRecipient`` rows are the source of truth: counters are recomputed
from them after every batch, so an interrupted send stays accurate and can be
resumed (only pending rows are processed).
"""
import logging
import threading
import time

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe

from home.emails import send_notification_email

from .audience import resolved_email_map
from .models import Campaign, CampaignRecipient
from .sanitizer import sanitize_campaign_html

logger = logging.getLogger(__name__)

UNSUBSCRIBE_SALT = 'campaign-unsubscribe'


def unsubscribe_url_for(user):
    """Signed, per-user unsubscribe link (no login required)."""
    token = signing.TimestampSigner(salt=UNSUBSCRIBE_SALT).sign(str(user.pk))
    path = reverse('campaigns:unsubscribe', args=[token])
    return f'{settings.SITE_URL.rstrip("/")}{path}'


def verify_unsubscribe_token(token):
    """Return the user pk for a valid token, or None."""
    try:
        return int(signing.TimestampSigner(salt=UNSUBSCRIBE_SALT).unsign(token))
    except Exception:
        return None


def _spawn(fn):
    """Run fn in a daemon thread (process-local, best effort)."""
    def _run():
        try:
            fn()
        except Exception:
            logger.exception('Campaign delivery crashed')
    threading.Thread(target=_run, daemon=True).start()


def start_send(campaign):
    """Materialize recipients and flip draft -> sending.

    Returns (ok, error_code). Duplicate starts are refused atomically.
    """
    with transaction.atomic():
        locked = Campaign.objects.select_for_update().get(pk=campaign.pk)
        if locked.status != Campaign.STATUS_DRAFT:
            return False, 'not_draft'
        email_map = resolved_email_map(locked)
        max_recipients = settings.CAMPAIGN_MAX_RECIPIENTS
        if len(email_map) > max_recipients:
            return False, 'too_many_recipients'
        rows = [
            CampaignRecipient(campaign=locked, user_id=pk, email=email)
            for pk, email in email_map.items()
        ]
        CampaignRecipient.objects.bulk_create(rows, ignore_conflicts=True)
        locked.batch_size = settings.CAMPAIGN_BATCH_SIZE
        locked.batch_delay_seconds = settings.CAMPAIGN_BATCH_DELAY_SECONDS
        locked.status = Campaign.STATUS_SENDING
        locked.started_at = timezone.now()
        locked.finished_at = None
        locked.save(update_fields=[
            'batch_size', 'batch_delay_seconds', 'status', 'started_at', 'finished_at', 'updated_at',
        ])
        _refresh_counters(locked)
        campaign_id = locked.pk
    _spawn(lambda: deliver_campaign(campaign_id))
    return True, None


def resume_send(campaign):
    """Re-queue a stuck/failed campaign; only pending rows are processed."""
    with transaction.atomic():
        locked = Campaign.objects.select_for_update().get(pk=campaign.pk)
        if locked.status not in (Campaign.STATUS_SENDING, Campaign.STATUS_FAILED):
            return False, 'not_resumable'
        if not CampaignRecipient.objects.filter(campaign=locked, status=CampaignRecipient.STATUS_PENDING).exists():
            return False, 'nothing_pending'
        locked.status = Campaign.STATUS_SENDING
        locked.finished_at = None
        locked.save(update_fields=['status', 'finished_at', 'updated_at'])
        campaign_id = locked.pk
    _spawn(lambda: deliver_campaign(campaign_id))
    return True, None


def deliver_campaign(campaign_id, *, sleep=time.sleep):
    """Deliver all pending recipients in batches; idempotent and resumable."""
    campaign = Campaign.objects.get(pk=campaign_id)
    batch_size = campaign.batch_size or settings.CAMPAIGN_BATCH_SIZE
    delay = campaign.batch_delay_seconds
    while True:
        pending = list(
            CampaignRecipient.objects.filter(
                campaign=campaign, status=CampaignRecipient.STATUS_PENDING,
            ).order_by('pk')[:batch_size]
        )
        if not pending:
            break
        for recipient in pending:
            _deliver_one(campaign, recipient)
        _refresh_counters(campaign)
        if delay and CampaignRecipient.objects.filter(
            campaign=campaign, status=CampaignRecipient.STATUS_PENDING,
        ).exists():
            sleep(delay)
    campaign.refresh_from_db()
    _refresh_counters(campaign)
    _finalize(campaign)


def _deliver_one(campaign, recipient):
    recipient.attempts += 1
    unsubscribe_url = None
    if recipient.user_id and recipient.user:
        try:
            unsubscribe_url = unsubscribe_url_for(recipient.user)
        except Exception:
            logger.exception('Could not build unsubscribe URL for %s', recipient.email)
    text = campaign.body_text or ''
    if unsubscribe_url:
        text = f'{text}\n\nUnsubscribe from marketing emails: {unsubscribe_url}\n'
    context = {
        'subject': campaign.subject,
        'body_html_safe': mark_safe(sanitize_campaign_html(campaign.body_html)),
        'unsubscribe_url': unsubscribe_url,
    }
    ok = send_notification_email(
        subject=campaign.subject,
        recipients=[recipient.email],
        template_name='emails/campaign_message.html',
        context=context,
        text_body=text,
        label='campaign',
    )
    if ok:
        recipient.status = CampaignRecipient.STATUS_SENT
        recipient.sent_at = timezone.now()
        recipient.last_error = ''
    else:
        recipient.status = CampaignRecipient.STATUS_FAILED
        recipient.last_error = 'Delivery failed (see server logs)'
    recipient.save(update_fields=['status', 'attempts', 'sent_at', 'last_error'])


def _refresh_counters(campaign):
    """Recompute counters from recipient rows (source of truth)."""
    agg = CampaignRecipient.objects.filter(campaign=campaign).aggregate(
        total=Count('id'),
        sent=Count('id', filter=Q(status=CampaignRecipient.STATUS_SENT)),
        failed=Count('id', filter=Q(status=CampaignRecipient.STATUS_FAILED)),
        pending=Count('id', filter=Q(status=CampaignRecipient.STATUS_PENDING)),
    )
    campaign.total_recipients = agg['total']
    campaign.sent_count = agg['sent']
    campaign.failed_count = agg['failed']
    campaign.pending_count = agg['pending']
    campaign.save(update_fields=[
        'total_recipients', 'sent_count', 'failed_count', 'pending_count', 'updated_at',
    ])


def _finalize(campaign):
    if campaign.status != Campaign.STATUS_SENDING:
        return
    if campaign.pending_count > 0:
        return
    if campaign.sent_count == 0 and campaign.failed_count > 0:
        campaign.status = Campaign.STATUS_FAILED
    else:
        campaign.status = Campaign.STATUS_SENT
    campaign.finished_at = timezone.now()
    campaign.save(update_fields=['status', 'finished_at', 'updated_at'])
