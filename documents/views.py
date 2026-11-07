"""Views for document administration, the client dashboard and email links."""
import logging
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    ClientSignatureForm,
    DocumentForm,
    DocumentLineItemFormSet,
    DocumentSettingsForm,
)
from .models import (
    Document,
    DocumentEvent,
    DocumentSettings,
    DocumentType,
)
from .pdf import money
from .services import (
    accept_document,
    apply_client_signature,
    cancel_document,
    ensure_pdf,
    generate_document_pdf,
    mark_paid,
    refresh_overdue_documents,
    reject_document,
    revise_document,
    send_document,
)
from .tokens import TokenError, make_token, read_token

logger = logging.getLogger(__name__)

CLIENT_VISIBLE_STATUSES = [
    Document.STATUS_SENT,
    Document.STATUS_VIEWED,
    Document.STATUS_ACCEPTED,
    Document.STATUS_REJECTED,
    Document.STATUS_SIGNED,
    Document.STATUS_PAID,
    Document.STATUS_OVERDUE,
    Document.STATUS_CANCELLED,
]


def is_admin(user):
    return bool(user.is_authenticated and (user.is_staff or user.is_superuser))


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_admin(request.user):
            raise PermissionDenied('Administrator access is required.')
        return view(request, *args, **kwargs)
    return wrapper


def _mark_viewed(document, request, user=None):
    if document.status != Document.STATUS_SENT:
        return
    document.status = Document.STATUS_VIEWED
    document.viewed_at = timezone.now()
    document.save(update_fields=['status', 'viewed_at', 'updated_at'])
    DocumentEvent.log(
        document,
        DocumentEvent.EVENT_VIEWED,
        actor=user,
        request=request,
        actor_email='' if user else document.client_email,
    )


def _serve_pdf(document, request, user=None):
    pdf_bytes = ensure_pdf(document, actor=user)
    DocumentEvent.log(
        document,
        DocumentEvent.EVENT_DOWNLOADED,
        actor=user,
        request=request,
        actor_email='' if user else document.client_email,
    )
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{document.reference}.pdf"'
    response['Content-Length'] = str(len(pdf_bytes))
    response['Cache-Control'] = 'private, no-store'
    return response


def _get_client_document(request, pk):
    document = get_object_or_404(
        Document.objects.select_related('doc_type', 'customer'), pk=pk,
    )
    if document.status not in CLIENT_VISIBLE_STATUSES:
        raise PermissionDenied('This document is not available yet.')
    if not document.is_visible_to(request.user):
        raise PermissionDenied('This document belongs to another client.')
    return document


# --------------------------------------------------------------------- admin
@admin_required
def admin_list(request):
    refresh_overdue_documents()
    base = Document.objects.select_related('doc_type', 'customer')
    qs = base

    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(reference__icontains=q)
            | Q(client_name__icontains=q)
            | Q(client_company__icontains=q)
            | Q(client_email__icontains=q)
        )
    type_code = (request.GET.get('type') or '').strip()
    if type_code:
        qs = qs.filter(doc_type__code=type_code)
    status = (request.GET.get('status') or '').strip()
    if status:
        qs = qs.filter(status=status)

    summary = {
        'total': base.count(),
        'draft': base.filter(status=Document.STATUS_DRAFT).count(),
        'overdue': base.filter(status=Document.STATUS_OVERDUE).count(),
        'outstanding': base.exclude(
            status__in=[Document.STATUS_DRAFT, Document.STATUS_PAID, Document.STATUS_CANCELLED],
        ).aggregate(value=Sum('total'))['value'] or 0,
    }

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    context = {
        'page_obj': page_obj,
        'summary': summary,
        'q': q,
        'type_code': type_code,
        'status': status,
        'document_types': DocumentType.objects.filter(is_active=True),
        'status_choices': Document.STATUS_CHOICES,
        'settings': DocumentSettings.load(),
    }
    return render(request, 'documents/admin_list.html', context)


