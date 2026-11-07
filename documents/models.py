"""Models for the document generation and e-signature system.

The app deliberately stores *documents*, not payments. Client identity comes
from ``crm.Customer`` and an optional link to the existing
``projects.Invoice`` is available for documents generated from an internal
invoice. No invoice, quotation or payment model is duplicated here.
"""
import os
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .storage import private_document_storage


MONEY = Decimal('0.01')
ZERO = Decimal('0.00')


def document_pdf_path(instance, filename):
    return f"documents/pdfs/{instance.reference or 'draft'}/{filename}"


def signature_image_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower() or '.png'
    return f"documents/signatures/{instance.document.reference or 'draft'}/{instance.pk or 'new'}{ext}"


def company_asset_path(folder, filename):
    ext = os.path.splitext(filename)[1].lower()
    base = slugify(os.path.splitext(os.path.basename(filename))[0]) or 'asset'
    return f"documents/company/{folder}/{base}{ext}"


def company_signature_path(instance, filename):
    return company_asset_path('signature', filename)


def company_stamp_path(instance, filename):
    return company_asset_path('stamp', filename)


class DocumentType(models.Model):
    """A configurable document template category (invoice, quotation, ...)."""

    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    prefix = models.CharField(max_length=8, help_text=_('Prefix used in reference numbers, e.g. INV.'))
    description = models.CharField(max_length=255, blank=True)

    requires_acceptance = models.BooleanField(
        default=False,
        help_text=_('The client can accept or reject this document (quotations, proposals).'),
    )
    requires_signature = models.BooleanField(
        default=False,
        help_text=_('The client must sign this document electronically (contracts).'),
    )
    is_active = models.BooleanField(default=True)
    ordering = models.PositiveIntegerField(default=0)
    next_number = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('ordering', 'name')
        verbose_name = _('Document type')
        verbose_name_plural = _('Document types')

    def __str__(self):
        return self.name


class DocumentSettings(models.Model):
    """Singleton holding company identity plus the authorized signature assets.

    The signature and stamp uploaded here are authorized company assets. They
    are applied to official documents by administrators and are *not* a client
    electronic signature.
    """

    company_name = models.CharField(max_length=150, default='OnWebApp')
    company_legal_name = models.CharField(max_length=200, blank=True)
    company_address = models.TextField(blank=True)
    company_email = models.EmailField(blank=True)
    company_phone = models.CharField(max_length=60, blank=True)
    company_website = models.URLField(blank=True)
    company_tax_id = models.CharField(max_length=80, blank=True, verbose_name=_('Tax / registration ID'))
    registration_note = models.CharField(max_length=200, blank=True)

    signatory_name = models.CharField(max_length=120, blank=True)
    signatory_position = models.CharField(max_length=120, blank=True)
    signature_image = models.FileField(
        upload_to=company_signature_path, blank=True,
        help_text=_('Transparent PNG of the authorized handwritten/digital signature.'),
    )
    stamp_image = models.FileField(
        upload_to=company_stamp_path, blank=True,
        help_text=_('Transparent PNG of the official company stamp or seal.'),
    )

    accent_color = models.CharField(max_length=7, default='#4F46E5')
    default_payment_terms = models.TextField(
        blank=True,
        default='Payment is due within 14 days of the issue date.',
    )
    default_validity_days = models.PositiveIntegerField(default=30)
    bank_details = models.TextField(blank=True)
    footer_note = models.CharField(max_length=255, blank=True, default='Thank you for your business.')

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Document settings')
        verbose_name_plural = _('Document settings')

    def __str__(self):
        return 'Document settings'

    def save(self, *args, **kwargs):
        # Enforce a single settings row so every document uses the same
        # signature and stamp.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def has_signature(self):
        return bool(self.signature_image and self.signature_image.name)

    @property
    def has_stamp(self):
        return bool(self.stamp_image and self.stamp_image.name)


