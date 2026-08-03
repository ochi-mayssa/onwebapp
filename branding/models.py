"""Data models for the enterprise Branding Service."""
import os
from datetime import datetime

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

# ---------------------------------------------------------------------------
# Choice constants
# ---------------------------------------------------------------------------

INDUSTRY_CHOICES = [
    ('manufacturing', 'Manufacturing'),
    ('healthcare', 'Healthcare'),
    ('restaurant', 'Restaurant'),
    ('construction', 'Construction'),
    ('real_estate', 'Real Estate'),
    ('education', 'Education'),
    ('finance', 'Finance'),
    ('logistics', 'Logistics'),
    ('technology', 'Technology'),
    ('saas', 'SaaS'),
    ('retail', 'Retail'),
    ('travel', 'Travel'),
    ('automotive', 'Automotive'),
    ('energy', 'Energy'),
    ('other', 'Other'),
]

COLLECTION_CATEGORIES = [
    ('manufacturing', 'Manufacturing'),
    ('healthcare', 'Healthcare'),
    ('restaurant', 'Restaurant'),
    ('construction', 'Construction'),
    ('education', 'Education'),
    ('finance', 'Finance'),
    ('real_estate', 'Real Estate'),
    ('saas', 'SaaS'),
]

BRAND_VALUES = [
    ('professional', 'Professional'),
    ('premium', 'Premium'),
    ('luxury', 'Luxury'),
    ('modern', 'Modern'),
    ('innovative', 'Innovative'),
    ('corporate', 'Corporate'),
    ('friendly', 'Friendly'),
    ('minimal', 'Minimal'),
    ('creative', 'Creative'),
    ('bold', 'Bold'),
]

PREFERRED_COLORS = [
    ('blue', 'Blue'),
    ('orange', 'Orange'),
    ('green', 'Green'),
    ('red', 'Red'),
    ('purple', 'Purple'),
    ('black', 'Black'),
    ('white', 'White'),
    ('gray', 'Gray'),
    ('none', 'No Preference'),
]

CURRENT_BRANDING_CHOICES = [
    ('logo', 'Logo'),
    ('brand_guidelines', 'Brand Guidelines'),
    ('website', 'Website'),
    ('social_media', 'Social Media'),
    ('packaging', 'Packaging'),
    ('marketing_materials', 'Marketing Materials'),
]

ASSET_TYPES = [
    ('logo', 'Logo'),
    ('brand_guidelines', 'Brand Guidelines'),
    ('inspiration', 'Inspiration Image'),
    ('document', 'Document'),
    ('image', 'Image'),
    ('archive', 'Archive'),
    ('other', 'Other'),
]

# Step 4 library filter categories map directly onto COLLECTION_CATEGORIES.

STATUS_CHOICES = [
    ('DRAFT', 'Draft'),
    ('PENDING_REVIEW', 'Pending Review'),
    ('IN_REVIEW', 'In Review'),
    ('ASSIGNED', 'Assigned'),
    ('DESIGNING', 'Designing'),
    ('WAITING_CLIENT', 'Waiting on Client'),
    ('REVISION', 'Revision'),
    ('APPROVED', 'Approved'),
    ('COMPLETED', 'Completed'),
    ('ARCHIVED', 'Archived'),
]

PRIORITY_CHOICES = [
    ('LOW', 'Low'),
    ('MEDIUM', 'Medium'),
    ('HIGH', 'High'),
    ('URGENT', 'Urgent'),
]

TIMELINE_EVENT_TYPES = [
    ('CREATED', 'Created'),
    ('STATUS_CHANGE', 'Status Change'),
    ('ASSIGNMENT', 'Designer Assignment'),
    ('NOTE', 'Internal Note'),
    ('COMMENT', 'Client Comment'),
    ('UPLOAD', 'File Upload'),
    ('FILE_UPDATE', 'File Updated'),
    ('COLLECTION_CHANGE', 'Collection Changed'),
    ('PRIORITY_CHANGE', 'Priority Changed'),
    ('DELIVERY_CHANGE', 'Delivery Date Changed'),
]

NOTIFICATION_TYPES = [
    ('NEW_REQUEST', 'New Request'),
    ('DESIGNER_ASSIGNED', 'Designer Assigned'),
    ('STATUS_CHANGED', 'Status Changed'),
    ('COMPLETED', 'Request Completed'),
    ('COMMENT', 'New Comment'),
    ('SYSTEM', 'System'),
]

RETENTION_CHOICES = [
    ('1y', '1 Year'),
    ('2y', '2 Years'),
    ('3y', '3 Years'),
    ('5y', '5 Years'),
    ('7y', '7 Years'),
    ('indefinite', 'Indefinite'),
]

CONSENT_TYPES = [
    ('data_processing', 'Data Processing'),
    ('marketing', 'Marketing Communications'),
    ('analytics', 'Analytics & Performance'),
    ('third_party', 'Third-Party Sharing'),
]

PRIVACY_PAGES = [
    ('privacy_policy', 'Privacy Policy'),
    ('terms_of_service', 'Terms of Service'),
    ('cookie_policy', 'Cookie Policy'),
]


def _upload_to(instance, filename):
    """Store request assets under media/branding/requests/<pk>/<uuid-name>."""
    base = getattr(instance.request, 'pk', None) or getattr(instance, 'request_id', 'pending')
    safe = os.path.basename(filename).replace(' ', '_')
    return f'branding/requests/{base}/assets/{safe}'


class BrandCollection(models.Model):
    """A curated brand identity collection shown in the Step 4 library."""

    category = models.CharField(max_length=40, choices=COLLECTION_CATEGORIES, db_index=True)
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    industry = models.CharField(max_length=80, blank=True, default='')
    description = models.TextField(blank=True, default='')
    style_tags = models.JSONField(default=list, blank=True)
    examples = models.JSONField(default=list, blank=True)
    preview_image = models.ImageField(upload_to='branding/collections/', blank=True, null=True)
    accent_color = models.CharField(max_length=9, default='#6366f1')

    # Collection preview kit
    hero_image = models.ImageField(upload_to='branding/collections/', blank=True, null=True)
    logo_image = models.ImageField(upload_to='branding/collections/', blank=True, null=True)
    typography_image = models.ImageField(upload_to='branding/collections/', blank=True, null=True)
    business_card_image = models.ImageField(upload_to='branding/collections/', blank=True, null=True)
    presentation_image = models.ImageField(upload_to='branding/collections/', blank=True, null=True)
    letterhead_image = models.ImageField(upload_to='branding/collections/', blank=True, null=True)
    email_signature_image = models.ImageField(upload_to='branding/collections/', blank=True, null=True)
    social_media_image = models.ImageField(upload_to='branding/collections/', blank=True, null=True)
    brand_guidelines_image = models.ImageField(upload_to='branding/collections/', blank=True, null=True)
    color_palette = models.JSONField(default=list, blank=True)
    fonts = models.JSONField(default=list, blank=True)

    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'sort_order', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    @property
    def preview_items(self):
        """Ordered kit of (key, label, icon, image) used on the detail preview."""
        items = [
            ('hero', 'Hero Image', 'fa-image', self.hero_image),
            ('logo', 'Logo', 'fa-shapes', self.logo_image),
            ('typography', 'Typography', 'fa-font', self.typography_image),
            ('business_card', 'Business Card', 'fa-id-card', self.business_card_image),
            ('presentation', 'Presentation', 'fa-file-powerpoint', self.presentation_image),
            ('letterhead', 'Letterhead', 'fa-envelope-open-text', self.letterhead_image),
            ('email_signature', 'Email Signature', 'fa-envelope', self.email_signature_image),
            ('social_media', 'Social Media', 'fa-hashtag', self.social_media_image),
            ('brand_guidelines', 'Brand Guidelines', 'fa-book-open', self.brand_guidelines_image),
        ]
        return [(key, label, icon, image) for key, label, icon, image in items if image]


COLLECTION_TEMPLATE_TYPES = [
    ('logo', 'Logo'),
    ('business_card', 'Business Card'),
    ('letterhead', 'Letterhead'),
    ('envelope', 'Envelope'),
    ('presentation', 'Presentation'),
    ('social_media', 'Social Media'),
    ('email_signature', 'Email Signature'),
    ('brand_guidelines', 'Brand Guidelines'),
    ('brochure', 'Brochure'),
    ('flyer', 'Flyer'),
    ('packaging', 'Packaging'),
    ('merchandise', 'Merchandise'),
    ('signage', 'Signage'),
    ('other', 'Other'),
]


class CollectionTemplate(models.Model):
    """A designer-uploadable template file associated with a brand collection."""

    collection = models.ForeignKey(
        BrandCollection,
        on_delete=models.CASCADE,
        related_name='templates',
    )
    designer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='collection_templates',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    template_type = models.CharField(max_length=20, choices=COLLECTION_TEMPLATE_TYPES, default='other')
    file = models.FileField(upload_to='branding/collection_templates/files/')
    thumbnail = models.ImageField(upload_to='branding/collection_templates/thumbs/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    download_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_template_type_display()})"

    def increment_downloads(self):
        self.download_count = models.F('download_count') + 1
        self.save(update_fields=['download_count'])


class BrandingRequest(models.Model):
    """A branding project intake captured through the 4-step wizard."""

    request_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='branding_requests',
    )
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='DRAFT', db_index=True)
    current_step = models.PositiveIntegerField(default=1)

    # Step 1 — Company information
    company_name = models.CharField(max_length=200, blank=True, default='')
    industry = models.CharField(max_length=40, choices=INDUSTRY_CHOICES, blank=True, default='')
    website = models.URLField(max_length=300, blank=True, default='')
    country = models.CharField(max_length=120, blank=True, default='')
    business_description = models.TextField(blank=True, default='')

    # Step 2 — Brand identity
    company_description = models.TextField(blank=True, default='')
    target_audience = models.TextField(blank=True, default='')
    brand_values = models.JSONField(default=list, blank=True)
    preferred_colors = models.JSONField(default=list, blank=True)
    current_branding = models.JSONField(default=list, blank=True)

    # Step 3 — Assets & notes
    additional_notes = models.TextField(blank=True, default='')

    # Step 4 — Selected collection
    collection = models.ForeignKey(
        BrandCollection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requests',
    )

    # Internal workflow fields
    designer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='branding_design_assignments',
    )
    priority = models.CharField(max_length=12, choices=PRIORITY_CHOICES, default='MEDIUM', db_index=True)
    estimated_delivery_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    internal_notes = models.TextField(blank=True, default='')

    # GDPR — Consent & retention
    consent_data_processing = models.BooleanField(default=False)
    consent_marketing = models.BooleanField(default=False)
    consent_analytics = models.BooleanField(default=False)
    consent_third_party = models.BooleanField(default=False)
    consent_timestamp = models.DateTimeField(null=True, blank=True)
    retention_period = models.CharField(
        max_length=12, choices=RETENTION_CHOICES, default='2y',
    )
    anonymized = models.BooleanField(default=False, db_index=True)
    anonymized_at = models.DateTimeField(null=True, blank=True)
    deletion_requested_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['request_number']),
            models.Index(fields=['priority', 'status']),
            models.Index(fields=['company_name'], name='idx_branding_company'),
            models.Index(fields=['user', 'status'], name='idx_branding_user_status'),
            models.Index(fields=['designer', 'status'], name='idx_branding_designer_status'),
            models.Index(fields=['completed_at'], name='idx_branding_completed'),
            models.Index(fields=['industry', 'status'], name='idx_branding_industry'),
        ]

    def __str__(self):
        return self.request_number or f"Draft #{self.pk}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            year = datetime.now().year
            self.request_number = f"BR-{year}-{self.pk:05d}"
            super().save(update_fields=['request_number'])

    def get_absolute_url(self):
        return reverse('branding:request_detail', args=[self.pk])

    @property
    def industry_display_value(self):
        return self.get_industry_display() or '—'

    @property
    def is_draft(self):
        return self.status == 'DRAFT'

    @property
    def completion_time_display(self):
        """Human-friendly total completion duration for completed requests."""
        if self.status != 'COMPLETED' or not self.completed_at or not self.created_at:
            return None
        delta = self.completed_at - self.created_at
        days = delta.days
        if days < 1:
            hours = max(1, delta.seconds // 3600)
            return f'{hours}h'
        return f'{days}d'

    def log(self, event_type, action, description='', actor=None):
        """Append a timeline entry for this request."""
        return BrandingTimeline.objects.create(
            request=self,
            event_type=event_type,
            action=action,
            description=description,
            actor=actor or self.user,
        )

    @property
    def retention_expiry(self):
        """Return the datetime when this request's data should be anonymized."""
        if self.retention_period == 'indefinite' or not self.created_at:
            return None
        years = {'1y': 1, '2y': 2, '3y': 3, '5y': 5, '7y': 7}.get(self.retention_period, 2)
        return self.created_at.replace(year=self.created_at.year + years)

    @property
    def is_retention_expired(self):
        """Check if this request's data has exceeded its retention period."""
        expiry = self.retention_expiry
        return expiry is not None and timezone.now() > expiry

    def get_consent_dict(self):
        return {
            'data_processing': self.consent_data_processing,
            'marketing': self.consent_marketing,
            'analytics': self.consent_analytics,
            'third_party': self.consent_third_party,
            'timestamp': self.consent_timestamp.isoformat() if self.consent_timestamp else None,
        }


class ConsentRecord(models.Model):
    """Immutable audit trail of consent give/revoke actions."""

    ACTION_GRANTED = 'granted'
    ACTION_REVOKED = 'revoked'
    ACTION_CHOICES = [
        (ACTION_GRANTED, 'Granted'),
        (ACTION_REVOKED, 'Revoked'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='branding_consents',
    )
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='consent_records',
    )
    consent_type = models.CharField(max_length=20, choices=CONSENT_TYPES)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'consent_type'], name='idx_consent_user_type'),
            models.Index(fields=['request', 'consent_type'], name='idx_consent_req_type'),
        ]

    def __str__(self):
        return f'{self.user} {self.action} {self.get_consent_type_display()} @ {self.created_at:%Y-%m-%d %H:%M}'


