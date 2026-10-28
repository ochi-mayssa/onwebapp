from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from crm.models import Customer

from .security.crypto import ENVELOPE_MARKER, decrypt_json, encrypt_json
from .security.redaction import redact_mapping


class AutomationRequest(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('reviewing', 'Reviewing'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('cancelled', 'Cancelled'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='automation_requests')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='automation_requests')
    title = models.CharField(max_length=200)
    description = models.TextField()
    requirement_notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_automation_requests')
    approved_at = models.DateTimeField(null=True, blank=True)
    needs_review = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    setup_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    recurring_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['customer', 'status']), models.Index(fields=['requested_by', 'status'])]

    def __str__(self):
        return f'{self.title} ({self.status})'

    def approve(self, user):
        self.is_approved = True
        self.status = 'approved'
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save(update_fields=['is_approved', 'status', 'approved_by', 'approved_at', 'updated_at'])

    def reject(self, user=None):
        self.is_approved = False
        self.status = 'rejected'
        if user:
            self.approved_by = user
        self.save(update_fields=['is_approved', 'status', 'approved_by', 'updated_at'])


class AutomationWorkflow(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('testing', 'Testing'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('suspended', 'Suspended'),
        ('cancelled', 'Cancelled'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='automation_workflows')
    request = models.ForeignKey(AutomationRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name='workflows')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    trigger = models.CharField(max_length=100, default='manual', help_text='Manual, webhook, schedule, or event trigger.')
    config = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_workflows')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_workflows')
    active_from = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['customer', 'status']), models.Index(fields=['request', 'status'])]

    def __str__(self):
        return self.title

    def activate(self):
        if self.status not in {'approved', 'testing', 'paused'}:
            raise ValidationError('Only approved or paused workflows can be activated.')
        self.status = 'active'
        self.active_from = timezone.now()
        self.save(update_fields=['status', 'active_from', 'updated_at'])

    def suspend(self):
        self.status = 'suspended'
        self.save(update_fields=['status', 'updated_at'])


class WorkflowVersion(models.Model):
    workflow = models.ForeignKey(AutomationWorkflow, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField(default=1)
    config = models.JSONField(default=dict, blank=True)
    change_log = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='workflow_versions')
    created_at = models.DateTimeField(auto_now_add=True)
    approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_versions')

    class Meta:
        ordering = ['workflow', 'version_number']
        constraints = [models.UniqueConstraint(fields=['workflow', 'version_number'], name='unique_workflow_version')]

    def __str__(self):
        return f'{self.workflow.title} v{self.version_number}'


class IntegrationConnection(models.Model):
    PROVIDER_CHOICES = [
        ('gmail', 'Gmail'),
        ('outlook', 'Outlook'),
        ('hubspot', 'HubSpot'),
        ('salesforce', 'Salesforce'),
        ('slack', 'Slack'),
        ('webhook', 'Webhook'),
        ('custom', 'Custom API'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('error', 'Error'),
        ('revoked', 'Revoked'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='integration_connections')
    name = models.CharField(max_length=200)
    provider = models.CharField(max_length=50, choices=PROVIDER_CHOICES)
    external_service = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='inactive')
    config = models.JSONField(default=dict, blank=True)
    credentials = models.JSONField(
        default=dict,
        blank=True,
        help_text='Encrypted credential envelope. Never populated with plaintext by application code.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['customer', 'status']), models.Index(fields=['provider', 'status'])]

    def __str__(self):
        return f'{self.name} ({self.provider})'

    def save(self, *args, **kwargs):
        # Transparently migrate legacy plaintext rows on their next save.
        if self.credentials and ENVELOPE_MARKER not in self.credentials:
            self.set_credentials(self.credentials)
        super().save(*args, **kwargs)

    def set_credentials(self, credentials: dict[str, Any]) -> None:
        """Encrypt credentials at rest using the managed automation key.

        The JSON field stores an authenticated envelope, not plaintext. Rotation is
        intentionally explicit: callers must re-save credentials after changing the
        key. Legacy plaintext rows are readable via ``get_credentials`` but are
        re-encrypted the next time they are saved through this method.
        """
        self.credentials = encrypt_json(credentials or {})

    def get_credentials(self) -> dict[str, Any]:
        """Return decrypted credentials, or raise ``CredentialDecryptionError``."""
        return decrypt_json(self.credentials)

    @property
    def redacted_config(self) -> dict[str, Any]:
        return redact_mapping(self.config or {})

    @property
    def redacted_credentials(self) -> dict[str, Any]:
        return redact_mapping(self.get_credentials())



class AutomationExecution(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('succeeded', 'Succeeded'),
        ('failed', 'Failed'),
        ('timed_out', 'Timed Out'),
        ('cancelled', 'Cancelled'),
    ]
    TRIGGER_CHOICES = [
        ('manual', 'Manual'),
        ('webhook', 'Webhook'),
        ('schedule', 'Schedule'),
        ('event', 'Event'),
    ]

    workflow = models.ForeignKey(AutomationWorkflow, on_delete=models.CASCADE, related_name='executions')
    subscription = models.ForeignKey('Subscription', on_delete=models.SET_NULL, null=True, blank=True, related_name='executions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    trigger = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default='manual')
    execution_key = models.CharField(max_length=128, unique=True)
    attempt_count = models.PositiveIntegerField(default=0)
    current_step = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(default=0.0)
    error_message = models.TextField(blank=True)
    failure_code = models.CharField(max_length=64, blank=True, default='')
    usage_count = models.PositiveIntegerField(default=0)
    payload = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workflow', 'status']),
            models.Index(fields=['subscription', 'status']),
            models.Index(fields=['status', 'next_retry_at']),
        ]

    def __str__(self):
        return f'{self.workflow.title} #{self.pk}'

    @property
    def is_success(self):
        return self.status == 'succeeded'

    @property
    def is_terminal(self):
        return self.status in {'succeeded', 'failed', 'timed_out', 'cancelled'}



class ExecutionLog(models.Model):
    LEVEL_CHOICES = [
        ('debug', 'Debug'),
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ]

    execution = models.ForeignKey(AutomationExecution, on_delete=models.CASCADE, related_name='logs')
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='info')
    message = models.TextField()
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['execution', 'created_at'])]

    def __str__(self):
        return f'{self.execution_id} [{self.level}]'


