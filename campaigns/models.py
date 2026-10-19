"""Email campaign models (admin-only marketing campaigns)."""
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Campaign(models.Model):
    """One administrator-composed marketing email campaign."""

    STATUS_DRAFT = 'draft'
    STATUS_SENDING = 'sending'
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'
    STATUS_CANCELED = 'canceled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SENDING, 'Sending'),
        (STATUS_SENT, 'Sent'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CANCELED, 'Canceled'),
    ]

    AUDIENCE_ALL = 'all'
    AUDIENCE_SUBSCRIBERS = 'subscribers'
    AUDIENCE_NON_SUBSCRIBERS = 'non_subscribers'
    AUDIENCE_SELECTED = 'selected'
    AUDIENCE_CHOICES = [
        (AUDIENCE_ALL, 'All eligible clients'),
        (AUDIENCE_SUBSCRIBERS, 'Clients with an active subscription'),
        (AUDIENCE_NON_SUBSCRIBERS, 'Clients without an active subscription'),
        (AUDIENCE_SELECTED, 'Selected individual clients'),
    ]

    reference = models.CharField(max_length=32, unique=True, blank=True, editable=False)
    name = models.CharField(max_length=200)
    subject = models.CharField(max_length=200)
    body_text = models.TextField(help_text='Plain-text version sent as the message body.')
    body_html = models.TextField(blank=True, help_text='Optional HTML version (sanitized before storage).')
    audience = models.CharField(max_length=32, choices=AUDIENCE_CHOICES, default=AUDIENCE_ALL)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='campaigns_created',
    )
    selected_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='email_campaigns_selected',
    )

    total_recipients = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    pending_count = models.PositiveIntegerField(default=0)

    batch_size = models.PositiveIntegerField(default=5)
    batch_delay_seconds = models.FloatField(default=2.5)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference} - {self.name}'

    def save(self, *args, **kwargs):
        if not self.reference:
            base = uuid.uuid4().hex[:10].upper()
            reference = f'CMP-{base}'
            while Campaign.objects.filter(reference=reference).exists():
                base = uuid.uuid4().hex[:10].upper()
                reference = f'CMP-{base}'
            self.reference = reference
        super().save(*args, **kwargs)

    @property
    def is_resumable(self):
        """A send can be resumed when rows are still pending after an interruption."""
        return (
            self.status in (self.STATUS_SENDING, self.STATUS_FAILED)
            and self.pending_count > 0
        )

    @property
    def looks_interrupted(self):
        """Sending for a long time with no finish usually means the process died."""
        if self.status != self.STATUS_SENDING or not self.started_at:
            return False
        if self.finished_at:
            return False
        age = timezone.now() - self.started_at
        return age.total_seconds() > 1800


class CampaignRecipient(models.Model):
    """Per-recipient delivery record (source of truth for counts)."""

    STATUS_PENDING = 'pending'
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SENT, 'Sent'),
        (STATUS_FAILED, 'Failed'),
    ]

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='recipients')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='campaign_deliveries',
    )
    email = models.EmailField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=300, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['email']
        constraints = [
            models.UniqueConstraint(fields=['campaign', 'email'], name='uniq_campaign_email'),
        ]

    def __str__(self):
        return f'{self.campaign.reference} -> {self.email} ({self.status})'