class DataExportRequest(models.Model):
    """User request to export all their branding data (GDPR Article 20)."""

    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_READY = 'ready'
    STATUS_EXPIRED = 'expired'
    STATUS_ERROR = 'error'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_READY, 'Ready for Download'),
        (STATUS_EXPIRED, 'Expired'),
        (STATUS_ERROR, 'Error'),
    ]

    FORMAT_JSON = 'json'
    FORMAT_CSV = 'csv'
    FORMAT_CHOICES = [
        (FORMAT_JSON, 'JSON'),
        (FORMAT_CSV, 'CSV'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='branding_export_requests',
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    export_format = models.CharField(max_length=4, choices=FORMAT_CHOICES, default=FORMAT_JSON)
    file = models.FileField(upload_to='branding/gdpr/exports/%Y/%m/', blank=True, null=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['user', 'status'], name='idx_export_user_status'),
        ]

    def __str__(self):
        return f'Export #{self.pk} by {self.user} — {self.get_status_display()}'


class PrivacyAcceptance(models.Model):
    """Track acceptance of specific privacy documents (policy pages)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='branding_privacy_acceptances',
    )
    page = models.CharField(max_length=30, choices=PRIVACY_PAGES)
    version = models.CharField(max_length=20, default='1.0')
    accepted = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['user', 'page']
        indexes = [
            models.Index(fields=['user', 'page'], name='idx_privacy_user_page'),
        ]

    def __str__(self):
        status = 'accepted' if self.accepted else 'revoked'
        return f'{self.user} {status} {self.get_page_display()} v{self.version}'


class BrandingAsset(models.Model):
    """A file uploaded as part of a branding request."""

    SCAN_PENDING = 'pending'
    SCAN_CLEAN = 'clean'
    SCAN_INFECTED = 'infected'
    SCAN_ERROR = 'error'
    SCAN_SKIPPED = 'skipped'
    SCAN_STATUS_CHOICES = [
        (SCAN_PENDING, 'Pending'),
        (SCAN_CLEAN, 'Clean'),
        (SCAN_INFECTED, 'Infected'),
        (SCAN_ERROR, 'Error'),
        (SCAN_SKIPPED, 'Skipped'),
    ]

    request = models.ForeignKey(BrandingRequest, on_delete=models.CASCADE, related_name='assets')
    file = models.FileField(upload_to=_upload_to)
    asset_type = models.CharField(max_length=30, choices=ASSET_TYPES, default='other')
    original_name = models.CharField(max_length=255, blank=True, default='')
    content_type = models.CharField(max_length=120, blank=True, default='')
    detected_mime = models.CharField(max_length=120, blank=True, default='')
    file_hash = models.CharField(max_length=64, blank=True, default='')
    sanitized_name = models.CharField(max_length=255, blank=True, default='')
    scan_status = models.CharField(max_length=12, choices=SCAN_STATUS_CHOICES, default=SCAN_PENDING)
    scan_result = models.TextField(blank=True, default='')
    size = models.PositiveBigIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']
        indexes = [
            models.Index(fields=['request', 'asset_type'], name='idx_asset_request_type'),
            models.Index(fields=['scan_status'], name='idx_asset_scan_status'),
            models.Index(fields=['file_hash'], name='idx_asset_file_hash'),
        ]

    def __str__(self):
        return f"{self.original_name or self.file.name} — {self.request}"

    @property
    def size_display(self):
        try:
            from django.templatetags.filesizeformat import filesizeformat
            return filesizeformat(self.size)
        except Exception:
            return f"{self.size} bytes"

    @property
    def is_image(self):
        return (self.content_type or '').startswith('image/')

    @property
    def scan_display(self):
        return self.get_scan_status_display()


class BrandingTimeline(models.Model):
    """Audit trail of events, notes and status changes on a request."""

    request = models.ForeignKey(BrandingRequest, on_delete=models.CASCADE, related_name='timeline_entries')
    event_type = models.CharField(max_length=30, choices=TIMELINE_EVENT_TYPES, default='NOTE')
    action = models.CharField(max_length=160)
    description = models.TextField(blank=True, default='')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='branding_timeline_entries',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['request', 'event_type', 'created_at'], name='idx_timeline_event'),
        ]

    def __str__(self):
        return f"{self.action} @ {self.created_at:%Y-%m-%d %H:%M}"


class BrandingAssetVersion(models.Model):
    """Snapshot of a file at a point in time (replacement history)."""

    asset = models.ForeignKey(BrandingAsset, on_delete=models.CASCADE, related_name='versions')
    file = models.FileField(upload_to=_upload_to)
    version_number = models.PositiveIntegerField(default=1)
    original_name = models.CharField(max_length=255, blank=True, default='')
    content_type = models.CharField(max_length=120, blank=True, default='')
    size = models.PositiveBigIntegerField(default=0)
    note = models.CharField(max_length=255, blank=True, default='')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='branding_asset_versions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version_number']

    def __str__(self):
        return f"v{self.version_number} — {self.original_name}"

    @property
    def size_display(self):
        try:
            from django.templatetags.filesizeformat import filesizeformat
            return filesizeformat(self.size)
        except Exception:
            return f"{self.size} bytes"


class BrandingNotification(models.Model):
    """In-app notification for designers, managers and clients."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='branding_notifications',
    )
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
    )
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES, default='SYSTEM')
    message = models.TextField()
    url = models.CharField(max_length=255, blank=True, default='')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
        ]

    def __str__(self):
        return f"{self.notification_type} → {self.recipient}"

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=['is_read'])


class BrandingMessage(models.Model):
    """Threaded message between client and staff on a branding request."""

    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='branding_messages_sent',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
    )
    content = models.TextField()
    is_read_by_client = models.BooleanField(default=False)
    is_read_by_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Branding Message'
        verbose_name_plural = 'Branding Messages'
        indexes = [
            models.Index(fields=['request', 'created_at']),
            models.Index(fields=['sender']),
            models.Index(fields=['is_read_by_client', 'is_read_by_staff'], name='idx_msg_read_flags'),
            models.Index(fields=['parent', 'created_at'], name='idx_msg_thread'),
        ]

    def __str__(self):
        return f"Message by {self.sender} on {self.request} — {self.created_at:%Y-%m-%d %H:%M}"

    def mark_read(self, by_user):
        """Mark this message as read by the given user."""
        if by_user.is_staff:
            if not self.is_read_by_staff:
                self.is_read_by_staff = True
                self.save(update_fields=['is_read_by_staff'])
        else:
            if not self.is_read_by_client:
                self.is_read_by_client = True
                self.save(update_fields=['is_read_by_client'])

    @classmethod
    def get_unread_count(cls, user):
        """Return the total unread message count across all requests for a user."""
        if user.is_staff:
            return cls.objects.filter(
                request__status__in=['PENDING_REVIEW', 'IN_REVIEW', 'ASSIGNED',
                                     'DESIGNING', 'WAITING_CLIENT', 'REVISION', 'APPROVED'],
                is_read_by_staff=False,
            ).exclude(sender=user).count()
        return cls.objects.filter(
            request__user=user,
            is_read_by_client=False,
        ).exclude(sender=user).count()