class Plan(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=8, default='USD')
    setup_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    max_active_workflows = models.PositiveIntegerField(default=3)
    monthly_execution_limit = models.PositiveIntegerField(default=1000)
    features = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['price']

    def __str__(self):
        return f'{self.name} ({self.currency} {self.price})'


class Subscription(models.Model):
    STATUS_CHOICES = [
        ('trialing', 'Trialing'),
        ('active', 'Active'),
        ('past_due', 'Past Due'),
        ('cancelled', 'Cancelled'),
        ('suspended', 'Suspended'),
        ('pending_payment', 'Pending Payment'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='subscriptions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trialing')
    provider = models.CharField(max_length=50, default='manual', help_text='stripe, paypal, manual, etc.')
    provider_subscription_id = models.CharField(max_length=128, blank=True, default='')
    provider_customer_id = models.CharField(max_length=128, blank=True, default='')
    billing_period_start = models.DateTimeField(null=True, blank=True)
    billing_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    payment_status = models.CharField(max_length=30, default='pending', help_text='pending, paid, failed, refunded')
    is_active = models.BooleanField(default=False)
    started_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['provider', 'provider_subscription_id'], condition=models.Q(provider_subscription_id__gt=''), name='unique_provider_subscription_id')
        ]
        indexes = [models.Index(fields=['customer', 'status']), models.Index(fields=['provider', 'payment_status'])]

    def __str__(self):
        return f'{self.customer.name} - {self.plan.name}'

    @property
    def is_currently_active(self):
        if self.status != 'active' or not self.is_active:
            return False
        if self.billing_period_end and self.billing_period_end < timezone.now():
            return False
        return True

    def activate(self, *, period_start=None, period_end=None, payment_status='paid'):
        self.status = 'active'
        self.is_active = True
        self.payment_status = payment_status
        if period_start:
            self.billing_period_start = period_start
        if period_end:
            self.billing_period_end = period_end
        self.cancelled_at = None
        self.save(update_fields=[
            'status', 'is_active', 'payment_status', 'billing_period_start',
            'billing_period_end', 'cancelled_at', 'updated_at',
        ])

    def mark_past_due(self):
        self.status = 'past_due'
        self.is_active = False
        self.payment_status = 'failed'
        self.save(update_fields=['status', 'is_active', 'payment_status', 'updated_at'])

    def mark_cancelled(self):
        self.status = 'cancelled'
        self.is_active = False
        self.cancelled_at = self.cancelled_at or timezone.now()
        self.save(update_fields=['status', 'is_active', 'cancelled_at', 'updated_at'])


class UsageRecord(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='usage_records')
    metric = models.CharField(max_length=60, default='execution_count')
    usage_window = models.CharField(max_length=20, default='monthly')
    used_count = models.PositiveIntegerField(default=0)
    limit_value = models.PositiveIntegerField(default=0)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']
        constraints = [models.UniqueConstraint(fields=['subscription', 'metric', 'usage_window'], name='unique_usage_record_window')]

    def __str__(self):
        return f'{self.subscription} {self.metric}: {self.used_count}/{self.limit_value}'


class BillingEvent(models.Model):
    PROVIDER_CHOICES = [
        ('stripe', 'Stripe'),
        ('paypal', 'PayPal'),
        ('manual', 'Manual'),
    ]

    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='billing_events')
    provider = models.CharField(max_length=30, choices=PROVIDER_CHOICES, default='manual')
    event_type = models.CharField(max_length=80)
    provider_event_id = models.CharField(max_length=255, blank=True, default='')
    payload = models.JSONField(default=dict, blank=True)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['provider', 'provider_event_id'], condition=models.Q(provider_event_id__gt=''), name='unique_provider_event_id')]
        indexes = [models.Index(fields=['subscription', 'event_type']), models.Index(fields=['provider', 'processed'])]

    def __str__(self):
        return f'{self.event_type} ({self.provider})'