class Document(models.Model):
    STATUS_DRAFT = 'DRAFT'
    STATUS_SENT = 'SENT'
    STATUS_VIEWED = 'VIEWED'
    STATUS_ACCEPTED = 'ACCEPTED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_SIGNED = 'SIGNED'
    STATUS_PAID = 'PAID'
    STATUS_OVERDUE = 'OVERDUE'
    STATUS_CANCELLED = 'CANCELLED'

    STATUS_CHOICES = [
        (STATUS_DRAFT, _('Draft')),
        (STATUS_SENT, _('Sent')),
        (STATUS_VIEWED, _('Viewed')),
        (STATUS_ACCEPTED, _('Accepted')),
        (STATUS_REJECTED, _('Rejected')),
        (STATUS_SIGNED, _('Signed')),
        (STATUS_PAID, _('Paid')),
        (STATUS_OVERDUE, _('Overdue')),
        (STATUS_CANCELLED, _('Cancelled')),
    ]

    STATUS_TONES = {
        STATUS_DRAFT: 'secondary',
        STATUS_SENT: 'primary',
        STATUS_VIEWED: 'info',
        STATUS_ACCEPTED: 'success',
        STATUS_SIGNED: 'success',
        STATUS_REJECTED: 'danger',
        STATUS_PAID: 'success',
        STATUS_OVERDUE: 'danger',
        STATUS_CANCELLED: 'dark',
    }

    doc_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT, related_name='documents')
    reference = models.CharField(max_length=40, unique=True, editable=False)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    customer = models.ForeignKey(
        'crm.Customer', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='documents', help_text=_('CRM customer this document belongs to.'),
    )
    client_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='documents', help_text=_('Registered account used for dashboard access.'),
    )
    project = models.ForeignKey(
        'projects.Project', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='documents',
    )
    source_invoice = models.ForeignKey(
        'projects.Invoice', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='documents', help_text=_('Optional internal invoice this document was generated from.'),
    )

    # Snapshot of the client details at issue time: the document must remain
    # accurate even if the CRM profile changes later.
    client_name = models.CharField(max_length=200)
    client_email = models.EmailField()
    client_company = models.CharField(max_length=200, blank=True)
    client_address = models.TextField(blank=True)
    client_tax_id = models.CharField(max_length=80, blank=True)

    title = models.CharField(max_length=200, blank=True)
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)

    currency = models.CharField(max_length=3, default='USD')
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    tax_rate = models.DecimalField(max_digits=6, decimal_places=2, default=ZERO, help_text=_('Percentage, e.g. 20.00'))
    tax_label = models.CharField(max_length=30, default='VAT')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)

    notes = models.TextField(blank=True, help_text=_('Shown to the client on the document.'))
    terms = models.TextField(blank=True)

    pdf_file = models.FileField(upload_to=document_pdf_path, storage=private_document_storage, blank=True)
    pdf_sha256 = models.CharField(max_length=64, blank=True)
    pdf_generated_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_documents',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    viewed_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    accepted_by_name = models.CharField(max_length=200, blank=True)
    rejected_reason = models.TextField(blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-issue_date', '-created_at')
        verbose_name = _('Document')
        verbose_name_plural = _('Documents')
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['reference']),
            models.Index(fields=['client_email']),
            models.Index(fields=['due_date']),
        ]

    def __str__(self):
        return f'{self.reference} - {self.client_name}'

    # ------------------------------------------------------------------ URLs
    def get_absolute_url(self):
        return reverse('documents:admin_detail', args=[self.pk])

    # --------------------------------------------------------------- Helpers
    @property
    def status_tone(self):
        return self.STATUS_TONES.get(self.status, 'secondary')

    @property
    def is_editable(self):
        return self.status in {self.STATUS_DRAFT, self.STATUS_SENT, self.STATUS_VIEWED}

    @property
    def is_final(self):
        return self.status in {
            self.STATUS_ACCEPTED, self.STATUS_REJECTED, self.STATUS_SIGNED,
            self.STATUS_PAID, self.STATUS_CANCELLED,
        }

    @property
    def is_overdue(self):
        return bool(
            self.due_date
            and self.status in {self.STATUS_SENT, self.STATUS_VIEWED}
            and self.doc_type_id
            and self.doc_type.code in {'invoice', 'receipt'}
            and self.due_date < timezone.localdate()
        )

    @property
    def display_status(self):
        return self.STATUS_OVERDUE if self.is_overdue else self.status

    @property
    def display_status_label(self):
        return dict(self.STATUS_CHOICES).get(self.display_status, self.display_status)

    @property
    def display_status_tone(self):
        return self.STATUS_TONES.get(self.display_status, 'secondary')

    @property
    def client_display_name(self):
        return self.client_company or self.client_name

    @property
    def title_display(self):
        return self.title or str(self.doc_type)

    @property
    def latest_signature(self):
        return self.signatures.filter(is_valid=True).order_by('-signed_at').first()

    @property
    def is_client_signed(self):
        return self.latest_signature is not None

    # ------------------------------------------------------------- Lifecycle
    def apply_client_snapshot(self):
        """Copy identity from the CRM customer and registered user."""
        customer = self.customer
        if not customer:
            return
        self.client_name = customer.name
        self.client_email = customer.email
        self.client_company = customer.company_name or ''
        parts = [customer.business_address, customer.city, customer.country]
        self.client_address = '\n'.join(p for p in parts if p)
        if customer.user_id:
            self.client_user = customer.user

    def recalculate(self, save=True):
        subtotal = sum((item.line_total for item in self.items.all()), ZERO)
        subtotal = Decimal(subtotal).quantize(MONEY, rounding=ROUND_HALF_UP)
        discount = (self.discount_amount or ZERO)
        taxable = max(subtotal - discount, ZERO)
        tax = (taxable * (self.tax_rate or ZERO) / Decimal('100')).quantize(MONEY, rounding=ROUND_HALF_UP)
        total = (taxable + tax).quantize(MONEY, rounding=ROUND_HALF_UP)
        self.subtotal = subtotal
        self.tax_amount = tax
        self.total = total
        if save:
            self.save(update_fields=['subtotal', 'tax_amount', 'total', 'updated_at'])
        return self.total

    def mark_overdue(self):
        if self.is_overdue and self.status != self.STATUS_OVERDUE:
            self.status = self.STATUS_OVERDUE
            self.save(update_fields=['status', 'updated_at'])
            DocumentEvent.log(self, DocumentEvent.EVENT_OVERDUE, note='Automatically marked overdue.')
            return True
        return False

    def is_visible_to(self, user):
        """Ownership check for dashboard access."""
        if not user or not user.is_authenticated:
            return False
        if user.is_staff:
            return True
        if self.client_user_id and self.client_user_id == user.pk:
            return True
        if self.customer_id and self.customer and self.customer.user_id == user.pk:
            return True
        return bool(
            user.email
            and self.client_email
            and user.email.strip().lower() == self.client_email.strip().lower()
        )

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self._allocate_reference()
        super().save(*args, **kwargs)

    def _allocate_reference(self):
        with transaction.atomic():
            doc_type = DocumentType.objects.select_for_update().get(pk=self.doc_type_id)
            doc_type.next_number += 1
            doc_type.save(update_fields=['next_number'])
            year = timezone.localdate().year
            return f'{doc_type.prefix}-{year}-{doc_type.next_number:05d}'