class BrandingClientProfile(models.Model):
    """Client-side profile for branding preferences and saved wizard state."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='branding_profile',
    )
    favorite_collections = models.ManyToManyField(
        BrandCollection,
        blank=True,
        related_name='favorited_by',
    )
    default_industry = models.CharField(max_length=40, choices=INDUSTRY_CHOICES, blank=True, default='')
    default_country = models.CharField(max_length=120, blank=True, default='')
    notification_preferences = models.JSONField(default=dict, blank=True, help_text='Per-channel notification toggles.')
    saved_briefs = models.JSONField(default=list, blank=True, help_text='Partial wizard saves (up to 5).')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Branding Client Profile'
        verbose_name_plural = 'Branding Client Profiles'

    def __str__(self):
        return f"Branding profile — {self.user}"

    @property
    def has_favorites(self):
        return self.favorite_collections.exists()

    def add_saved_brief(self, brief):
        """Append a brief dict, keeping at most 5."""
        briefs = list(self.saved_briefs or [])
        briefs.insert(0, brief)
        self.saved_briefs = briefs[:5]
        self.save(update_fields=['saved_briefs', 'updated_at'])

    def remove_saved_brief(self, index):
        """Remove a brief by index."""
        briefs = list(self.saved_briefs or [])
        if 0 <= index < len(briefs):
            briefs.pop(index)
            self.saved_briefs = briefs
            self.save(update_fields=['saved_briefs', 'updated_at'])


class BrandingFeedback(models.Model):
    """Client feedback submitted after a branding request is completed."""

    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    request = models.OneToOneField(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='feedback',
    )
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    comment = models.TextField(blank=True, default='')
    would_recommend = models.BooleanField(default=True)
    staff_response = models.TextField(blank=True, default='')
    responded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='feedback_responses',
    )
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Branding Feedback'
        verbose_name_plural = 'Branding Feedback'

    def __str__(self):
        return f"{self.request} — {self.rating}/5"

    @property
    def rating_percentage(self):
        return (self.rating / 5) * 100

    @property
    def star_range(self):
        return range(1, 6)


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------

WEBHOOK_EVENT_TYPES = [
    ('status_change', 'Status Change'),
    ('assignment', 'Designer Assignment'),
    ('completion', 'Request Completed'),
    ('asset_upload', 'Asset Uploaded'),
    ('feedback_submitted', 'Feedback Submitted'),
    ('request_created', 'Request Created'),
]


class BrandingWebhook(models.Model):
    """A third-party webhook endpoint that receives event notifications."""

    name = models.CharField(max_length=120)
    url = models.URLField(max_length=500, help_text='POST target URL')
    events = models.JSONField(
        default=list,
        help_text='List of event types to subscribe to, e.g. ["status_change", "completion"]',
    )
    secret = models.CharField(
        max_length=128,
        blank=True,
        default='',
        help_text='Shared secret for HMAC-SHA256 signature verification.',
    )
    is_active = models.BooleanField(default=True)
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    failure_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Branding Webhook'
        verbose_name_plural = 'Branding Webhooks'

    def __str__(self):
        return f"{self.name} ({self.url})"

    def __iter__(self):
        """Allow dict-like serialization for API responses."""
        return iter({
            'id': self.pk,
            'name': self.name,
            'url': self.url,
            'events': self.events,
            'is_active': self.is_active,
            'last_triggered_at': self.last_triggered_at,
            'failure_count': self.failure_count,
            'created_at': self.created_at,
        }.items())

    def accepts_event(self, event_type):
        """Return True if this webhook is subscribed to the given event."""
        return self.is_active and event_type in (self.events or [])


class WebhookDelivery(models.Model):
    """Log of a single webhook delivery attempt."""

    DELIVERY_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('retrying', 'Retrying'),
    ]

    webhook = models.ForeignKey(
        BrandingWebhook,
        on_delete=models.CASCADE,
        related_name='deliveries',
    )
    event_type = models.CharField(max_length=40)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=12,
        choices=DELIVERY_STATUS_CHOICES,
        default='pending',
    )
    status_code = models.PositiveIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True, default='')
    attempt = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Webhook Delivery'
        verbose_name_plural = 'Webhook Deliveries'

    def __str__(self):
        return f"{self.webhook.name} — {self.event_type} ({self.status})"


# ---------------------------------------------------------------------------
# Analytics models
# ---------------------------------------------------------------------------

class DailyAggregate(models.Model):
    """Daily aggregate metrics for the branding service."""

    date = models.DateField(unique=True, db_index=True)
    total_requests = models.PositiveIntegerField(default=0)
    new_requests = models.PositiveIntegerField(default=0)
    completed_requests = models.PositiveIntegerField(default=0)
    archived_requests = models.PositiveIntegerField(default=0)
    avg_completion_days = models.FloatField(default=0)
    total_messages = models.PositiveIntegerField(default=0)
    total_uploads = models.PositiveIntegerField(default=0)
    satisfaction_avg = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']
        verbose_name_plural = 'Daily Aggregates'

    def __str__(self):
        return f"Aggregate for {self.date}"


class StaffWorkload(models.Model):
    """Staff workload tracking — one record per staff per day."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='branding_workload',
    )
    date = models.DateField(db_index=True)
    assigned_count = models.PositiveIntegerField(default=0)
    in_progress_count = models.PositiveIntegerField(default=0)
    completed_count = models.PositiveIntegerField(default=0)
    messages_sent = models.PositiveIntegerField(default=0)
    avg_response_hours = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        unique_together = ['user', 'date']
        verbose_name_plural = 'Staff Workloads'

    def __str__(self):
        return f"{self.user} workload — {self.date}"


class CollectionPerformance(models.Model):
    """Track how often each collection is selected and completion rates."""

    collection = models.ForeignKey(
        BrandCollection,
        on_delete=models.CASCADE,
        related_name='performance',
    )
    date = models.DateField(db_index=True)
    times_selected = models.PositiveIntegerField(default=0)
    times_completed = models.PositiveIntegerField(default=0)
    avg_satisfaction = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        unique_together = ['collection', 'date']

    def __str__(self):
        return f"{self.collection.name} performance — {self.date}"


# ---------------------------------------------------------------------------
# Supervisor Review & Notes
# ---------------------------------------------------------------------------

QUALITY_CHECKLIST = [
    ('logo_delivered', 'Logo files delivered'),
    ('color_accuracy', 'Color accuracy verified'),
    ('font_usage', 'Font usage correct'),
    ('file_naming', 'Files properly named'),
    ('format_compliance', 'File formats compliant'),
    ('brand_guidelines', 'Brand guidelines included'),
    ('client_feedback', 'Client feedback addressed'),
    ('final_approval', 'Final approval ready'),
]


class DesignerNote(models.Model):
    """Supervisor note about a designer's performance or instructions."""

    designer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='designer_notes_about',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='designer_notes_authored',
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Note about {self.designer} by {self.author} — {self.created_at:%Y-%m-%d}"


REVIEW_STATUS_CHOICES = [
    ('PENDING', 'Pending Review'),
    ('APPROVED', 'Approved'),
    ('REJECTED', 'Rejected'),
    ('REVISION_REQUESTED', 'Revision Requested'),
]


class ProjectReview(models.Model):
    """Supervisor approval/rejection record for a branding request."""

    request = models.OneToOneField(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='supervisor_review',
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='project_reviews',
    )
    status = models.CharField(
        max_length=20,
        choices=REVIEW_STATUS_CHOICES,
        default='PENDING',
    )
    quality_checklist = models.JSONField(
        default=dict,
        blank=True,
        help_text='Dict mapping checklist key → bool. Keys from QUALITY_CHECKLIST.',
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Review of {self.request} — {self.get_status_display()}"

    @property
    def checklist_progress(self):
        """Return (checked_count, total_count) for the quality checklist."""
        total = len(QUALITY_CHECKLIST)
        checked = sum(1 for key, _ in QUALITY_CHECKLIST if self.quality_checklist.get(key))
        return checked, total

    @property
    def checklist_percentage(self):
        checked, total = self.checklist_progress
        return round(checked / total * 100) if total else 0


# ────────────────────────────────────────────────────────────────────────────
# Design Drafts & Version Control
# ────────────────────────────────────────────────────────────────────────────

DRAFT_VERSION_TYPES = [
    ('major', 'Major'),
    ('minor', 'Minor'),
]


def _draft_upload_to(instance, filename):
    base = getattr(instance.request, 'pk', None) or 'pending'
    safe = os.path.basename(filename).replace(' ', '_')
    return f'branding/drafts/{base}/{safe}'


class DesignDraft(models.Model):
    """A design draft uploaded by a designer for a branding request."""

    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='design_drafts',
    )
    designer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='design_drafts',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    is_submitted = models.BooleanField(
        default=False,
        help_text='True when designer submits for client review.',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Draft: {self.title} — {self.request}"

    @property
    def latest_version(self):
        return self.versions.order_by('-version_number').first()

    @property
    def version_count(self):
        return self.versions.count()

    def submit_for_review(self):
        self.is_submitted = True
        self.submitted_at = timezone.now()
        self.save(update_fields=['is_submitted', 'submitted_at', 'updated_at'])


class DraftVersion(models.Model):
    """A specific version of a design draft file."""

    draft = models.ForeignKey(
        DesignDraft,
        on_delete=models.CASCADE,
        related_name='versions',
    )
    file = models.FileField(upload_to=_draft_upload_to)
    version_number = models.PositiveIntegerField(default=1)
    version_type = models.CharField(max_length=6, choices=DRAFT_VERSION_TYPES, default='minor')
    original_name = models.CharField(max_length=255, blank=True, default='')
    content_type = models.CharField(max_length=120, blank=True, default='')
    size = models.PositiveBigIntegerField(default=0)
    notes = models.TextField(blank=True, default='')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='draft_versions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version_number']

    def __str__(self):
        return f"v{self.version_number} — {self.original_name}"

    @property
    def size_display(self):
        try:
            from django.templatetags.filesizeformat import filesizeformat
            return filesizeformat(self.size)
        except Exception:
            return f"{self.size} bytes"

    @property
    def is_image(self):
        return (self.content_type or '').startswith('image/')

    def save(self, *args, **kwargs):
        if not self.version_number:
            last = self.draft.versions.order_by('-version_number').first()
            self.version_number = (last.version_number + 1) if last else 1
        super().save(*args, **kwargs)


# ────────────────────────────────────────────────────────────────────────────
# Feedback Requests
# ────────────────────────────────────────────────────────────────────────────

FEEDBACK_REQUEST_STATUS = [
    ('PENDING', 'Pending'),
    ('RESPONDED', 'Responded'),
    ('CLOSED', 'Closed'),
]


class FeedbackRequest(models.Model):
    """Designer-initiated request for specific client feedback."""

    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='feedback_requests',
    )
    designer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feedback_requests_sent',
    )
    subject = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(max_length=12, choices=FEEDBACK_REQUEST_STATUS, default='PENDING')
    client_responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Feedback: {self.subject} — {self.request}"

    def mark_responded(self):
        self.status = 'RESPONDED'
        self.client_responded_at = timezone.now()
        self.save(update_fields=['status', 'client_responded_at', 'updated_at'])


class FeedbackQuestion(models.Model):
    """Specific question within a feedback request."""

    feedback_request = models.ForeignKey(
        FeedbackRequest,
        on_delete=models.CASCADE,
        related_name='questions',
    )
    question = models.TextField()
    client_answer = models.TextField(blank=True, default='')
    answered_at = models.DateTimeField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order']

    def __str__(self):
        return self.question[:80]

    @property
    def is_answered(self):
        return bool(self.client_answer)


# ────────────────────────────────────────────────────────────────────────────
# Design Resources Library
# ────────────────────────────────────────────────────────────────────────────

RESOURCE_CATEGORIES = [
    ('template', 'Template'),
    ('asset', 'Asset'),
    ('style_guide', 'Style Guide'),
    ('font', 'Font'),
    ('color_palette', 'Color Palette'),
    ('icon', 'Icon Set'),
    ('mockup', 'Mockup'),
    ('photo', 'Photo'),
    ('illustration', 'Illustration'),
    ('document', 'Document'),
    ('other', 'Other'),
]


class DesignResource(models.Model):
    """A shared or personal design resource."""

    SHARED_LEVELS = [
        ('team', 'Team Shared'),
        ('personal', 'Personal'),
        ('collection', 'Collection-Specific'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    category = models.CharField(max_length=20, choices=RESOURCE_CATEGORIES, default='other')
    shared_level = models.CharField(max_length=12, choices=SHARED_LEVELS, default='team')
    file = models.FileField(upload_to='branding/resources/', blank=True, null=True)
    url = models.URLField(max_length=500, blank=True, default='')
    thumbnail = models.ImageField(upload_to='branding/resources/thumbs/', blank=True, null=True)
    collection = models.ForeignKey(
        BrandCollection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resources',
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='design_resources',
    )
    tags = models.JSONField(default=list, blank=True)
    download_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"

    def increment_downloads(self):
        self.download_count = models.F('download_count') + 1
        self.save(update_fields=['download_count'])


# ────────────────────────────────────────────────────────────────────────────
# Time Tracking
# ────────────────────────────────────────────────────────────────────────────

TIME_TRACK_PHASES = [
    ('research', 'Research'),
    ('concept', 'Concept Development'),
    ('design', 'Design'),
    ('revision', 'Revision'),
    ('delivery', 'Delivery'),
    ('meeting', 'Meeting'),
    ('other', 'Other'),
]


class TimeEntry(models.Model):
    """A time tracking entry for a branding request."""

    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='time_entries',
    )
    designer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='time_entries',
    )
    phase = models.CharField(max_length=12, choices=TIME_TRACK_PHASES, default='design')
    description = models.CharField(max_length=300, blank=True, default='')
    duration_minutes = models.PositiveIntegerField(default=0)
    date = models.DateField(default=timezone.now)
    is_timer_running = models.BooleanField(default=False)
    timer_started_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.duration_minutes}m — {self.request} ({self.get_phase_display()})"

    @property
    def duration_display(self):
        h = self.duration_minutes // 60
        m = self.duration_minutes % 60
        if h and m:
            return f'{h}h {m}m'
        if h:
            return f'{h}h'
        return f'{m}m'

    def start_timer(self):
        self.is_timer_running = True
        self.timer_started_at = timezone.now()
        self.save(update_fields=['is_timer_running', 'timer_started_at'])

    def stop_timer(self):
        if self.is_timer_running and self.timer_started_at:
            elapsed = (timezone.now() - self.timer_started_at).total_seconds() / 60
            self.duration_minutes += int(elapsed)
        self.is_timer_running = False
        self.timer_started_at = None
        self.save(update_fields=['is_timer_running', 'timer_started_at', 'duration_minutes', 'updated_at'])

    @classmethod
    def get_running(cls, designer):
        return cls.objects.filter(designer=designer, is_timer_running=True).first()

    @classmethod
    def daily_summary(cls, designer, date=None):
        date = date or timezone.now().date()
        entries = cls.objects.filter(designer=designer, date=date)
        total = entries.aggregate(total=Sum('duration_minutes'))['total'] or 0
        by_phase = entries.values('phase').annotate(total=Sum('duration_minutes')).order_by('-total')
        return {'total': total, 'by_phase': list(by_phase), 'entries': entries}


