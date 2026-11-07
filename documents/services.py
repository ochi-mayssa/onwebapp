"""Business services for documents: PDF lifecycle, email delivery, signatures.

Keeping this logic out of the views means the same rules apply whether an
action is triggered from the admin dashboard, the client dashboard or a
tokenised email link.
"""
import hashlib
import logging

from django.conf import settings as django_settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from home.emails import send_notification_email

from .models import (
    Document,
    DocumentEmail,
    DocumentEvent,
    DocumentSettings,
    DocumentSignature,
)
from .pdf import money, render_document_pdf
from .tokens import make_token, public_url

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------- utils
def _client_meta(request):
    if request is None:
        return None, ''
    ip = (request.META.get('HTTP_X_FORWARDED_FOR') or '').split(',')[0].strip()
    ip = ip or request.META.get('REMOTE_ADDR') or None
    ua = (request.META.get('HTTP_USER_AGENT') or '')[:500]
    return ip, ua


def _asset_path(field_file):
    if not field_file:
        return None
    try:
        return field_file.path
    except (NotImplementedError, ValueError):
        return None


def _site_url(request=None):
    configured = (getattr(django_settings, 'SITE_URL', '') or '').rstrip('/')
    if configured:
        return configured
    if request is not None:
        return request.build_absolute_uri('/').rstrip('/')
    return ''


# ----------------------------------------------------------------------- PDF
def generate_document_pdf(document, *, actor=None):
    """Render and persist the PDF for ``document``; returns the PDF bytes."""
    pdf_bytes = render_document_pdf(document)
    filename = f'{document.reference}-v{document.version}.pdf'

    if document.pdf_file:
        try:
            document.pdf_file.delete(save=False)
        except Exception:
            logger.warning('Could not delete previous PDF for %s', document.reference)

    document.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
    document.pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    document.pdf_generated_at = timezone.now()
    document.save(update_fields=['pdf_file', 'pdf_sha256', 'pdf_generated_at', 'updated_at'])

    DocumentEvent.log(
        document,
        DocumentEvent.EVENT_GENERATED,
        actor=actor,
        note=f'PDF v{document.version} generated ({len(pdf_bytes):,} bytes).',
        metadata={'sha256': document.pdf_sha256, 'version': document.version},
    )
    return pdf_bytes


def ensure_pdf(document, *, actor=None):
    """Return the stored PDF bytes, generating the PDF when necessary."""
    if document.pdf_file and document.pdf_sha256:
        try:
            with document.pdf_file.open('rb') as handle:
                return handle.read()
        except Exception:
            logger.warning('Stored PDF unreadable for %s, regenerating', document.reference)
    return generate_document_pdf(document, actor=actor)


# --------------------------------------------------------------------- email
def _inline_images(cfg):
    images = []
    signature = _asset_path(cfg.signature_image)
    if signature:
        images.append({'path': signature, 'cid': 'document-signature',
                       'filename': 'signature.png'})
    stamp = _asset_path(cfg.stamp_image)
    if stamp:
        images.append({'path': stamp, 'cid': 'document-stamp', 'filename': 'stamp.png'})
    return images


def _text_body(document, cfg, link):
    lines = [
        f'Dear {document.client_name},',
        '',
        f'Please find attached {document.doc_type.name.lower()} {document.reference} '
        f'from {cfg.company_name or "OnWebApp"}.',
        '',
        f'Issue date: {document.issue_date:%d %b %Y}',
    ]
    if document.due_date:
        lines.append(f'Due date: {document.due_date:%d %b %Y}')
    lines.append(f'Total: {money(document.total, document.currency)}')
    lines.append('')
    lines.append(f'View or download the document: {link}')
    if document.doc_type.requires_signature:
        lines.append('')
        lines.append('This contract requires your electronic signature. Open the link above to review and sign it.')
    elif document.doc_type.requires_acceptance:
        lines.append('')
        lines.append('You can accept or reject this document from the link above.')
    if cfg.default_payment_terms:
        lines += ['', f'Payment terms: {cfg.default_payment_terms}']
    lines += [
        '',
        f'Kind regards,',
        cfg.signatory_name or cfg.company_name or 'OnWebApp',
        cfg.signatory_position or '',
        '',
        'The company signature and stamp included with this document are authorized '
        'company assets. They are not a client electronic signature.',
    ]
    return '\n'.join(line for line in lines if line is not None)