class DocumentLineItem(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=255)
    details = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    ordering = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('ordering', 'pk')
        verbose_name = _('Line item')
        verbose_name_plural = _('Line items')

    def __str__(self):
        return self.description

    def save(self, *args, **kwargs):
        self.line_total = (self.quantity * self.unit_price).quantize(MONEY, rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)


class DocumentEvent(models.Model):
    """Append-only audit trail for every document action."""

    EVENT_CREATED = 'created'
    EVENT_REVISED = 'revised'
    EVENT_GENERATED = 'generated'
    EVENT_SENT = 'sent'
    EVENT_RESENT = 'resent'
    EVENT_VIEWED = 'viewed'
    EVENT_DOWNLOADED = 'downloaded'
    EVENT_ACCEPTED = 'accepted'
    EVENT_REJECTED = 'rejected'
    EVENT_SIGNED = 'signed'
    EVENT_PAID = 'paid'
    EVENT_OVERDUE = 'overdue'
    EVENT_CANCELLED = 'cancelled'
    EVENT_EMAIL_FAILED = 'email_failed'

    EVENT_CHOICES = [
        (EVENT_CREATED, _('Created')),
        (EVENT_REVISED, _('Revised')),
        (EVENT_GENERATED, _('PDF generated')),
        (EVENT_SENT, _('Sent by email')),
        (EVENT_RESENT, _('Resent by email')),
        (EVENT_VIEWED, _('Viewed')),
        (EVENT_DOWNLOADED, _('Downloaded')),
        (EVENT_ACCEPTED, _('Accepted')),
        (EVENT_REJECTED, _('Rejected')),
        (EVENT_SIGNED, _('Signed')),
        (EVENT_PAID, _('Marked paid')),
        (EVENT_OVERDUE, _('Marked overdue')),
        (EVENT_CANCELLED, _('Cancelled')),
        (EVENT_EMAIL_FAILED, _('Email delivery failed')),
    ]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='events')
    event = models.CharField(max_length=20, choices=EVENT_CHOICES)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='document_events',
    )
    actor_email = models.EmailField(blank=True)
    note = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = _('Document event')
        verbose_name_plural = _('Document events')

    def __str__(self):
        return f'{self.document.reference}: {self.event}'

    @classmethod
    def log(cls, document, event, *, actor=None, request=None, note='', metadata=None, actor_email=''):
        ip = None
        ua = ''
        if request is not None:
            ip = (request.META.get('HTTP_X_FORWARDED_FOR') or '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')
            ua = (request.META.get('HTTP_USER_AGENT') or '')[:500]
        if actor is not None and not actor_email:
            actor_email = getattr(actor, 'email', '') or ''
        return cls.objects.create(
            document=document,
            event=event,
            actor=actor if getattr(actor, 'is_authenticated', False) else None,
            actor_email=actor_email or '',
            note=note[:255],
            ip_address=ip or None,
            user_agent=ua,
            metadata=metadata or {},
        )