# ────────────────────────────────────────────────────────────────────────────
# Notes & Journal
# ────────────────────────────────────────────────────────────────────────────

NOTE_CATEGORIES = [
    ('design', 'Design Note'),
    ('decision', 'Design Decision'),
    ('research', 'Research'),
    ('inspiration', 'Inspiration'),
    ('client', 'Client Communication'),
    ('other', 'Other'),
]


class DesignNote(models.Model):
    """A project-specific note, decision, or research entry."""

    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='design_notes',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='design_notes',
    )
    category = models.CharField(max_length=12, choices=NOTE_CATEGORIES, default='design')
    title = models.CharField(max_length=200)
    content = models.TextField()
    links = models.JSONField(default=list, blank=True, help_text='List of URL strings')
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f"{self.title} — {self.request}"


# ────────────────────────────────────────────────────────────────────────────
# Design Templates
# ────────────────────────────────────────────────────────────────────────────

TEMPLATE_CATEGORIES = [
    ('brief', 'Design Brief'),
    ('communication', 'Client Communication'),
    ('status_update', 'Status Update'),
    ('feedback', 'Feedback Request'),
    ('checklist', 'Checklist'),
    ('other', 'Other'),
]


class DesignTemplate(models.Model):
    """A reusable template for briefs, communications, status updates, etc."""

    name = models.CharField(max_length=200)
    category = models.CharField(max_length=18, choices=TEMPLATE_CATEGORIES, default='other')
    subject = models.CharField(max_length=300, blank=True, default='')
    content = models.TextField()
    variables = models.JSONField(
        default=list, blank=True,
        help_text='List of variable names like ["client_name", "project_name"]',
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='design_templates',
    )
    is_team_shared = models.BooleanField(default=False)
    use_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-use_count', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    def increment_uses(self):
        self.use_count = models.F('use_count') + 1
        self.save(update_fields=['use_count'])


# ═══════════════════════════════════════════════════════════════════════════
# Peer Review System
# ═══════════════════════════════════════════════════════════════════════════

REVIEW_STATUS = [
    ('PENDING', 'Pending'),
    ('IN_PROGRESS', 'In Progress'),
    ('COMPLETED', 'Completed'),
    ('CANCELLED', 'Cancelled'),
]


class CritiqueTemplate(models.Model):
    """A reusable template for structuring design critiques."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    prompts = models.JSONField(
        default=list, blank=True,
        help_text='List of critique prompt strings',
    )
    category = models.CharField(max_length=50, blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='critique_templates',
    )
    use_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-use_count', 'name']

    def __str__(self):
        return self.name

    def increment_uses(self):
        self.use_count = models.F('use_count') + 1
        self.save(update_fields=['use_count'])


class PeerReview(models.Model):
    """A peer review request from one designer to another."""

    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='peer_reviews',
    )
    draft = models.ForeignKey(
        'DesignDraft',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='peer_reviews',
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='peer_reviews_received',
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='peer_reviews_sent',
    )
    status = models.CharField(max_length=14, choices=REVIEW_STATUS, default='PENDING')
    critique_template = models.ForeignKey(
        CritiqueTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviews',
    )
    message = models.TextField(blank=True, default='')
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Review: {self.request} → {self.reviewer}"

    def complete(self):
        self.status = 'COMPLETED'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])


class PeerReviewFeedback(models.Model):
    """Feedback provided by a peer reviewer."""

    review = models.ForeignKey(
        PeerReview,
        on_delete=models.CASCADE,
        related_name='feedbacks',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='peer_feedbacks',
    )
    category = models.CharField(max_length=50, blank=True, default='')
    content = models.TextField()
    rating = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Optional 1-5 rating',
    )
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Feedback by {self.author} on {self.review}"


# ═══════════════════════════════════════════════════════════════════════════
# Internal Comments
# ═══════════════════════════════════════════════════════════════════════════

COMMENT_TAGS = [
    ('general', 'General'),
    ('design', 'Design'),
    ('typography', 'Typography'),
    ('color', 'Color'),
    ('layout', 'Layout'),
    ('branding', 'Branding'),
    ('feedback', 'Client Feedback'),
    ('urgent', 'Urgent'),
]


class DesignComment(models.Model):
    """An internal comment on a branding request with threading and @mentions."""

    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='design_comments',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='design_comments',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
    )
    content = models.TextField()
    tag = models.CharField(max_length=12, choices=COMMENT_TAGS, default='general')
    mentions = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='mentioned_in_comments',
    )
    annotation_x = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Screenshot annotation X position (%)',
    )
    annotation_y = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Screenshot annotation Y position (%)',
    )
    annotation_image = models.ImageField(
        upload_to='branding/annotations/',
        blank=True, null=True,
    )
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_comments',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f"Comment by {self.author} on {self.request}"

    @property
    def is_thread(self):
        return self.replies.exists()

    def resolve(self, user):
        self.is_resolved = True
        self.resolved_by = user
        self.resolved_at = timezone.now()
        self.save(update_fields=['is_resolved', 'resolved_by', 'resolved_at', 'updated_at'])

    def unresolve(self):
        self.is_resolved = False
        self.resolved_by = None
        self.resolved_at = None
        self.save(update_fields=['is_resolved', 'resolved_by', 'resolved_at', 'updated_at'])

    def extract_mentions(self):
        """Return list of usernames mentioned with @ in content."""
        import re
        return re.findall(r'@(\w+)', self.content)


# ═══════════════════════════════════════════════════════════════════════════
# Design Handoff System
# ═══════════════════════════════════════════════════════════════════════════

HANDOFF_STATUS = [
    ('DRAFT', 'Draft'),
    ('READY', 'Ready for Handoff'),
    ('HANDED_OFF', 'Handed Off'),
    ('ACKNOWLEDGED', 'Acknowledged'),
]


def _handoff_upload_to(instance, filename):
    base = getattr(instance.handoff, 'pk', None) or 'pending'
    safe = os.path.basename(filename).replace(' ', '_')
    return f'branding/handoffs/{base}/{safe}'


class DesignHandoff(models.Model):
    """Packages deliverables for client/developer handoff."""

    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='handoffs',
    )
    designer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='handoffs',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    status = models.CharField(max_length=14, choices=HANDOFF_STATUS, default='DRAFT')
    handoff_notes = models.TextField(
        blank=True, default='',
        help_text='Notes for the developer or client receiving the handoff',
    )
    style_guide_content = models.TextField(
        blank=True, default='',
        help_text='Auto-generated or manual style guide',
    )
    handed_off_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_handoffs',
    )
    handed_off_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Handoff: {self.title} — {self.request}"


def _handoff_file_upload_to(instance, filename):
    base = getattr(instance.handoff, 'pk', None) or 'pending'
    safe = os.path.basename(filename).replace(' ', '_')
    return f'branding/handoffs/{base}/files/{safe}'


class HandoffDeliverable(models.Model):
    """A file deliverable in a design handoff."""

    DELIVERABLE_TYPES = [
        ('logo', 'Logo'),
        ('color_palette', 'Color Palette'),
        ('typography', 'Typography'),
        ('mockup', 'Mockup'),
        ('source_file', 'Source File'),
        ('export', 'Export'),
        ('document', 'Document'),
        ('other', 'Other'),
    ]

    handoff = models.ForeignKey(
        DesignHandoff,
        on_delete=models.CASCADE,
        related_name='deliverables',
    )
    file = models.FileField(upload_to=_handoff_file_upload_to)
    original_name = models.CharField(max_length=255, blank=True, default='')
    deliverable_type = models.CharField(max_length=14, choices=DELIVERABLE_TYPES, default='other')
    description = models.CharField(max_length=300, blank=True, default='')
    content_type = models.CharField(max_length=120, blank=True, default='')
    size = models.PositiveBigIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='handoff_deliverables',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['deliverable_type', 'created_at']

    def __str__(self):
        return f"{self.get_deliverable_type_display()}: {self.original_name}"


class HandoffNote(models.Model):
    """A note attached to a design handoff (developer handoff notes)."""

    handoff = models.ForeignKey(
        DesignHandoff,
        on_delete=models.CASCADE,
        related_name='notes',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='handoff_notes',
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    note_type = models.CharField(
        max_length=20, default='general',
        choices=[('general', 'General'), ('technical', 'Technical'), ('brand', 'Brand Guidelines'), ('usage', 'Usage Instructions')],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return self.title


# ═══════════════════════════════════════════════════════════════════════════
# Knowledge Base
# ═══════════════════════════════════════════════════════════════════════════

KB_CATEGORIES = [
    ('tips', 'Design Tips'),
    ('best_practices', 'Best Practices'),
    ('solutions', 'Common Solutions'),
    ('collection_insights', 'Collection Insights'),
    ('communication', 'Client Communication'),
    ('tools', 'Tools & Software'),
    ('process', 'Process & Workflow'),
    ('other', 'Other'),
]


class KnowledgeArticle(models.Model):
    """An article in the internal knowledge base."""

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    category = models.CharField(max_length=20, choices=KB_CATEGORIES, default='tips')
    content = models.TextField()
    summary = models.CharField(max_length=300, blank=True, default='')
    tags = models.JSONField(default=list, blank=True)
    collection = models.ForeignKey(
        BrandCollection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='knowledge_articles',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='knowledge_articles',
    )
    is_published = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    view_count = models.PositiveIntegerField(default=0)
    helpful_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_featured', '-created_at']

    def __str__(self):
        return self.title

    def increment_views(self):
        self.view_count = models.F('view_count') + 1
        self.save(update_fields=['view_count'])

    def increment_helpful(self):
        self.helpful_count = models.F('helpful_count') + 1
        self.save(update_fields=['helpful_count'])

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base = slugify(self.title)[:200]
            slug = base
            n = 1
            while KnowledgeArticle.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# Design Showcase
# ═══════════════════════════════════════════════════════════════════════════

SHOWCASE_CATEGORIES = [
    ('branding', 'Branding'),
    ('logo', 'Logo Design'),
    ('packaging', 'Packaging'),
    ('print', 'Print'),
    ('digital', 'Digital'),
    ('illustration', 'Illustration'),
    ('other', 'Other'),
]


class ShowcaseProject(models.Model):
    """A project featured in the designer showcase/portfolio."""

    request = models.OneToOneField(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='showcase',
    )
    designer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='showcase_projects',
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(max_length=14, choices=SHOWCASE_CATEGORIES, default='branding')
    cover_image = models.ImageField(
        upload_to='branding/showcase/covers/',
        blank=True, null=True,
    )
    is_featured = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    view_count = models.PositiveIntegerField(default=0)
    like_count = models.PositiveIntegerField(default=0)
    tags = models.JSONField(default=list, blank=True)
    client_name = models.CharField(max_length=200, blank=True, default='')
    project_year = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_featured', '-created_at']

    def __str__(self):
        return self.title

    def increment_views(self):
        self.view_count = models.F('view_count') + 1
        self.save(update_fields=['view_count'])

    def increment_likes(self):
        self.like_count = models.F('like_count') + 1
        self.save(update_fields=['like_count'])


# ═══════════════════════════════════════════════════════════════════════════
# Figma Integration
# ═══════════════════════════════════════════════════════════════════════════

class FigmaConnection(models.Model):
    """A connected Figma account."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='figma_connection',
    )
    figma_user_id = models.CharField(max_length=100)
    figma_email = models.EmailField()
    access_token = models.CharField(max_length=500)
    refresh_token = models.CharField(max_length=500, blank=True, default='')
    token_expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Figma connections'

    def __str__(self):
        return f"Figma: {self.figma_email}"