@admin_required
def admin_create(request):
    if request.method == 'POST':
        form = DocumentForm(request.POST)
        formset = DocumentLineItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            document = form.save(commit=False)
            document.created_by = request.user
            document.apply_client_snapshot()
            document.save()
            formset.instance = document
            formset.save()
            document.recalculate()
            DocumentEvent.log(
                document, DocumentEvent.EVENT_CREATED, actor=request.user, request=request,
            )
            messages.success(request, f'{document.doc_type.name} {document.reference} created.')
            return redirect('documents:admin_detail', pk=document.pk)
        messages.error(request, 'Please correct the errors below.')
    else:
        form = DocumentForm()
        formset = DocumentLineItemFormSet()
    return render(request, 'documents/admin_form.html', {
        'form': form,
        'formset': formset,
        'is_create': True,
        'settings': DocumentSettings.load(),
    })


@admin_required
def admin_edit(request, pk):
    document = get_object_or_404(Document, pk=pk)
    was_draft = document.status == Document.STATUS_DRAFT
    can_edit = document.is_editable

    if request.method == 'POST':
        if not can_edit:
            messages.error(request, 'This document can no longer be edited.')
            return redirect('documents:admin_detail', pk=document.pk)
        form = DocumentForm(request.POST, instance=document)
        formset = DocumentLineItemFormSet(request.POST, instance=document)
        if form.is_valid() and formset.is_valid():
            document = form.save(commit=False)
            document.apply_client_snapshot()
            document.save()
            formset.save()
            document.recalculate()
            if not was_draft:
                revise_document(document, actor=request.user, request=request)
                messages.success(
                    request,
                    f'Saved as version {document.version}. Regenerate and resend it to the client.',
                )
            else:
                messages.success(request, 'Document updated.')
            return redirect('documents:admin_detail', pk=document.pk)
        messages.error(request, 'Please correct the errors below.')
    else:
        form = DocumentForm(instance=document)
        formset = DocumentLineItemFormSet(instance=document)

    return render(request, 'documents/admin_form.html', {
        'form': form,
        'formset': formset,
        'document': document,
        'is_create': False,
        'can_edit': can_edit,
        'settings': DocumentSettings.load(),
    })


@admin_required
def admin_detail(request, pk):
    document = get_object_or_404(
        Document.objects.select_related('doc_type', 'customer', 'client_user'),
        pk=pk,
    )
    context = {
        'document': document,
        'items': document.items.all(),
        'events': document.events.select_related('actor')[:50],
        'emails': document.emails.select_related('sent_by')[:20],
        'signatures': document.signatures.select_related('signer_user'),
        'settings': DocumentSettings.load(),
        'public_link': request.build_absolute_uri(
            reverse('documents:public_view', args=[make_token(document)])
        ) if document.status != Document.STATUS_DRAFT else '',
    }
    return render(request, 'documents/admin_detail.html', context)


@admin_required
def admin_preview(request, pk):
    document = get_object_or_404(Document.objects.select_related('doc_type'), pk=pk)
    return render(request, 'documents/admin_preview.html', {
        'document': document,
        'items': document.items.all(),
        'settings': DocumentSettings.load(),
        'amount': money(document.total, document.currency),
    })


@admin_required
def admin_download(request, pk):
    document = get_object_or_404(Document, pk=pk)
    return _serve_pdf(document, request, user=request.user)