class DocumentEmail(models.Model):
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='emails')
    to_email = models.EmailField()
    subject = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=[(STATUS_SENT, _('Sent')), (STATUS_FAILED, _('Failed'))])
    error = models.TextField(blank=True)
    message_id = models.CharField(max_length=255, blank=True)
    is_resend = models.BooleanField(default=False)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='document_emails',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = _('Document email')
        verbose_name_plural = _('Document emails')

    def __str__(self):
        return f'{self.document.reference} -> {self.to_email} ({self.status})'


class DocumentSignature(models.Model):
    """A client's electronic signature on a contract.

    This is intentionally separate from the company signature image stored in
    :class:`DocumentSettings`. A document is never considered signed merely
    because the company signature was applied.
    """

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='signatures')
    signer_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='document_signatures',
    )
    signer_name = models.CharField(max_length=200)
    signer_email = models.EmailField()
    signer_role = models.CharField(max_length=120, blank=True)
    typed_signature = models.CharField(max_length=200, blank=True)
    signature_image = models.FileField(upload_to=signature_image_path, storage=private_document_storage, blank=True)
    consent_text = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    document_version = models.PositiveIntegerField(default=1)
    pdf_sha256 = models.CharField(max_length=64, blank=True, help_text=_('Hash of the PDF the signer signed.'))
    is_valid = models.BooleanField(default=True)
    signed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ('-signed_at',)
        verbose_name = _('Document signature')
        verbose_name_plural = _('Document signatures')

    def __str__(self):
        return f'{self.document.reference} signed by {self.signer_name}'