class FigmaDesign(models.Model):
    """A design imported from Figma."""

    SYNC_STATUS = [
        ('SYNCED', 'Synced'),
        ('OUTDATED', 'Outdated'),
        ('ERROR', 'Error'),
    ]

    connection = models.ForeignKey(
        FigmaConnection,
        on_delete=models.CASCADE,
        related_name='designs',
    )
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='figma_designs',
    )
    figma_file_key = models.CharField(max_length=200)
    figma_file_name = models.CharField(max_length=300)
    figma_node_id = models.CharField(max_length=100, blank=True, default='')
    figma_url = models.URLField(max_length=500)
    thumbnail_url = models.URLField(max_length=500, blank=True, default='')
    version = models.CharField(max_length=100, blank=True, default='')
    sync_status = models.CharField(max_length=10, choices=SYNC_STATUS, default='SYNCED')
    last_synced = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-last_synced']

    def __str__(self):
        return f"Figma: {self.figma_file_name}"


class FigmaComment(models.Model):
    """A comment synced from Figma."""

    design = models.ForeignKey(
        FigmaDesign,
        on_delete=models.CASCADE,
        related_name='figma_comments',
    )
    figma_comment_id = models.CharField(max_length=100)
    author_name = models.CharField(max_length=200)
    message = models.TextField()
    resolved = models.BooleanField(default=False)
    figma_created_at = models.DateTimeField()
    synced_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-figma_created_at']

    def __str__(self):
        return f"Comment by {self.author_name}: {self.message[:50]}"


# ═══════════════════════════════════════════════════════════════════════════
# Adobe Creative Cloud Integration
# ═══════════════════════════════════════════════════════════════════════════

class AdobeConnection(models.Model):
    """A connected Adobe Creative Cloud account."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='adobe_connection',
    )
    adobe_user_id = models.CharField(max_length=100)
    adobe_email = models.EmailField()
    access_token = models.CharField(max_length=500)
    refresh_token = models.CharField(max_length=500, blank=True, default='')
    token_expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Adobe connections'

    def __str__(self):
        return f"Adobe: {self.adobe_email}"


class AdobeAsset(models.Model):
    """An asset from Adobe CC Libraries."""

    ASSET_TYPES = [
        ('color', 'Color'),
        ('graphic', 'Graphic'),
        ('character_style', 'Character Style'),
        ('layer_style', 'Layer Style'),
        ('image', 'Image'),
        ('brush', 'Brush'),
        ('other', 'Other'),
    ]

    connection = models.ForeignKey(
        AdobeConnection,
        on_delete=models.CASCADE,
        related_name='adobe_assets',
    )
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adobe_assets',
    )
    library_id = models.CharField(max_length=200, blank=True, default='')
    library_name = models.CharField(max_length=200, blank=True, default='')
    asset_id = models.CharField(max_length=200)
    asset_name = models.CharField(max_length=300)
    asset_type = models.CharField(max_length=16, choices=ASSET_TYPES, default='other')
    preview_url = models.URLField(max_length=500, blank=True, default='')
    creation_url = models.URLField(max_length=500, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_asset_type_display()}: {self.asset_name}"


# ═══════════════════════════════════════════════════════════════════════════
# Design Tools
# ═══════════════════════════════════════════════════════════════════════════

class ColorPalette(models.Model):
    """A saved color palette for quick access."""

    name = models.CharField(max_length=200)
    colors = models.JSONField(default=list, help_text='List of hex color strings')
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='color_palettes',
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='color_palettes',
    )
    is_public = models.BooleanField(default=False)
    use_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def increment_uses(self):
        self.use_count = models.F('use_count') + 1
        self.save(update_fields=['use_count'])


class FontEntry(models.Model):
    """A saved font entry for quick reference."""

    name = models.CharField(max_length=200)
    family = models.CharField(max_length=200)
    weights = models.JSONField(default=list, blank=True, help_text='Available weights')
    styles = models.JSONField(default=list, blank=True, help_text='Available styles')
    source_url = models.URLField(max_length=500, blank=True, default='')
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fonts',
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='fonts',
    )
    is_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.family})"


class AssetOrganizerItem(models.Model):
    """An organized asset item in the asset organizer."""

    ITEM_TYPES = [
        ('image', 'Image'),
        ('logo', 'Logo'),
        ('icon', 'Icon'),
        ('pattern', 'Pattern'),
        ('texture', 'Texture'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=200)
    item_type = models.CharField(max_length=10, choices=ITEM_TYPES, default='other')
    file = models.FileField(upload_to='branding/organizer/', blank=True, null=True)
    thumbnail = models.ImageField(upload_to='branding/organizer/thumbs/', blank=True, null=True)
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='organizer_items',
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='organizer_items',
    )
    tags = models.JSONField(default=list, blank=True)
    folder = models.CharField(max_length=200, blank=True, default='General')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['folder', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_item_type_display()})"


class BrandGuidelineCheck(models.Model):
    """A brand guideline compliance check result."""

    CHECK_RESULTS = [
        ('PASS', 'Pass'),
        ('WARN', 'Warning'),
        ('FAIL', 'Fail'),
    ]

    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='guideline_checks',
    )
    checker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='guideline_checks',
    )
    check_name = models.CharField(max_length=200)
    result = models.CharField(max_length=4, choices=CHECK_RESULTS, default='PASS')
    details = models.TextField(blank=True, default='')
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-checked_at']

    def __str__(self):
        return f"{self.check_name}: {self.get_result_display()}"


# ═══════════════════════════════════════════════════════════════════════════
# Slack Integration
# ═══════════════════════════════════════════════════════════════════════════

class SlackConnection(models.Model):
    """A connected Slack workspace."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='slack_connection',
    )
    workspace_id = models.CharField(max_length=100)
    workspace_name = models.CharField(max_length=200)
    bot_token = models.CharField(max_length=500)
    bot_user_id = models.CharField(max_length=100, blank=True, default='')
    channel_id = models.CharField(max_length=100, blank=True, default='')
    channel_name = models.CharField(max_length=200, blank=True, default='')
    is_active = models.BooleanField(default=True)
    notify_assignments = models.BooleanField(default=True)
    notify_deadlines = models.BooleanField(default=True)
    notify_feedback = models.BooleanField(default=True)
    notify_daily_digest = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Slack connections'

    def __str__(self):
        return f"Slack: {self.workspace_name}"


class SlackMessage(models.Model):
    """A sent Slack notification log."""

    MESSAGE_TYPES = [
        ('assignment', 'Assignment'),
        ('deadline', 'Deadline'),
        ('feedback', 'Feedback'),
        ('digest', 'Daily Digest'),
        ('status', 'Status Update'),
    ]

    connection = models.ForeignKey(
        SlackConnection,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='slack_messages',
    )
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPES)
    slack_message_ts = models.CharField(max_length=50, blank=True, default='')
    channel = models.CharField(max_length=100)
    text = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"[{self.get_message_type_display()}] {self.text[:50]}"


# ═══════════════════════════════════════════════════════════════════════════
# Calendar Integration
# ═══════════════════════════════════════════════════════════════════════════

class CalendarConnection(models.Model):
    """A connected calendar account (Google Calendar, etc.)."""

    PROVIDERS = [
        ('google', 'Google Calendar'),
        ('outlook', 'Outlook Calendar'),
        ('apple', 'Apple Calendar'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='calendar_connection',
    )
    provider = models.CharField(max_length=10, choices=PROVIDERS, default='google')
    calendar_id = models.CharField(max_length=300)
    calendar_name = models.CharField(max_length=200)
    access_token = models.CharField(max_length=500)
    refresh_token = models.CharField(max_length=500, blank=True, default='')
    token_expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    sync_deadlines = models.BooleanField(default=True)
    sync_meetings = models.BooleanField(default=True)
    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Calendar connections'

    def __str__(self):
        return f"{self.get_provider_display()}: {self.calendar_name}"


class CalendarEvent(models.Model):
    """A synced calendar event."""

    EVENT_TYPES = [
        ('deadline', 'Deadline'),
        ('meeting', 'Meeting'),
        ('milestone', 'Milestone'),
        ('review', 'Review'),
    ]

    connection = models.ForeignKey(
        CalendarConnection,
        on_delete=models.CASCADE,
        related_name='events',
    )
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='calendar_events',
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default='')
    event_type = models.CharField(max_length=10, choices=EVENT_TYPES, default='deadline')
    external_event_id = models.CharField(max_length=200, blank=True, default='')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    all_day = models.BooleanField(default=False)
    location = models.CharField(max_length=300, blank=True, default='')
    synced = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_time']

    def __str__(self):
        return f"{self.title} ({self.start_time})"


# ═══════════════════════════════════════════════════════════════════════════
# Unified Staff Dashboard
# ═══════════════════════════════════════════════════════════════════════════

WIDGET_TYPES = [
    ('stats_quick', 'Quick Stats'),
    ('stats_projects', 'Project Stats'),
    ('stats_team', 'Team Stats'),
    ('stats_designer', 'Designer Stats'),
    ('chart_status', 'Status Distribution'),
    ('chart_timeline', 'Timeline Chart'),
    ('chart_workload', 'Workload Chart'),
    ('chart_performance', 'Performance Chart'),
    ('table_recent', 'Recent Requests'),
    ('table_team', 'Team Performance'),
    ('table_deadlines', 'Upcoming Deadlines'),
    ('table_timesheet', 'My Timesheet'),
    ('feed_activity', 'Recent Activity'),
    ('feed_notifications', 'Notifications'),
    ('feed_messages', 'Messages'),
    ('feed_calendar', 'Calendar Events'),
    ('tools_shortcuts', 'Quick Tools'),
    ('tools_timer', 'Timer'),
    ('tools_figma', 'Figma'),
    ('tools_adobe', 'Adobe CC'),
]

DASHBOARD_LAYOUTS = [
    ('default', 'Default'),
    ('compact', 'Compact'),
    ('wide', 'Wide'),
    ('fullscreen', 'Full Screen'),
]


class WidgetDefinition(models.Model):
    """Defines a available widget type that can be placed on dashboards."""
    widget_type = models.CharField(max_length=30, unique=True, choices=WIDGET_TYPES)
    label = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    icon = models.CharField(max_length=60, default='fa-solid fa-puzzle-piece')
    category = models.CharField(max_length=30, default='stats', choices=[
        ('stats', 'Statistics'),
        ('chart', 'Charts'),
        ('table', 'Tables'),
        ('feed', 'Feeds'),
        ('tools', 'Tools'),
    ])
    default_width = models.PositiveSmallIntegerField(default=1, help_text='Grid columns (1-4)')
    default_height = models.PositiveSmallIntegerField(default=1, help_text='Grid rows (1-3)')
    min_width = models.PositiveSmallIntegerField(default=1)
    min_height = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category', 'label']

    def __str__(self):
        return f"{self.label} ({self.widget_type})"