@admin_required
def admin_regenerate(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if request.method != 'POST':
        return redirect('documents:admin_detail', pk=document.pk)
    generate_document_pdf(document, actor=request.user)
    messages.success(request, f'PDF regenerated for {document.reference}.')
    return redirect('documents:admin_detail', pk=document.pk)


@admin_required
def admin_send(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if request.method != 'POST':
        return redirect('documents:admin_detail', pk=document.pk)
    if document.status == Document.STATUS_CANCELLED:
        messages.error(request, 'Cancelled documents cannot be sent.')
        return redirect('documents:admin_detail', pk=document.pk)

    sent = send_document(document, actor=request.user, request=request)
    if sent:
        messages.success(request, f'Document emailed to {document.client_email}.')
    else:
        messages.error(
            request,
            'The email could not be delivered. Check the email configuration and the client address.',
        )
    return redirect('documents:admin_detail', pk=document.pk)


@admin_required
def admin_mark_paid(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if request.method == 'POST':
        mark_paid(document, actor=request.user, request=request)
        messages.success(request, 'Document marked as paid.')
    return redirect('documents:admin_detail', pk=document.pk)


@admin_required
def admin_cancel(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if request.method == 'POST':
        cancel_document(document, actor=request.user, request=request)
        messages.success(request, 'Document cancelled.')
    return redirect('documents:admin_detail', pk=document.pk)


@admin_required
def settings_view(request):
    cfg = DocumentSettings.load()

    if request.method == 'POST' and request.POST.get('action') in {'remove_signature', 'remove_stamp'}:
        field_name = 'signature_image' if request.POST['action'] == 'remove_signature' else 'stamp_image'
        field = getattr(cfg, field_name)
        if field:
            field.delete(save=False)
            setattr(cfg, field_name, '')
            cfg.updated_by = request.user
            cfg.save()
        messages.success(request, 'Asset removed.')
        return redirect('documents:settings')

    if request.method == 'POST':
        form = DocumentSettingsForm(request.POST, request.FILES, instance=cfg)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.updated_by = request.user
            saved.save()
            messages.success(request, 'Company document settings saved.')
            return redirect('documents:settings')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = DocumentSettingsForm(instance=cfg)

    return render(request, 'documents/settings.html', {
        'form': form,
        'settings': cfg,
    })


# -------------------------------------------------------------------- client
@login_required
def client_list(request):
    if is_admin(request.user):
        return redirect('documents:admin_list')
    refresh_overdue_documents()

    query = Q(status__in=CLIENT_VISIBLE_STATUSES)
    ownership = Q(client_user=request.user) | Q(customer__user=request.user)
    if request.user.email:
        ownership |= Q(client_email__iexact=request.user.email)
    documents = (
        Document.objects.filter(query)
        .filter(ownership)
        .select_related('doc_type')
        .distinct()
    )

    status = (request.GET.get('status') or '').strip()
    if status:
        documents = documents.filter(status=status)

    return render(request, 'documents/client_list.html', {
        'documents': documents,
        'status': status,
        'status_choices': [
            (value, label) for value, label in Document.STATUS_CHOICES
            if value in CLIENT_VISIBLE_STATUSES
        ],
        'settings': DocumentSettings.load(),
        'summary': {
            'received': documents.count(),
            'awaiting_signature': documents.filter(
                doc_type__requires_signature=True,
                status__in=[Document.STATUS_SENT, Document.STATUS_VIEWED],
            ).count(),
            'to_review': documents.filter(
                doc_type__requires_acceptance=True,
                status__in=[Document.STATUS_SENT, Document.STATUS_VIEWED],
            ).count(),
        },
    })


@login_required
def client_detail(request, pk):
    document = _get_client_document(request, pk)
    _mark_viewed(document, request, user=request.user)
    can_respond = (
        document.doc_type.requires_acceptance
        and document.status in {Document.STATUS_SENT, Document.STATUS_VIEWED}
    )
    can_sign = (
        document.doc_type.requires_signature
        and not document.is_client_signed
        and document.status in {Document.STATUS_SENT, Document.STATUS_VIEWED, Document.STATUS_ACCEPTED}
    )
    return render(request, 'documents/client_detail.html', {
        'document': document,
        'items': document.items.all(),
        'settings': DocumentSettings.load(),
        'events': document.events.filter(
            event__in=[
                DocumentEvent.EVENT_SENT, DocumentEvent.EVENT_VIEWED,
                DocumentEvent.EVENT_ACCEPTED, DocumentEvent.EVENT_REJECTED,
                DocumentEvent.EVENT_SIGNED, DocumentEvent.EVENT_PAID,
                DocumentEvent.EVENT_OVERDUE,
            ],
        )[:30],
        'can_respond': can_respond,
        'can_sign': can_sign,
        'signature': document.latest_signature,
        'amount': money(document.total, document.currency),
    })


@login_required
def client_download(request, pk):
    document = _get_client_document(request, pk)
    _mark_viewed(document, request, user=request.user)
    return _serve_pdf(document, request, user=request.user)


@login_required
def client_accept(request, pk):
    document = _get_client_document(request, pk)
    if request.method != 'POST':
        return redirect('documents:client_detail', pk=document.pk)
    if not (
        document.doc_type.requires_acceptance
        and document.status in {Document.STATUS_SENT, Document.STATUS_VIEWED}
    ):
        messages.error(request, 'This document cannot be accepted in its current state.')
        return redirect('documents:client_detail', pk=document.pk)
    accept_document(
        document,
        actor=request.user,
        request=request,
        name=request.user.get_full_name() or request.user.get_username(),
    )
    messages.success(request, f'{document.doc_type.name} accepted.')
    return redirect('documents:client_detail', pk=document.pk)


@login_required
def client_reject(request, pk):
    document = _get_client_document(request, pk)
    if request.method != 'POST':
        return redirect('documents:client_detail', pk=document.pk)
    if not (
        document.doc_type.requires_acceptance
        and document.status in {Document.STATUS_SENT, Document.STATUS_VIEWED}
    ):
        messages.error(request, 'This document cannot be rejected in its current state.')
        return redirect('documents:client_detail', pk=document.pk)
    reject_document(
        document,
        actor=request.user,
        request=request,
        reason=request.POST.get('reason', ''),
    )
    messages.success(request, 'Your response has been recorded.')
    return redirect('documents:client_detail', pk=document.pk)


@login_required
def client_sign(request, pk):
    document = _get_client_document(request, pk)
    if not document.doc_type.requires_signature:
        messages.error(request, 'This document does not require a signature.')
        return redirect('documents:client_detail', pk=document.pk)
    if document.is_client_signed:
        messages.info(request, 'This document is already signed.')
        return redirect('documents:client_detail', pk=document.pk)
    if document.status not in {
        Document.STATUS_SENT, Document.STATUS_VIEWED, Document.STATUS_ACCEPTED,
    }:
        messages.error(request, 'This document cannot be signed in its current state.')
        return redirect('documents:client_detail', pk=document.pk)

    if request.method == 'POST':
        form = ClientSignatureForm(request.POST, request.FILES)
        if form.is_valid():
            email = form.cleaned_data['signer_email']
            allowed = {document.client_email.lower(), (request.user.email or '').lower()}
            if email.lower() not in allowed:
                form.add_error('signer_email', 'Use the email address this document was sent to.')
            else:
                apply_client_signature(
                    document,
                    signer_name=form.cleaned_data['signer_name'],
                    signer_email=email,
                    signer_role=form.cleaned_data.get('signer_role', ''),
                    typed_signature=form.cleaned_data.get('typed_signature', ''),
                    signature_image=form.cleaned_data.get('signature_image'),
                    consent_text=str(form.fields['consent'].label),
                    request=request,
                    actor_user=request.user,
                )
                messages.success(request, 'Thank you. Your signature has been recorded.')
                return redirect('documents:client_detail', pk=document.pk)
        messages.error(request, 'Please complete the signature form.')
    else:
        form = ClientSignatureForm(initial={
            'signer_name': request.user.get_full_name() or request.user.get_username(),
            'signer_email': document.client_email,
        })

    return render(request, 'documents/sign.html', {
        'document': document,
        'form': form,
        'settings': DocumentSettings.load(),
        'is_public': False,
    })


# ---------------------------------------------------------------- token links
def _load_token_document(request, token):
    try:
        return read_token(token), None
    except TokenError as exc:
        return None, render(request, 'documents/link_error.html', {
            'message': str(exc),
            'settings': DocumentSettings.load(),
        }, status=410)


def public_view(request, token):
    document, error = _load_token_document(request, token)
    if error:
        return error
    _mark_viewed(document, request)
    can_respond = (
        document.doc_type.requires_acceptance
        and document.status in {Document.STATUS_SENT, Document.STATUS_VIEWED}
    )
    can_sign = (
        document.doc_type.requires_signature
        and not document.is_client_signed
        and document.status in {Document.STATUS_SENT, Document.STATUS_VIEWED, Document.STATUS_ACCEPTED}
    )
    return render(request, 'documents/public_view.html', {
        'document': document,
        'items': document.items.all(),
        'settings': DocumentSettings.load(),
        'token': token,
        'can_respond': can_respond,
        'can_sign': can_sign,
        'signature': document.latest_signature,
        'amount': money(document.total, document.currency),
    })


def public_download(request, token):
    document, error = _load_token_document(request, token)
    if error:
        return error
    _mark_viewed(document, request)
    return _serve_pdf(document, request)


def _token_email_ok(document, email):
    return bool(email) and email.strip().lower() == (document.client_email or '').strip().lower()


def public_accept(request, token):
    document, error = _load_token_document(request, token)
    if error:
        return error
    if request.method != 'POST':
        return redirect('documents:public_view', token=token)
    if not (
        document.doc_type.requires_acceptance
        and document.status in {Document.STATUS_SENT, Document.STATUS_VIEWED}
    ):
        messages.error(request, 'This document cannot be accepted in its current state.')
        return redirect('documents:public_view', token=token)
    email = request.POST.get('email', '')
    if not _token_email_ok(document, email):
        messages.error(request, 'Enter the email address this document was sent to.')
        return redirect('documents:public_view', token=token)
    accept_document(document, request=request, name=request.POST.get('name', '') or document.client_name)
    messages.success(request, f'{document.doc_type.name} accepted.')
    return redirect('documents:public_view', token=token)


def public_reject(request, token):
    document, error = _load_token_document(request, token)
    if error:
        return error
    if request.method != 'POST':
        return redirect('documents:public_view', token=token)
    if not (
        document.doc_type.requires_acceptance
        and document.status in {Document.STATUS_SENT, Document.STATUS_VIEWED}
    ):
        messages.error(request, 'This document cannot be rejected in its current state.')
        return redirect('documents:public_view', token=token)
    email = request.POST.get('email', '')
    if not _token_email_ok(document, email):
        messages.error(request, 'Enter the email address this document was sent to.')
        return redirect('documents:public_view', token=token)
    reject_document(document, request=request, reason=request.POST.get('reason', ''))
    messages.success(request, 'Your response has been recorded.')
    return redirect('documents:public_view', token=token)


def public_sign(request, token):
    document, error = _load_token_document(request, token)
    if error:
        return error
    if not document.doc_type.requires_signature:
        messages.error(request, 'This document does not require a signature.')
        return redirect('documents:public_view', token=token)
    if document.is_client_signed:
        messages.info(request, 'This document is already signed.')
        return redirect('documents:public_view', token=token)
    if document.status not in {
        Document.STATUS_SENT, Document.STATUS_VIEWED, Document.STATUS_ACCEPTED,
    }:
        messages.error(request, 'This document cannot be signed in its current state.')
        return redirect('documents:public_view', token=token)

    if request.method == 'POST':
        form = ClientSignatureForm(request.POST, request.FILES)
        if form.is_valid():
            email = form.cleaned_data['signer_email']
            if not _token_email_ok(document, email):
                form.add_error('signer_email', 'Use the email address this document was sent to.')
            else:
                apply_client_signature(
                    document,
                    signer_name=form.cleaned_data['signer_name'],
                    signer_email=email,
                    signer_role=form.cleaned_data.get('signer_role', ''),
                    typed_signature=form.cleaned_data.get('typed_signature', ''),
                    signature_image=form.cleaned_data.get('signature_image'),
                    consent_text=str(form.fields['consent'].label),
                    request=request,
                )
                messages.success(request, 'Thank you. Your signature has been recorded.')
                return redirect('documents:public_view', token=token)
        messages.error(request, 'Please complete the signature form.')
    else:
        form = ClientSignatureForm(initial={
            'signer_name': document.client_name,
            'signer_email': document.client_email,
        })

    return render(request, 'documents/sign.html', {
        'document': document,
        'form': form,
        'settings': DocumentSettings.load(),
        'token': token,
        'is_public': True,
    })