def send_document(document, *, actor=None, request=None):
    """Generate the PDF and email it to the client. Returns True on success."""
    cfg = DocumentSettings.load()
    is_resend = bool(document.sent_at or document.emails.exists())

    pdf_bytes = generate_document_pdf(document, actor=actor)
    link = public_url(document)
    site_url = _site_url(request)

    subject = f'{document.doc_type.name} {document.reference} from {cfg.company_name or "OnWebApp"}'
    context = {
        'document': document,
        'settings': cfg,
        'company': cfg,
        'link': link,
        'site_url': site_url,
        'amount': money(document.total, document.currency),
        'has_signature': cfg.has_signature,
        'has_stamp': cfg.has_stamp,
        'is_quote': document.doc_type.requires_acceptance,
        'requires_signature': document.doc_type.requires_signature,
        'client_name': document.client_name,
    }

    sent = send_notification_email(
        subject=subject,
        recipients=[document.client_email],
        text_body=_text_body(document, cfg, link),
        template_name='documents/emails/document_sent.html',
        context=context,
        attachments=[(f'{document.reference}.pdf', pdf_bytes, 'application/pdf')],
        inline_images=_inline_images(cfg),
        label=f'document {document.reference}',
    )

    DocumentEmail.objects.create(
        document=document,
        to_email=document.client_email,
        subject=subject,
        status=DocumentEmail.STATUS_SENT if sent else DocumentEmail.STATUS_FAILED,
        error='' if sent else 'Email backend reported a delivery failure.',
        is_resend=is_resend,
        sent_by=actor if getattr(actor, 'is_authenticated', False) else None,
    )

    if sent:
        update_fields = ['updated_at']
        if document.status == Document.STATUS_DRAFT:
            document.status = Document.STATUS_SENT
            update_fields.append('status')
        if not document.sent_at:
            document.sent_at = timezone.now()
            update_fields.append('sent_at')
        document.save(update_fields=update_fields)
        DocumentEvent.log(
            document,
            DocumentEvent.EVENT_RESENT if is_resend else DocumentEvent.EVENT_SENT,
            actor=actor,
            request=request,
            note=f'Emailed to {document.client_email}.',
            metadata={'version': document.version},
        )
    else:
        DocumentEvent.log(
            document,
            DocumentEvent.EVENT_EMAIL_FAILED,
            actor=actor,
            request=request,
            note=f'Email to {document.client_email} could not be delivered.',
        )
    return sent


# ---------------------------------------------------------------- signatures
def apply_client_signature(document, *, signer_name, signer_email, consent_text,
                           signer_role='', typed_signature='', signature_image=None,
                           request=None, actor_user=None):
    """Record a client e-signature, then regenerate the signed PDF.

    The company signature image is never enough: this function is the only
    place that marks a document as ``SIGNED``.
    """
    if not document.doc_type.requires_signature:
        raise ValueError('This document type does not require a client signature.')

    ip, ua = _client_meta(request)
    signature = DocumentSignature(
        document=document,
        signer_user=actor_user if getattr(actor_user, 'is_authenticated', False) else None,
        signer_name=signer_name.strip(),
        signer_email=signer_email.strip(),
        signer_role=signer_role.strip(),
        typed_signature=(typed_signature or '').strip(),
        consent_text=consent_text,
        ip_address=ip,
        user_agent=ua,
        document_version=document.version,
    )
    if signature_image is not None:
        signature.signature_image = signature_image
    signature.save()

    # The signed PDF includes the client signature block and the certificate.
    generate_document_pdf(document, actor=actor_user)
    signature.pdf_sha256 = document.pdf_sha256
    signature.save(update_fields=['pdf_sha256'])

    document.status = Document.STATUS_SIGNED
    document.accepted_by_name = signature.signer_name
    if not document.accepted_at:
        document.accepted_at = timezone.now()
    document.save(update_fields=['status', 'accepted_by_name', 'accepted_at', 'updated_at'])

    DocumentEvent.log(
        document,
        DocumentEvent.EVENT_SIGNED,
        actor=actor_user if getattr(actor_user, 'is_authenticated', False) else None,
        actor_email=signature.signer_email,
        request=request,
        note=f'Contract signed electronically by {signature.signer_name}.',
        metadata={
            'version': signature.document_version,
            'pdf_sha256': signature.pdf_sha256,
            'ip': signature.ip_address,
        },
    )
    return signature