class StaffDashboard(models.Model):
    """Per-user customizable dashboard layout and configuration."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='branding_dashboard',
    )
    layout = models.CharField(max_length=20, choices=DASHBOARD_LAYOUTS, default='default')
    columns = models.PositiveSmallIntegerField(default=3, help_text='Number of grid columns (2-4)')
    show_sidebar = models.BooleanField(default=True)
    show_header = models.BooleanField(default=True)
    compact_mode = models.BooleanField(default=False)
    active_role_view = models.CharField(max_length=20, blank=True, default='', help_text='Current role perspective')
    allow_role_switch = models.BooleanField(default=False, help_text='Can switch between role views')
    preferences = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Staff Dashboard'
        verbose_name_plural = 'Staff Dashboards'

    def __str__(self):
        return f"Dashboard: {self.user.username}"

    def get_widgets_for_role(self, role):
        return self.widgets.filter(
            models.Q(visible_roles__contains=role) | models.Q(visible_roles='')
        ).order_by('row', 'col')


class DashboardWidget(models.Model):
    """A widget instance placed on a user's dashboard."""
    dashboard = models.ForeignKey(
        StaffDashboard,
        on_delete=models.CASCADE,
        related_name='widgets',
    )
    widget_def = models.ForeignKey(
        WidgetDefinition,
        on_delete=models.CASCADE,
        related_name='instances',
    )
    title = models.CharField(max_length=150, blank=True, default='')
    col = models.PositiveSmallIntegerField(default=0, help_text='Grid column position (0-indexed)')
    row = models.PositiveSmallIntegerField(default=0, help_text='Grid row position (0-indexed)')
    width = models.PositiveSmallIntegerField(default=1, help_text='Grid columns span')
    height = models.PositiveSmallIntegerField(default=1, help_text='Grid rows span')
    is_visible = models.BooleanField(default=True)
    is_collapsed = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True, help_text='Widget-specific configuration')
    visible_roles = models.JSONField(default=list, blank=True, help_text='Roles that see this widget')
    refresh_interval = models.PositiveIntegerField(default=0, help_text='Auto-refresh seconds (0=off)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['row', 'col']
        unique_together = [('dashboard', 'col', 'row')]

    def __str__(self):
        title = self.title or self.widget_def.label
        return f"{title} @ ({self.col},{self.row})"

    def visible_for_role(self, role):
        if not self.visible_roles:
            return True
        return role in self.visible_roles


class RoleSwitchLog(models.Model):
    """Audit log for role perspective switches."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='role_switch_logs',
    )
    from_role = models.CharField(max_length=20)
    to_role = models.CharField(max_length=20)
    switched_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-switched_at']

    def __str__(self):
        return f"{self.user.username}: {self.from_role} -> {self.to_role}"


# ═══════════════════════════════════════════════════════════════════════════
# Designer Workflow System
# ═══════════════════════════════════════════════════════════════════════════

WORKFLOW_STAGES = [
    ('brief_review', 'Initial Brief Review'),
    ('concept', 'Concept Development'),
    ('first_presentation', 'First Presentation'),
    ('client_feedback', 'Client Feedback'),
    ('revisions', 'Revisions'),
    ('question_phase', 'Question Phase'),
    ('final_presentation', 'Final Presentation'),
    ('completion', 'Project Completion'),
]

QUESTION_CATEGORIES = [
    ('brand_direction', 'Brand Direction'),
    ('color', 'Color'),
    ('typography', 'Typography'),
    ('layout', 'Layout'),
    ('imagery', 'Imagery'),
    ('tone', 'Tone & Voice'),
    ('target_audience', 'Target Audience'),
    ('general', 'General'),
]

FEEDBACK_STATUSES = [
    ('new', 'New'),
    ('in_review', 'In Review'),
    ('addressed', 'Addressed'),
    ('resolved', 'Resolved'),
]


class ProjectWorkflow(models.Model):
    """Tracks the workflow stage of a branding request through the design process."""
    request = models.OneToOneField(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='workflow',
    )
    current_stage = models.CharField(max_length=30, choices=WORKFLOW_STAGES, default='brief_review')
    stage_started_at = models.DateTimeField(auto_now_add=True)
    completed_stages = models.JSONField(default=list, blank=True)
    escalation_threshold_days = models.PositiveIntegerField(default=5, help_text='Days before escalation alert')
    is_escalated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Workflow: {self.request.request_number} ({self.get_current_stage_display()})"

    def stage_duration(self):
        """Return timedelta since current stage started."""
        return timezone.now() - self.stage_started_at

    def stage_days(self):
        return self.stage_duration().days

    def is_overdue(self):
        return self.stage_days() > self.escalation_threshold_days

    def progress_percent(self):
        stages = [s[0] for s in WORKFLOW_STAGES]
        if self.current_stage in stages:
            idx = stages.index(self.current_stage)
            return round((idx + 1) / len(stages) * 100)
        return 0

    def advance_stage(self):
        """Move to next workflow stage."""
        stages = [s[0] for s in WORKFLOW_STAGES]
        if self.current_stage in stages:
            idx = stages.index(self.current_stage)
            if idx < len(stages) - 1:
                self.completed_stages = list(set(self.completed_stages + [self.current_stage]))
                self.current_stage = stages[idx + 1]
                self.stage_started_at = timezone.now()
                self.is_escalated = False
                self.save(update_fields=['current_stage', 'stage_started_at', 'completed_stages', 'is_escalated', 'updated_at'])
                return True
        return False

    def move_to_stage(self, target_stage):
        """Move to a specific workflow stage."""
        stages = [s[0] for s in WORKFLOW_STAGES]
        if target_stage in stages:
            self.completed_stages = list(set(self.completed_stages + [self.current_stage]))
            self.current_stage = target_stage
            self.stage_started_at = timezone.now()
            self.is_escalated = False
            self.save(update_fields=['current_stage', 'stage_started_at', 'completed_stages', 'is_escalated', 'updated_at'])
            return True
        return False


class WorkflowStageLog(models.Model):
    """Log entry for each stage transition."""
    workflow = models.ForeignKey(
        ProjectWorkflow,
        on_delete=models.CASCADE,
        related_name='stage_logs',
    )
    from_stage = models.CharField(max_length=30, choices=WORKFLOW_STAGES)
    to_stage = models.CharField(max_length=30, choices=WORKFLOW_STAGES)
    duration_seconds = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, default='')
    moved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='stage_moves',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.workflow.request.request_number}: {self.from_stage} -> {self.to_stage}"


class ClientQuestion(models.Model):
    """Questions for clients about their design preferences."""
    workflow = models.ForeignKey(
        ProjectWorkflow,
        on_delete=models.CASCADE,
        related_name='questions',
    )
    category = models.CharField(max_length=20, choices=QUESTION_CATEGORIES, default='general')
    question = models.TextField()
    is_required = models.BooleanField(default=True)
    answer = models.TextField(blank=True, default='')
    is_answered = models.BooleanField(default=False)
    asked_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    asked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='asked_questions',
    )

    class Meta:
        ordering = ['-is_required', '-asked_at']

    def __str__(self):
        return f"Q: {self.question[:60]}..."

    def mark_answered(self, answer_text):
        self.answer = answer_text
        self.is_answered = True
        self.answered_at = timezone.now()
        self.save(update_fields=['answer', 'is_answered', 'answered_at'])


class FeedbackItem(models.Model):
    """Client feedback on designs."""
    workflow = models.ForeignKey(
        ProjectWorkflow,
        on_delete=models.CASCADE,
        related_name='feedback_items',
    )
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='workflow_feedback',
    )
    status = models.CharField(max_length=15, choices=FEEDBACK_STATUSES, default='new')
    category = models.CharField(max_length=20, choices=QUESTION_CATEGORIES, default='general')
    title = models.CharField(max_length=200)
    content = models.TextField()
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='client_feedback_items',
    )
    internal_notes = models.TextField(blank=True, default='')
    linked_element = models.CharField(max_length=100, blank=True, default='', help_text='Design element reference')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Feedback items'
        ordering = ['-created_at']

    def __str__(self):
        return f"Feedback: {self.title} ({self.get_status_display()})"


class DesignIteration(models.Model):
    """Version history of design iterations."""
    workflow = models.ForeignKey(
        ProjectWorkflow,
        on_delete=models.CASCADE,
        related_name='iterations',
    )
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='design_iterations',
    )
    version_number = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=200, blank=True, default='')
    description = models.TextField(blank=True, default='')
    file = models.FileField(upload_to='design_iterations/%Y/%m/', blank=True)
    thumbnail = models.ImageField(upload_to='design_iterations/thumbs/%Y/%m/', blank=True)
    change_notes = models.TextField(blank=True, default='')
    is_current = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='design_iterations',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version_number']

    def __str__(self):
        return f"v{self.version_number}: {self.title or self.request.request_number}"

    def save(self, *args, **kwargs):
        if self.is_current:
            DesignIteration.objects.filter(
                workflow=self.workflow, is_current=True
            ).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)


class DecisionLog(models.Model):
    """Track all client decisions for a project."""
    workflow = models.ForeignKey(
        ProjectWorkflow,
        on_delete=models.CASCADE,
        related_name='decisions',
    )
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='decision_logs',
    )
    category = models.CharField(max_length=20, choices=QUESTION_CATEGORIES, default='general')
    decision = models.TextField()
    rationale = models.TextField(blank=True, default='')
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='client_decisions',
    )
    is_confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Decision logs'

    def __str__(self):
        return f"Decision: {self.decision[:60]}..."


class CommunicationEntry(models.Model):
    """Combined timeline of all designer-client interactions."""
    INTERACTION_TYPES = [
        ('message', 'Message'),
        ('question', 'Question'),
        ('feedback', 'Feedback'),
        ('approval', 'Approval'),
        ('revision', 'Revision Request'),
        ('note', 'Internal Note'),
    ]

    workflow = models.ForeignKey(
        ProjectWorkflow,
        on_delete=models.CASCADE,
        related_name='communications',
    )
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='workflow_communications',
    )
    interaction_type = models.CharField(max_length=15, choices=INTERACTION_TYPES, default='message')
    title = models.CharField(max_length=200)
    content = models.TextField(blank=True, default='')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='workflow_communications',
    )
    is_from_client = models.BooleanField(default=False)
    response_time_seconds = models.PositiveIntegerField(default=0)
    is_action_item = models.BooleanField(default=False)
    action_taken = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_interaction_type_display()}: {self.title[:60]}"


# ═══════════════════════════════════════════════════════════════════════════
# Concept Presentation System
# ═══════════════════════════════════════════════════════════════════════════

CONCEPT_TAGS = [
    ('modern', 'Modern'),
    ('classic', 'Classic'),
    ('minimalist', 'Minimalist'),
    ('bold', 'Bold'),
    ('elegant', 'Elegant'),
    ('playful', 'Playful'),
    ('corporate', 'Corporate'),
    ('organic', 'Organic'),
    ('vintage', 'Vintage'),
    ('futuristic', 'Futuristic'),
    ('luxury', 'Luxury'),
    ('tech', 'Tech'),
]

CONCEPT_STATUSES = [
    ('draft', 'Draft'),
    ('presented', 'Presented'),
    ('in_review', 'In Review'),
    ('client_selected', 'Client Selected'),
    ('designer_recommended', 'Designer Recommended'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('archived', 'Archived'),
]

RATING_ELEMENTS = [
    ('logo', 'Logo'),
    ('colors', 'Color Palette'),
    ('typography', 'Typography'),
    ('layout', 'Layout'),
    ('imagery', 'Imagery'),
    ('overall', 'Overall'),
]

REFINEMENT_STATUSES = [
    ('requested', 'Requested'),
    ('in_progress', 'In Progress'),
    ('submitted', 'Submitted'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
]

ANNOTATION_TYPES = [
    ('comment', 'Comment'),
    ('question', 'Question'),
    ('suggestion', 'Suggestion'),
    ('issue', 'Issue'),
    ('praise', 'Praise'),
]

SESSION_STATUSES = [
    ('scheduled', 'Scheduled'),
    ('in_progress', 'In Progress'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
]


def concept_upload_path(instance, filename):
    return f'concepts/{instance.request.pk}/{filename}'


def concept_image_path(instance, filename):
    return f'concepts/{instance.concept.request.pk}/{instance.concept.pk}/{filename}'


class DesignConcept(models.Model):
    """A single design concept presented to the client."""
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='concepts',
    )
    designer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='designed_concepts',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, help_text='Designer explanation of the concept')
    status = models.CharField(max_length=25, choices=CONCEPT_STATUSES, default='draft')

    preview_image = models.ImageField(upload_to=concept_upload_path, blank=True, null=True)
    color_palette = models.JSONField(default=list, blank=True, help_text='List of hex color codes')
    fonts = models.JSONField(default=list, blank=True, help_text='List of font names used')
    tags = models.JSONField(default=list, blank=True, help_text='Concept type tags')
    layout_description = models.TextField(blank=True, help_text='Description of layout approach')

    pros = models.JSONField(default=list, blank=True, help_text='Pros of this concept')
    cons = models.JSONField(default=list, blank=True, help_text='Cons of this concept')
    feature_checklist = models.JSONField(default=list, blank=True, help_text='Feature checklist items')

    designer_ranking = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Designer recommended ranking (1 = top pick)',
    )
    client_ranking = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Client ranking (1 = favorite)',
    )
    is_designer_top_pick = models.BooleanField(default=False)
    is_client_favorite = models.BooleanField(default=False)
    combine_with = models.JSONField(
        default=list, blank=True,
        help_text='List of concept IDs to combine elements from',
    )

    overall_score = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    total_ratings = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    presented_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['designer_ranking', '-created_at']

    def __str__(self):
        return f"{self.request.request_number} - {self.title}"

    def get_absolute_url(self):
        return reverse('branding:concept_detail', kwargs={'pk': self.pk})

    def avg_rating(self):
        if self.total_ratings == 0:
            return 0
        return round(self.overall_score / self.total_ratings, 1)

    def rating_breakdown(self):
        ratings = self.element_ratings.all()
        breakdown = {}
        for element_key, element_label in RATING_ELEMENTS:
            element_ratings = ratings.filter(element=element_key)
            if element_ratings.exists():
                avg = sum(r.score for r in element_ratings) / element_ratings.count()
                breakdown[element_key] = {
                    'label': element_label,
                    'avg': round(avg, 1),
                    'count': element_ratings.count(),
                }
        return breakdown

    def annotation_count(self):
        return self.annotations.count()

    def feedback_count(self):
        return self.feedbacks.count()

    def pending_refinements(self):
        return self.refinements.filter(status__in=['requested', 'in_progress']).count()

    def update_score(self):
        from django.db.models import Avg
        agg = self.element_ratings.aggregate(avg=Avg('score'))
        self.overall_score = (agg['avg'] or 0) * self.total_ratings
        self.save(update_fields=['overall_score', 'total_ratings'])


class ConceptImage(models.Model):
    """Supporting images for a concept (layouts, mockups, etc.)."""
    concept = models.ForeignKey(
        DesignConcept,
        on_delete=models.CASCADE,
        related_name='supporting_images',
    )
    image = models.ImageField(upload_to=concept_image_path)
    caption = models.CharField(max_length=200, blank=True)
    image_type = models.CharField(
        max_length=30,
        choices=[
            ('layout', 'Layout'),
            ('mockup', 'Mockup'),
            ('detail', 'Detail'),
            ('variation', 'Variation'),
            ('reference', 'Reference'),
        ],
        default='mockup',
    )
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'created_at']

    def __str__(self):
        return f"{self.concept.title} - {self.get_image_type_display()}"


class ConceptElementRating(models.Model):
    """Rating for a specific design element within a concept."""
    concept = models.ForeignKey(
        DesignConcept,
        on_delete=models.CASCADE,
        related_name='element_ratings',
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='concept_ratings',
    )
    element = models.CharField(max_length=20, choices=RATING_ELEMENTS)
    score = models.PositiveIntegerField(help_text='Rating 1-5')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['concept', 'client', 'element']

    def __str__(self):
        return f"{self.concept.title} - {self.get_element_display()}: {self.score}/5"


class ConceptAnnotation(models.Model):
    """Click-to-annotate on design images."""
    concept = models.ForeignKey(
        DesignConcept,
        on_delete=models.CASCADE,
        related_name='annotations',
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='concept_annotations',
    )
    annotation_type = models.CharField(max_length=20, choices=ANNOTATION_TYPES, default='comment')
    text = models.TextField()
    x_position = models.FloatField(help_text='X coordinate as percentage (0-100)')
    y_position = models.FloatField(help_text='Y coordinate as percentage (0-100)')
    image = models.ForeignKey(
        ConceptImage,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        help_text='If attached to a specific supporting image',
    )
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='resolved_annotations',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.get_annotation_type_display()}: {self.text[:50]}"


class ConceptFeedback(models.Model):
    """Free text feedback per concept."""
    concept = models.ForeignKey(
        DesignConcept,
        on_delete=models.CASCADE,
        related_name='feedbacks',
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='concept_feedbacks',
    )
    overall_rating = models.PositiveIntegerField(
        help_text='Overall concept rating 1-5 stars',
    )
    title = models.CharField(max_length=200, blank=True)
    feedback_text = models.TextField()
    strengths = models.TextField(blank=True, help_text='What works well')
    improvements = models.TextField(blank=True, help_text='What could be improved')
    is_public = models.BooleanField(
        default=True,
        help_text='Visible to designer',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Feedback on {self.concept.title} ({self.overall_rating}/5)"


class ConceptStickyNote(models.Model):
    """Sticky notes attached to specific areas of a concept."""
    concept = models.ForeignKey(
        DesignConcept,
        on_delete=models.CASCADE,
        related_name='sticky_notes',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='concept_sticky_notes',
    )
    text = models.TextField()
    x_position = models.FloatField(help_text='X coordinate as percentage (0-100)')
    y_position = models.FloatField(help_text='Y coordinate as percentage (0-100)')
    color = models.CharField(
        max_length=20,
        choices=[
            ('yellow', 'Yellow'),
            ('blue', 'Blue'),
            ('green', 'Green'),
            ('pink', 'Pink'),
            ('orange', 'Orange'),
        ],
        default='yellow',
    )
    is_pinned = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f"Note: {self.text[:40]}"


class ConceptDecision(models.Model):
    """Tracks client decisions on concepts."""
    concept = models.ForeignKey(
        DesignConcept,
        on_delete=models.CASCADE,
        related_name='decisions',
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='concept_decisions',
    )
    decision = models.CharField(
        max_length=30,
        choices=[
            ('favorite', 'Marked as Favorite'),
            ('recommended', 'Designer Recommended'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('combined', 'Combining with Other Concepts'),
        ],
    )
    notes = models.TextField(blank=True)
    combine_with_concepts = models.JSONField(
        default=list, blank=True,
        help_text='Concept IDs to combine if decision is "combined"',
    )
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-decided_at']

    def __str__(self):
        return f"{self.get_decision_display()} - {self.concept.title}"


class ConceptDecisionTrail(models.Model):
    """Full decision trail with timestamps for audit."""
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='concept_decision_trail',
    )
    concept = models.ForeignKey(
        DesignConcept,
        on_delete=models.CASCADE,
        related_name='decision_trail',
    )
    action = models.CharField(max_length=100)
    details = models.JSONField(default=dict, blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'Concept decision trails'

    def __str__(self):
        return f"{self.action} - {self.concept.title} ({self.timestamp})"


class ConceptRefinement(models.Model):
    """Refinement request on a selected concept."""
    concept = models.ForeignKey(
        DesignConcept,
        on_delete=models.CASCADE,
        related_name='refinements',
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='concept_refinements',
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(
        max_length=15,
        choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')],
        default='medium',
    )
    status = models.CharField(max_length=20, choices=REFINEMENT_STATUSES, default='requested')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Refinement: {self.title} ({self.get_status_display()})"


class ConceptRefinementIteration(models.Model):
    """Before/after iteration for a refinement."""
    refinement = models.ForeignKey(
        ConceptRefinement,
        on_delete=models.CASCADE,
        related_name='iterations',
    )
    version_number = models.PositiveIntegerField(default=1)
    description = models.TextField(help_text='What was changed')
    before_image = models.ImageField(
        upload_to=concept_upload_path,
        null=True, blank=True,
    )
    after_image = models.ImageField(
        upload_to=concept_upload_path,
        null=True, blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    client_approved = models.BooleanField(null=True, blank=True)
    client_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version_number']

    def __str__(self):
        return f"{self.refinement.title} v{self.version_number}"


class ConceptComparison(models.Model):
    """Stores a comparison between two or more concepts."""
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='concept_comparisons',
    )
    title = models.CharField(max_length=200, default='Concept Comparison')
    concepts = models.ManyToManyField(DesignConcept, related_name='comparisons')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class ConceptPresentationSession(models.Model):
    """Scheduled live presentation sessions."""
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='presentation_sessions',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=60)
    meeting_url = models.URLField(blank=True, help_text='Video call link')
    status = models.CharField(max_length=20, choices=SESSION_STATUSES, default='scheduled')
    recording_url = models.URLField(blank=True, help_text='Recording link')
    recording_file = models.FileField(
        upload_to=concept_upload_path,
        null=True, blank=True,
    )
    notes_taken = models.TextField(blank=True)
    realtime_feedback = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_sessions',
    )
    attendees = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='attended_sessions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_at']

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    def is_upcoming(self):
        return self.scheduled_at > timezone.now() and self.status == 'scheduled'

    def is_live(self):
        return self.status == 'in_progress'


# ═══════════════════════════════════════════════════════════════════════════
# Intelligent Questionnaire System
# ═══════════════════════════════════════════════════════════════════════════

QUESTION_TYPES = [
    ('multiple_choice', 'Multiple Choice'),
    ('preference_scale', 'Preference Scale (1-10)'),
    ('yes_no', 'Yes/No'),
    ('short_text', 'Short Text'),
    ('long_text', 'Long Text'),
    ('color_picker', 'Color Picker'),
    ('font_selection', 'Font Selection'),
    ('image_upload', 'Image Upload (Inspiration)'),
    ('rank_order', 'Rank Ordering'),
    ('rating', 'Star Rating (1-5)'),
]

QUESTION_IMPORTANCE = [
    ('critical', 'Critical'),
    ('important', 'Important'),
    ('nice_to_know', 'Nice to Know'),
]

DESIGN_PHASES = [
    ('discovery', 'Brand Discovery'),
    ('concept_direction', 'Concept Direction'),
    ('color_typography', 'Color & Typography'),
    ('layout_structure', 'Layout & Structure'),
    ('final_polish', 'Final Polish'),
]

QUESTION_CATEGORIES = [
    ('logo', 'Logo Design'),
    ('colors', 'Color Palette'),
    ('typography', 'Typography'),
    ('layout', 'Layout'),
    ('imagery', 'Imagery'),
    ('tone', 'Tone & Voice'),
    ('direction', 'Overall Direction'),
    ('general', 'General'),
]

DECISION_STATUSES = [
    ('pending', 'Pending'),
    ('in_progress', 'In Progress'),
    ('completed', 'Completed'),
    ('skipped', 'Skipped'),
]

QUESTIONNAIRE_STATUSES = [
    ('draft', 'Draft'),
    ('sent', 'Sent'),
    ('in_progress', 'In Progress'),
    ('completed', 'Completed'),
    ('expired', 'Expired'),
]


class Questionnaire(models.Model):
    """A questionnaire sent to a client."""
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='questionnaires',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=QUESTIONNAIRE_STATUSES, default='draft')
    phase = models.CharField(max_length=25, choices=DESIGN_PHASES, default='discovery')

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_questionnaires',
    )
    designer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='sent_questionnaires',
    )

    share_token = models.CharField(max_length=64, unique=True, blank=True)
    send_email = models.BooleanField(default=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_reminder_count = models.PositiveIntegerField(default=0)
    last_reminder_at = models.DateTimeField(null=True, blank=True)

    expires_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.share_token:
            import secrets
            self.share_token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def get_share_url(self):
        from django.urls import reverse
        return reverse('branding:client_questionnaire', kwargs={'token': self.share_token})

    def total_questions(self):
        return self.questions.filter(is_active=True).count()

    def answered_questions(self):
        return Answer.objects.filter(
            question__questionnaire=self,
        ).values('question').distinct().count()

    def completion_percent(self):
        total = self.total_questions()
        if total == 0:
            return 0
        return round(self.answered_questions() / total * 100)

    def is_expired(self):
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False

    def is_complete(self):
        return self.answered_questions() >= self.total_questions() and self.total_questions() > 0

    def categories_summary(self):
        questions = self.questions.filter(is_active=True)
        summary = {}
        for cat_key, cat_label in QUESTION_CATEGORIES:
            cat_questions = questions.filter(category=cat_key)
            cat_answers = Answer.objects.filter(
                question__in=cat_questions,
            ).values('question').distinct().count()
            summary[cat_key] = {
                'label': cat_label,
                'total': cat_questions.count(),
                'answered': cat_answers,
                'percent': round(cat_answers / cat_questions.count() * 100) if cat_questions.count() > 0 else 0,
            }
        return summary


class Question(models.Model):
    """A single question within a questionnaire."""
    questionnaire = models.ForeignKey(
        Questionnaire,
        on_delete=models.CASCADE,
        related_name='questions',
    )
    text = models.TextField(help_text='Question text')
    description = models.TextField(blank=True, help_text='Additional context or help text')
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    category = models.CharField(max_length=20, choices=QUESTION_CATEGORIES, default='general')
    phase = models.CharField(max_length=25, choices=DESIGN_PHASES, default='discovery')
    importance = models.CharField(max_length=15, choices=QUESTION_IMPORTANCE, default='important')
    is_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    options = models.JSONField(default=list, blank=True, help_text='Options for multiple choice / rank order')
    scale_min = models.PositiveIntegerField(default=1, help_text='Min value for preference scale')
    scale_max = models.PositiveIntegerField(default=10, help_text='Max value for preference scale')
    scale_labels = models.JSONField(default=dict, blank=True, help_text='Labels for scale endpoints')
    allow_multiple = models.BooleanField(default=False, help_text='Allow multiple selections')
    placeholder = models.CharField(max_length=200, blank=True)
    help_text = models.CharField(max_length=300, blank=True)
    max_file_size_mb = models.PositiveIntegerField(default=5, help_text='Max upload size for image questions')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'created_at']

    def __str__(self):
        return f"{self.get_question_type_display()}: {self.text[:60]}"

    def get_answer_count(self):
        return self.answers.count()

    def get_answers(self):
        return self.answers.all()

    def has_condition(self):
        return self.conditions_from.exists()

    def get_conditions(self):
        return self.conditions_from.all()


class QuestionCondition(models.Model):
    """Conditional logic: show this question only if condition is met."""
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='conditions_from',
        help_text='This question is shown when...',
    )
    depends_on = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='conditions_to',
        help_text='...this question has answer...',
    )
    condition_type = models.CharField(
        max_length=20,
        choices=[
            ('equals', 'Equals'),
            ('not_equals', 'Does Not Equal'),
            ('contains', 'Contains'),
            ('greater_than', 'Greater Than'),
            ('less_than', 'Less Than'),
        ],
        default='equals',
    )
    condition_value = models.CharField(max_length=500, help_text='Expected answer value')

    class Meta:
        verbose_name_plural = 'Question conditions'

    def __str__(self):
        return f"Show Q{self.question.sort_order} when Q{self.depends_on.sort_order} {self.condition_type} {self.condition_value}"

    def is_met(self, client):
        answer = Answer.objects.filter(
            question=self.depends_on,
            client=client,
        ).first()
        if not answer:
            return False
        val = answer.value
        if self.condition_type == 'equals':
            return str(val) == str(self.condition_value)
        elif self.condition_type == 'not_equals':
            return str(val) != str(self.condition_value)
        elif self.condition_type == 'contains':
            return str(self.condition_value).lower() in str(val).lower()
        elif self.condition_type == 'greater_than':
            try:
                return float(val) > float(self.condition_value)
            except (ValueError, TypeError):
                return False
        elif self.condition_type == 'less_than':
            try:
                return float(val) < float(self.condition_value)
            except (ValueError, TypeError):
                return False
        return False


def answer_upload_path(instance, filename):
    return f'questionnaires/{instance.question.questionnaire.pk}/{filename}'


class Answer(models.Model):
    """Client answer to a question."""
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='answers',
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='questionnaire_answers',
    )
    value = models.JSONField(default=None, blank=True, null=True)
    text_value = models.TextField(blank=True)
    image = models.ImageField(upload_to=answer_upload_path, null=True, blank=True)
    selected_options = models.JSONField(default=list, blank=True)
    rank_order = models.JSONField(default=list, blank=True)
    color_value = models.CharField(max_length=7, blank=True)
    font_choice = models.CharField(max_length=100, blank=True)
    scale_value = models.PositiveIntegerField(null=True, blank=True)
    boolean_value = models.BooleanField(null=True, blank=True)

    is_skipped = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['question', 'client', 'version']

    def __str__(self):
        return f"Answer to Q{self.question.sort_order}: {self.get_display_value()[:50]}"

    def get_display_value(self):
        q = self.question
        if q.question_type == 'multiple_choice':
            return ', '.join(self.selected_options) if self.selected_options else ''
        elif q.question_type == 'preference_scale' or q.question_type == 'rating':
            return str(self.scale_value) if self.scale_value is not None else ''
        elif q.question_type == 'yes_no':
            return 'Yes' if self.boolean_value else 'No' if self.boolean_value is not None else ''
        elif q.question_type in ('short_text', 'long_text'):
            return self.text_value
        elif q.question_type == 'color_picker':
            return self.color_value
        elif q.question_type == 'font_selection':
            return self.font_choice
        elif q.question_type == 'rank_order':
            return ' > '.join(self.rank_order) if self.rank_order else ''
        elif q.question_type == 'image_upload':
            return 'Image uploaded' if self.image else ''
        return str(self.value) if self.value else ''

    def get_effective_value(self):
        q = self.question
        if q.question_type == 'multiple_choice':
            return self.selected_options
        elif q.question_type in ('preference_scale', 'rating'):
            return self.scale_value
        elif q.question_type == 'yes_no':
            return self.boolean_value
        elif q.question_type in ('short_text', 'long_text'):
            return self.text_value
        elif q.question_type == 'color_picker':
            return self.color_value
        elif q.question_type == 'font_selection':
            return self.font_choice
        elif q.question_type == 'rank_order':
            return self.rank_order
        elif q.question_type == 'image_upload':
            return self.image.url if self.image else None
        return self.value


class QuestionnaireTemplate(models.Model):
    """Pre-built questionnaire template for design phases."""
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    phase = models.CharField(max_length=25, choices=DESIGN_PHASES)
    industry = models.CharField(max_length=50, blank=True, help_text='Specific to industry, or blank for all')
    collection = models.ForeignKey(
        BrandCollection,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        help_text='Specific to collection, or blank for all',
    )

    questions_data = models.JSONField(
        default=list,
        help_text='List of question dicts: [{text, type, category, importance, required, options, ...}]',
    )

    is_active = models.BooleanField(default=True)
    use_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['phase', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_phase_display()})"

    def create_questionnaire(self, request, client, title=None):
        """Create a questionnaire from this template."""
        import secrets
        q = Questionnaire.objects.create(
            request=request,
            title=title or f"{self.name} - {request.company_name}",
            phase=self.phase,
            client=client,
            designer=request.designer,
            share_token=secrets.token_urlsafe(32),
        )
        for i, qdata in enumerate(self.questions_data):
            Question.objects.create(
                questionnaire=q,
                text=qdata.get('text', ''),
                description=qdata.get('description', ''),
                question_type=qdata.get('type', 'short_text'),
                category=qdata.get('category', 'general'),
                phase=qdata.get('phase', self.phase),
                importance=qdata.get('importance', 'important'),
                is_required=qdata.get('required', True),
                sort_order=i + 1,
                options=qdata.get('options', []),
                scale_min=qdata.get('scale_min', 1),
                scale_max=qdata.get('scale_max', 10),
                scale_labels=qdata.get('scale_labels', {}),
                allow_multiple=qdata.get('allow_multiple', False),
                placeholder=qdata.get('placeholder', ''),
                help_text=qdata.get('help_text', ''),
            )
        self.use_count += 1
        self.save(update_fields=['use_count'])
        return q


class DecisionPoint(models.Model):
    """Critical decision that needs client input."""
    questionnaire = models.ForeignKey(
        Questionnaire,
        on_delete=models.CASCADE,
        related_name='decision_points',
        null=True, blank=True,
    )
    request = models.ForeignKey(
        BrandingRequest,
        on_delete=models.CASCADE,
        related_name='decision_points',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=DECISION_STATUSES, default='pending')
    category = models.CharField(max_length=20, choices=QUESTION_CATEGORIES, default='general')
    importance = models.CharField(max_length=15, choices=QUESTION_IMPORTANCE, default='critical')

    options = models.JSONField(default=list, blank=True, help_text='Decision options to choose from')
    selected_option = models.CharField(max_length=500, blank=True)
    client_notes = models.TextField(blank=True)
    designer_notes = models.TextField(blank=True)

    deadline = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    notified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['status', '-importance', '-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    def is_overdue(self):
        if self.deadline and self.status != 'completed':
            return timezone.now() > self.deadline
        return False

    def mark_decided(self, option, notes=''):
        self.selected_option = option
        self.client_notes = notes
        self.status = 'completed'
        self.decided_at = timezone.now()
        self.save(update_fields=['selected_option', 'client_notes', 'status', 'decided_at', 'updated_at'])


class ClientPreferenceProfile(models.Model):
    """Aggregated design preference profile for a client."""
    client = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='preference_profile',
    )
    preferred_colors = models.JSONField(default=list, blank=True)
    preferred_fonts = models.JSONField(default=list, blank=True)
    preferred_styles = models.JSONField(default=list, blank=True)
    preferred_tones = models.JSONField(default=list, blank=True)
    preferred_layouts = models.JSONField(default=list, blank=True)

    avg_scale_scores = models.JSONField(default=dict, blank=True)
    common_keywords = models.JSONField(default=list, blank=True)
    total_questionnaires_completed = models.PositiveIntegerField(default=0)
    avg_completion_time_hours = models.FloatField(default=0)

    contradictions = models.JSONField(default=list, blank=True)
    patterns = models.JSONField(default=list, blank=True)

    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Client preference profiles'

    def __str__(self):
        return f"Profile: {self.client.username}"

    def update_from_answers(self):
        answers = Answer.objects.filter(
            client=self.client,
            is_skipped=False,
        ).select_related('question')

        colors = []
        fonts = []
        styles = []
        tones = []
        layouts = []

        for answer in answers:
            q = answer.question
            if q.category == 'colors' and answer.color_value:
                colors.append(answer.color_value)
            if q.category == 'typography' and answer.font_choice:
                fonts.append(answer.font_choice)
            if q.category == 'direction':
                val = answer.get_effective_value()
                if isinstance(val, list):
                    styles.extend(val)
                elif val:
                    styles.append(str(val))
            if q.category == 'tone':
                val = answer.get_effective_value()
                if isinstance(val, list):
                    tones.extend(val)
                elif val:
                    tones.append(str(val))
            if q.category == 'layout':
                val = answer.get_effective_value()
                if isinstance(val, list):
                    layouts.extend(val)
                elif val:
                    layouts.append(str(val))

        from collections import Counter
        self.preferred_colors = [c for c, _ in Counter(colors).most_common(10)]
        self.preferred_fonts = [f for f, _ in Counter(fonts).most_common(10)]
        self.preferred_styles = [s for s, _ in Counter(styles).most_common(10)]
        self.preferred_tones = [t for t, _ in Counter(tones).most_common(10)]
        self.preferred_layouts = [l for l, _ in Counter(layouts).most_common(10)]

        scale_scores = {}
        scale_answers = answers.filter(question__question_type='preference_scale')
        for sa in scale_answers:
            cat = sa.question.category
            if cat not in scale_scores:
                scale_scores[cat] = []
            if sa.scale_value:
                scale_scores[cat].append(sa.scale_value)
        self.avg_scale_scores = {
            cat: round(sum(vals) / len(vals), 1)
            for cat, vals in scale_scores.items()
        }

        self.total_questionnaires_completed = self.client.received_questionnaires.filter(
            status='completed',
        ).count()

        self.save()
        return self