def accept_document(document, *, actor=None, request=None, name=''):
    if not document.doc_type.requires_acceptance:
        raise ValueError('This document type cannot be accepted.')
    document.status = Document.STATUS_ACCEPTED
    document.accepted_at = timezone.now()
    document.accepted_by_name = name or (actor.get_full_name() if actor and actor.get_full_name() else '')
    document.save(update_fields=['status', 'accepted_at', 'accepted_by_name', 'updated_at'])
    DocumentEvent.log(
        document, DocumentEvent.EVENT_ACCEPTED, actor=actor, request=request,
        actor_email=(document.client_email if actor is None else ''),
        note=f'Accepted by {document.accepted_by_name or document.client_email}.',
    )
    return document


def reject_document(document, *, actor=None, request=None, reason=''):
    if not document.doc_type.requires_acceptance:
        raise ValueError('This document type cannot be rejected.')
    document.status = Document.STATUS_REJECTED
    document.rejected_at = timezone.now()
    document.rejected_reason = reason.strip()
    document.save(update_fields=['status', 'rejected_at', 'rejected_reason', 'updated_at'])
    DocumentEvent.log(
        document, DocumentEvent.EVENT_REJECTED, actor=actor, request=request,
        actor_email=(document.client_email if actor is None else ''),
        note=reason.strip()[:255] or 'Rejected without a reason.',
    )
    return document


def mark_paid(document, *, actor=None, request=None):
    document.status = Document.STATUS_PAID
    document.paid_at = timezone.now()
    document.save(update_fields=['status', 'paid_at', 'updated_at'])
    DocumentEvent.log(document, DocumentEvent.EVENT_PAID, actor=actor, request=request)
    return document


def cancel_document(document, *, actor=None, request=None, note=''):
    document.status = Document.STATUS_CANCELLED
    document.save(update_fields=['status', 'updated_at'])
    DocumentEvent.log(document, DocumentEvent.EVENT_CANCELLED, actor=actor, request=request, note=note)
    return document


def revise_document(document, *, actor=None, request=None):
    """Bump the version and drop the stale PDF before regenerating."""
    document.version += 1
    if document.pdf_file:
        try:
            document.pdf_file.delete(save=False)
        except Exception:
            logger.warning('Could not remove stale PDF for %s', document.reference)
    document.pdf_file = ''
    document.pdf_sha256 = ''
    document.pdf_generated_at = None
    document.save(update_fields=[
        'version', 'pdf_file', 'pdf_sha256', 'pdf_generated_at', 'updated_at',
    ])
    DocumentEvent.log(
        document, DocumentEvent.EVENT_REVISED, actor=actor, request=request,
        note=f'Revised to version {document.version}.',
        metadata={'version': document.version},
    )
    return document


def refresh_overdue_documents():
    """Move sent documents past their due date into OVERDUE. Returns count."""
    from .models import DocumentType

    today = timezone.localdate()
    candidates = Document.objects.filter(
        status__in=[Document.STATUS_SENT, Document.STATUS_VIEWED],
        due_date__lt=today,
        doc_type__code__in=['invoice', 'receipt'],
    ).select_related('doc_type')
    changed = 0
    for document in candidates:
        if document.mark_overdue():
            changed += 1
    return changed


def document_email_context(document, request=None):
    """Shared context for the emailed and on-screen document views."""
    cfg = DocumentSettings.load()
    token = make_token(document)
    link = public_url(document)
    download_url = reverse('documents:public_download', args=[token])
    return {
        'document': document,
        'settings': cfg,
        'company': cfg,
        'token': token,
        'link': link,
        'download_path': download_url,
        'site_url': _site_url(request),
        'amount': money(document.total, document.currency),
    }
