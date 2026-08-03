"""Views for the enterprise Branding Service (wizard + staff dashboard)."""
import json
import os
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.db.models import Avg, Count, Q, Case, When, IntegerField, F, Value, Sum
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    BrandingRequestForm,
    DesignConceptForm,
    ConceptAnnotationForm,
    ConceptFeedbackForm,
    ConceptStickyNoteForm,
    ConceptRefinementForm,
    ConceptRefinementIterationForm,
    ConceptPresentationSessionForm,
    CollectionTemplateForm,
)
from .utils import (
    TIMEOUT_COLLECTIONS,
    TIMEOUT_DASHBOARD,
    TIMEOUT_DESIGNERS,
    TIMEOUT_KANBAN,
    cache_get_or_set,
    cache_set,
    collections_key,
    dashboard_stats_key,
    designer_detail_key,
    designers_key,
    invalidate_after_request_mutation,
    invalidate_after_status_change,
    invalidate_collections,
    invalidate_designer_detail,
    invalidate_kanban,
    invalidate_team_overview,
    kanban_key,
    team_overview_key,
)
from .decorators import rate_limit
from .roles import get_role_dashboard_url, designer_required, supervisor_required, staff_required
from .models import (
    ASSET_TYPES,
    AdobeAsset,
    AdobeConnection,
    AssetOrganizerItem,
    BRAND_VALUES,
    BrandGuidelineCheck,
    COLLECTION_CATEGORIES,
    COMMENT_TAGS,
    CURRENT_BRANDING_CHOICES,
    WORKFLOW_STAGES,
    ProjectWorkflow,
    WorkflowStageLog,
    ClientQuestion,
    FeedbackItem,
    DesignIteration,
    DecisionLog,
    CommunicationEntry,
    DesignConcept,
    ConceptImage,
    ConceptDecisionTrail,
    ConceptDecision,
    ConceptAnnotation,
    ConceptElementRating,
    ConceptFeedback,
    ConceptStickyNote,
    ConceptRefinement,
    ConceptRefinementIteration,
    WidgetDefinition,
    WIDGET_TYPES,
    DASHBOARD_LAYOUTS,
    COLLECTION_TEMPLATE_TYPES,
    RATING_ELEMENTS,
    CalendarConnection,
    CalendarEvent,
    ColorPalette,
    CritiqueTemplate,
    DesignComment,
    DesignDraft,
    DesignHandoff,
    DesignNote,
    DesignResource,
    DesignTemplate,
    DesignerNote,
    DraftVersion,
    FigmaComment,
    FigmaConnection,
    FigmaDesign,
    FeedbackRequest,
    FeedbackQuestion,
    FontEntry,
    HandoffDeliverable,
    HandoffNote,
    INDUSTRY_CHOICES,
    KB_CATEGORIES,
    KnowledgeArticle,
    NOTIFICATION_TYPES,
    PeerReview,
    PeerReviewFeedback,
    PREFERRED_COLORS,
    PRIORITY_CHOICES,
    QUALITY_CHECKLIST,
    RESOURCE_CATEGORIES,
    REVIEW_STATUS,
    SHOWCASE_CATEGORIES,
    SlackConnection,
    SlackMessage,
    STATUS_CHOICES,
    TEMPLATE_CATEGORIES,
    TIME_TRACK_PHASES,
    NOTE_CATEGORIES,
    BrandCollection,
    BrandingAsset,
    BrandingAssetVersion,
    BrandingClientProfile,
    BrandingFeedback,
    BrandingMessage,
    BrandingNotification,
    BrandingRequest,
    BrandingTimeline,
    ProjectReview,
    ShowcaseProject,
    TimeEntry,
)

User = get_user_model()

WIZARD_STEP_COUNT = 4
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50MB
SITE_URL = getattr(settings, 'SITE_URL', 'https://onwebapp.com')

COLOR_SWATCHES = {
    'blue': '#3b82f6',
    'orange': '#f97316',
    'green': '#22c55e',
    'red': '#ef4444',
    'purple': '#8b5cf6',
    'black': '#0f172a',
    'white': '#f8fafc',
    'gray': '#94a3b8',
    'none': None,
}

# Statuses surfaced as quick-filter cards on the dashboard.
BRANDING_CARD_STATUSES = [
    ('PENDING_REVIEW', 'Pending', 'fa-clock'),
    ('IN_REVIEW', 'In Review', 'fa-magnifying-glass'),
    ('ASSIGNED', 'Assigned', 'fa-user-check'),
    ('WAITING_CLIENT', 'Waiting Client', 'fa-user-clock'),
    ('DESIGNING', 'Designing', 'fa-palette'),
    ('REVISION', 'Revision', 'fa-rotate-left'),
    ('APPROVED', 'Approved', 'fa-circle-check'),
    ('COMPLETED', 'Completed', 'fa-truck-fast'),
]

# Kanban board columns (ARCHIVED excluded from the board).
KANBAN_COLUMNS = [
    ('PENDING_REVIEW', 'Pending', 'fa-hourglass-half'),
    ('IN_REVIEW', 'Review', 'fa-magnifying-glass'),
    ('ASSIGNED', 'Assigned', 'fa-user-check'),
    ('DESIGNING', 'Designing', 'fa-palette'),
    ('WAITING_CLIENT', 'Waiting Client', 'fa-user-clock'),
    ('REVISION', 'Revision', 'fa-rotate-left'),
    ('COMPLETED', 'Completed', 'fa-circle-check'),
]

# Milestone stepper shown on the request detail page.
TIMELINE_STAGES = [
    ('PENDING_REVIEW', 'Pending', 'fa-hourglass-half'),
    ('IN_REVIEW', 'Reviewed', 'fa-magnifying-glass'),
    ('ASSIGNED', 'Assigned', 'fa-user-check'),
    ('DESIGNING', 'Design Started', 'fa-palette'),
    ('WAITING_CLIENT', 'Client Review', 'fa-user-clock'),
    ('REVISION', 'Revision', 'fa-rotate-left'),
    ('APPROVED', 'Approved', 'fa-circle-check'),
    ('COMPLETED', 'Delivered', 'fa-truck-fast'),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_create_draft(user):
    draft = BrandingRequest.objects.filter(user=user, status='DRAFT').order_by('-updated_at').first()
    if draft:
        return draft
    draft = BrandingRequest.objects.create(user=user, status='DRAFT')
    draft.log('CREATED', 'Branding request started', actor=user)
    return draft


def _apply_step_data(draft, step, src):
    """Persist the given step's fields from a POST QueryDict or plain dict."""
    def getlist(key):
        return src.getlist(key) if hasattr(src, 'getlist') else (src.get(key) or [])

    def get(key, default=''):
        return (src.get(key) or default).strip()

    if step == 1:
        draft.company_name = get('company_name')
        draft.industry = get('industry')
        draft.website = get('website')
        draft.country = get('country')
        draft.business_description = get('business_description')
        # GDPR consent
        draft.consent_data_processing = src.get('consent_data_processing') == 'on'
        draft.consent_analytics = src.get('consent_analytics') == 'on'
        draft.consent_marketing = src.get('consent_marketing') == 'on'
        draft.consent_third_party = src.get('consent_third_party') == 'on'
        if draft.consent_data_processing and not draft.consent_timestamp:
            draft.consent_timestamp = timezone.now()
            # Record consent history
            from .gdpr import record_consent
            for ct, granted in [
                ('data_processing', draft.consent_data_processing),
                ('analytics', draft.consent_analytics),
                ('marketing', draft.consent_marketing),
                ('third_party', draft.consent_third_party),
            ]:
                if granted:
                    record_consent(
                        draft.user, ct, 'granted',
                        request_obj=draft,
                    )
    elif step == 2:
        draft.company_description = get('company_description')
        draft.target_audience = get('target_audience')
        draft.brand_values = getlist('brand_values')
        draft.preferred_colors = getlist('preferred_colors')
        draft.current_branding = getlist('current_branding')
    elif step == 3:
        draft.additional_notes = get('additional_notes')
    elif step == 4:
        collection_id = get('collection')
        draft.collection = None
        if collection_id:
            draft.collection = BrandCollection.objects.filter(
                pk=collection_id, is_active=True
            ).first()
    draft.current_step = step


def _validate_step(draft, step, for_submit=False):
    """Return a list of validation errors for a step. Empty list == valid."""
    errors = []
    if step == 1 or for_submit:
        if not draft.company_name:
            errors.append('Company name is required.')
        if not draft.industry:
            errors.append('Please select an industry.')
        if not draft.consent_data_processing:
            errors.append('You must consent to data processing to continue.')
    if step == 4 or for_submit:
        if not draft.collection:
            errors.append('Please choose a brand collection to continue.')
    return errors


def _build_wizard_context(request, draft, step, errors=None):
    collections = cache_get_or_set(
        collections_key(),
        lambda: list(BrandCollection.objects.filter(is_active=True)),
        TIMEOUT_COLLECTIONS,
    )
    return {
        'draft': draft,
        'step': step,
        'wizard_steps': range(1, WIZARD_STEP_COUNT + 1),
        'step_labels': ['Company Information', 'Brand Identity', 'Upload Assets', 'Brand Collection'],
        'step_icon': ['fa-building', 'fa-brush', 'fa-cloud-arrow-up', 'fa-folder-open'][step - 1],
        'step_title': [
            'Company Information', 'Brand Identity', 'Upload Assets', 'Choose Your Brand Collection',
        ][step - 1],
        'step_subtitle': [
            'Tell us about your business so we can tailor a brand.',
            'Help us understand the personality your brand should express.',
            'Share existing branding, logos and inspiration images.',
            'Select the collection that best matches your vision.',
        ][step - 1],
        'errors': errors or [],
        'industries': INDUSTRY_CHOICES,
        'brand_values': BRAND_VALUES,
        'current_branding_choices': CURRENT_BRANDING_CHOICES,
        'categories': COLLECTION_CATEGORIES,
        'collections': collections,
        'assets': draft.assets.all(),
        'asset_types': ASSET_TYPES,
        'max_file_size_mb': MAX_FILE_SIZE_BYTES // (1024 * 1024),
        'is_partial': request.GET.get('partial') == '1',
        'gdpr': {
            'consent_data_processing': draft.consent_data_processing,
            'consent_analytics': draft.consent_analytics,
            'consent_marketing': draft.consent_marketing,
            'consent_third_party': draft.consent_third_party,
            'consent_timestamp': draft.consent_timestamp,
            'retention_period': draft.retention_period,
        },
    }


@rate_limit('wizard_submit')
def _finalize(request, draft):
    draft.status = 'PENDING_REVIEW'
    draft.current_step = WIZARD_STEP_COUNT
    draft.save(update_fields=['status', 'current_step', 'updated_at'])
    draft.log(
        'STATUS_CHANGE',
        'Request submitted',
        'Status changed to Pending Review.',
        actor=request.user,
    )
    try:
        from users.models import ActivityLog
        ActivityLog.objects.create(
            user=request.user,
            action='Submitted branding request',
            metadata={'request_number': draft.request_number},
        )
    except Exception:
        pass
    # Notify all staff about the new request.
    invalidate_after_request_mutation()
    for staff in User.objects.filter(is_staff=True):
        _notify(
            staff,
            draft,
            'NEW_REQUEST',
            f"{draft.company_name} submitted {draft.request_number} and is awaiting review.",
            email_subject=f"[OnWebApp Branding] New request {draft.request_number}",
        )
    return redirect('branding:submitted', request_number=draft.request_number)


def _detect_asset_type(name, content_type):
    name = (name or '').lower()
    ctype = (content_type or '').lower()
    if ctype.startswith('image/') or name.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')):
        if 'logo' in name:
            return 'logo'
        return 'image'
    if name.endswith(('.svg', '.ai')):
        return 'logo'
    if 'guideline' in name:
        return 'brand_guidelines'
    if name.endswith(('.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx')):
        return 'document'
    if name.endswith(('.zip', '.rar', '.7z')):
        return 'archive'
    return 'other'


# ---------------------------------------------------------------------------
# Public wizard
# ---------------------------------------------------------------------------

@login_required
def wizard(request):
    draft = _get_or_create_draft(request.user)
    return redirect('branding:wizard_step', step=draft.current_step)


@login_required
def wizard_step(request, step):
    try:
        step = int(step)
    except (TypeError, ValueError):
        step = 1
    step = max(1, min(step, WIZARD_STEP_COUNT))

    draft = _get_or_create_draft(request.user)

    if request.method == 'POST':
        action = request.POST.get('action', 'next')
        _apply_step_data(draft, step, request.POST)

        if action == 'prev':
            draft.save()
            draft.current_step = max(1, step - 1)
            draft.save(update_fields=['current_step', 'updated_at'])
            if _is_ajax(request):
                return JsonResponse({'ok': True, 'redirect_url': reverse('branding:wizard_step', args=[draft.current_step])})
            return redirect('branding:wizard_step', step=draft.current_step)

        errors = _validate_step(draft, step, for_submit=(action == 'submit'))
        if errors:
            # Discard the invalid step data so previously saved fields are kept.
            draft.refresh_from_db()
            if _is_ajax(request):
                return JsonResponse({'ok': False, 'errors': errors})
            context = _build_wizard_context(request, draft, step, errors=errors)
            return render(request, 'branding/wizard.html', context)

        draft.save()

        if action == 'submit':
            if _is_ajax(request):
                return JsonResponse({'ok': True, 'redirect_url': reverse('branding:submitted', args=[draft.request_number])})
            return _finalize(request, draft)

        draft.current_step = min(WIZARD_STEP_COUNT, step + 1)
        draft.save(update_fields=['current_step', 'updated_at'])
        if _is_ajax(request):
            return JsonResponse({'ok': True, 'redirect_url': reverse('branding:wizard_step', args=[draft.current_step])})
        return redirect('branding:wizard_step', step=draft.current_step)

    # GET — navigate to the requested step
    draft.current_step = step
    draft.save(update_fields=['current_step', 'updated_at'])
    context = _build_wizard_context(request, draft, step)
    template = 'branding/partials/wizard_step.html' if context['is_partial'] else 'branding/wizard.html'
    return render(request, template, context)


@login_required
@require_POST
def wizard_autosave(request):
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    step = int(data.get('step', 1))
    draft = _get_or_create_draft(request.user)
    _apply_step_data(draft, step, data.get('data', {}))
    draft.save()
    return JsonResponse({'status': 'saved', 'step': step})


@login_required
@require_POST
@rate_limit('file_upload')
def upload_file(request):
    draft = _get_or_create_draft(request.user)
    file = request.FILES.get('file')
    if not file:
        return JsonResponse({'error': 'No file provided'}, status=400)

    # Detect asset type first (needed for size/MIME validation)
    asset_type = _detect_asset_type(file.name, file.content_type or '')

    # --- File security validation ---
    from .file_security import validate_upload, sanitize_filename

    is_valid, errors, metadata = validate_upload(file, asset_type, request.user)

    if not is_valid:
        return JsonResponse({
            'error': 'File rejected',
            'details': errors,
        }, status=400)

    # Use sanitized name and detected MIME type
    asset = BrandingAsset.objects.create(
        request=draft,
        file=file,
        asset_type=asset_type,
        original_name=file.name,
        content_type=file.content_type or '',
        detected_mime=metadata['detected_mime'],
        file_hash=metadata['file_hash'],
        sanitized_name=metadata['sanitized_name'],
        scan_status=BrandingAsset.SCAN_PENDING,
        size=metadata['file_size'],
    )

    # Queue async virus scan if ClamAV is enabled
    if getattr(settings, 'CLAMAV_ENABLED', False):
        try:
            from .tasks import scan_asset_for_virus
            scan_asset_for_virus.delay(asset.pk)
        except Exception:
            pass  # Non-critical; sync scan already ran in validate_upload

    # Log the successful upload
    from .file_security import log_upload_success
    log_upload_success(
        request.user,
        file.name,
        metadata['file_hash'],
        detected_mime=metadata['detected_mime'],
        request_meta=request.META,
    )

    draft.log('UPLOAD', f'Uploaded {metadata["sanitized_name"]}', actor=request.user)
    return JsonResponse({
        'ok': True,
        'id': asset.pk,
        'name': asset.original_name,
        'sanitized_name': asset.sanitized_name,
        'size': asset.size_display,
        'type': asset.get_asset_type_display(),
        'mime': asset.detected_mime,
        'hash': asset.file_hash[:16],
        'is_image': asset.is_image,
        'url': asset.file.url,
    })


@login_required
@require_POST
def delete_asset(request, asset_id):
    asset = get_object_or_404(BrandingAsset, id=asset_id)
    if asset.request.user != request.user and not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    name = asset.original_name or asset.file.name
    for version in asset.versions.all():
        version.file.delete(save=False)
    asset.versions.all().delete()
    asset.file.delete(save=False)
    asset.delete()
    asset.request.log('FILE_UPDATE', f'Deleted {name}', actor=request.user)
    return JsonResponse({'ok': True, 'name': name})


@staff_member_required
def download_asset(request, asset_id):
    asset = get_object_or_404(BrandingAsset, id=asset_id)
    if not asset.file:
        raise Http404
    response = FileResponse(
        asset.file.open('rb'),
        as_attachment=True,
        filename=asset.original_name or asset.file.name,
    )
    return response


@staff_member_required
def download_asset_version(request, version_id):
    version = get_object_or_404(BrandingAssetVersion, id=version_id)
    if not version.file:
        raise Http404
    response = FileResponse(
        version.file.open('rb'),
        as_attachment=True,
        filename=f"v{version.version_number}_{version.original_name or version.file.name}",
    )
    return response


@staff_member_required
@require_POST
def replace_asset(request, asset_id):
    """Replace an asset file; the previous file becomes a version snapshot."""
    asset = get_object_or_404(BrandingAsset, id=asset_id)
    file = request.FILES.get('file')
    if not file:
        if _is_ajax(request):
            return JsonResponse({'error': 'No file provided'}, status=400)
        messages.error(request, 'No file provided.')
        return redirect('branding:request_detail', pk=asset.request.pk)
    if file.size > MAX_FILE_SIZE_BYTES:
        if _is_ajax(request):
            return JsonResponse(
                {'error': f'File exceeds the {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB limit.'},
                status=400,
            )
        messages.error(request, 'File exceeds the 50MB limit.')
        return redirect('branding:request_detail', pk=asset.request.pk)
    note = request.POST.get('note', '').strip()

    if asset.file:
        current_version = asset.versions.filter(version_number__gte=1).first()
        next_number = (current_version.version_number + 1) if current_version else 1
        BrandingAssetVersion.objects.create(
            asset=asset,
            file=asset.file,
            version_number=next_number,
            original_name=asset.original_name,
            content_type=asset.content_type,
            size=asset.size,
            note=note or 'Replaced by staff',
            uploaded_by=request.user,
        )

    asset.file = file
    asset.original_name = file.name
    asset.content_type = file.content_type or ''
    asset.size = file.size
    asset.save(update_fields=['file', 'original_name', 'content_type', 'size', 'uploaded_at'])
    asset.request.log(
        'FILE_UPDATE',
        f"Replaced {file.name}",
        note or f"New version of {file.name}",
        actor=request.user,
    )
    if _is_ajax(request):
        return JsonResponse({
            'ok': True,
            'id': asset.pk,
        'name': asset.original_name,
        'size': asset.size_display,
        'url': asset.file.url,
    })
    messages.success(request, f'File replaced: {asset.original_name}')
    return redirect('branding:request_detail', pk=asset.request.pk)


def submitted(request, request_number):
    req = get_object_or_404(BrandingRequest, request_number=request_number)
    if not request.user.is_authenticated or (
        req.user != request.user and not request.user.is_staff
    ):
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    return render(request, 'branding/submitted.html', {'branding_request': req})


@login_required
def my_requests(request):
    """Client dashboard: show all non-draft requests for the logged-in user."""
    qs = BrandingRequest.objects.filter(
        user=request.user,
    ).exclude(
        status='DRAFT',
    ).select_related('collection', 'designer').annotate(
        msg_count=Count('messages', distinct=True),
        unread_count=Count(
            'messages',
            filter=Q(messages__is_read_by_client=False) & ~Q(messages__sender=request.user),
            distinct=True,
        ),
    ).order_by('-created_at')

    # Filters
    status_filter = request.GET.get('status', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if status_filter:
        qs = qs.filter(status=status_filter)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    paginator = Paginator(qs, 10)
    page = paginator.get_page(request.GET.get('page'))

    # Status summary counts (for stat cards)
    status_counts = BrandingRequest.objects.filter(
        user=request.user,
    ).exclude(status='DRAFT').values('status').annotate(
        cnt=Count('id'),
    )
    counts = {item['status']: item['cnt'] for item in status_counts}
    total = sum(counts.values())

    return render(request, 'branding/my_requests.html', {
        'requests': page,
        'card_statuses': BRANDING_CARD_STATUSES,
        'status_counts': counts,
        'total_count': total,
        'current_status': status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': [s for s in STATUS_CHOICES if s[0] != 'DRAFT'],
    })


@login_required
def client_project_progress(request, pk):
    """Client-facing project progress tracking dashboard."""
    br = get_object_or_404(
        BrandingRequest.objects.select_related('collection', 'designer', 'user'),
        pk=pk,
        user=request.user,
    )

    now = timezone.now()
    today = now.date()

    workflow = ProjectWorkflow.objects.filter(request=br).first()
    stage_logs = WorkflowStageLog.objects.filter(
        request=br
    ).select_related('moved_by').order_by('-moved_at')[:20] if workflow else []

    questions = ClientQuestion.objects.filter(
        request=br, is_answered=True
    ).order_by('-answered_at') if workflow else []
    unanswered = ClientQuestion.objects.filter(
        request=br, is_answered=False
    ).count() if workflow else 0

    feedback_items = FeedbackItem.objects.filter(
        request=br
    ).order_by('-created_at')[:10] if workflow else []
    feedback_pending = FeedbackItem.objects.filter(
        request=br, status__in=['new', 'in_review']
    ).count() if workflow else 0
    feedback_resolved = FeedbackItem.objects.filter(
        request=br, status='resolved'
    ).count() if workflow else 0

    iterations = DesignIteration.objects.filter(
        request=br
    ).order_by('-version_number') if workflow else []

    decisions = DecisionLog.objects.filter(
        request=br
    ).order_by('-created_at')[:10] if workflow else []

    communications = CommunicationEntry.objects.filter(
        request=br
    ).select_related('author').order_by('-created_at')[:20] if workflow else []

    concepts = DesignConcept.objects.filter(
        request=br
    ).order_by('-created_at')[:5]

    # Days remaining
    days_remaining = None
    if br.estimated_delivery_date:
        delta = br.estimated_delivery_date - today
        days_remaining = delta.days

    # Unread messages
    unread_messages = BrandingMessage.objects.filter(
        request=br, is_read_by_client=False
    ).exclude(sender=request.user).count()

    return render(request, 'branding/client_project_progress.html', {
        'br': br,
        'workflow': workflow,
        'stage_logs': stage_logs,
        'questions': questions,
        'unanswered': unanswered,
        'feedback_items': feedback_items,
        'feedback_pending': feedback_pending,
        'feedback_resolved': feedback_resolved,
        'iterations': iterations,
        'decisions': decisions,
        'communications': communications,
        'concepts': concepts,
        'stages': WORKFLOW_STAGES,
        'days_remaining': days_remaining,
        'unread_messages': unread_messages,
        'today': today,
        'page_title': f'Project Progress - {br.request_number}',
    })


@login_required
def client_messages(request, pk):
    """Client-facing messages page for a specific request."""
    br = get_object_or_404(
        BrandingRequest.objects.select_related('collection', 'designer', 'user'),
        pk=pk,
        user=request.user,
    )

    chat_messages = BrandingMessage.objects.filter(
        request=br
    ).select_related('sender', 'parent').order_by('created_at')

    # Mark unread messages as read by client
    unread = chat_messages.filter(is_read_by_client=False).exclude(sender=request.user)
    for msg in unread:
        msg.mark_read(request.user)

    return render(request, 'branding/client_messages.html', {
        'br': br,
        'chat_messages': chat_messages,
        'page_title': f'Messages - {br.request_number}',
    })


def landing(request):
    if request.user.is_authenticated and request.user.is_staff:
        dashboard_url = get_role_dashboard_url(request.user)
        if dashboard_url:
            return redirect(dashboard_url)
    featured = BrandCollection.objects.filter(is_active=True)[:6]
    return render(request, 'branding/landing.html', {
        'featured_collections': featured,
        'categories': COLLECTION_CATEGORIES,
    })


@login_required
def client_profile(request):
    """Client profile: preferences, favorite collections, and saved briefs."""
    profile, _ = BrandingClientProfile.objects.get_or_create(user=request.user)
    collections = BrandCollection.objects.filter(is_active=True).order_by('category', 'name')
    drafts = BrandingRequest.objects.filter(
        user=request.user, status='DRAFT'
    ).order_by('-updated_at')

    if request.method == 'POST':
        action = request.POST.get('action', 'save_profile')

        if action == 'save_profile':
            profile.default_industry = request.POST.get('default_industry', '').strip()
            profile.default_country = request.POST.get('default_country', '').strip()

            # Notification preferences
            profile.notification_preferences = {
                'email_on_status': request.POST.get('email_on_status') == 'on',
                'email_on_message': request.POST.get('email_on_message') == 'on',
                'email_on_assignment': request.POST.get('email_on_assignment') == 'on',
                'email_marketing': request.POST.get('email_marketing') == 'on',
            }
            profile.save()
            messages.success(request, 'Profile updated successfully.')

        elif action == 'toggle_favorite':
            coll_id = request.POST.get('collection_id')
            if coll_id:
                try:
                    coll = BrandCollection.objects.get(pk=coll_id, is_active=True)
                    if profile.favorite_collections.filter(pk=coll.pk).exists():
                        profile.favorite_collections.remove(coll)
                    else:
                        profile.favorite_collections.add(coll)
                except BrandingRequest.DoesNotExist:
                    pass

        elif action == 'delete_brief':
            try:
                idx = int(request.POST.get('brief_index', -1))
                profile.remove_saved_brief(idx)
                messages.success(request, 'Saved brief deleted.')
            except (ValueError, IndexError):
                pass

        if _is_ajax(request):
            return JsonResponse({'ok': True})

        return redirect('branding:client_profile')

    favorite_ids = list(profile.favorite_collections.values_list('pk', flat=True))

    # Stats
    total_requests = BrandingRequest.objects.filter(
        user=request.user
    ).exclude(status='DRAFT').count()
    completed_requests = BrandingRequest.objects.filter(
        user=request.user, status='COMPLETED'
    ).count()

    return render(request, 'branding/client_profile.html', {
        'profile': profile,
        'collections': collections,
        'favorite_ids': favorite_ids,
        'drafts': drafts,
        'industries': INDUSTRY_CHOICES,
        'total_requests': total_requests,
        'completed_requests': completed_requests,
    })


# ═══════════════════════════════════════════════════════════════════════════
# Concept Presentation System
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def concept_list(request, request_pk):
    """List all concepts for a branding request."""
    br = get_object_or_404(BrandingRequest, pk=request_pk)
    is_designer = br.designer == request.user
    is_client = br.user == request.user
    is_staff = request.user.is_staff or request.user.is_superuser

    if not (is_designer or is_client or is_staff):
        messages.error(request, 'You do not have access to this project.')
        return redirect('branding:dashboard')

    concepts = br.concepts.select_related('designer', 'designer__profile').prefetch_related(
        'supporting_images', 'element_ratings', 'annotations', 'feedbacks',
    )

    if is_designer:
        concepts = concepts.exclude(status='archived')

    concept_data = []
    for c in concepts:
        concept_data.append({
            'concept': c,
            'avg_rating': c.avg_rating(),
            'annotation_count': c.annotation_count(),
            'feedback_count': c.feedback_count(),
            'rating_breakdown': c.rating_breakdown(),
        })

    return render(request, 'branding/concepts/list.html', {
        'request_obj': br,
        'concepts': concept_data,
        'is_designer': is_designer,
        'is_client': is_client,
        'is_staff': is_staff,
        'page_title': f'Concepts - {br.request_number}',
    })


@login_required
def concept_detail(request, pk):
    """Detailed view of a single concept."""
    concept = get_object_or_404(
        DesignConcept.objects.select_related(
            'request', 'request__user', 'request__collection',
            'designer', 'designer__profile',
        ),
        pk=pk,
    )
    br = concept.request
    is_designer = br.designer == request.user
    is_client = br.user == request.user
    is_staff = request.user.is_staff or request.user.is_superuser

    if not (is_designer or is_client or is_staff):
        messages.error(request, 'You do not have access to this concept.')
        return redirect('branding:dashboard')

    annotations = concept.annotations.select_related('client', 'resolved_by').all()
    feedbacks = concept.feedbacks.select_related('client').all()
    refinements = concept.refinements.select_related('client').prefetch_related('iterations').all()
    decisions = concept.decisions.select_related('client').all()
    trail = concept.decision_trail.select_related('performed_by').all()
    images = concept.supporting_images.all()

    from django.db.models import Avg, Count
    element_avg_qs = concept.element_ratings.values('element').annotate(
        avg_score=Avg('score'), count=Count('id')
    )
    element_avg = {item['element']: item for item in element_avg_qs}

    my_rating = None
    if is_client:
        my_rating = concept.element_ratings.filter(client=request.user)

    return render(request, 'branding/concepts/detail.html', {
        'concept': concept,
        'request_obj': br,
        'annotations': annotations,
        'feedbacks': feedbacks,
        'refinements': refinements,
        'decisions': decisions,
        'trail': trail,
        'images': images,
        'element_avg': element_avg,
        'my_rating': my_rating,
        'is_designer': is_designer,
        'is_client': is_client,
        'is_staff': is_staff,
        'RATING_ELEMENTS': RATING_ELEMENTS,
        'page_title': concept.title,
    })


@designer_required
def concept_create(request, request_pk):
    """Create a new concept for a branding request."""
    br = get_object_or_404(BrandingRequest, pk=request_pk, designer=request.user)

    if request.method == 'POST':
        form = DesignConceptForm(request.POST, request.FILES)
        if form.is_valid():
            concept = form.save(commit=False)
            concept.request = br
            concept.designer = request.user
            concept.save()

            for img in request.FILES.getlist('additional_images'):
                ConceptImage.objects.create(
                    concept=concept,
                    image=img,
                    image_type=request.POST.get('image_type', 'mockup'),
                )

            ConceptDecisionTrail.objects.create(
                request=br, concept=concept,
                action='Concept created',
                details={'title': concept.title},
                performed_by=request.user,
            )

            messages.success(request, f'Concept "{concept.title}" created.')
            return redirect('branding:concept_detail', pk=concept.pk)
    else:
        form = DesignConceptForm()

    return render(request, 'branding/concepts/create.html', {
        'form': form,
        'request_obj': br,
        'page_title': f'New Concept - {br.request_number}',
    })


@designer_required
def concept_edit(request, pk):
    """Edit a concept."""
    concept = get_object_or_404(DesignConcept, pk=pk, designer=request.user)

    if request.method == 'POST':
        form = DesignConceptForm(request.POST, request.FILES, instance=concept)
        if form.is_valid():
            form.save()

            for img in request.FILES.getlist('additional_images'):
                ConceptImage.objects.create(
                    concept=concept,
                    image=img,
                    image_type=request.POST.get('image_type', 'mockup'),
                )

            messages.success(request, 'Concept updated.')
            return redirect('branding:concept_detail', pk=concept.pk)
    else:
        form = DesignConceptForm(instance=concept)

    return render(request, 'branding/concepts/edit.html', {
        'form': form,
        'concept': concept,
        'request_obj': concept.request,
        'page_title': f'Edit - {concept.title}',
    })


@designer_required
@require_POST
def concept_present(request, pk):
    """Mark concept as presented to client."""
    concept = get_object_or_404(DesignConcept, pk=pk, designer=request.user)
    concept.status = 'presented'
    concept.presented_at = timezone.now()
    concept.save(update_fields=['status', 'presented_at', 'updated_at'])

    ConceptDecisionTrail.objects.create(
        request=concept.request, concept=concept,
        action='Concept presented to client',
        performed_by=request.user,
    )

    messages.success(request, f'"{concept.title}" marked as presented.')
    return redirect('branding:concept_detail', pk=pk)


@designer_required
@require_POST
def concept_recommend(request, pk):
    """Designer marks a concept as their top pick."""
    concept = get_object_or_404(DesignConcept, pk=pk, designer=request.user)
    DesignConcept.objects.filter(
        request=concept.request, designer=request.user,
    ).update(is_designer_top_pick=False)
    concept.is_designer_top_pick = True
    concept.status = 'designer_recommended'
    concept.save(update_fields=['is_designer_top_pick', 'status', 'updated_at'])

    ConceptDecisionTrail.objects.create(
        request=concept.request, concept=concept,
        action='Designer recommended as top pick',
        performed_by=request.user,
    )

    messages.success(request, f'"{concept.title}" set as your recommendation.')
    return redirect('branding:concept_detail', pk=pk)


@designer_required
@require_POST
def concept_archive(request, pk):
    """Archive a concept."""
    concept = get_object_or_404(DesignConcept, pk=pk, designer=request.user)
    concept.status = 'archived'
    concept.save(update_fields=['status', 'updated_at'])
    messages.success(request, f'"{concept.title}" archived.')
    return redirect('branding:concept_list', request_pk=concept.request.pk)


@staff_member_required
@require_POST
def concept_delete(request, pk):
    """Supervisor/Admin: permanently delete a concept."""
    concept = get_object_or_404(DesignConcept, pk=pk)
    request_pk = concept.request.pk
    title = concept.title
    concept.delete()
    messages.success(request, f'Concept "{title}" deleted.')
    return redirect('branding:concept_list', request_pk=request_pk)


@designer_required
@require_POST
def concept_delete_image(request, pk, img_id):
    """Delete a supporting image."""
    concept = get_object_or_404(DesignConcept, pk=pk, designer=request.user)
    img = get_object_or_404(ConceptImage, pk=img_id, concept=concept)
    img.image.delete(save=False)
    img.delete()
    messages.success(request, 'Image deleted.')
    return redirect('branding:concept_edit', pk=pk)


# ── Client Review Actions ──────────────────────────────────────────────────

@login_required
@require_POST
def concept_mark_favorite(request, pk):
    """Client marks a concept as favorite."""
    concept = get_object_or_404(DesignConcept, pk=pk)
    br = concept.request
    if br.user != request.user and not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    DesignConcept.objects.filter(
        request=br, is_client_favorite=True,
    ).update(is_client_favorite=False, client_ranking=None)
    concept.is_client_favorite = True
    concept.status = 'client_selected'
    concept.decided_at = timezone.now()
    concept.save(update_fields=['is_client_favorite', 'status', 'decided_at', 'updated_at'])

    ConceptDecision.objects.create(
        concept=concept, client=request.user,
        decision='favorite',
    )
    ConceptDecisionTrail.objects.create(
        request=br, concept=concept,
        action='Client marked as favorite',
        performed_by=request.user,
    )

    return JsonResponse({'ok': True})


@login_required
@require_POST
def concept_rate_element(request, pk):
    """Rate an individual design element."""
    concept = get_object_or_404(DesignConcept, pk=pk)
    br = concept.request
    if br.user != request.user and not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    element = request.POST.get('element', '')
    score = request.POST.get('score', 0)
    try:
        score = int(score)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid score'}, status=400)

    if not (1 <= score <= 5):
        return JsonResponse({'error': 'Score must be 1-5'}, status=400)

    valid_elements = [e[0] for e in RATING_ELEMENTS]
    if element not in valid_elements:
        return JsonResponse({'error': 'Invalid element'}, status=400)

    rating, created = ConceptElementRating.objects.update_or_create(
        concept=concept, client=request.user, element=element,
        defaults={'score': score},
    )

    concept.total_ratings = concept.element_ratings.filter(client=request.user).count()
    concept.update_score()

    return JsonResponse({'ok': True, 'created': created})


@login_required
@require_POST
def concept_add_annotation(request, pk):
    """Add a click-to-annotate comment."""
    concept = get_object_or_404(DesignConcept, pk=pk)
    br = concept.request
    if br.user != request.user and not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    form = ConceptAnnotationForm(request.POST)
    if form.is_valid():
        annotation = form.save(commit=False)
        annotation.concept = concept
        annotation.client = request.user
        annotation.save()
        return JsonResponse({'ok': True, 'id': annotation.pk})

    return JsonResponse({'error': 'Invalid data'}, status=400)


@login_required
@require_POST
def concept_resolve_annotation(request, pk, ann_id):
    """Resolve an annotation."""
    concept = get_object_or_404(DesignConcept, pk=pk)
    annotation = get_object_or_404(ConceptAnnotation, pk=ann_id, concept=concept)
    annotation.is_resolved = True
    annotation.resolved_by = request.user
    annotation.resolved_at = timezone.now()
    annotation.save(update_fields=['is_resolved', 'resolved_by', 'resolved_at'])
    return JsonResponse({'ok': True})


@login_required
@require_POST
def concept_add_feedback(request, pk):
    """Add feedback to a concept."""
    concept = get_object_or_404(DesignConcept, pk=pk)
    br = concept.request
    if br.user != request.user and not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    form = ConceptFeedbackForm(request.POST)
    if form.is_valid():
        feedback = form.save(commit=False)
        feedback.concept = concept
        feedback.client = request.user
        feedback.save()
        return JsonResponse({'ok': True, 'id': feedback.pk})

    return JsonResponse({'errors': form.errors}, status=400)


@login_required
@require_POST
def concept_add_sticky_note(request, pk):
    """Add a sticky note to a concept."""
    concept = get_object_or_404(DesignConcept, pk=pk)
    br = concept.request
    if br.user != request.user and not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    form = ConceptStickyNoteForm(request.POST)
    if form.is_valid():
        note = form.save(commit=False)
        note.concept = concept
        note.author = request.user
        note.save()
        return JsonResponse({'ok': True, 'id': note.pk})

    return JsonResponse({'errors': form.errors}, status=400)


@login_required
@require_POST
def concept_decide(request, pk):
    """Make a decision on a concept (approve, reject, combine)."""
    concept = get_object_or_404(DesignConcept, pk=pk)
    br = concept.request
    if br.user != request.user and not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    decision_type = request.POST.get('decision', '')
    notes = request.POST.get('notes', '')
    combine_ids = request.POST.getlist('combine_with')

    valid_decisions = ['favorite', 'approved', 'approve', 'rejected', 'reject', 'combined']
    if decision_type not in valid_decisions:
        return JsonResponse({'error': 'Invalid decision'}, status=400)

    if decision_type in ('rejected', 'reject'):
        concept.status = 'rejected'
        concept.decided_at = timezone.now()
        concept.save(update_fields=['status', 'decided_at', 'updated_at'])
    elif decision_type in ('approved', 'approve'):
        concept.status = 'approved'
        concept.is_client_favorite = True
        concept.decided_at = timezone.now()
        concept.save(update_fields=['status', 'is_client_favorite', 'decided_at', 'updated_at'])
    elif decision_type == 'combined':
        concept.combine_with = [int(cid) for cid in combine_ids if cid.isdigit()]
        concept.save(update_fields=['combine_with', 'updated_at'])

    ConceptDecision.objects.create(
        concept=concept, client=request.user,
        decision=decision_type,
        notes=notes,
        combine_with_concepts=[int(cid) for cid in combine_ids if cid.isdigit()],
    )
    ConceptDecisionTrail.objects.create(
        request=br, concept=concept,
        action=f'Client decision: {decision_type}',
        details={'notes': notes},
        performed_by=request.user,
    )

    label = decision_type.replace('_', ' ').title()
    messages.success(request, f'Decision recorded: {label} on "{concept.title}".')
    return redirect('branding:concept_detail', pk=pk)


# ── Refinement Process ──────────────────────────────────────────────────────

@login_required
def concept_refinements(request, pk):
    """View refinements for a concept."""
    concept = get_object_or_404(DesignConcept, pk=pk)
    br = concept.request
    is_client = br.user == request.user
    is_designer = br.designer == request.user
    is_staff = request.user.is_staff or request.user.is_superuser

    if not (is_client or is_designer or is_staff):
        return redirect('branding:dashboard')

    refinements = concept.refinements.select_related('client').prefetch_related('iterations').all()

    if request.method == 'POST' and is_client:
        form = ConceptRefinementForm(request.POST)
        if form.is_valid():
            refinement = form.save(commit=False)
            refinement.concept = concept
            refinement.client = request.user
            refinement.save()
            messages.success(request, 'Refinement requested.')
            return redirect('branding:concept_refinements', pk=pk)
    else:
        form = ConceptRefinementForm()

    return render(request, 'branding/concepts/refinements.html', {
        'concept': concept,
        'request_obj': br,
        'refinements': refinements,
        'form': form,
        'is_client': is_client,
        'is_designer': is_designer,
        'page_title': f'Refinements - {concept.title}',
    })


@designer_required
@require_POST
def concept_add_iteration(request, pk, refinement_id):
    """Add a refinement iteration (before/after)."""
    concept = get_object_or_404(DesignConcept, pk=pk, designer=request.user)
    refinement = get_object_or_404(ConceptRefinement, pk=refinement_id, concept=concept)

    form = ConceptRefinementIterationForm(request.POST, request.FILES)
    if form.is_valid():
        iteration = form.save(commit=False)
        iteration.refinement = refinement
        iteration.created_by = request.user
        last_version = refinement.iterations.order_by('-version_number').first()
        iteration.version_number = (last_version.version_number + 1) if last_version else 1
        iteration.save()

        refinement.status = 'submitted'
        refinement.save(update_fields=['status', 'updated_at'])

        return redirect('branding:concept_refinements', pk=pk)

    return redirect('branding:concept_refinements', pk=pk)


@login_required
@require_POST
def concept_approve_iteration(request, pk, refinement_id, iteration_id):
    """Client approves or rejects a refinement iteration."""
    concept = get_object_or_404(DesignConcept, pk=pk)
    refinement = get_object_or_404(ConceptRefinement, pk=refinement_id, concept=concept)
    iteration = get_object_or_404(ConceptRefinementIteration, pk=iteration_id, refinement=refinement)

    if refinement.client != request.user and not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    approved = request.POST.get('approved') == 'true'
    iteration.client_approved = approved
    iteration.client_notes = request.POST.get('notes', '')
    iteration.save(update_fields=['client_approved', 'client_notes'])

    if approved:
        refinement.status = 'approved'
    else:
        refinement.status = 'requested'
    refinement.save(update_fields=['status', 'updated_at'])

    return redirect('branding:concept_refinements', pk=pk)


# ── Comparison & Analysis ───────────────────────────────────────────────────

@login_required
def concept_compare(request, request_pk):
    """Side-by-side comparison of concepts."""
    br = get_object_or_404(BrandingRequest, pk=request_pk)
    is_client = br.user == request.user
    is_designer = br.designer == request.user
    is_staff = request.user.is_staff or request.user.is_superuser

    if not (is_client or is_designer or is_staff):
        return redirect('branding:dashboard')

    compare_ids = request.GET.getlist('concept')
    concepts = br.concepts.filter(pk__in=compare_ids).prefetch_related(
        'element_ratings', 'supporting_images', 'feedbacks', 'annotations',
    ) if compare_ids else br.concepts.exclude(status='archived')

    import json
    overlay_mode = request.GET.get('overlay') == 'true'

    return render(request, 'branding/concepts/compare.html', {
        'request_obj': br,
        'concepts': concepts,
        'compare_ids': compare_ids,
        'overlay_mode': overlay_mode,
        'is_client': is_client,
        'is_designer': is_designer,
        'RATING_ELEMENTS': RATING_ELEMENTS,
        'page_title': f'Compare Concepts - {br.request_number}',
    })


@login_required
def concept_feedback_analysis(request, request_pk):
    """Feedback analysis dashboard for a request."""
    br = get_object_or_404(BrandingRequest, pk=request_pk)
    is_client = br.user == request.user
    is_designer = br.designer == request.user
    is_staff = request.user.is_staff or request.user.is_superuser

    if not (is_client or is_designer or is_staff):
        return redirect('branding:dashboard')

    concepts = br.concepts.prefetch_related('element_ratings', 'feedbacks', 'annotations')

    concept_analytics = []
    for c in concepts:
        from django.db.models import Avg
        element_avgs = c.element_ratings.values('element').annotate(avg=Avg('score'))
        all_annotations = c.annotations.all()
        annotation_types = {}
        for a in all_annotations:
            annotation_types[a.annotation_type] = annotation_types.get(a.annotation_type, 0) + 1

        strengths = []
        improvements = []
        for fb in c.feedbacks.all():
            if fb.strengths:
                strengths.append(fb.strengths)
            if fb.improvements:
                improvements.append(fb.improvements)

        concept_analytics.append({
            'concept': c,
            'element_avgs': {e['element']: round(e['avg'], 1) for e in element_avgs},
            'avg_rating': c.avg_rating(),
            'total_feedback': c.feedbacks.count(),
            'annotation_count': c.annotations.count(),
            'annotation_types': annotation_types,
            'resolved_annotations': c.annotations.filter(is_resolved=True).count(),
            'strengths': strengths,
            'improvements': improvements,
        })

    return render(request, 'branding/concepts/analysis.html', {
        'request_obj': br,
        'concept_analytics': concept_analytics,
        'is_client': is_client,
        'is_designer': is_designer,
        'RATING_ELEMENTS': RATING_ELEMENTS,
        'page_title': f'Feedback Analysis - {br.request_number}',
    })


# ── Client Decision Dashboard ───────────────────────────────────────────────

@login_required
def concept_decision_dashboard(request, request_pk):
    """Client decision dashboard showing all decisions."""
    br = get_object_or_404(BrandingRequest, pk=request_pk)
    is_client = br.user == request.user
    is_designer = br.designer == request.user
    is_staff = request.user.is_staff or request.user.is_superuser

    if not (is_client or is_designer or is_staff):
        return redirect('branding:dashboard')

    concepts = br.concepts.all()
    all_decisions = ConceptDecision.objects.filter(
        concept__request=br,
    ).select_related('concept', 'client').order_by('-decided_at')

    all_trail = ConceptDecisionTrail.objects.filter(
        request=br,
    ).select_related('concept', 'performed_by').order_by('-timestamp')

    favorite = concepts.filter(is_client_favorite=True).first()
    designer_pick = concepts.filter(is_designer_top_pick=True).first()
    approved = concepts.filter(status='approved')
    rejected = concepts.filter(status='rejected')
    combined = concepts.filter(combine_with__isnull=False).exclude(combine_with=[])

    return render(request, 'branding/concepts/decisions.html', {
        'request_obj': br,
        'concepts': concepts,
        'all_decisions': all_decisions,
        'all_trail': all_trail,
        'favorite': favorite,
        'designer_pick': designer_pick,
        'approved': approved,
        'rejected': rejected,
        'combined': combined,
        'is_client': is_client,
        'is_designer': is_designer,
        'is_staff': is_staff,
        'page_title': f'Client Decisions - {br.request_number}',
    })


# ── Presentation Sessions ───────────────────────────────────────────────────

@login_required
def concept_sessions(request, request_pk):
    """List presentation sessions."""
    br = get_object_or_404(BrandingRequest, pk=request_pk)
    is_client = br.user == request.user
    is_designer = br.designer == request.user
    is_staff = request.user.is_staff or request.user.is_superuser

    if not (is_client or is_designer or is_staff):
        return redirect('branding:dashboard')

    sessions = br.presentation_sessions.all()
    upcoming = sessions.filter(status='scheduled')
    past = sessions.filter(status__in=['completed', 'cancelled'])

    if request.method == 'POST' and is_designer:
        form = ConceptPresentationSessionForm(request.POST)
        if form.is_valid():
            session = form.save(commit=False)
            session.request = br
            session.created_by = request.user
            session.save()
            form.save_m2m()
            messages.success(request, 'Presentation session scheduled.')
            return redirect('branding:concept_sessions', request_pk=request_pk)
    else:
        form = ConceptPresentationSessionForm()

    return render(request, 'branding/concepts/sessions.html', {
        'request_obj': br,
        'upcoming': upcoming,
        'past': past,
        'form': form,
        'is_designer': is_designer,
        'page_title': f'Presentations - {br.request_number}',
    })


@designer_required
@require_POST
def concept_session_update(request, pk, session_id):
    """Update session status or notes."""
    br = get_object_or_404(BrandingRequest, pk=pk, designer=request.user)
    session = get_object_or_404(ConceptPresentationSession, pk=session_id, request=br)

    new_status = request.POST.get('status')
    if new_status in [s[0] for s in SESSION_STATUSES]:
        session.status = new_status

    notes = request.POST.get('notes_taken')
    if notes is not None:
        session.notes_taken = notes

    recording_url = request.POST.get('recording_url')
    if recording_url:
        session.recording_url = recording_url

    realtime = request.POST.get('realtime_feedback')
    if realtime:
        import json
        try:
            session.realtime_feedback = json.loads(realtime)
        except (json.JSONDecodeError, TypeError):
            pass

    session.save()
    return redirect('branding:concept_sessions', request_pk=pk)


# ═══════════════════════════════════════════════════════════════════════════
# Designer Workflow System
# ═══════════════════════════════════════════════════════════════════════════

@designer_required
def workflow_dashboard(request):
    """Main workflow dashboard showing all assigned projects by stage."""
    from .models import (
        ProjectWorkflow, WORKFLOW_STAGES, WorkflowStageLog,
        ClientQuestion, FeedbackItem, DesignIteration, DecisionLog, CommunicationEntry,
    )

    me = request.user
    my_projects = BrandingRequest.objects.filter(designer=me).exclude(status__in=['DRAFT', 'ARCHIVED'])

    workflows = ProjectWorkflow.objects.filter(
        request__in=my_projects
    ).select_related('request', 'request__user', 'request__collection')

    stage_filter = request.GET.get('stage', '')
    if stage_filter:
        workflows = workflows.filter(current_stage=stage_filter)

    workflows_by_stage = {}
    for stage_key, stage_label in WORKFLOW_STAGES:
        workflows_by_stage[stage_key] = {
            'label': stage_label,
            'items': [w for w in workflows if w.current_stage == stage_key],
        }

    escalated = [w for w in workflows if w.is_overdue() and not w.is_escalated]
    for w in escalated:
        w.is_escalated = True
        w.save(update_fields=['is_escalated'])

    stage_counts = {}
    for stage_key, _ in WORKFLOW_STAGES:
        stage_counts[stage_key] = workflows.filter(current_stage=stage_key).count()

    recent_comms = CommunicationEntry.objects.filter(
        workflow__in=workflows
    ).select_related('author', 'workflow', 'workflow__request')[:15]

    return render(request, 'branding/workflow/dashboard.html', {
        'workflows_by_stage': workflows_by_stage,
        'stages': WORKFLOW_STAGES,
        'stage_counts': stage_counts,
        'stage_filter': stage_filter,
        'escalated': [w for w in workflows if w.is_overdue()],
        'recent_comms': recent_comms,
        'total_projects': workflows.count(),
        'page_title': 'Workflow Dashboard',
    })


@designer_required
def workflow_project(request, pk):
    """Workflow detail for a specific project."""
    from .models import (
        ProjectWorkflow, WorkflowStageLog, WORKFLOW_STAGES,
        ClientQuestion, FeedbackItem, DesignIteration, DecisionLog, CommunicationEntry,
        QUESTION_CATEGORIES, FEEDBACK_STATUSES,
    )

    br = get_object_or_404(BrandingRequest, pk=pk, designer=request.user)
    workflow, created = ProjectWorkflow.objects.get_or_create(request=br)

    stage_logs = workflow.stage_logs.select_related('moved_by')[:20]
    questions = workflow.questions.all()
    unanswered = questions.filter(is_answered=False)
    feedback_items = workflow.feedback_items.all()
    iterations = workflow.iterations.all()
    decisions = workflow.decisions.all()
    communications = workflow.communications.select_related('author').all()

    comm_type_filter = request.GET.get('comm_type', '')
    fb_status_filter = request.GET.get('fb_status', '')
    if comm_type_filter:
        communications = communications.filter(interaction_type=comm_type_filter)
    if fb_status_filter:
        feedback_items = feedback_items.filter(status=fb_status_filter)

    return render(request, 'branding/workflow/project.html', {
        'br': br,
        'workflow': workflow,
        'stage_logs': stage_logs,
        'questions': questions,
        'unanswered_count': unanswered.count(),
        'feedback_items': feedback_items,
        'iterations': iterations,
        'decisions': decisions,
        'communications': communications,
        'stages': WORKFLOW_STAGES,
        'question_categories': QUESTION_CATEGORIES,
        'feedback_statuses': FEEDBACK_STATUSES,
        'comm_type_filter': comm_type_filter,
        'fb_status_filter': fb_status_filter,
        'page_title': f'Workflow: {br.request_number}',
    })


@designer_required
@require_POST
def workflow_advance_stage(request, pk):
    """Move workflow to next stage."""
    from .models import ProjectWorkflow, WorkflowStageLog

    workflow = get_object_or_404(ProjectWorkflow, request__pk=pk, request__designer=request.user)
    old_stage = workflow.current_stage
    if workflow.advance_stage():
        WorkflowStageLog.objects.create(
            workflow=workflow,
            from_stage=old_stage,
            to_stage=workflow.current_stage,
            duration_seconds=int(workflow.stage_duration().total_seconds()),
            moved_by=request.user,
        )
        CommunicationEntry.objects.create(
            workflow=workflow,
            request=workflow.request,
            interaction_type='note',
            title=f'Stage moved: {old_stage} -> {workflow.current_stage}',
            author=request.user,
        )
        messages.success(request, f'Moved to {workflow.get_current_stage_display()}')
    else:
        messages.warning(request, 'Cannot advance further — already at final stage.')
    return redirect('branding:workflow_project', pk=pk)


@designer_required
@require_POST
def workflow_move_stage(request, pk):
    """Move workflow to a specific stage."""
    from .models import ProjectWorkflow, WorkflowStageLog

    workflow = get_object_or_404(ProjectWorkflow, request__pk=pk, request__designer=request.user)
    target = request.POST.get('target_stage', '')
    old_stage = workflow.current_stage
    if workflow.move_to_stage(target):
        WorkflowStageLog.objects.create(
            workflow=workflow,
            from_stage=old_stage,
            to_stage=target,
            duration_seconds=int(workflow.stage_duration().total_seconds()),
            moved_by=request.user,
            notes=request.POST.get('notes', ''),
        )
        CommunicationEntry.objects.create(
            workflow=workflow,
            request=workflow.request,
            interaction_type='note',
            title=f'Stage changed: {old_stage} -> {target}',
            content=request.POST.get('notes', ''),
            author=request.user,
        )
        messages.success(request, f'Moved to {workflow.get_current_stage_display()}')
    else:
        messages.error(request, 'Invalid stage.')
    return redirect('branding:workflow_project', pk=pk)


@designer_required
@require_POST
def workflow_add_question(request, pk):
    """Add a question for the client."""
    from .models import ProjectWorkflow, ClientQuestion

    workflow = get_object_or_404(ProjectWorkflow, request__pk=pk, request__designer=request.user)
    question_text = request.POST.get('question', '').strip()
    category = request.POST.get('category', 'general')
    is_required = request.POST.get('is_required') == 'on'

    if question_text:
        ClientQuestion.objects.create(
            workflow=workflow,
            category=category,
            question=question_text,
            is_required=is_required,
            asked_by=request.user,
        )
        CommunicationEntry.objects.create(
            workflow=workflow,
            request=workflow.request,
            interaction_type='question',
            title=f'New question: {question_text[:80]}',
            author=request.user,
        )
        messages.success(request, 'Question added.')
    return redirect('branding:workflow_project', pk=pk)


@designer_required
@require_POST
def workflow_answer_question(request, pk, q_id):
    """Mark a question as answered (designer can pre-fill answers)."""
    from .models import ProjectWorkflow, ClientQuestion

    workflow = get_object_or_404(ProjectWorkflow, request__pk=pk, request__designer=request.user)
    question = get_object_or_404(ClientQuestion, pk=q_id, workflow=workflow)
    answer = request.POST.get('answer', '').strip()
    if answer:
        question.mark_answered(answer)
        messages.success(request, 'Question marked as answered.')
    return redirect('branding:workflow_project', pk=pk)


@designer_required
@require_POST
def workflow_add_feedback(request, pk):
    """Add a feedback item."""
    from .models import ProjectWorkflow, FeedbackItem

    workflow = get_object_or_404(ProjectWorkflow, request__pk=pk, request__designer=request.user)
    title = request.POST.get('title', '').strip()
    content = request.POST.get('content', '').strip()
    category = request.POST.get('category', 'general')
    linked_element = request.POST.get('linked_element', '').strip()

    if title and content:
        FeedbackItem.objects.create(
            workflow=workflow,
            request=workflow.request,
            title=title,
            content=content,
            category=category,
            client=workflow.request.user,
            linked_element=linked_element,
        )
        CommunicationEntry.objects.create(
            workflow=workflow,
            request=workflow.request,
            interaction_type='feedback',
            title=f'Feedback received: {title[:80]}',
            content=content,
            author=request.user,
        )
        messages.success(request, 'Feedback item added.')
    return redirect('branding:workflow_project', pk=pk)


@designer_required
@require_POST
def workflow_update_feedback(request, pk, fb_id):
    """Update feedback status or add internal notes."""
    from .models import ProjectWorkflow, FeedbackItem

    workflow = get_object_or_404(ProjectWorkflow, request__pk=pk, request__designer=request.user)
    fb = get_object_or_404(FeedbackItem, pk=fb_id, workflow=workflow)

    new_status = request.POST.get('status', '')
    notes = request.POST.get('internal_notes', '')
    if new_status:
        fb.status = new_status
    if notes is not None:
        fb.internal_notes = notes
    fb.save(update_fields=['status', 'internal_notes', 'updated_at'])
    messages.success(request, 'Feedback updated.')
    return redirect('branding:workflow_project', pk=pk)


@designer_required
@require_POST
def workflow_add_iteration(request, pk):
    """Add a design iteration."""
    from .models import ProjectWorkflow, DesignIteration

    workflow = get_object_or_404(ProjectWorkflow, request__pk=pk, request__designer=request.user)
    last_version = workflow.iterations.order_by('-version_number').first()
    next_version = (last_version.version_number + 1) if last_version else 1

    title = request.POST.get('title', '').strip()
    description = request.POST.get('description', '').strip()
    change_notes = request.POST.get('change_notes', '').strip()

    iteration = DesignIteration(
        workflow=workflow,
        request=workflow.request,
        version_number=next_version,
        title=title or f'Version {next_version}',
        description=description,
        change_notes=change_notes,
        created_by=request.user,
    )
    if request.FILES.get('file'):
        iteration.file = request.FILES['file']
    iteration.save()

    CommunicationEntry.objects.create(
        workflow=workflow,
        request=workflow.request,
        interaction_type='revision',
        title=f'New iteration: v{next_version} — {title or "Untitled"}',
        content=change_notes,
        author=request.user,
    )
    messages.success(request, f'Iteration v{next_version} added.')
    return redirect('branding:workflow_project', pk=pk)


@designer_required
@require_POST
def workflow_add_decision(request, pk):
    """Add a decision log entry."""
    from .models import ProjectWorkflow, DecisionLog

    workflow = get_object_or_404(ProjectWorkflow, request__pk=pk, request__designer=request.user)
    decision = request.POST.get('decision', '').strip()
    rationale = request.POST.get('rationale', '').strip()
    category = request.POST.get('category', 'general')

    if decision:
        DecisionLog.objects.create(
            workflow=workflow,
            request=workflow.request,
            decision=decision,
            rationale=rationale,
            category=category,
            decided_by=request.user,
        )
        CommunicationEntry.objects.create(
            workflow=workflow,
            request=workflow.request,
            interaction_type='approval',
            title=f'Decision logged: {decision[:80]}',
            content=rationale,
            author=request.user,
        )
        messages.success(request, 'Decision logged.')
    return redirect('branding:workflow_project', pk=pk)


@designer_required
@require_POST
def workflow_add_communication(request, pk):
    """Add a communication entry."""
    from .models import ProjectWorkflow, CommunicationEntry

    workflow = get_object_or_404(ProjectWorkflow, request__pk=pk, request__designer=request.user)
    title = request.POST.get('title', '').strip()
    content = request.POST.get('content', '').strip()
    interaction_type = request.POST.get('interaction_type', 'note')
    is_action = request.POST.get('is_action_item') == 'on'

    if title:
        CommunicationEntry.objects.create(
            workflow=workflow,
            request=workflow.request,
            interaction_type=interaction_type,
            title=title,
            content=content,
            author=request.user,
            is_action_item=is_action,
        )
        messages.success(request, 'Entry added to timeline.')
    return redirect('branding:workflow_project', pk=pk)


@designer_required
@require_POST
def workflow_toggle_action(request, pk, comm_id):
    """Toggle action item status."""
    from .models import ProjectWorkflow, CommunicationEntry

    workflow = get_object_or_404(ProjectWorkflow, request__pk=pk, request__designer=request.user)
    entry = get_object_or_404(CommunicationEntry, pk=comm_id, workflow=workflow)
    entry.action_taken = not entry.action_taken
    entry.save(update_fields=['action_taken'])
    return JsonResponse({'ok': True, 'action_taken': entry.action_taken})


# ---------------------------------------------------------------------------
# Staff dashboard
# ---------------------------------------------------------------------------

def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


# ---------------------------------------------------------------------------
# Notifications & email
# ---------------------------------------------------------------------------

def _request_url(req):
    if req and req.pk:
        return reverse('branding:request_detail', args=[req.pk])
    return ''


def _send_email(user, subject, message, template_name=None, template_context=None):
    """Best-effort email. Uses HTML template if provided, falls back to plain text."""
    if not user or not user.email:
        return False
    try:
        if template_name:
            from .emails import send_html_email
            return send_html_email(
                recipient=user,
                subject=subject,
                template_name=template_name,
                context=template_context or {},
                log_label=template_name,
            )
        return send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL or 'noreply@onwebapp.com',
            [user.email],
            fail_silently=True,
        )
    except Exception:
        return False


def _notify(recipient, req, ntype, message, email_subject=None, url='',
            template_name=None, template_context=None):
    """Create an in-app notification and (optionally) an HTML email."""
    if not recipient:
        return None
    url = url or _request_url(req)
    notification = BrandingNotification.objects.create(
        recipient=recipient,
        request=req,
        notification_type=ntype,
        message=message,
        url=url,
    )
    if email_subject:
        body = f"{message}\n\nOpen request: {url}" if url else message
        _send_email(recipient, email_subject, body,
                    template_name=template_name, template_context=template_context)
    return notification


def _notify_managers(req, ntype, message, email_subject=None):
    """Notify platform managers (superusers) about a request."""
    for manager in User.objects.filter(is_superuser=True):
        _notify(manager, req, ntype, message, email_subject)


def _set_status(req, new_status, actor, log_action=None, notify_client=True):
    """Shared status transition helper: logs, notifies client and managers."""
    old_label = req.get_status_display()
    req.status = new_status
    fields = ['status', 'updated_at']
    if new_status == 'COMPLETED':
        req.completed_at = timezone.now()
        fields.append('completed_at')
    elif req.completed_at and new_status != 'COMPLETED':
        req.completed_at = None
        fields.append('completed_at')
    req.save(update_fields=fields)
    req.log(
        'STATUS_CHANGE',
        log_action or f"Status changed from {old_label} to {req.get_status_display()}",
        actor=actor,
    )
    if notify_client and req.user_id and req.user_id != actor.id:
        from .emails import STATUS_COLORS
        _notify(
            req.user,
            req,
            'STATUS_CHANGED',
            f"Your branding request {req.request_number} is now {req.get_status_display()}.",
            email_subject=f"[OnWebApp Branding] {req.request_number} — {req.get_status_display()}",
            template_name='emails/status_update.html',
            template_context={
                'request_number': req.request_number,
                'company_name': req.company_name,
                'status_display': req.get_status_display(),
                'status_color': STATUS_COLORS.get(req.status, '#4f46e5'),
                'old_status': old_label,
                'designer_name': str(req.designer) if req.designer else '',
                'action_url': f"{SITE_URL}/branding/requests/{req.pk}/",
            },
        )
    if new_status == 'COMPLETED':
        _notify_managers(
            req,
            'COMPLETED',
            f"Request {req.request_number} ({req.company_name}) was completed.",
            email_subject=f"[OnWebApp Branding] {req.request_number} completed",
        )
    invalidate_after_status_change()
    return req


@staff_member_required
def dashboard(request):
    qs = (
        BrandingRequest.objects
        .exclude(status='DRAFT')
        .select_related('user', 'collection', 'designer')
        .only(
            'id', 'request_number', 'company_name', 'status', 'priority',
            'industry', 'estimated_delivery_date', 'completed_at', 'created_at',
            'user__id', 'user__first_name', 'user__last_name', 'user__username',
            'collection__id', 'collection__name',
            'designer__id', 'designer__first_name', 'designer__last_name', 'designer__username',
        )
    )

    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()
    industry = request.GET.get('industry', '')
    collection = request.GET.get('collection', '')
    designer = request.GET.get('designer', '')
    priority = request.GET.get('priority', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(
            models_q_company(request, search)
        )
    if industry:
        qs = qs.filter(industry=industry)
    if collection:
        qs = qs.filter(collection_id=collection)
    if designer:
        qs = qs.filter(designer_id=designer)
    if priority:
        qs = qs.filter(priority=priority)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    # Stat cards — cached per user for 5 minutes
    def _compute_stats():
        now = timezone.now()
        agg = BrandingRequest.objects.aggregate(
            pending_review=Count('id', filter=Q(status='PENDING_REVIEW')),
            in_review=Count('id', filter=Q(status='IN_REVIEW')),
            assigned=Count('id', filter=Q(status='ASSIGNED')),
            designing=Count('id', filter=Q(status='DESIGNING')),
            waiting_client=Count('id', filter=Q(status='WAITING_CLIENT')),
            revision=Count('id', filter=Q(status='REVISION')),
            approved=Count('id', filter=Q(status='APPROVED')),
            completed=Count('id', filter=Q(status='COMPLETED')),
            monthly=Count('id', filter=Q(
                created_at__year=now.year, created_at__month=now.month
            )),
            archived=Count('id', filter=Q(status='ARCHIVED')),
            avg_seconds=Avg(
                F('completed_at') - F('created_at'),
                filter=Q(status='COMPLETED', completed_at__isnull=False),
            ),
        )
        return {
            'PENDING_REVIEW': agg['pending_review'],
            'IN_REVIEW': agg['in_review'],
            'ASSIGNED': agg['assigned'],
            'DESIGNING': agg['designing'],
            'WAITING_CLIENT': agg['waiting_client'],
            'REVISION': agg['revision'],
            'APPROVED': agg['approved'],
            'COMPLETED': agg['completed'],
            'MONTHLY': agg['monthly'],
            'ARCHIVED': agg['archived'],
            'avg_seconds': agg['avg_seconds'].total_seconds() if agg['avg_seconds'] else None,
        }

    stats = cache_get_or_set(dashboard_stats_key(request.user.pk), _compute_stats, TIMEOUT_DASHBOARD)
    counts = {k: v for k, v in stats.items() if k != 'avg_seconds'}
    avg_seconds = stats.get('avg_seconds')

    paginator = Paginator(qs, 12)
    page = paginator.get_page(request.GET.get('page'))

    designers = cache_get_or_set(
        designers_key(),
        lambda: list(User.objects.filter(is_staff=True).order_by('username')),
        TIMEOUT_DESIGNERS,
    )
    collections = cache_get_or_set(
        collections_key(),
        lambda: list(BrandCollection.objects.filter(is_active=True).order_by('name')),
        TIMEOUT_COLLECTIONS,
    )

    return render(request, 'branding/dashboard.html', {
        'requests': page,
        'card_statuses': BRANDING_CARD_STATUSES,
        'counts': counts,
        'avg_seconds': avg_seconds,
        'current_status': status_filter,
        'search': search,
        'industry': industry,
        'collection': collection,
        'designer': designer,
        'priority': priority,
        'date_from': date_from,
        'date_to': date_to,
        'designers': designers,
        'collections': collections,
        'industries': INDUSTRY_CHOICES,
        'priorities': PRIORITY_CHOICES,
        'status_choices': [s for s in STATUS_CHOICES if s[0] != 'DRAFT'],
    })


def models_q_company(request, search):
    """Build a Q() across company name + request number + client username."""
    from django.db.models import Q
    q = Q(company_name__icontains=search) | Q(request_number__icontains=search)
    if request.GET.get('q'):
        q |= Q(user__username__icontains=search) | Q(user__email__icontains=search)
    return q


@staff_member_required
def request_detail(request, pk):
    req = get_object_or_404(
        BrandingRequest.objects.select_related('user', 'collection', 'designer'),
        pk=pk,
    )
    timeline = req.timeline_entries.select_related('actor').all()
    form = BrandingRequestForm(instance=req)
    designers = cache_get_or_set(
        designers_key(),
        lambda: list(User.objects.filter(is_staff=True).order_by('username')),
        TIMEOUT_DESIGNERS,
    )

    # Milestone stepper: reach the stage index of the current status.
    stage_codes = [code for code, _, _ in TIMELINE_STAGES]
    if req.status in stage_codes:
        current_idx = stage_codes.index(req.status)
        current_stage = req.status
    elif req.status == 'ARCHIVED':
        current_idx = len(stage_codes)
        current_stage = 'ARCHIVED'
    else:
        current_idx = -1
        current_stage = None

    # Earliest event that moved the request INTO each milestone stage.
    # Use a single query instead of re-filtering timeline.
    status_changes = list(
        timeline.filter(event_type='STATUS_CHANGE').order_by('created_at')
    )
    stage_timestamps = {}
    for t in status_changes:
        action_lower = (t.action or '').lower()
        for code, label, _icon in TIMELINE_STAGES:
            if code.lower() in action_lower or label.lower() in action_lower:
                stage_timestamps.setdefault(code, t.created_at)

    milestone_stages = []
    for idx, (code, label, icon) in enumerate(TIMELINE_STAGES):
        if idx < current_idx:
            state = 'done'
        elif idx == current_idx:
            state = 'current'
        else:
            state = 'pending'
        milestone_stages.append({
            'code': code,
            'label': label,
            'icon': icon,
            'state': state,
            'timestamp': stage_timestamps.get(code),
        })
    if current_stage == 'ARCHIVED':
        milestone_stages.append({
            'code': 'ARCHIVED', 'label': 'Archived', 'icon': 'fa-box-archive',
            'state': 'current', 'timestamp': stage_timestamps.get('archived'),
        })

    # Assets with versions — prefetch to avoid N+1
    assets_qs = req.assets.prefetch_related('versions').all()
    assets_with_versions = [
        {'asset': a, 'versions': list(a.versions.all()[:5])} for a in assets_qs
    ]

    # Messages: root messages (no parent) with replies prefetched
    messages_qs = req.messages.select_related('sender').filter(parent__isnull=True)
    unread_msg_count = BrandingMessage.get_unread_count(request.user)

    # Activity log reuses the timeline queryset (avoids extra query)
    activity_log = list(timeline.order_by('-created_at')[:40])

    # Supervisor review
    review, _ = ProjectReview.objects.get_or_create(request=req)
    quality_checklist = QUALITY_CHECKLIST

    # Handle supervisor review POST actions
    if request.method == 'POST' and request.user.is_staff:
        action = request.POST.get('action')

        if action == 'update_checklist':
            for key, _ in QUALITY_CHECKLIST:
                review.quality_checklist[key] = request.POST.get(f'cl_{key}') == 'on'
            review.save(update_fields=['quality_checklist', 'updated_at'])
            review.refresh_from_db()
            messages.success(request, 'Quality checklist updated.')

        elif action == 'approve_review':
            review.status = 'APPROVED'
            review.reviewer = request.user
            notes = request.POST.get('review_notes', '').strip()
            if notes:
                review.notes = notes
            # Also save checklist state
            for key, _ in QUALITY_CHECKLIST:
                review.quality_checklist[key] = request.POST.get(f'cl_{key}') == 'on'
            review.save()
            req.log('STATUS_CHANGE', f'Approved by supervisor {request.user.get_full_name() or request.user.username}',
                    description=review.notes, actor=request.user)
            messages.success(request, 'Project approved.')

        elif action == 'reject_review':
            review.status = 'REJECTED'
            review.reviewer = request.user
            notes = request.POST.get('review_notes', '').strip()
            review.notes = notes
            review.save()
            req.log('STATUS_CHANGE', f'Rejected by supervisor {request.user.get_full_name() or request.user.username}',
                    description=review.notes, actor=request.user)
            messages.warning(request, 'Project rejected.')

        elif action == 'request_revision':
            review.status = 'REVISION_REQUESTED'
            review.reviewer = request.user
            notes = request.POST.get('review_notes', '').strip()
            review.notes = notes
            review.save()
            req.status = 'REVISION'
            req.save(update_fields=['status', 'updated_at'])
            req.log('STATUS_CHANGE', f'Revision requested by supervisor {request.user.get_full_name() or request.user.username}',
                    description=review.notes, actor=request.user)
            messages.info(request, 'Revision requested.')

        return redirect('branding:request_detail', pk=pk)

    return render(request, 'branding/request_detail.html', {
        'branding_request': req,
        'form': form,
        'timeline': timeline,
        'designers': designers,
        'status_choices': [s for s in STATUS_CHOICES if s[0] != 'DRAFT'],
        'priorities': PRIORITY_CHOICES,
        'milestone_stages': milestone_stages,
        'assets_with_versions': assets_with_versions,
        'activity_log': activity_log,
        'messages': messages_qs,
        'unread_msg_count': unread_msg_count,
        'review': review,
        'quality_checklist': quality_checklist,
    })


@staff_member_required
@require_POST
def assign_designer(request, pk):
    req = get_object_or_404(BrandingRequest, pk=pk)
    designer_id = request.POST.get('designer', '')
    designer = User.objects.filter(pk=designer_id, is_staff=True).first()
    if designer:
        req.designer = designer
        if req.status in ('PENDING_REVIEW', 'IN_REVIEW'):
            req.status = 'ASSIGNED'
        req.save(update_fields=['designer', 'status', 'updated_at'])
        req.log(
            'ASSIGNMENT',
            f"Assigned to {designer.get_full_name() or designer.username}",
            actor=request.user,
        )
        if req.status == 'ASSIGNED':
            req.log('STATUS_CHANGE', 'Status changed to Assigned', actor=request.user)
        _notify(
            designer,
            req,
            'DESIGNER_ASSIGNED',
            f"You've been assigned to {req.company_name} ({req.request_number}).",
            email_subject=f"[OnWebApp Branding] New assignment: {req.request_number}",
            template_name='emails/assignment.html',
            template_context={
                'request_number': req.request_number,
                'company_name': req.company_name,
                'designer_name': designer.get_full_name() or designer.username,
                'designer_email': designer.email,
                'estimated_delivery': req.estimated_delivery_date.strftime('%B %d, %Y') if req.estimated_delivery_date else '',
                'action_url': f"{SITE_URL}/branding/requests/{req.pk}/",
            },
        )
        messages.success(request, f'Designer assigned: {designer.username}')
    else:
        messages.error(request, 'Please select a valid designer.')
    invalidate_after_status_change()
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
    if next_url and 'branding' in next_url:
        return redirect(next_url)
    return redirect('branding:request_detail', pk=pk)


@staff_member_required
@require_POST
def update_status(request, pk):
    req = get_object_or_404(BrandingRequest, pk=pk)
    new_status = request.POST.get('status', '')
    valid = {code for code, _ in STATUS_CHOICES if code != 'DRAFT'}
    if new_status in valid and new_status != req.status:
        _set_status(req, new_status, request.user)
        messages.success(request, f'Status updated to {req.get_status_display()}.')
    elif new_status == req.status:
        messages.info(request, 'Status unchanged.')
    else:
        messages.error(request, 'Invalid status.')
    return redirect('branding:request_detail', pk=pk)


@staff_member_required
@require_POST
def add_note(request, pk):
    req = get_object_or_404(BrandingRequest, pk=pk)
    note = request.POST.get('note', '').strip()
    if note:
        req.log('NOTE', note, actor=request.user)
        messages.success(request, 'Internal note added.')
    return redirect('branding:request_detail', pk=pk)


@staff_member_required
@require_POST
def archive_request(request, pk):
    req = get_object_or_404(BrandingRequest, pk=pk)
    if req.status == 'ARCHIVED':
        req.status = 'PENDING_REVIEW'
        action = 'Request unarchived'
    else:
        req.status = 'ARCHIVED'
        action = 'Request archived'
    req.save(update_fields=['status', 'updated_at'])
    req.log('STATUS_CHANGE', action, actor=request.user)
    messages.success(request, action + '.')
    invalidate_after_status_change()
    return redirect('branding:dashboard')


@staff_member_required
def kanban(request):
    """Kanban board view with draggable request cards grouped by status."""
    def _compute_kanban():
        # Single query: fetch all non-DRAFT requests, grouped by status in Python
        all_requests = (
            BrandingRequest.objects
            .exclude(status='DRAFT')
            .select_related('user', 'collection', 'designer')
            .only('id', 'request_number', 'company_name', 'status', 'priority',
                  'industry', 'estimated_delivery_date', 'created_at',
                  'user__first_name', 'user__last_name', 'user__username',
                  'collection__name', 'designer__first_name', 'designer__last_name',
                  'designer__username')
            .order_by('-priority', '-created_at')
        )

        # Bucket into columns
        buckets = {code: [] for code, _, _ in KANBAN_COLUMNS}
        for req in all_requests:
            if req.status in buckets:
                buckets[req.status].append(req)

        cols = []
        for code, label, icon in KANBAN_COLUMNS:
            cols.append({
                'code': code,
                'label': label,
                'icon': icon,
                'requests': buckets[code],
            })

        archived_count = BrandingRequest.objects.filter(status='ARCHIVED').count()
        return {'columns': cols, 'archived_count': archived_count}

    data = cache_get_or_set(kanban_key(), _compute_kanban, TIMEOUT_KANBAN)
    return render(request, 'branding/kanban.html', {
        'kanban_columns': data['columns'],
        'archived_count': data['archived_count'],
    })


@staff_member_required
@require_POST
def kanban_update(request):
    """Drag-and-drop: move a request to another status column."""
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    req_id = data.get('request_id')
    new_status = data.get('status', '')
    valid = {code for code, _ in STATUS_CHOICES if code not in ('DRAFT', 'ARCHIVED')}
    req = get_object_or_404(BrandingRequest, pk=req_id)
    if new_status not in valid:
        return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)
    if req.status == new_status:
        return JsonResponse({'success': True, 'status': new_status})
    _set_status(req, new_status, request.user)
    invalidate_after_status_change()
    return JsonResponse({'success': True, 'status': req.status})


@staff_member_required
@require_POST
def update_priority(request, pk):
    req = get_object_or_404(BrandingRequest, pk=pk)
    new_priority = request.POST.get('priority', '')
    valid = {code for code, _ in PRIORITY_CHOICES}
    if new_priority in valid and new_priority != req.priority:
        old = req.get_priority_display()
        req.priority = new_priority
        req.save(update_fields=['priority', 'updated_at'])
        req.log(
            'PRIORITY_CHANGE',
            f"Priority changed from {old} to {req.get_priority_display()}",
            actor=request.user,
        )
        messages.success(request, f'Priority set to {req.get_priority_display()}.')
    else:
        messages.error(request, 'Invalid priority.')
    return redirect('branding:request_detail', pk=pk)


@staff_member_required
@require_POST
def update_delivery(request, pk):
    req = get_object_or_404(BrandingRequest, pk=pk)
    date_value = request.POST.get('estimated_delivery_date', '').strip()
    if date_value:
        from django.utils.dateparse import parse_date
        parsed = parse_date(date_value)
        if not parsed:
            messages.error(request, 'Invalid delivery date.')
            return redirect('branding:request_detail', pk=pk)
        req.estimated_delivery_date = parsed
        req.save(update_fields=['estimated_delivery_date', 'updated_at'])
        req.log(
            'DELIVERY_CHANGE',
            f"Estimated delivery set to {parsed:%b %d, %Y}",
            actor=request.user,
        )
        messages.success(request, f'Estimated delivery updated to {parsed:%b %d, %Y}.')
    else:
        req.estimated_delivery_date = None
        req.save(update_fields=['estimated_delivery_date', 'updated_at'])
        req.log('DELIVERY_CHANGE', 'Estimated delivery cleared', actor=request.user)
        messages.success(request, 'Estimated delivery cleared.')
    return redirect('branding:request_detail', pk=pk)


@staff_member_required
@require_POST
def update_internal_notes(request, pk):
    req = get_object_or_404(BrandingRequest, pk=pk)
    notes = request.POST.get('internal_notes', '').strip()
    req.internal_notes = notes
    req.save(update_fields=['internal_notes', 'updated_at'])
    req.log('NOTE', 'Internal notes updated', actor=request.user)
    messages.success(request, 'Internal notes saved.')
    return redirect('branding:request_detail', pk=pk)


@login_required
def notifications(request):
    notes = BrandingNotification.objects.filter(recipient=request.user).select_related('request')
    return render(request, 'branding/notifications.html', {
        'notifications': notes,
        'user': request.user,
    })


@login_required
@require_POST
def mark_notification_read(request, pk):
    note = get_object_or_404(BrandingNotification, pk=pk, recipient=request.user)
    note.mark_read()
    return JsonResponse({'ok': True})


@staff_member_required
def edit_request(request, pk):
    req = get_object_or_404(BrandingRequest, pk=pk)
    if request.method == 'POST':
        form = BrandingRequestForm(request.POST, instance=req)
        if form.is_valid():
            form.save()
            req.log('NOTE', 'Request details updated by staff', actor=request.user)
            messages.success(request, 'Request updated.')
            return redirect('branding:request_detail', pk=pk)
    else:
        form = BrandingRequestForm(instance=req)
    return render(request, 'branding/request_edit.html', {
        'branding_request': req,
        'form': form,
    })


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------

@login_required
@require_POST
def send_message(request, pk):
    """AJAX endpoint: send a message on a branding request."""
    req = get_object_or_404(BrandingRequest, pk=pk)
    if req.user != request.user and not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    content = (data.get('content') or '').strip()
    parent_id = data.get('parent_id')

    if not content:
        return JsonResponse({'error': 'Message cannot be empty.'}, status=400)

    parent = None
    if parent_id:
        parent = BrandingMessage.objects.filter(pk=parent_id, request=req).first()
        if not parent:
            return JsonResponse({'error': 'Parent message not found.'}, status=400)

    msg = BrandingMessage.objects.create(
        request=req,
        sender=request.user,
        parent=parent,
        content=content,
        is_read_by_client=request.user == req.user,
        is_read_by_staff=request.user.is_staff,
    )

    req.log(
        'COMMENT',
        f"{'Staff' if request.user.is_staff else 'Client'} message sent",
        content[:160],
        actor=request.user,
    )

    # Notify the other party
    if request.user.is_staff and req.user:
        _notify(
            req.user,
            req,
            'COMMENT',
            f"New message on {req.request_number}: {content[:120]}",
            email_subject=f"[OnWebApp Branding] New message — {req.request_number}",
            template_name='emails/message_notification.html',
            template_context={
                'request_number': req.request_number,
                'company_name': req.company_name,
                'sender_name': request.user.get_full_name() or request.user.username,
                'message_preview': content[:300],
                'message_truncated': len(content) > 300,
                'action_url': f"{SITE_URL}/branding/requests/{req.pk}/#messages",
            },
        )
    elif not request.user.is_staff:
        for staff in User.objects.filter(is_staff=True):
            _notify(
                staff,
                req,
                'COMMENT',
                f"Client message on {req.request_number} from {request.user.username}: {content[:120]}",
            )

    return JsonResponse({
        'ok': True,
        'message': {
            'id': msg.pk,
            'content': msg.content,
            'sender': request.user.get_full_name() or request.user.username,
            'sender_id': request.user.pk,
            'sender_is_staff': request.user.is_staff,
            'parent_id': msg.parent_id,
            'created_at': msg.created_at.strftime('%b %d, %Y %H:%M'),
        },
    })


@login_required
@require_POST
def mark_message_read(request, pk):
    """AJAX endpoint: mark a single message as read by the current user."""
    msg = get_object_or_404(BrandingMessage, pk=pk)
    if msg.request.user != request.user and not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    msg.mark_read(request.user)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def mark_thread_read(request, pk):
    """AJAX endpoint: mark all messages in a thread as read by the current user."""
    msg = get_object_or_404(BrandingMessage, pk=pk)
    if msg.request.user != request.user and not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    root = msg.parent or msg
    thread_ids = [root.pk] + list(
        BrandingMessage.objects.filter(parent=root).values_list('pk', flat=True)
    )
    updated = 0
    for m in BrandingMessage.objects.filter(pk__in=thread_ids):
        before = m.is_read_by_staff if request.user.is_staff else m.is_read_by_client
        m.mark_read(request.user)
        if not before:
            updated += 1

    return JsonResponse({'ok': True, 'marked': updated})


@login_required
def unread_message_count(request):
    """AJAX endpoint: return the user's total unread message count."""
    count = BrandingMessage.get_unread_count(request.user)
    return JsonResponse({'count': count})


@login_required
def poll_messages(request, pk):
    """AJAX endpoint: return messages newer than `since` for live polling."""
    req = get_object_or_404(BrandingRequest, pk=pk)
    if req.user != request.user and not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    since_id = request.GET.get('since', '0')
    try:
        since_id = int(since_id)
    except (TypeError, ValueError):
        since_id = 0

    new_msgs = BrandingMessage.objects.filter(
        request=req, pk__gt=since_id,
    ).select_related('sender').order_by('created_at')

    data = []
    for m in new_msgs:
        data.append({
            'id': m.pk,
            'content': m.content,
            'sender': m.sender.get_full_name() or m.sender.username,
            'sender_id': m.sender_id,
            'sender_is_staff': m.sender.is_staff,
            'parent_id': m.parent_id,
            'created_at': m.created_at.strftime('%b %d, %Y %H:%M'),
            'is_own': m.sender == request.user,
        })

    return JsonResponse({'ok': True, 'messages': data, 'count': len(data)})


@login_required
@require_POST
def mark_visible_read(request, pk):
    """AJAX endpoint: mark all messages on this request as read by the current user."""
    req = get_object_or_404(BrandingRequest, pk=pk)
    if req.user != request.user and not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    updated = 0
    for msg in BrandingMessage.objects.filter(request=req):
        before = msg.is_read_by_staff if request.user.is_staff else msg.is_read_by_client
        msg.mark_read(request.user)
        if not before:
            updated += 1

    return JsonResponse({'ok': True, 'marked': updated})


# ---------------------------------------------------------------------------
# Feedback / Reviews
# ---------------------------------------------------------------------------

@login_required
def feedback_create(request, pk):
    """Client submits feedback on a completed request. One per request."""
    req = get_object_or_404(BrandingRequest, pk=pk, user=request.user, status='COMPLETED')

    if BrandingFeedback.objects.filter(request=req).exists():
        messages.info(request, 'You have already submitted feedback for this request.')
        return redirect('branding:request_detail', pk=pk)

    if request.method == 'POST':
        try:
            rating = int(request.POST.get('rating', 0))
        except (TypeError, ValueError):
            rating = 0
        if rating not in range(1, 6):
            messages.error(request, 'Please select a rating from 1 to 5.')
            return redirect('branding:request_detail', pk=pk)

        comment = request.POST.get('comment', '').strip()
        would_recommend = request.POST.get('would_recommend') == 'on'

        BrandingFeedback.objects.create(
            request=req,
            rating=rating,
            comment=comment,
            would_recommend=would_recommend,
        )
        invalidate_after_status_change()
        messages.success(request, 'Thank you for your feedback!')
        return redirect('branding:request_detail', pk=pk)

    return redirect('branding:request_detail', pk=pk)


@login_required
def feedback_update(request, pk):
    """Staff responds to feedback or updates the staff response."""
    fb = get_object_or_404(BrandingFeedback, pk=pk)
    if not request.user.is_staff:
        return redirect('branding:landing')

    if request.method == 'POST':
        fb.staff_response = request.POST.get('staff_response', '').strip()
        fb.responded_by = request.user
        fb.responded_at = timezone.now()
        fb.save(update_fields=['staff_response', 'responded_by', 'responded_at', 'updated_at'])
        invalidate_after_status_change()
        messages.success(request, 'Response saved.')
    return redirect('branding:request_detail', pk=fb.request.pk)


@staff_member_required
def feedback_list(request):
    """Staff dashboard: view all client feedback."""
    qs = BrandingFeedback.objects.select_related('request', 'request__user', 'request__collection', 'responded_by')

    # Filters
    rating_filter = request.GET.get('rating', '')
    search = request.GET.get('q', '').strip()
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if rating_filter:
        try:
            qs = qs.filter(rating=int(rating_filter))
        except (TypeError, ValueError):
            pass
    if search:
        qs = qs.filter(
            Q(request__company_name__icontains=search) |
            Q(request__request_number__icontains=search) |
            Q(request__user__username__icontains=search)
        )
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    paginator = Paginator(qs, 12)
    page = paginator.get_page(request.GET.get('page'))

    # Aggregate stats
    from django.db.models import Avg
    avg_rating = BrandingFeedback.objects.aggregate(avg=Avg('rating'))['avg']
    total = BrandingFeedback.objects.count()
    recommend_count = BrandingFeedback.objects.filter(would_recommend=True).count()

    return render(request, 'branding/feedback_list.html', {
        'feedbacks': page,
        'avg_rating': avg_rating,
        'total_count': total,
        'recommend_count': recommend_count,
        'rating_filter': rating_filter,
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
    })


# ---------------------------------------------------------------------------
# PDF Report
# ---------------------------------------------------------------------------

@login_required
def download_project_pdf(request, pk):
    """Download a PDF summary report for a branding request."""
    req = get_object_or_404(BrandingRequest, pk=pk)

    if req.user != request.user and not request.user.is_staff:
        raise Http404

    from .reports import ProjectSummaryReport
    report = ProjectSummaryReport(req)
    return report.generate_pdf()


@staff_member_required
def analytics_report(request):
    """Generate and download the analytics PDF report."""
    months = int(request.GET.get('months', 6))
    months = max(1, min(months, 24))

    from .reports import AnalyticsReport
    report = AnalyticsReport(months=months)
    return report.generate_pdf()


# ---------------------------------------------------------------------------
# GDPR — Data export
# ---------------------------------------------------------------------------

@login_required
def request_data_export(request):
    """Allow a user to request a data export (GDPR Article 20)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    export_format = request.POST.get('format', 'json')
    if export_format not in ('json', 'csv'):
        export_format = 'json'

    from .models import DataExportRequest

    # Check for a recent pending/processing request
    recent = DataExportRequest.objects.filter(
        user=request.user,
        status__in=[DataExportRequest.STATUS_PENDING, DataExportRequest.STATUS_PROCESSING],
    ).first()
    if recent:
        return JsonResponse({
            'ok': True,
            'message': 'Your export is being processed. You will be notified when it is ready.',
            'request_id': recent.pk,
            'status': recent.status,
        })

    req = DataExportRequest.objects.create(
        user=request.user,
        export_format=export_format,
    )

    # Queue async processing
    try:
        from .tasks import task_process_data_export
        task_process_data_export.delay(req.pk)
    except Exception:
        pass

    return JsonResponse({
        'ok': True,
        'message': 'Your data export has been requested. You will be notified when it is ready.',
        'request_id': req.pk,
    })


@login_required
def download_data_export(request, pk):
    """Download a completed data export."""
    from .models import DataExportRequest

    req = get_object_or_404(DataExportRequest, pk=pk, user=request.user)

    if req.status != DataExportRequest.STATUS_READY:
        return JsonResponse({'error': 'Export is not ready yet.'}, status=400)

    if req.expires_at and req.expires_at < timezone.now():
        return JsonResponse({'error': 'Export has expired.'}, status=410)

    if req.file:
        from django.http import FileResponse
        return FileResponse(req.file.open('rb'), as_attachment=True,
                            filename=f'branding_data_export.{req.export_format}')

    return JsonResponse({'error': 'Export file not found.'}, status=404)


@login_required
def data_export_list(request):
    """List all data export requests for the current user."""
    from .models import DataExportRequest

    exports = DataExportRequest.objects.filter(user=request.user)[:10]
    data = [{
        'id': e.pk,
        'status': e.status,
        'format': e.export_format,
        'requested_at': e.requested_at.isoformat(),
        'completed_at': e.completed_at.isoformat() if e.completed_at else None,
        'expires_at': e.expires_at.isoformat() if e.expires_at else None,
        'download_url': f'/branding/gdpr/export/{e.pk}/download/' if e.status == 'ready' else None,
    } for e in exports]

    return JsonResponse({'exports': data})


# ---------------------------------------------------------------------------
# GDPR — Consent management
# ---------------------------------------------------------------------------

@login_required
def update_consent(request):
    """Update consent preferences for the current user."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    consent_type = request.POST.get('consent_type', '')
    action = request.POST.get('action', '')  # 'grant' or 'revoke'

    valid_types = ['data_processing', 'marketing', 'analytics', 'third_party']
    if consent_type not in valid_types:
        return JsonResponse({'error': f'Invalid consent type. Must be one of: {", ".join(valid_types)}'}, status=400)
    if action not in ('grant', 'revoke'):
        return JsonResponse({'error': 'Action must be "grant" or "revoke".'}, status=400)

    from .gdpr import record_consent
    record_consent(
        request.user,
        consent_type,
        'granted' if action == 'grant' else 'revoked',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:200],
    )

    return JsonResponse({
        'ok': True,
        'consent_type': consent_type,
        'action': action,
    })


@login_required
def consent_history(request):
    """View consent history for the current user."""
    from .models import ConsentRecord

    records = ConsentRecord.objects.filter(user=request.user)[:50]
    data = [{
        'consent_type': c.consent_type,
        'action': c.action,
        'timestamp': c.created_at.isoformat(),
    } for c in records]

    return JsonResponse({'consents': data})


@login_required
def privacy_accept(request):
    """Accept or revoke a privacy document."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    page = request.POST.get('page', '')
    version = request.POST.get('version', '1.0')
    accepted = request.POST.get('accepted', 'true').lower() == 'true'

    valid_pages = ['privacy_policy', 'terms_of_service', 'cookie_policy']
    if page not in valid_pages:
        return JsonResponse({'error': f'Invalid page. Must be one of: {", ".join(valid_pages)}'}, status=400)

    from .gdpr import record_privacy_acceptance
    obj = record_privacy_acceptance(
        request.user, page, version, accepted,
        ip_address=request.META.get('REMOTE_ADDR'),
    )

    return JsonResponse({
        'ok': True,
        'page': page,
        'accepted': accepted,
        'version': obj.version,
    })


# ---------------------------------------------------------------------------
# GDPR — Anonymization (staff only)
# ---------------------------------------------------------------------------

@staff_member_required
def anonymize_request_view(request, pk):
    """Manually anonymize a specific request (staff only)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    req = get_object_or_404(BrandingRequest, pk=pk)

    if req.anonymized:
        return JsonResponse({'error': 'Request is already anonymized.'}, status=400)

    from .gdpr import anonymize_request
    counts = anonymize_request(req, keep_analytics=True)

    req.log('ANONYMIZED', 'Request data anonymized', actor=request.user)

    return JsonResponse({
        'ok': True,
        'message': f'Request {req.request_number} has been anonymized.',
        'counts': counts,
    })


# ---------------------------------------------------------------------------
# Email testing (staff only)
# ---------------------------------------------------------------------------

EMAIL_TEST_TEMPLATES = {
    'status_update': 'emails/status_update.html',
    'assignment': 'emails/assignment.html',
    'completion': 'emails/completion.html',
    'feedback_request': 'emails/feedback_request.html',
    'message_notification': 'emails/message_notification.html',
}


@staff_member_required
def test_email(request):
    """Send a test email to verify email template rendering.

    GET: show form with template selector.
    POST: send the selected test email.
    """
    from django.contrib import messages as view_messages

    if request.method == 'POST':
        template_key = request.POST.get('template', 'status_update')
        to_email = request.POST.get('email', '').strip()

        if not to_email:
            view_messages.error(request, 'Please enter an email address.')
            return redirect('branding:test_email')

        template_name = EMAIL_TEST_TEMPLATES.get(template_key)
        if not template_name:
            view_messages.error(request, 'Invalid template selected.')
            return redirect('branding:test_email')

        from .emails import send_test_email
        sent = send_test_email(to_email, template_name)

        if sent:
            view_messages.success(request, f'Test "{template_key}" email sent to {to_email}.')
        else:
            view_messages.error(request, f'Failed to send email to {to_email}. Check email config.')

        return redirect('branding:test_email')

    return render(request, 'branding/test_email.html', {
        'templates': EMAIL_TEST_TEMPLATES,
    })


# ---------------------------------------------------------------------------
# Analytics Dashboard
# ---------------------------------------------------------------------------

@staff_member_required
def analytics_overview(request):
    """Main analytics dashboard with charts and KPIs."""
    from .analytics import (
        _parse_date_range, get_overview_metrics,
        get_requests_over_time, export_analytics_csv,
    )

    date_from, date_to = _parse_date_range(request)

    # CSV export
    if request.GET.get('export') == 'csv':
        return export_analytics_csv(date_from, date_to)

    overview = get_overview_metrics(date_from, date_to)
    timeline = get_requests_over_time(date_from, date_to)

    return render(request, 'branding/analytics/overview.html', {
        'overview': overview,
        'timeline': json.dumps(timeline),
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
        'page_title': 'Analytics Overview',
    })


@staff_member_required
def analytics_staff(request):
    """Staff performance analytics."""
    from .analytics import _parse_date_range, get_staff_metrics

    date_from, date_to = _parse_date_range(request)
    staff_metrics = get_staff_metrics(date_from, date_to)

    # Chart data
    chart_data = {
        'labels': [m['user'].get_full_name() or m['user'].username for m in staff_metrics],
        'assigned': [m['assigned'] for m in staff_metrics],
        'completed': [m['completed'] for m in staff_metrics],
        'messages': [m['messages'] for m in staff_metrics],
    }

    return render(request, 'branding/analytics/staff.html', {
        'staff_metrics': staff_metrics,
        'chart_data': json.dumps(chart_data),
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
        'page_title': 'Staff Performance',
    })


@staff_member_required
def analytics_collections(request):
    """Collection popularity analytics."""
    from .analytics import _parse_date_range, get_collection_metrics

    date_from, date_to = _parse_date_range(request)
    collection_metrics = get_collection_metrics(date_from, date_to)

    # Chart data
    chart_data = {
        'labels': [m['collection'].name for m in collection_metrics if m['total_requests'] > 0],
        'requests': [m['total_requests'] for m in collection_metrics if m['total_requests'] > 0],
        'completed': [m['completed'] for m in collection_metrics if m['total_requests'] > 0],
        'completion_rates': [m['completion_rate'] for m in collection_metrics if m['total_requests'] > 0],
    }

    return render(request, 'branding/analytics/collections.html', {
        'collection_metrics': collection_metrics,
        'chart_data': json.dumps(chart_data),
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
        'page_title': 'Collection Performance',
    })


@staff_member_required
def analytics_timeline(request):
    """Time-based analytics with monthly trends."""
    from .analytics import _parse_date_range, get_timeline_metrics, get_overview_metrics

    date_from, date_to = _parse_date_range(request)
    timeline = get_timeline_metrics(date_from, date_to)
    overview = get_overview_metrics(date_from, date_to)

    return render(request, 'branding/analytics/timeline.html', {
        'timeline': json.dumps(timeline),
        'overview': overview,
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
        'page_title': 'Timeline Analytics',
    })


# ---------------------------------------------------------------------------
# Supervisor Dashboard
# ---------------------------------------------------------------------------

ACTIVE_STATUSES = ['PENDING_REVIEW', 'IN_REVIEW', 'ASSIGNED', 'DESIGNING', 'WAITING_CLIENT', 'REVISION', 'APPROVED']
WORKLOAD_THRESHOLD = 5


def _designer_performance():
    """Compute per-designer performance metrics."""
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    designers = User.objects.filter(is_staff=True, is_active=True).order_by('username')

    perf = []
    for d in designers:
        active = BrandingRequest.objects.filter(
            designer=d, status__in=ACTIVE_STATUSES
        ).count()
        completed_month = BrandingRequest.objects.filter(
            designer=d, status='COMPLETED', completed_at__gte=month_start
        ).count()

        avg_comp = BrandingRequest.objects.filter(
            designer=d, status='COMPLETED', completed_at__isnull=False
        ).aggregate(avg=Avg(F('completed_at') - F('created_at')))['avg']
        avg_days = round(avg_comp.total_seconds() / 86400, 1) if avg_comp else None

        on_time_total = BrandingRequest.objects.filter(
            designer=d, status='COMPLETED', estimated_delivery_date__isnull=False
        ).count()
        on_time_done = BrandingRequest.objects.filter(
            designer=d, status='COMPLETED',
            completed_at__date__lte=F('estimated_delivery_date'),
        ).count() if on_time_total else 0
        on_time_pct = round(on_time_done / on_time_total * 100) if on_time_total else None

        perf.append({
            'user': d,
            'active': active,
            'completed_month': completed_month,
            'avg_days': avg_days,
            'on_time_pct': on_time_pct,
            'is_overloaded': active > WORKLOAD_THRESHOLD,
        })

    return perf


def _overdue_qs():
    """Return queryset of non-draft requests past their EDD."""
    return BrandingRequest.objects.filter(
        estimated_delivery_date__lt=timezone.now().date(),
        status__in=ACTIVE_STATUSES,
    )


@supervisor_required
def supervisor_dashboard(request):
    qs = BrandingRequest.objects.exclude(status='DRAFT').select_related(
        'user', 'designer', 'collection'
    )

    tab = request.GET.get('tab', 'overview')
    project_filter = request.GET.get('filter', '')
    project_sort = request.GET.get('sort', '-created_at')
    page_num = request.GET.get('page')

    # ---- Key metrics ----
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    agg = qs.aggregate(
        active=Count('id', filter=Q(status__in=ACTIVE_STATUSES)),
        pending=Count('id', filter=Q(status='PENDING_REVIEW')),
        in_review=Count('id', filter=Q(status='IN_REVIEW')),
        assigned=Count('id', filter=Q(status='ASSIGNED')),
        designing=Count('id', filter=Q(status='DESIGNING')),
        waiting=Count('id', filter=Q(status='WAITING_CLIENT')),
        revision=Count('id', filter=Q(status='REVISION')),
        completed=Count('id', filter=Q(status='COMPLETED')),
        completed_month=Count('id', filter=Q(status='COMPLETED', completed_at__gte=month_start)),
        overdue=Count('id', filter=Q(
            estimated_delivery_date__lt=now.date(), status__in=ACTIVE_STATUSES
        )),
        unassigned_old=Count('id', filter=Q(
            designer__isnull=True, status='PENDING_REVIEW',
            created_at__lt=now - timedelta(hours=24),
        )),
        avg_seconds=Avg(
            F('completed_at') - F('created_at'),
            filter=Q(status='COMPLETED', completed_at__isnull=False),
        ),
    )
    active_designers = User.objects.filter(
        is_staff=True, is_active=True,
        branding_design_assignments__status__in=ACTIVE_STATUSES,
    ).distinct().count()

    total_designers = User.objects.filter(is_staff=True, is_active=True).count()
    avg_days = round(agg['avg_seconds'].total_seconds() / 86400, 1) if agg['avg_seconds'] else None
    workload_balance = round(agg['active'] / active_designers, 1) if active_designers else 0

    # Feedback satisfaction
    satisfaction = BrandingFeedback.objects.aggregate(
        avg=Avg('rating')
    )['avg']
    satisfaction_pct = round(satisfaction / 5 * 100, 1) if satisfaction else None

    # ---- Charts data ----
    # Requests over last 30 days
    thirty_days_ago = now - timedelta(days=30)
    daily_created = list(
        qs.filter(created_at__date__gte=thirty_days_ago.date())
        .values_list('created_at__date').annotate(c=Count('id')).order_by('created_at__date')
    )
    daily_completed = list(
        qs.filter(completed_at__date__gte=thirty_days_ago.date(), status='COMPLETED')
        .values_list('completed_at__date').annotate(c=Count('id')).order_by('completed_at__date')
    )
    created_map = {str(d): c for d, c in daily_created}
    completed_map = {str(d): c for d, c in daily_completed}
    chart_dates = []
    chart_created = []
    chart_completed = []
    for i in range(30, -1, -1):
        d = (thirty_days_ago + timedelta(days=i)).date()
        ds = str(d)
        chart_dates.append(d.strftime('%b %d'))
        chart_created.append(created_map.get(ds, 0))
        chart_completed.append(completed_map.get(ds, 0))

    # Status distribution
    status_dist = list(
        qs.values('status').annotate(c=Count('id')).order_by('-c')
    )
    status_labels = [s['status'].replace('_', ' ').title() for s in status_dist]
    status_counts = [s['c'] for s in status_dist]

    # Priority distribution
    priority_dist = list(
        qs.values('priority').annotate(c=Count('id')).order_by('-c')
    )
    priority_labels = [p['priority'].title() for p in priority_dist]
    priority_counts = [p['c'] for p in priority_dist]

    # Workload per designer
    perf = _designer_performance()
    workload_labels = [p['user'].get_full_name() or p['user'].username for p in perf if p['active'] > 0]
    workload_values = [p['active'] for p in perf if p['active'] > 0]

    # ---- Alerts ----
    alerts = []
    unassigned_urgent = qs.filter(designer__isnull=True, status='PENDING_REVIEW').order_by('created_at')[:5]
    for r in unassigned_urgent:
        hours = int((now - r.created_at).total_seconds() / 3600)
        alerts.append({
            'type': 'warning',
            'icon': 'fa-user-slash',
            'text': f'{r.request_number} ({r.company_name}) unassigned for {hours}h',
            'url': r.get_absolute_url(),
        })

    overdue_requests = _overdue_qs().select_related('designer').order_by('estimated_delivery_date')[:5]
    for r in overdue_requests:
        alerts.append({
            'type': 'danger',
            'icon': 'fa-triangle-exclamation',
            'text': f'{r.request_number} overdue — due {r.estimated_delivery_date|date:"M j"}',
            'url': r.get_absolute_url(),
        })

    high_priority = qs.filter(
        priority__in=['HIGH', 'URGENT'], status__in=ACTIVE_STATUSES
    ).select_related('designer').order_by('-priority', 'created_at')[:5]
    for r in high_priority:
        alerts.append({
            'type': 'info' if r.priority == 'HIGH' else 'danger',
            'icon': 'fa-fire' if r.priority == 'URGENT' else 'fa-arrow-up',
            'text': f'{r.request_number} — {r.get_priority_display()} priority',
            'url': r.get_absolute_url(),
        })

    overloaded = [p for p in perf if p['is_overloaded']]
    for p in overloaded:
        alerts.append({
            'type': 'warning',
            'icon': 'fa-weight-hanging',
            'text': f'{p["user"].get_full_name() or p["user"].username} — {p["active"]} active projects',
            'url': '#staff-tab',
        })

    # ---- Activity feed ----
    activity_filter = request.GET.get('activity_type', '')
    activity_qs = BrandingTimeline.objects.select_related('request', 'actor').order_by('-created_at')
    if activity_filter:
        activity_qs = activity_qs.filter(event_type=activity_filter)
    activity_paginator = Paginator(activity_qs, 15)
    activity_page = activity_paginator.get_page(request.GET.get('activity_page'))

    # ---- Projects list ----
    if project_filter == 'pending':
        qs = qs.filter(status='PENDING_REVIEW')
    elif project_filter == 'review':
        qs = qs.filter(status='IN_REVIEW')
    elif project_filter == 'overdue':
        qs = _overdue_qs()
    elif project_filter == 'unassigned':
        qs = qs.filter(designer__isnull=True, status__in=ACTIVE_STATUSES)

    valid_sorts = {
        'created_at': 'created_at',
        '-created_at': '-created_at',
        'priority': 'priority',
        '-priority': '-priority',
        'company_name': 'company_name',
        '-company_name': '-company_name',
        'status': 'status',
    }
    qs = qs.order_by(valid_sorts.get(project_sort, '-created_at'))

    project_paginator = Paginator(qs, 15)
    project_page = project_paginator.get_page(page_num)

    designers = cache_get_or_set(
        designers_key(),
        lambda: list(User.objects.filter(is_staff=True).order_by('username')),
        TIMEOUT_DESIGNERS,
    )

    return render(request, 'branding/supervisor_dashboard.html', {
        'tab': tab,
        # Metrics
        'active_count': agg['active'],
        'pending_count': agg['pending'],
        'in_review_count': agg['in_review'],
        'assigned_count': agg['assigned'],
        'designing_count': agg['designing'],
        'waiting_count': agg['waiting'],
        'revision_count': agg['revision'],
        'completed_count': agg['completed'],
        'completed_month_count': agg['completed_month'],
        'overdue_count': agg['overdue'],
        'unassigned_old_count': agg['unassigned_old'],
        'active_designers': active_designers,
        'total_designers': total_designers,
        'avg_days': avg_days,
        'workload_balance': workload_balance,
        'satisfaction_pct': satisfaction_pct,
        # Charts
        'chart_dates': json.dumps(chart_dates),
        'chart_created': json.dumps(chart_created),
        'chart_completed': json.dumps(chart_completed),
        'status_labels': json.dumps(status_labels),
        'status_counts': json.dumps(status_counts),
        'priority_labels': json.dumps(priority_labels),
        'priority_counts': json.dumps(priority_counts),
        'workload_labels': json.dumps(workload_labels),
        'workload_values': json.dumps(workload_values),
        # Staff performance
        'designer_performance': perf,
        # Projects
        'projects': project_page,
        'project_filter': project_filter,
        'project_sort': project_sort,
        # Activity
        'activity': activity_page,
        'activity_filter': activity_filter,
        # Alerts
        'alerts': alerts,
        # Designers list for assign modal
        'designers': designers,
        # Statuses for bulk actions
        'status_choices': [s for s in STATUS_CHOICES if s[0] != 'DRAFT'],
        'today': now.date(),
    })


# ────────────────────────────────────────────────────────────────────────────
# Supervisor — Designer Detail
# ────────────────────────────────────────────────────────────────────────────

@supervisor_required
def supervisor_designer_detail(request, user_id):
    designer = get_object_or_404(User, pk=user_id, is_staff=True, is_active=True)
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # ── Metrics ──
    all_assigned = BrandingRequest.objects.filter(designer=designer).exclude(status='DRAFT')
    active_qs = all_assigned.filter(status__in=ACTIVE_STATUSES)
    completed_qs = all_assigned.filter(status='COMPLETED', completed_at__isnull=False)

    total_assigned = all_assigned.count()
    active_count = active_qs.count()
    completed_count = completed_qs.count()
    completed_month = completed_qs.filter(completed_at__gte=month_start).count()

    avg_comp = completed_qs.aggregate(
        avg=Avg(F('completed_at') - F('created_at'))
    )['avg']
    avg_days = round(avg_comp.total_seconds() / 86400, 1) if avg_comp else None

    on_time_total = all_assigned.filter(
        status='COMPLETED', estimated_delivery_date__isnull=False
    ).count()
    on_time_done = all_assigned.filter(
        status='COMPLETED',
        completed_at__date__lte=F('estimated_delivery_date'),
    ).count() if on_time_total else 0
    on_time_pct = round(on_time_done / on_time_total * 100) if on_time_total else None

    # Client ratings
    rating_agg = BrandingFeedback.objects.filter(
        request__designer=designer
    ).aggregate(avg=Avg('rating'), count=Count('id'))
    satisfaction_avg = round(rating_agg['avg'], 1) if rating_agg['avg'] else None
    feedback_count = rating_agg['count']

    # Status distribution
    status_dist = list(
        all_assigned.values('status').annotate(c=Count('id')).order_by('-c')
    )

    # ── Current projects ──
    current_projects = active_qs.select_related('user').order_by(
        '-priority', 'created_at'
    )[:20]

    # ── Completed projects with ratings ──
    completed_projects = completed_qs.select_related('user').order_by(
        '-completed_at'
    )[:20]
    # Fetch feedbacks for completed projects
    feedback_map = {}
    if completed_projects:
        fb_ids = [p.pk for p in completed_projects]
        fbs = BrandingFeedback.objects.filter(
            request_id__in=fb_ids
        ).values_list('request_id', 'rating')
        feedback_map = dict(fbs)

    # ── Notes ──
    notes = DesignerNote.objects.filter(designer=designer).select_related('author')

    if request.method == 'POST' and request.POST.get('action') == 'add_note':
        content = request.POST.get('content', '').strip()
        if content:
            DesignerNote.objects.create(
                designer=designer,
                author=request.user,
                content=content,
            )
            invalidate_designer_detail(user_id)
            return redirect('branding:supervisor_designer_detail', user_id=user_id)

    is_overloaded = active_count > WORKLOAD_THRESHOLD

    return render(request, 'branding/supervisor/designer_detail.html', {
        'designer': designer,
        'total_assigned': total_assigned,
        'active_count': active_count,
        'completed_count': completed_count,
        'completed_month': completed_month,
        'avg_days': avg_days,
        'on_time_pct': on_time_pct,
        'on_time_done': on_time_done,
        'on_time_total': on_time_total,
        'satisfaction_avg': satisfaction_avg,
        'feedback_count': feedback_count,
        'status_dist': status_dist,
        'current_projects': current_projects,
        'completed_projects': completed_projects,
        'feedback_map': feedback_map,
        'notes': notes,
        'is_overloaded': is_overloaded,
        'WORKLOAD_THRESHOLD': WORKLOAD_THRESHOLD,
        'today': now.date(),
    })


# ────────────────────────────────────────────────────────────────────────────
# Supervisor — Team Overview
# ────────────────────────────────────────────────────────────────────────────

@supervisor_required
def supervisor_team(request):
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    designers = User.objects.filter(is_staff=True, is_active=True).order_by('username')

    team_data = []
    for d in designers:
        active = BrandingRequest.objects.filter(
            designer=d, status__in=ACTIVE_STATUSES
        ).count()
        completed = BrandingRequest.objects.filter(
            designer=d, status='COMPLETED'
        ).count()
        completed_month = BrandingRequest.objects.filter(
            designer=d, status='COMPLETED', completed_at__gte=month_start
        ).count()

        avg_comp = BrandingRequest.objects.filter(
            designer=d, status='COMPLETED', completed_at__isnull=False
        ).aggregate(avg=Avg(F('completed_at') - F('created_at')))['avg']
        avg_days = round(avg_comp.total_seconds() / 86400, 1) if avg_comp else None

        on_time_total = BrandingRequest.objects.filter(
            designer=d, status='COMPLETED', estimated_delivery_date__isnull=False
        ).count()
        on_time_done = BrandingRequest.objects.filter(
            designer=d, status='COMPLETED',
            completed_at__date__lte=F('estimated_delivery_date'),
        ).count() if on_time_total else 0
        on_time_pct = round(on_time_done / on_time_total * 100) if on_time_total else None

        rating_agg = BrandingFeedback.objects.filter(
            request__designer=d
        ).aggregate(avg=Avg('rating'), count=Count('id'))
        satisfaction = round(rating_agg['avg'], 1) if rating_agg['avg'] else None

        team_data.append({
            'user': d,
            'active': active,
            'completed': completed,
            'completed_month': completed_month,
            'avg_days': avg_days,
            'on_time_pct': on_time_pct,
            'satisfaction': satisfaction,
            'feedback_count': rating_agg['count'],
            'is_overloaded': active > WORKLOAD_THRESHOLD,
        })

    # Sort by active count descending
    team_data.sort(key=lambda x: (-x['active'], x['user'].username))

    return render(request, 'branding/supervisor/team.html', {
        'team_data': team_data,
        'WORKLOAD_THRESHOLD': WORKLOAD_THRESHOLD,
        'today': now.date(),
    })


# ────────────────────────────────────────────────────────────────────────────
# Supervisor — Team PDF Report
# ────────────────────────────────────────────────────────────────────────────

@supervisor_required
def supervisor_team_pdf(request):
    from .reports import TeamPerformanceReport
    report = TeamPerformanceReport()
    return report.render_response()


# ────────────────────────────────────────────────────────────────────────────
# Designer Dashboard
# ────────────────────────────────────────────────────────────────────────────

DESIGNER_ACTIVE_STATUSES = ['ASSIGNED', 'DESIGNING', 'WAITING_CLIENT', 'REVISION']
DESIGNER_UPCOMING_STATUSES = ['IN_REVIEW', 'PENDING_REVIEW']


@designer_required
def designer_dashboard(request):
    me = request.user
    now = timezone.now()
    today = now.date()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    my_projects = BrandingRequest.objects.filter(designer=me).exclude(status='DRAFT')

    # ── Metrics ──
    active_qs = my_projects.filter(status__in=DESIGNER_ACTIVE_STATUSES)
    active_count = active_qs.count()

    overdue_qs = active_qs.filter(estimated_delivery_date__lt=today)
    overdue_count = overdue_qs.count()

    today_deadline_qs = active_qs.filter(estimated_delivery_date=today)
    today_deadline_count = today_deadline_qs.count()

    waiting_feedback_qs = my_projects.filter(status='WAITING_CLIENT')
    waiting_feedback_count = waiting_feedback_qs.count()

    completed_qs = my_projects.filter(status='COMPLETED', completed_at__isnull=False)
    completed_total = completed_qs.count()
    completed_month = completed_qs.filter(completed_at__gte=month_start).count()

    avg_comp = completed_qs.aggregate(
        avg=Avg(F('completed_at') - F('created_at'))
    )['avg']
    avg_days = round(avg_comp.total_seconds() / 86400, 1) if avg_comp else None

    # Completion rate this month (completed / total assigned this month)
    assigned_month = my_projects.filter(created_at__gte=month_start).count()
    completion_rate = round(completed_month / assigned_month * 100) if assigned_month else None

    # Next deadline
    next_deadline = active_qs.filter(
        estimated_delivery_date__gte=today
    ).order_by('estimated_delivery_date').values_list('estimated_delivery_date', flat=True).first()

    # Days until next deadline
    days_to_next = (next_deadline - today).days if next_deadline else None

    # ── Project Lists ──
    active_projects = active_qs.select_related('user', 'collection').order_by(
        '-priority', 'estimated_delivery_date', 'created_at'
    )

    waiting_projects = waiting_feedback_qs.select_related('user', 'collection').order_by(
        'estimated_delivery_date', 'created_at'
    )

    completed_projects = completed_qs.select_related('user', 'collection').order_by(
        '-completed_at'
    )[:20]

    upcoming_qs = my_projects.filter(
        status__in=DESIGNER_UPCOMING_STATUSES
    ).select_related('user', 'collection').order_by('-priority', 'created_at')
    upcoming_projects = upcoming_qs[:20]

    # ── Today's Priority (sorted by urgency) ──
    priority_projects = active_qs.select_related('user', 'collection')
    # Overdue first, then by priority weight, then by nearest deadline
    priority_order = {'URGENT': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    priority_projects = sorted(
        priority_projects,
        key=lambda r: (
            0 if r.estimated_delivery_date and r.estimated_delivery_date < today else 1,
            priority_order.get(r.priority, 9),
            r.estimated_delivery_date or timezone.now().date() + timedelta(days=365),
        )
    )

    # ── Weekly Overview (deadlines this week + next week) ──
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    next_week_end = week_end + timedelta(days=7)

    weekly_deadlines = active_qs.filter(
        estimated_delivery_date__gte=week_start,
        estimated_delivery_date__lte=next_week_end,
    ).select_related('user').order_by('estimated_delivery_date')

    # Group by day for calendar
    calendar_days = []
    for i in range(14):
        day = week_start + timedelta(days=i)
        day_projects = [r for r in weekly_deadlines if r.estimated_delivery_date == day]
        calendar_days.append({
            'date': day,
            'is_today': day == today,
            'is_weekend': day.weekday() >= 5,
            'projects': day_projects,
            'count': len(day_projects),
        })

    # Workload distribution (days of week for next 2 weeks)
    workload_by_day = {}
    for i in range(14):
        day = week_start + timedelta(days=i)
        day_name = day.strftime('%a')
        count = sum(1 for r in weekly_deadlines if r.estimated_delivery_date == day)
        if day_name not in workload_by_day:
            workload_by_day[day_name] = 0
        workload_by_day[day_name] += count

    # ── Notifications (recent for me) ──
    recent_notifications = BrandingNotification.objects.filter(
        recipient=me, is_read=False
    ).select_related('request')[:10]

    # ── Status update handling ──
    if request.method == 'POST':
        action = request.POST.get('action')
        req_pk = request.POST.get('request_pk')

        if action and req_pk:
            req = get_object_or_404(BrandingRequest, pk=req_pk, designer=me)
            new_status = request.POST.get('new_status', '')

            if action == 'update_status' and new_status:
                valid_designer_statuses = ['DESIGNING', 'WAITING_CLIENT', 'COMPLETED']
                if new_status in valid_designer_statuses:
                    req.status = new_status
                    if new_status == 'COMPLETED':
                        req.completed_at = now
                    req.save(update_fields=['status', 'completed_at', 'updated_at'])
                    req.log('STATUS_CHANGE',
                            f'Status changed to {req.get_status_display()} by designer',
                            actor=me)
                    if new_status == 'WAITING_CLIENT':
                        _notify(
                            req.user, req, 'STATUS_CHANGED',
                            f'Your project {req.request_number} is ready for your review.',
                            actor=me,
                        )
                    elif new_status == 'COMPLETED':
                        _notify(
                            req.user, req, 'COMPLETED',
                            f'Your project {req.request_number} has been completed!',
                            actor=me,
                        )
                    messages.success(request, f'{req.request_number} updated to {req.get_status_display()}')
                    invalidate_after_status_change(me.pk)

            elif action == 'start_working':
                if req.status == 'ASSIGNED':
                    req.status = 'DESIGNING'
                    req.save(update_fields=['status', 'updated_at'])
                    req.log('STATUS_CHANGE', 'Started designing', actor=me)
                    messages.success(request, f'Started working on {req.request_number}')
                    invalidate_after_status_change(me.pk)

            elif action == 'mark_complete':
                if req.status in ('DESIGNING', 'REVISION'):
                    req.status = 'COMPLETED'
                    req.completed_at = now
                    req.save(update_fields=['status', 'completed_at', 'updated_at'])
                    req.log('STATUS_CHANGE', 'Marked as completed by designer', actor=me)
                    _notify(
                        req.user, req, 'COMPLETED',
                        f'Your project {req.request_number} has been completed!',
                        actor=me,
                    )
                    messages.success(request, f'{req.request_number} marked as completed')
                    invalidate_after_status_change(me.pk)

            return redirect('branding:designer_dashboard')

    return render(request, 'branding/designer_dashboard.html', {
        # Metrics
        'active_count': active_count,
        'overdue_count': overdue_count,
        'today_deadline_count': today_deadline_count,
        'waiting_feedback_count': waiting_feedback_count,
        'completed_total': completed_total,
        'completed_month': completed_month,
        'avg_days': avg_days,
        'completion_rate': completion_rate,
        'next_deadline': next_deadline,
        'days_to_next': days_to_next,
        # Project lists
        'active_projects': active_projects,
        'waiting_projects': waiting_projects,
        'completed_projects': completed_projects,
        'upcoming_projects': upcoming_projects,
        # Priority
        'priority_projects': priority_projects,
        # Calendar
        'calendar_days': calendar_days,
        'workload_by_day': workload_by_day,
        'week_start': week_start,
        'week_end': week_end,
        # Notifications
        'recent_notifications': recent_notifications,
        # Context
        'today': today,
        'STATUS_CHOICES': STATUS_CHOICES,
        'PRIORITY_CHOICES': PRIORITY_CHOICES,
    })


# ═══════════════════════════════════════════════════════════════════════════
# DESIGNER WORKFLOW TOOLS
# ═══════════════════════════════════════════════════════════════════════════

@designer_required
def designer_drafts(request, pk):
    """List design drafts for a branding request."""
    br = get_object_or_404(BrandingRequest, pk=pk)
    drafts = br.design_drafts.filter(designer=request.user)
    if request.method == 'POST' and request.POST.get('action') == 'create_draft':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        if title:
            draft = DesignDraft.objects.create(
                request=br, designer=request.user,
                title=title, description=description,
            )
            files = request.FILES.getlist('files')
            for f in files:
                DraftVersion.objects.create(
                    draft=draft, file=f,
                    original_name=f.name, content_type=f.content_type or '',
                    size=f.size, uploaded_by=request.user,
                )
            messages.success(request, f'Draft "{title}" created with {len(files)} file(s).')
            return redirect('branding:designer_drafts', pk=pk)
    return render(request, 'branding/designer/drafts.html', {
        'br': br, 'drafts': drafts,
    })


@designer_required
def designer_draft_detail(request, pk, draft_id):
    """View a specific draft with all versions."""
    br = get_object_or_404(BrandingRequest, pk=pk)
    draft = get_object_or_404(DesignDraft, pk=draft_id, request=br)
    versions = draft.versions.all()
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'upload_version':
            files = request.FILES.getlist('files')
            notes = request.POST.get('notes', '').strip()
            version_type = request.POST.get('version_type', 'minor')
            last_v = draft.versions.order_by('-version_number').first()
            next_num = (last_v.version_number + 1) if last_v else 1
            for f in files:
                DraftVersion.objects.create(
                    draft=draft, file=f,
                    original_name=f.name, content_type=f.content_type or '',
                    size=f.size, notes=notes, uploaded_by=request.user,
                    version_number=next_num, version_type=version_type,
                )
            messages.success(request, f'Uploaded {len(files)} file(s) as v{next_num}.')
            return redirect('branding:designer_draft_detail', pk=pk, draft_id=draft_id)
        elif action == 'submit':
            draft.submit_for_review()
            br.status = 'WAITING_CLIENT'
            br.save(update_fields=['status'])
            messages.success(request, 'Draft submitted for client review.')
            return redirect('branding:designer_drafts', pk=pk)
    return render(request, 'branding/designer/draft_detail.html', {
        'br': br, 'draft': draft, 'versions': versions,
    })


@designer_required
def designer_feedback_requests(request, pk):
    """List feedback requests for a project."""
    br = get_object_or_404(BrandingRequest, pk=pk)
    frs = br.feedback_requests.filter(designer=request.user)
    if request.method == 'POST' and request.POST.get('action') == 'create_frs':
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()
        questions = request.POST.getlist('questions')
        if subject and message:
            fr = FeedbackRequest.objects.create(
                request=br, designer=request.user,
                subject=subject, message=message,
            )
            for i, q in enumerate(questions):
                if q.strip():
                    FeedbackQuestion.objects.create(
                        feedback_request=fr, question=q.strip(), sort_order=i,
                    )
            messages.success(request, 'Feedback request created.')
            return redirect('branding:designer_feedback_requests', pk=pk)
    return render(request, 'branding/designer/feedback_requests.html', {
        'br': br, 'feedback_requests': frs,
    })


@designer_required
def designer_feedback_detail(request, pk, fr_id):
    """View a feedback request and client responses."""
    br = get_object_or_404(BrandingRequest, pk=pk)
    fr = get_object_or_404(FeedbackRequest, pk=fr_id, request=br)
    questions = fr.questions.all()
    if request.method == 'POST' and request.POST.get('action') == 'mark_received':
        fr.mark_responded()
        messages.success(request, 'Feedback marked as received.')
        return redirect('branding:designer_feedback_detail', pk=pk, fr_id=fr_id)
    return render(request, 'branding/designer/feedback_detail.html', {
        'br': br, 'fr': fr, 'questions': questions,
    })


@login_required
@designer_required
def designer_resources(request):
    """Design resources library."""
    resources = DesignResource.objects.filter(is_active=True).select_related('owner', 'collection')
    shared = resources.filter(shared_level='team')
    mine = resources.filter(owner=request.user)
    category_filter = request.GET.get('category', '')
    if category_filter:
        shared = shared.filter(category=category_filter)
        mine = mine.filter(category=category_filter)
    if request.method == 'POST' and request.POST.get('action') == 'add_resource':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        category = request.POST.get('category', 'other')
        shared_level = request.POST.get('shared_level', 'personal')
        url = request.POST.get('url', '').strip()
        tags_raw = request.POST.get('tags', '').strip()
        tags = [t.strip() for t in tags_raw.split(',') if t.strip()] if tags_raw else []
        file = request.FILES.get('file')
        collection_id = request.POST.get('collection_id')
        collection = None
        if collection_id:
            collection = BrandCollection.objects.filter(pk=collection_id).first()
        if title:
            DesignResource.objects.create(
                title=title, description=description, category=category,
                shared_level=shared_level, url=url, tags=tags,
                file=file, collection=collection, owner=request.user,
            )
            messages.success(request, f'Resource "{title}" added.')
            return redirect('branding:designer_resources')
    collections = BrandCollection.objects.all()
    return render(request, 'branding/designer/resources.html', {
        'shared': shared, 'mine': mine,
        'categories': RESOURCE_CATEGORIES,
        'category_filter': category_filter,
        'collections': collections,
    })


@login_required
@designer_required
def designer_time_tracking(request):
    """Time tracking dashboard."""
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    running = TimeEntry.get_running(request.user)
    today_entries = TimeEntry.objects.filter(designer=request.user, date=today)
    today_total = today_entries.aggregate(t=Sum('duration_minutes'))['t'] or 0
    week_entries = TimeEntry.objects.filter(
        designer=request.user, date__gte=week_start, date__lte=week_end,
    )
    week_total = week_entries.aggregate(t=Sum('duration_minutes'))['t'] or 0
    by_phase = week_entries.values('phase').annotate(
        total=Sum('duration_minutes')
    ).order_by('-total')
    by_request = week_entries.values(
        'request__request_number', 'request__company_name'
    ).annotate(total=Sum('duration_minutes')).order_by('-total')[:10]
    recent = TimeEntry.objects.filter(designer=request.user).select_related('request')[:15]
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'start_timer':
            request_id = request.POST.get('request_id')
            phase = request.POST.get('phase', 'design')
            br = BrandingRequest.objects.filter(pk=request_id).first()
            if br:
                TimeEntry.objects.create(
                    request=br, designer=request.user,
                    phase=phase, date=today, is_timer_running=True,
                    timer_started_at=timezone.now(),
                )
                messages.success(request, 'Timer started.')
                return redirect('branding:designer_time_tracking')
        elif action == 'stop_timer':
            entry_id = request.POST.get('entry_id')
            entry = TimeEntry.objects.filter(pk=entry_id, designer=request.user).first()
            if entry:
                entry.stop_timer()
                messages.success(request, f'Timer stopped. {entry.duration_display} recorded.')
                return redirect('branding:designer_time_tracking')
        elif action == 'add_entry':
            request_id = request.POST.get('request_id')
            phase = request.POST.get('phase', 'design')
            desc = request.POST.get('description', '').strip()
            hours = request.POST.get('hours', '0')
            mins = request.POST.get('minutes', '0')
            date = request.POST.get('date', str(today))
            total_mins = int(float(hours or 0) * 60) + int(float(mins or 0))
            br = BrandingRequest.objects.filter(pk=request_id).first()
            if br and total_mins > 0:
                TimeEntry.objects.create(
                    request=br, designer=request.user,
                    phase=phase, description=desc,
                    duration_minutes=total_mins, date=date,
                )
                messages.success(request, f'{total_mins} minutes added.')
                return redirect('branding:designer_time_tracking')
    active_requests = BrandingRequest.objects.filter(
        designer=request.user,
        status__in=['ASSIGNED', 'DESIGNING', 'WAITING_CLIENT', 'REVISION', 'IN_REVIEW'],
    )
    return render(request, 'branding/designer/time_tracking.html', {
        'running': running,
        'today_entries': today_entries,
        'today_total': today_total,
        'week_total': week_total,
        'by_phase': by_phase,
        'by_request': by_request,
        'recent': recent,
        'active_requests': active_requests,
        'PHASES': TIME_TRACK_PHASES,
        'week_start': week_start, 'week_end': week_end, 'today': today,
    })


@designer_required
def designer_notes(request, pk):
    """Project-specific design notes."""
    br = get_object_or_404(BrandingRequest, pk=pk)
    notes = br.design_notes.filter(author=request.user)
    category_filter = request.GET.get('category', '')
    if category_filter:
        notes = notes.filter(category=category_filter)
    if request.method == 'POST' and request.POST.get('action') == 'add_note':
        category = request.POST.get('category', 'design')
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        links_raw = request.POST.get('links', '').strip()
        links = [l.strip() for l in links_raw.split('\n') if l.strip()] if links_raw else []
        is_pinned = request.POST.get('is_pinned') == 'on'
        if title and content:
            DesignNote.objects.create(
                request=br, author=request.user,
                category=category, title=title,
                content=content, links=links, is_pinned=is_pinned,
            )
            messages.success(request, f'Note "{title}" saved.')
            return redirect('branding:designer_notes', pk=pk)
    return render(request, 'branding/designer/notes.html', {
        'br': br, 'notes': notes,
        'categories': NOTE_CATEGORIES,
        'category_filter': category_filter,
    })


@designer_required
def designer_templates(request):
    """Reusable templates library."""
    templates_qs = DesignTemplate.objects.filter(
        Q(owner=request.user) | Q(is_team_shared=True)
    ).distinct()
    mine = templates_qs.filter(owner=request.user)
    shared = templates_qs.filter(is_team_shared=True).exclude(owner=request.user)
    category_filter = request.GET.get('category', '')
    if category_filter:
        mine = mine.filter(category=category_filter)
        shared = shared.filter(category=category_filter)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_template':
            name = request.POST.get('name', '').strip()
            category = request.POST.get('category', 'other')
            subject = request.POST.get('subject', '').strip()
            content = request.POST.get('content', '').strip()
            variables_raw = request.POST.get('variables', '').strip()
            variables = [v.strip() for v in variables_raw.split(',') if v.strip()] if variables_raw else []
            is_team_shared = request.POST.get('is_team_shared') == 'on'
            if name and content:
                DesignTemplate.objects.create(
                    name=name, category=category, subject=subject,
                    content=content, variables=variables,
                    owner=request.user, is_team_shared=is_team_shared,
                )
                messages.success(request, f'Template "{name}" saved.')
                return redirect('branding:designer_templates')
        elif action == 'use_template':
            tpl_id = request.POST.get('template_id')
            tpl = DesignTemplate.objects.filter(pk=tpl_id).first()
            if tpl:
                tpl.increment_uses()
                # Return template content as JSON for client-side usage
                return JsonResponse({
                    'subject': tpl.subject,
                    'content': tpl.content,
                    'variables': tpl.variables,
                })
    return render(request, 'branding/designer/templates.html', {
        'mine': mine, 'shared': shared,
        'categories': TEMPLATE_CATEGORIES,
        'category_filter': category_filter,
    })


# ── Collection Templates (designer CRUD) ────────────────────────────────────

@designer_required
def collection_template_list(request):
    """List all active collections with template counts."""
    collections = BrandCollection.objects.filter(is_active=True).order_by('category', 'name')
    category_filter = request.GET.get('category', '')
    if category_filter:
        collections = collections.filter(category=category_filter)
    collections = collections.annotate(template_count=Count('templates'))
    return render(request, 'branding/designer/collection_templates.html', {
        'collections': collections,
        'categories': COLLECTION_CATEGORIES,
        'category_filter': category_filter,
    })


@designer_required
def collection_template_detail(request, collection_pk):
    """List and manage templates for a specific collection."""
    collection = get_object_or_404(BrandCollection, pk=collection_pk, is_active=True)
    templates = collection.templates.order_by('sort_order', 'name')
    type_filter = request.GET.get('type', '')
    if type_filter:
        templates = templates.filter(template_type=type_filter)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_template':
            form = CollectionTemplateForm(request.POST, request.FILES)
            if form.is_valid():
                tpl = form.save(commit=False)
                tpl.collection = collection
                tpl.designer = request.user
                tpl.save()
                messages.success(request, f'Template "{tpl.name}" added to {collection.name}.')
                return redirect('branding:collection_template_detail', collection_pk=collection.pk)
        elif action == 'delete_template':
            tpl_id = request.POST.get('template_id')
            tpl = collection.templates.filter(pk=tpl_id).first()
            if tpl:
                tpl.file.delete(save=False)
                if tpl.thumbnail:
                    tpl.thumbnail.delete(save=False)
                tpl.delete()
                messages.success(request, 'Template deleted.')
                return redirect('branding:collection_template_detail', collection_pk=collection.pk)

    add_form = CollectionTemplateForm()
    return render(request, 'branding/designer/collection_template_detail.html', {
        'collection': collection,
        'templates': templates,
        'add_form': add_form,
        'template_types': COLLECTION_TEMPLATE_TYPES,
        'type_filter': type_filter,
    })


@designer_required
def collection_template_edit(request, pk):
    """Edit a collection template."""
    tpl = get_object_or_404(CollectionTemplate, pk=pk, designer=request.user)
    if request.method == 'POST':
        form = CollectionTemplateForm(request.POST, request.FILES, instance=tpl)
        if form.is_valid():
            form.save()
            messages.success(request, f'Template "{tpl.name}" updated.')
            return redirect('branding:collection_template_detail', collection_pk=tpl.collection.pk)
    else:
        form = CollectionTemplateForm(instance=tpl)
    return render(request, 'branding/designer/collection_template_form.html', {
        'form': form, 'tpl': tpl, 'collection': tpl.collection,
    })


@designer_required
@require_POST
def collection_template_delete(request, pk):
    """Delete a collection template."""
    tpl = get_object_or_404(CollectionTemplate, pk=pk, designer=request.user)
    collection_pk = tpl.collection.pk
    tpl.file.delete(save=False)
    if tpl.thumbnail:
        tpl.thumbnail.delete(save=False)
    tpl.delete()
    messages.success(request, f'Template "{tpl.name}" deleted.')
    return redirect('branding:collection_template_detail', collection_pk=collection_pk)


@designer_required
@require_POST
def collection_template_download(request, pk):
    """Increment download count and redirect to file."""
    tpl = get_object_or_404(CollectionTemplate, pk=pk)
    tpl.increment_downloads()
    return redirect(tpl.file.url)


@designer_required
def designer_export_timesheet(request):
    """Export timesheet as CSV."""
    from django.http import HttpResponse
    import csv as csv_mod
    date_from = request.GET.get('from')
    date_to = request.GET.get('to')
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())
    date_from = date_from or str(week_start)
    date_to = date_to or str(today)
    entries = TimeEntry.objects.filter(
        designer=request.user,
        date__gte=date_from, date__lte=date_to,
    ).select_related('request').order_by('date')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="timesheet_{date_from}_to_{date_to}.csv"'
    writer = csv_mod.writer(response)
    writer.writerow(['Date', 'Project', 'Phase', 'Duration', 'Description'])
    for e in entries:
        writer.writerow([
            str(e.date), e.request.request_number or str(e.request.pk),
            e.get_phase_display(), e.duration_display, e.description,
        ])
    total = entries.aggregate(t=Sum('duration_minutes'))['t'] or 0
    writer.writerow([])
    writer.writerow(['', '', 'Total', f'{total // 60}h {total % 60}m', ''])
    return response


# ═══════════════════════════════════════════════════════════════════════════
# COLLABORATION FEATURES
# ═══════════════════════════════════════════════════════════════════════════

# ── Peer Review ──────────────────────────────────────────────────────────

@login_required
@staff_member_required
def peer_reviews(request, pk):
    """List peer reviews for a branding request."""
    br = get_object_or_404(BrandingRequest, pk=pk)
    reviews = br.peer_reviews.select_related('reviewer', 'requested_by', 'draft')
    my_reviews = reviews.filter(reviewer=request.user)
    others_reviews = reviews.exclude(reviewer=request.user)
    templates = CritiqueTemplate.objects.all()
    if request.method == 'POST' and request.POST.get('action') == 'create_review':
        reviewer_id = request.POST.get('reviewer_id')
        message = request.POST.get('message', '').strip()
        due_date = request.POST.get('due_date') or None
        template_id = request.POST.get('template_id')
        draft_id = request.POST.get('draft_id')
        reviewer = User.objects.filter(pk=reviewer_id, is_staff=True).first()
        if reviewer and reviewer != request.user:
            review = PeerReview.objects.create(
                request=br, reviewer=reviewer, requested_by=request.user,
                message=message, due_date=due_date,
                draft=DesignDraft.objects.filter(pk=draft_id).first() if draft_id else None,
                critique_template=CritiqueTemplate.objects.filter(pk=template_id).first() if template_id else None,
            )
            if template_id:
                tpl = CritiqueTemplate.objects.filter(pk=template_id).first()
                if tpl:
                    tpl.increment_uses()
            messages.success(request, f'Review requested from {reviewer.get_full_name() or reviewer.username}.')
            return redirect('branding:peer_reviews', pk=pk)
    designers = User.objects.filter(is_staff=True).exclude(pk=request.user.pk)
    return render(request, 'branding/designer/peer_reviews.html', {
        'br': br, 'my_reviews': my_reviews, 'others_reviews': others_reviews,
        'designers': designers, 'templates': templates,
        'drafts': br.design_drafts.all(),
    })


@login_required
@staff_member_required
def peer_review_detail(request, pk, review_id):
    """View a peer review and provide feedback."""
    br = get_object_or_404(BrandingRequest, pk=pk)
    review = get_object_or_404(PeerReview, pk=review_id, request=br)
    feedbacks = review.feedbacks.select_related('author')
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_feedback' and review.reviewer == request.user:
            category = request.POST.get('category', '').strip()
            content = request.POST.get('content', '').strip()
            rating = request.POST.get('rating')
            if content:
                PeerReviewFeedback.objects.create(
                    review=review, author=request.user,
                    category=category, content=content,
                    rating=int(rating) if rating else None,
                )
                messages.success(request, 'Feedback submitted.')
                return redirect('branding:peer_review_detail', pk=pk, review_id=review_id)
        elif action == 'complete':
            review.complete()
            messages.success(request, 'Review marked as completed.')
            return redirect('branding:peer_review_detail', pk=pk, review_id=review_id)
        elif action == 'start':
            review.status = 'IN_PROGRESS'
            review.save(update_fields=['status', 'updated_at'])
            messages.success(request, 'Review started.')
            return redirect('branding:peer_review_detail', pk=pk, review_id=review_id)
    return render(request, 'branding/designer/peer_review_detail.html', {
        'br': br, 'review': review, 'feedbacks': feedbacks,
    })


# ── Internal Comments ────────────────────────────────────────────────────

@login_required
@staff_member_required
def design_comments(request, pk):
    """List and manage internal comments on a branding request."""
    br = get_object_or_404(BrandingRequest, pk=pk)
    comments = br.design_comments.filter(parent__isnull=True).select_related('author', 'resolved_by').prefetch_related('replies__author', 'mentions')
    unresolved_count = br.design_comments.filter(is_resolved=False).count()
    tag_filter = request.GET.get('tag', '')
    if tag_filter:
        comments = comments.filter(tag=tag_filter)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_comment':
            content = request.POST.get('content', '').strip()
            tag = request.POST.get('tag', 'general')
            parent_id = request.POST.get('parent_id')
            annotation_x = request.POST.get('annotation_x')
            annotation_y = request.POST.get('annotation_y')
            annotation_img = request.FILES.get('annotation_image')
            if content:
                comment = DesignComment.objects.create(
                    request=br, author=request.user,
                    content=content, tag=tag,
                    parent=DesignComment.objects.filter(pk=parent_id).first() if parent_id else None,
                    annotation_x=int(annotation_x) if annotation_x else None,
                    annotation_y=int(annotation_y) if annotation_y else None,
                    annotation_image=annotation_img,
                )
                import re
                mentioned_usernames = re.findall(r'@(\w+)', content)
                if mentioned_usernames:
                    mentioned = User.objects.filter(username__in=mentioned_usernames, is_staff=True)
                    comment.mentions.set(mentioned)
                messages.success(request, 'Comment posted.')
                return redirect('branding:design_comments', pk=pk)
        elif action == 'resolve':
            comment_id = request.POST.get('comment_id')
            comment = DesignComment.objects.filter(pk=comment_id).first()
            if comment:
                comment.resolve(request.user)
                messages.success(request, 'Comment resolved.')
                return redirect('branding:design_comments', pk=pk)
        elif action == 'unresolve':
            comment_id = request.POST.get('comment_id')
            comment = DesignComment.objects.filter(pk=comment_id).first()
            if comment:
                comment.unresolve()
                messages.success(request, 'Comment unresolved.')
                return redirect('branding:design_comments', pk=pk)
    staff_users = User.objects.filter(is_staff=True).exclude(pk=request.user.pk)
    return render(request, 'branding/designer/comments.html', {
        'br': br, 'comments': comments,
        'unresolved_count': unresolved_count,
        'comment_tags': COMMENT_TAGS,
        'tag_filter': tag_filter,
        'staff_users': staff_users,
    })


@login_required
@staff_member_required
def comment_mention_search(request, pk):
    """AJAX endpoint to search staff users for @mentions."""
    q = request.GET.get('q', '').strip()
    if len(q) < 1:
        return JsonResponse([], safe=False)
    users = User.objects.filter(
        is_staff=True, username__icontains=q
    ).exclude(pk=request.user.pk)[:8]
    data = [{'id': u.pk, 'username': u.username, 'name': u.get_full_name() or u.username} for u in users]
    return JsonResponse(data, safe=False)


# ── Design Handoff ───────────────────────────────────────────────────────

@login_required
@staff_member_required
def design_handoffs(request, pk):
    """List handoffs for a branding request."""
    br = get_object_or_404(BrandingRequest, pk=pk)
    handoffs = br.handoffs.select_related('designer', 'handed_off_to')
    if request.method == 'POST' and request.POST.get('action') == 'create_handoff':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        handoff_notes = request.POST.get('handoff_notes', '').strip()
        if title:
            DesignHandoff.objects.create(
                request=br, designer=request.user,
                title=title, description=description,
                handoff_notes=handoff_notes,
            )
            messages.success(request, f'Handoff "{title}" created.')
            return redirect('branding:design_handoffs', pk=pk)
    return render(request, 'branding/designer/handoffs.html', {
        'br': br, 'handoffs': handoffs,
    })


@login_required
@staff_member_required
def handoff_detail(request, pk, handoff_id):
    """View handoff details, deliverables, and notes."""
    br = get_object_or_404(BrandingRequest, pk=pk)
    handoff = get_object_or_404(DesignHandoff, pk=handoff_id, request=br)
    deliverables = handoff.deliverables.all()
    notes = handoff.notes.select_related('author').all()
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_deliverable':
            files = request.FILES.getlist('files')
            dtype = request.POST.get('deliverable_type', 'other')
            desc = request.POST.get('description', '').strip()
            for f in files:
                HandoffDeliverable.objects.create(
                    handoff=handoff, file=f,
                    original_name=f.name, deliverable_type=dtype,
                    description=desc, content_type=f.content_type or '',
                    size=f.size, uploaded_by=request.user,
                )
            messages.success(request, f'Added {len(files)} deliverable(s).')
            return redirect('branding:handoff_detail', pk=pk, handoff_id=handoff_id)
        elif action == 'add_note':
            title = request.POST.get('note_title', '').strip()
            content = request.POST.get('note_content', '').strip()
            note_type = request.POST.get('note_type', 'general')
            if title and content:
                HandoffNote.objects.create(
                    handoff=handoff, author=request.user,
                    title=title, content=content, note_type=note_type,
                )
                messages.success(request, 'Note added.')
                return redirect('branding:handoff_detail', pk=pk, handoff_id=handoff_id)
        elif action == 'mark_ready':
            handoff.status = 'READY'
            handoff.save(update_fields=['status', 'updated_at'])
            messages.success(request, 'Handoff marked as ready.')
            return redirect('branding:handoff_detail', pk=pk, handoff_id=handoff_id)
        elif action == 'handoff':
            handoff.status = 'HANDED_OFF'
            handoff.handed_off_at = timezone.now()
            handoff.handed_off_to = request.user
            handoff.save(update_fields=['status', 'handed_off_to', 'handed_off_at', 'updated_at'])
            messages.success(request, 'Handoff completed.')
            return redirect('branding:handoff_detail', pk=pk, handoff_id=handoff_id)
    return render(request, 'branding/designer/handoff_detail.html', {
        'br': br, 'handoff': handoff,
        'deliverables': deliverables, 'notes': notes,
        'DELIVERABLE_TYPES': HandoffDeliverable.DELIVERABLE_TYPES,
        'NOTE_TYPES': [('general', 'General'), ('technical', 'Technical'), ('brand', 'Brand Guidelines'), ('usage', 'Usage Instructions')],
    })


# ── Knowledge Base ───────────────────────────────────────────────────────

@login_required
@staff_member_required
def knowledge_base(request):
    """Knowledge base listing."""
    articles = KnowledgeArticle.objects.filter(is_published=True).select_related('author', 'collection')
    category_filter = request.GET.get('category', '')
    q = request.GET.get('q', '').strip()
    if category_filter:
        articles = articles.filter(category=category_filter)
    if q:
        articles = articles.filter(Q(title__icontains=q) | Q(content__icontains=q) | Q(tags__icontains=q))
    featured = articles.filter(is_featured=True)[:3]
    if request.method == 'POST' and request.POST.get('action') == 'create_article':
        title = request.POST.get('title', '').strip()
        category = request.POST.get('category', 'tips')
        content = request.POST.get('content', '').strip()
        summary = request.POST.get('summary', '').strip()
        tags_raw = request.POST.get('tags', '').strip()
        tags = [t.strip() for t in tags_raw.split(',') if t.strip()] if tags_raw else []
        collection_id = request.POST.get('collection_id')
        collection = BrandCollection.objects.filter(pk=collection_id).first() if collection_id else None
        if title and content:
            KnowledgeArticle.objects.create(
                title=title, category=category, content=content,
                summary=summary, tags=tags, collection=collection,
                author=request.user,
            )
            messages.success(request, f'Article "{title}" published.')
            return redirect('branding:knowledge_base')
    collections = BrandCollection.objects.all()
    return render(request, 'branding/designer/knowledge_base.html', {
        'articles': articles, 'featured': featured,
        'categories': KB_CATEGORIES,
        'category_filter': category_filter, 'q': q,
        'collections': collections,
    })


@login_required
@staff_member_required
def knowledge_detail(request, slug):
    """View a knowledge base article."""
    article = get_object_or_404(KnowledgeArticle, slug=slug, is_published=True)
    article.increment_views()
    if request.method == 'POST' and request.POST.get('action') == 'mark_helpful':
        article.increment_helpful()
        messages.success(request, 'Thanks for your feedback!')
        return redirect('branding:knowledge_detail', slug=slug)
    related = KnowledgeArticle.objects.filter(
        category=article.category, is_published=True
    ).exclude(pk=article.pk)[:4]
    return render(request, 'branding/designer/knowledge_detail.html', {
        'article': article, 'related': related,
    })


# ── Design Showcase ──────────────────────────────────────────────────────

@login_required
@staff_member_required
def showcase(request):
    """Design showcase/portfolio listing."""
    projects = ShowcaseProject.objects.filter(is_published=True).select_related('designer', 'request')
    category_filter = request.GET.get('category', '')
    if category_filter:
        projects = projects.filter(category=category_filter)
    featured = projects.filter(is_featured=True)[:6]
    if request.method == 'POST' and request.POST.get('action') == 'create_showcase':
        request_id = request.POST.get('request_id')
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        category = request.POST.get('category', 'branding')
        client_name = request.POST.get('client_name', '').strip()
        project_year = request.POST.get('project_year')
        tags_raw = request.POST.get('tags', '').strip()
        tags = [t.strip() for t in tags_raw.split(',') if t.strip()] if tags_raw else []
        cover_image = request.FILES.get('cover_image')
        br = BrandingRequest.objects.filter(pk=request_id).first() if request_id else None
        if title and description:
            ShowcaseProject.objects.create(
                request=br, designer=request.user,
                title=title, description=description,
                category=category, client_name=client_name,
                project_year=int(project_year) if project_year else None,
                tags=tags, cover_image=cover_image,
            )
            messages.success(request, f'Project "{title}" added to showcase.')
            return redirect('branding:showcase')
    completed = BrandingRequest.objects.filter(status='COMPLETED')
    return render(request, 'branding/designer/showcase.html', {
        'projects': projects, 'featured': featured,
        'categories': SHOWCASE_CATEGORIES,
        'category_filter': category_filter,
        'completed_requests': completed,
    })


@login_required
@staff_member_required
def showcase_detail(request, showcase_id):
    """View a showcase project."""
    project = get_object_or_404(ShowcaseProject, pk=showcase_id, is_published=True)
    project.increment_views()
    if request.method == 'POST' and request.POST.get('action') == 'like':
        project.increment_likes()
        return redirect('branding:showcase_detail', showcase_id=showcase_id)
    related = ShowcaseProject.objects.filter(
        category=project.category, is_published=True
    ).exclude(pk=project.pk)[:4]
    return render(request, 'branding/designer/showcase_detail.html', {
        'project': project, 'related': related,
    })


# ═══════════════════════════════════════════════════════════════════════════
# DESIGNER INTEGRATIONS
# ═══════════════════════════════════════════════════════════════════════════

# ── Figma Integration ────────────────────────────────────────────────────

@login_required
@staff_member_required
def figma_integration(request):
    """Figma integration dashboard."""
    connection = FigmaConnection.objects.filter(user=request.user).first()
    designs = connection.designs.all() if connection else []
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'connect':
            token = request.POST.get('access_token', '').strip()
            if token:
                FigmaConnection.objects.update_or_create(
                    user=request.user,
                    defaults={
                        'figma_user_id': 'pending',
                        'figma_email': request.user.email,
                        'access_token': token,
                        'is_active': True,
                    },
                )
                messages.success(request, 'Figma account connected.')
                return redirect('branding:figma_integration')
        elif action == 'disconnect' and connection:
            connection.delete()
            messages.success(request, 'Figma account disconnected.')
            return redirect('branding:figma_integration')
        elif action == 'import_design':
            file_key = request.POST.get('file_key', '').strip()
            file_name = request.POST.get('file_name', '').strip()
            figma_url = request.POST.get('figma_url', '').strip()
            request_id = request.POST.get('request_id')
            if file_key and file_name and connection:
                br = BrandingRequest.objects.filter(pk=request_id).first() if request_id else None
                FigmaDesign.objects.create(
                    connection=connection, request=br,
                    figma_file_key=file_key, figma_file_name=file_name,
                    figma_url=figma_url or f'https://figma.com/file/{file_key}',
                )
                messages.success(request, f'Figma design "{file_name}" imported.')
                return redirect('branding:figma_integration')
    active_requests = BrandingRequest.objects.filter(
        designer=request.user,
        status__in=['ASSIGNED', 'DESIGNING', 'IN_REVIEW', 'WAITING_CLIENT', 'REVISION'],
    )
    return render(request, 'branding/designer/figma.html', {
        'connection': connection, 'designs': designs,
        'active_requests': active_requests,
    })


# ── Adobe CC Integration ─────────────────────────────────────────────────

@login_required
@staff_member_required
def adobe_integration(request):
    """Adobe Creative Cloud integration dashboard."""
    connection = AdobeConnection.objects.filter(user=request.user).first()
    assets = connection.adobe_assets.all() if connection else []
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'connect':
            token = request.POST.get('access_token', '').strip()
            if token:
                AdobeConnection.objects.update_or_create(
                    user=request.user,
                    defaults={
                        'adobe_user_id': 'pending',
                        'adobe_email': request.user.email,
                        'access_token': token,
                        'is_active': True,
                    },
                )
                messages.success(request, 'Adobe CC account connected.')
                return redirect('branding:adobe_integration')
        elif action == 'disconnect' and connection:
            connection.delete()
            messages.success(request, 'Adobe CC account disconnected.')
            return redirect('branding:adobe_integration')
        elif action == 'import_asset':
            asset_name = request.POST.get('asset_name', '').strip()
            asset_type = request.POST.get('asset_type', 'other')
            library_name = request.POST.get('library_name', '').strip()
            request_id = request.POST.get('request_id')
            if asset_name and connection:
                br = BrandingRequest.objects.filter(pk=request_id).first() if request_id else None
                AdobeAsset.objects.create(
                    connection=connection, request=br,
                    asset_id=f'asset-{timezone.now().timestamp()}',
                    asset_name=asset_name, asset_type=asset_type,
                    library_name=library_name,
                )
                messages.success(request, f'Asset "{asset_name}" imported.')
                return redirect('branding:adobe_integration')
    active_requests = BrandingRequest.objects.filter(
        designer=request.user,
        status__in=['ASSIGNED', 'DESIGNING', 'IN_REVIEW', 'WAITING_CLIENT', 'REVISION'],
    )
    return render(request, 'branding/designer/adobe.html', {
        'connection': connection, 'assets': assets,
        'active_requests': active_requests,
        'ASSET_TYPES': AdobeAsset.ASSET_TYPES,
    })


# ── Design Tools ─────────────────────────────────────────────────────────

@login_required
@staff_member_required
def design_tools_color(request):
    """Color picker and palette tool."""
    palettes = ColorPalette.objects.filter(
        Q(owner=request.user) | Q(is_public=True)
    ).select_related('owner')
    if request.method == 'POST' and request.POST.get('action') == 'save_palette':
        name = request.POST.get('name', '').strip()
        colors_raw = request.POST.get('colors', '').strip()
        request_id = request.POST.get('request_id')
        is_public = request.POST.get('is_public') == 'on'
        colors = [c.strip() for c in colors_raw.split(',') if c.strip()] if colors_raw else []
        if name and colors:
            br = BrandingRequest.objects.filter(pk=request_id).first() if request_id else None
            ColorPalette.objects.create(
                name=name, colors=colors, request=br,
                owner=request.user, is_public=is_public,
            )
            messages.success(request, f'Palette "{name}" saved.')
            return redirect('branding:design_tools_color')
    active_requests = BrandingRequest.objects.filter(designer=request.user)
    return render(request, 'branding/designer/tools_color.html', {
        'palettes': palettes, 'active_requests': active_requests,
    })


@login_required
@staff_member_required
def design_tools_fonts(request):
    """Font finder tool."""
    fonts = FontEntry.objects.filter(
        Q(owner=request.user) | Q(is_public=True)
    ).select_related('owner')
    q = request.GET.get('q', '').strip()
    if q:
        fonts = fonts.filter(Q(name__icontains=q) | Q(family__icontains=q))
    if request.method == 'POST' and request.POST.get('action') == 'add_font':
        name = request.POST.get('name', '').strip()
        family = request.POST.get('family', '').strip()
        weights_raw = request.POST.get('weights', '').strip()
        styles_raw = request.POST.get('styles', '').strip()
        source_url = request.POST.get('source_url', '').strip()
        request_id = request.POST.get('request_id')
        is_public = request.POST.get('is_public') == 'on'
        weights = [w.strip() for w in weights_raw.split(',') if w.strip()] if weights_raw else []
        styles_list = [s.strip() for s in styles_raw.split(',') if s.strip()] if styles_raw else []
        if name and family:
            br = BrandingRequest.objects.filter(pk=request_id).first() if request_id else None
            FontEntry.objects.create(
                name=name, family=family, weights=weights,
                styles=styles_list, source_url=source_url,
                request=br, owner=request.user, is_public=is_public,
            )
            messages.success(request, f'Font "{name}" added.')
            return redirect('branding:design_tools_fonts')
    active_requests = BrandingRequest.objects.filter(designer=request.user)
    return render(request, 'branding/designer/tools_fonts.html', {
        'fonts': fonts, 'q': q, 'active_requests': active_requests,
    })


@login_required
@staff_member_required
def design_tools_organizer(request):
    """Asset organizer tool."""
    items = AssetOrganizerItem.objects.filter(owner=request.user)
    folder_filter = request.GET.get('folder', '')
    if folder_filter:
        items = items.filter(folder=folder_filter)
    folders = AssetOrganizerItem.objects.filter(owner=request.user).values_list('folder', flat=True).distinct()
    if request.method == 'POST' and request.POST.get('action') == 'add_item':
        name = request.POST.get('name', '').strip()
        item_type = request.POST.get('item_type', 'other')
        folder = request.POST.get('folder', 'General').strip()
        tags_raw = request.POST.get('tags', '').strip()
        request_id = request.POST.get('request_id')
        tags = [t.strip() for t in tags_raw.split(',') if t.strip()] if tags_raw else []
        file = request.FILES.get('file')
        thumbnail = request.FILES.get('thumbnail')
        if name:
            br = BrandingRequest.objects.filter(pk=request_id).first() if request_id else None
            AssetOrganizerItem.objects.create(
                name=name, item_type=item_type, folder=folder,
                tags=tags, file=file, thumbnail=thumbnail,
                request=br, owner=request.user,
            )
            messages.success(request, f'Asset "{name}" added.')
            return redirect('branding:design_tools_organizer')
    active_requests = BrandingRequest.objects.filter(designer=request.user)
    return render(request, 'branding/designer/tools_organizer.html', {
        'items': items, 'folders': folders,
        'folder_filter': folder_filter,
        'active_requests': active_requests,
        'ITEM_TYPES': AssetOrganizerItem.ITEM_TYPES,
    })


@login_required
@staff_member_required
def design_tools_brand_check(request):
    """Brand guidelines compliance checker."""
    checks = BrandGuidelineCheck.objects.filter(checker=request.user)
    if request.method == 'POST' and request.POST.get('action') == 'run_check':
        request_id = request.POST.get('request_id')
        br = BrandingRequest.objects.filter(pk=request_id).first()
        if br:
            # Run automated checks
            check_items = [
                ('Logo Delivered', bool(br.assets.filter(asset_type='logo').exists())),
                ('Color Palette Defined', bool(getattr(br, 'preferred_colors', None))),
                ('Brand Values Selected', bool(getattr(br, 'brand_values', None))),
                ('Collection Selected', bool(br.collection)),
                ('Client Brief Complete', bool(br.company_name and br.industry)),
                ('Design Files Uploaded', bool(br.assets.exists())),
                ('Internal Notes Added', bool(br.internal_notes)),
            ]
            for name, passed in check_items:
                BrandGuidelineCheck.objects.create(
                    request=br, checker=request.user,
                    check_name=name,
                    result='PASS' if passed else 'FAIL',
                    details='Compliant' if passed else 'Non-compliant — action required',
                )
            messages.success(request, f'{len(check_items)} checks completed for {br.request_number}.')
            return redirect('branding:design_tools_brand_check')
    active_requests = BrandingRequest.objects.filter(designer=request.user)
    return render(request, 'branding/designer/tools_brand_check.html', {
        'checks': checks, 'active_requests': active_requests,
    })


# ── Slack Integration ────────────────────────────────────────────────────

@login_required
@staff_member_required
def slack_integration(request):
    """Slack integration settings."""
    connection = SlackConnection.objects.filter(user=request.user).first()
    recent_messages = connection.messages.all()[:20] if connection else []
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'connect':
            bot_token = request.POST.get('bot_token', '').strip()
            workspace_name = request.POST.get('workspace_name', '').strip()
            channel_id = request.POST.get('channel_id', '').strip()
            channel_name = request.POST.get('channel_name', '').strip()
            if bot_token and workspace_name:
                SlackConnection.objects.update_or_create(
                    user=request.user,
                    defaults={
                        'workspace_id': f'ws-{timezone.now().timestamp()}',
                        'workspace_name': workspace_name,
                        'bot_token': bot_token,
                        'channel_id': channel_id,
                        'channel_name': channel_name,
                        'is_active': True,
                    },
                )
                messages.success(request, 'Slack workspace connected.')
                return redirect('branding:slack_integration')
        elif action == 'disconnect' and connection:
            connection.delete()
            messages.success(request, 'Slack disconnected.')
            return redirect('branding:slack_integration')
        elif action == 'update_settings' and connection:
            connection.notify_assignments = request.POST.get('notify_assignments') == 'on'
            connection.notify_deadlines = request.POST.get('notify_deadlines') == 'on'
            connection.notify_feedback = request.POST.get('notify_feedback') == 'on'
            connection.notify_daily_digest = request.POST.get('notify_daily_digest') == 'on'
            connection.save()
            messages.success(request, 'Notification settings updated.')
            return redirect('branding:slack_integration')
        elif action == 'test' and connection:
            SlackMessage.objects.create(
                connection=connection, message_type='status',
                channel=connection.channel_id,
                text='Test notification from Branding Studio.',
            )
            messages.success(request, 'Test notification sent (logged).')
            return redirect('branding:slack_integration')
    return render(request, 'branding/designer/slack.html', {
        'connection': connection, 'recent_messages': recent_messages,
    })


# ── Calendar Integration ─────────────────────────────────────────────────

@login_required
@staff_member_required
def calendar_integration(request):
    """Calendar integration dashboard."""
    connection = CalendarConnection.objects.filter(user=request.user).first()
    if connection:
        events = connection.events.all()[:30]
        upcoming = connection.events.filter(start_time__gte=timezone.now())[:10]
        past = connection.events.filter(start_time__lt=timezone.now())[:10]
    else:
        events = []
        upcoming = []
        past = []
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'connect':
            provider = request.POST.get('provider', 'google')
            calendar_id = request.POST.get('calendar_id', '').strip()
            calendar_name = request.POST.get('calendar_name', '').strip()
            access_token = request.POST.get('access_token', '').strip()
            if calendar_id and access_token:
                CalendarConnection.objects.update_or_create(
                    user=request.user,
                    defaults={
                        'provider': provider,
                        'calendar_id': calendar_id,
                        'calendar_name': calendar_name or f'{provider.title()} Calendar',
                        'access_token': access_token,
                        'is_active': True,
                    },
                )
                messages.success(request, 'Calendar connected.')
                return redirect('branding:calendar_integration')
        elif action == 'disconnect' and connection:
            connection.delete()
            messages.success(request, 'Calendar disconnected.')
            return redirect('branding:calendar_integration')
        elif action == 'add_event':
            title = request.POST.get('title', '').strip()
            description = request.POST.get('description', '').strip()
            event_type = request.POST.get('event_type', 'deadline')
            start_time = request.POST.get('start_time')
            end_time = request.POST.get('end_time') or None
            request_id = request.POST.get('request_id')
            if title and start_time and connection:
                br = BrandingRequest.objects.filter(pk=request_id).first() if request_id else None
                CalendarEvent.objects.create(
                    connection=connection, request=br,
                    title=title, description=description,
                    event_type=event_type,
                    start_time=start_time,
                    end_time=end_time,
                )
                messages.success(request, f'Event "{title}" added.')
                return redirect('branding:calendar_integration')
        elif action == 'sync_deadlines' and connection:
            # Sync project deadlines to calendar
            active = BrandingRequest.objects.filter(
                designer=request.user,
                estimated_delivery_date__isnull=False,
                status__in=['ASSIGNED', 'DESIGNING', 'IN_REVIEW', 'WAITING_CLIENT', 'REVISION'],
            )
            count = 0
            for br in active:
                event, created = CalendarEvent.objects.get_or_create(
                    connection=connection,
                    request=br,
                    event_type='deadline',
                    defaults={
                        'title': f'Deadline: {br.request_number or br.company_name}',
                        'description': f'Brand project deadline for {br.company_name}',
                        'start_time': timezone.make_timezone_aware(
                            timezone.datetime.combine(br.estimated_delivery_date, timezone.datetime.min.time())
                        ) if br.estimated_delivery_date else timezone.now(),
                        'all_day': True,
                    },
                )
                if created:
                    count += 1
            messages.success(request, f'{count} deadline(s) synced to calendar.')
            return redirect('branding:calendar_integration')
    active_requests = BrandingRequest.objects.filter(designer=request.user)
    return render(request, 'branding/designer/calendar.html', {
        'connection': connection, 'upcoming': upcoming,
        'past': past, 'events': events,
        'active_requests': active_requests,
        'EVENT_TYPES': CalendarEvent.EVENT_TYPES,
    })


# ═══════════════════════════════════════════════════════════════════════════
# Unified Staff Dashboard
# ═══════════════════════════════════════════════════════════════════════════

@staff_member_required
def unified_dashboard(request):
    """Single entry point for all staff roles. Detects role, renders dashboard with widgets."""
    from .widget_registry import ensure_dashboard, get_widget_data, seed_all_widget_definitions
    from .roles import get_user_role, get_role_nav_items, is_supervisor, is_designer

    seed_all_widget_definitions()
    dashboard = ensure_dashboard(request.user)
    role = get_user_role(request.user)
    active_role = request.session.get('active_role_view', '')
    effective_role = active_role if active_role and dashboard.allow_role_switch else role

    widgets = dashboard.widgets.filter(is_visible=True).select_related('widget_def')
    widget_data = {}
    for w in widgets:
        if w.visible_for_role(effective_role):
            widget_data[w.id] = {
                'instance': w,
                'data': get_widget_data(w.widget_def.widget_type, request, w.config),
            }

    switchable_roles = []
    if dashboard.allow_role_switch:
        switchable_roles = [
            {'role': 'supervisor', 'label': 'Supervisor View', 'allowed': is_supervisor(request.user)},
            {'role': 'designer', 'label': 'Designer View', 'allowed': is_designer(request.user)},
            {'role': 'staff', 'label': 'Staff View', 'allowed': request.user.is_staff},
        ]

    available_widget_defs = []
    existing_types = set(widgets.values_list('widget_def__widget_type', flat=True))
    for wd in WidgetDefinition.objects.filter(is_active=True):
        if wd.widget_type not in existing_types:
            available_widget_defs.append(wd)

    return render(request, 'branding/unified_dashboard.html', {
        'dashboard': dashboard,
        'role': role,
        'effective_role': effective_role,
        'widget_data': widget_data,
        'widget_cols': dashboard.columns,
        'layout': dashboard.layout,
        'compact_mode': dashboard.compact_mode,
        'show_sidebar': dashboard.show_sidebar,
        'switchable_roles': switchable_roles,
        'available_widgets': available_widget_defs,
        'WIDGET_TYPES': WIDGET_TYPES,
        'DASHBOARD_LAYOUTS': DASHBOARD_LAYOUTS,
        'page_title': 'Staff Dashboard',
    })


@staff_member_required
@require_POST
def switch_role_view(request):
    """Switch the active role perspective on the dashboard."""
    from .widget_registry import ensure_dashboard
    from .roles import is_supervisor, is_designer, get_user_role

    new_role = request.POST.get('role', '').strip()
    dashboard = ensure_dashboard(request.user)

    if not dashboard.allow_role_switch:
        return JsonResponse({'ok': False, 'error': 'Role switching is disabled.'}, status=403)

    allowed = False
    if new_role == 'supervisor' and is_supervisor(request.user):
        allowed = True
    elif new_role == 'designer' and is_designer(request.user):
        allowed = True
    elif new_role == 'staff' and request.user.is_staff:
        allowed = True

    if not allowed:
        return JsonResponse({'ok': False, 'error': 'You do not have permission for this role.'}, status=403)

    old_role = request.session.get('active_role_view', get_user_role(request.user))
    request.session['active_role_view'] = new_role

    from .models import RoleSwitchLog
    RoleSwitchLog.objects.create(
        user=request.user,
        from_role=old_role,
        to_role=new_role,
        ip_address=request.META.get('REMOTE_ADDR'),
    )

    return JsonResponse({'ok': True, 'role': new_role})


@staff_member_required
@require_POST
def save_layout(request):
    """Save dashboard layout preferences."""
    from .widget_registry import ensure_dashboard

    dashboard = ensure_dashboard(request.user)
    data = json.loads(request.body) if request.content_type == 'application/json' else request.POST

    if 'layout' in data:
        dashboard.layout = data['layout']
    if 'columns' in data:
        dashboard.columns = min(4, max(2, int(data['columns'])))
    if 'compact_mode' in data:
        dashboard.compact_mode = data['compact_mode'] in ('true', '1', 'True', True)
    if 'show_sidebar' in data:
        dashboard.show_sidebar = data['show_sidebar'] in ('true', '1', 'True', True)
    if 'show_header' in data:
        dashboard.show_header = data['show_header'] in ('true', '1', 'True', True)
    if 'allow_role_switch' in data:
        dashboard.allow_role_switch = data['allow_role_switch'] in ('true', '1', 'True', True)
    dashboard.save()

    return JsonResponse({'ok': True, 'layout': dashboard.layout, 'columns': dashboard.columns})


@staff_member_required
@require_POST
def save_widget_positions(request):
    """Save widget positions after drag-and-drop."""
    from .widget_registry import ensure_dashboard

    dashboard = ensure_dashboard(request.user)
    positions = json.loads(request.body) if request.content_type == 'application/json' else {}

    if not isinstance(positions, dict) or 'widgets' not in positions:
        return JsonResponse({'ok': False, 'error': 'Invalid data format.'}, status=400)

    for wp in positions['widgets']:
        widget_id = wp.get('id')
        if not widget_id:
            continue
        try:
            w = DashboardWidget.objects.get(id=widget_id, dashboard=dashboard)
        except DashboardWidget.DoesNotExist:
            continue
        if 'col' in wp:
            w.col = int(wp['col'])
        if 'row' in wp:
            w.row = int(wp['row'])
        if 'width' in wp:
            w.width = max(1, min(4, int(wp['width'])))
        if 'height' in wp:
            w.height = max(1, min(3, int(wp['height'])))
        if 'is_collapsed' in wp:
            w.is_collapsed = wp['is_collapsed']
        w.save()

    return JsonResponse({'ok': True})


@staff_member_required
@require_POST
def add_widget(request):
    """Add a widget to the dashboard."""
    from .widget_registry import ensure_dashboard

    dashboard = ensure_dashboard(request.user)
    widget_type = request.POST.get('widget_type', '').strip()

    try:
        wd = WidgetDefinition.objects.get(widget_type=widget_type, is_active=True)
    except WidgetDefinition.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Unknown widget type.'}, status=400)

    max_row = dashboard.widgets.order_by('-row').values_list('row', flat=True).first() or 0
    DashboardWidget.objects.create(
        dashboard=dashboard,
        widget_def=wd,
        col=0,
        row=max_row + 1,
        width=wd.default_width,
        height=wd.default_height,
    )

    return JsonResponse({'ok': True, 'widget_type': widget_type})


@staff_member_required
@require_POST
def remove_widget(request, widget_id):
    """Remove a widget from the dashboard."""
    from .widget_registry import ensure_dashboard

    dashboard = ensure_dashboard(request.user)
    try:
        w = DashboardWidget.objects.get(id=widget_id, dashboard=dashboard)
    except DashboardWidget.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Widget not found.'}, status=404)

    w.delete()
    return JsonResponse({'ok': True})


@staff_member_required
@require_POST
def toggle_widget_collapse(request, widget_id):
    """Collapse/expand a widget."""
    from .widget_registry import ensure_dashboard

    dashboard = ensure_dashboard(request.user)
    try:
        w = DashboardWidget.objects.get(id=widget_id, dashboard=dashboard)
    except DashboardWidget.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Widget not found.'}, status=404)

    w.is_collapsed = not w.is_collapsed
    w.save()
    return JsonResponse({'ok': True, 'collapsed': w.is_collapsed})


@staff_member_required
@require_POST
def toggle_widget_visibility(request, widget_id):
    """Show/hide a widget."""
    from .widget_registry import ensure_dashboard

    dashboard = ensure_dashboard(request.user)
    try:
        w = DashboardWidget.objects.get(id=widget_id, dashboard=dashboard)
    except DashboardWidget.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Widget not found.'}, status=404)

    w.is_visible = not w.is_visible
    w.save()
    return JsonResponse({'ok': True, 'visible': w.is_visible})


@staff_member_required
def widget_data_api(request, widget_id):
    """Return fresh widget data as JSON (for auto-refresh)."""
    from .widget_registry import ensure_dashboard, get_widget_data
    from .roles import get_user_role

    dashboard = ensure_dashboard(request.user)
    try:
        w = DashboardWidget.objects.select_related('widget_def').get(id=widget_id, dashboard=dashboard)
    except DashboardWidget.DoesNotExist:
        return JsonResponse({'error': 'Widget not found.'}, status=404)

    data = get_widget_data(w.widget_def.widget_type, request, w.config)
    return JsonResponse(data, safe=False)


@staff_member_required
@require_POST
def reset_dashboard(request):
    """Reset dashboard to default layout."""
    from .widget_registry import ensure_dashboard, _seed_default_widgets

    dashboard = ensure_dashboard(request.user)
    dashboard.widgets.all().delete()
    _seed_default_widgets(dashboard, request.user)

    return JsonResponse({'ok': True})


# ═══════════════════════════════════════════════════════════════════════════
# QUESTIONNAIRE SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

# ── Designer Management Views ─────────────────────────────────────────────

@designer_required
def questionnaire_list(request, request_pk):
    br = get_object_or_404(BrandingRequest, pk=request_pk, designer=request.user)
    questionnaires = br.questionnaires.select_related('request').prefetch_related('questions').order_by('-created_at')

    status_filter = request.GET.get('status', '')
    if status_filter:
        questionnaires = questionnaires.filter(status=status_filter)

    status_counts = br.questionnaires.values('status').annotate(cnt=Count('id'))
    counts = {item['status']: item['cnt'] for item in status_counts}

    return render(request, 'branding/questionnaire/list.html', {
        'request_obj': br,
        'questionnaires': questionnaires,
        'counts': counts,
        'total_count': questionnaires.count(),
        'status_filter': status_filter,
    })


@designer_required
def questionnaire_create(request, request_pk):
    br = get_object_or_404(BrandingRequest, pk=request_pk, designer=request.user)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        questionnaire_type = request.POST.get('questionnaire_type', 'standard')

        if title:
            from .models import Questionnaire
            questionnaire = Questionnaire.objects.create(
                request=br,
                title=title,
                description=description,
                questionnaire_type=questionnaire_type,
                created_by=request.user,
            )
            br.log('QUESTIONNAIRE', f'Questionnaire "{title}" created', actor=request.user)
            messages.success(request, f'Questionnaire "{title}" created.')
            return redirect('branding:questionnaire_detail', pk=questionnaire.pk)
        messages.error(request, 'Title is required.')

    return render(request, 'branding/questionnaire/create.html', {
        'request_obj': br,
    })


@designer_required
def questionnaire_edit(request, pk):
    from .models import Questionnaire
    questionnaire = get_object_or_404(Questionnaire, pk=pk, created_by=request.user)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        questionnaire_type = request.POST.get('questionnaire_type', 'standard')

        if title:
            questionnaire.title = title
            questionnaire.description = description
            questionnaire.questionnaire_type = questionnaire_type
            questionnaire.save(update_fields=['title', 'description', 'questionnaire_type', 'updated_at'])
            messages.success(request, 'Questionnaire updated.')
            return redirect('branding:questionnaire_detail', pk=questionnaire.pk)
        messages.error(request, 'Title is required.')

    return render(request, 'branding/questionnaire/edit.html', {
        'questionnaire': questionnaire,
        'request_obj': questionnaire.request,
    })


@designer_required
def questionnaire_detail(request, pk):
    from .models import Questionnaire
    questionnaire = get_object_or_404(
        Questionnaire.objects.select_related('request'),
        pk=pk,
    )
    br = questionnaire.request
    if br.designer != request.user and not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('branding:dashboard')

    questions = questionnaire.questions.order_by('sort_order')
    answers = questionnaire.answers.select_related('question', 'client').all()

    question_data = []
    for q in questions:
        q_answers = answers.filter(question=q)
        question_data.append({
            'question': q,
            'answers': q_answers,
            'answer_count': q_answers.count(),
        })

    return render(request, 'branding/questionnaire/detail.html', {
        'questionnaire': questionnaire,
        'request_obj': br,
        'questions': questions,
        'question_data': question_data,
        'answers': answers,
    })


@designer_required
@require_POST
def questionnaire_send(request, pk):
    from .models import Questionnaire
    questionnaire = get_object_or_404(Questionnaire, pk=pk, created_by=request.user)
    questionnaire.status = 'sent'
    questionnaire.email_sent_at = timezone.now()
    questionnaire.save(update_fields=['status', 'email_sent_at', 'updated_at'])

    br = questionnaire.request
    br.log('QUESTIONNAIRE', f'Questionnaire "{questionnaire.title}" sent', actor=request.user)

    if br.user:
        _notify(
            br.user, br, 'QUESTIONNAIRE_SENT',
            f'A questionnaire "{questionnaire.title}" has been sent for {br.request_number}.',
            email_subject=f'[OnWebApp Branding] Questionnaire: {questionnaire.title}',
        )

    messages.success(request, 'Questionnaire sent to client.')
    return redirect('branding:questionnaire_detail', pk=pk)


@designer_required
@require_POST
def questionnaire_reminder(request, pk):
    from .models import Questionnaire
    questionnaire = get_object_or_404(Questionnaire, pk=pk, created_by=request.user)
    questionnaire.email_reminder_count = F('email_reminder_count') + 1
    questionnaire.last_reminder_at = timezone.now()
    questionnaire.save(update_fields=['email_reminder_count', 'last_reminder_at', 'updated_at'])
    questionnaire.refresh_from_db()

    br = questionnaire.request
    br.log('QUESTIONNAIRE', f'Reminder sent for "{questionnaire.title}"', actor=request.user)

    if br.user:
        _notify(
            br.user, br, 'QUESTIONNAIRE_REMINDER',
            f'Reminder: please complete the questionnaire "{questionnaire.title}".',
            email_subject=f'[OnWebApp Branding] Reminder: {questionnaire.title}',
        )

    messages.success(request, 'Reminder sent.')
    return redirect('branding:questionnaire_detail', pk=pk)


@designer_required
def questionnaire_add_question(request, qid):
    from .models import Questionnaire, QuestionnaireQuestion
    questionnaire = get_object_or_404(Questionnaire, pk=qid, created_by=request.user)

    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        question_type = request.POST.get('question_type', 'text')
        is_required = request.POST.get('is_required') == 'on'
        options_raw = request.POST.get('options', '').strip()
        placeholder = request.POST.get('placeholder', '').strip()
        help_text = request.POST.get('help_text', '').strip()
        max_length = request.POST.get('max_length', '')

        if text:
            last_order = questionnaire.questions.order_by('-sort_order').first()
            next_order = (last_order.sort_order + 1) if last_order else 0
            QuestionnaireQuestion.objects.create(
                questionnaire=questionnaire,
                text=text,
                question_type=question_type,
                is_required=is_required,
                options=[o.strip() for o in options_raw.split('\n') if o.strip()] if options_raw else [],
                placeholder=placeholder,
                help_text=help_text,
                max_length=int(max_length) if max_length else None,
                sort_order=next_order,
            )
            messages.success(request, 'Question added.')
            return redirect('branding:questionnaire_detail', pk=qid)
        messages.error(request, 'Question text is required.')

    return render(request, 'branding/questionnaire/add_question.html', {
        'questionnaire': questionnaire,
        'request_obj': questionnaire.request,
    })


@designer_required
def questionnaire_edit_question(request, qid):
    from .models import QuestionnaireQuestion
    question = get_object_or_404(
        QuestionnaireQuestion.objects.select_related('questionnaire', 'questionnaire__request'),
        pk=qid,
    )
    questionnaire = question.questionnaire
    if questionnaire.created_by != request.user:
        messages.error(request, 'Access denied.')
        return redirect('branding:dashboard')

    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        question_type = request.POST.get('question_type', 'text')
        is_required = request.POST.get('is_required') == 'on'
        options_raw = request.POST.get('options', '').strip()
        placeholder = request.POST.get('placeholder', '').strip()
        help_text = request.POST.get('help_text', '').strip()
        max_length = request.POST.get('max_length', '')

        if text:
            question.text = text
            question.question_type = question_type
            question.is_required = is_required
            question.options = [o.strip() for o in options_raw.split('\n') if o.strip()] if options_raw else []
            question.placeholder = placeholder
            question.help_text = help_text
            question.max_length = int(max_length) if max_length else None
            question.save(update_fields=[
                'text', 'question_type', 'is_required', 'options',
                'placeholder', 'help_text', 'max_length', 'updated_at',
            ])
            messages.success(request, 'Question updated.')
            return redirect('branding:questionnaire_detail', pk=questionnaire.pk)
        messages.error(request, 'Question text is required.')

    return render(request, 'branding/questionnaire/edit_question.html', {
        'question': question,
        'questionnaire': questionnaire,
        'request_obj': questionnaire.request,
    })


@designer_required
@require_POST
def questionnaire_delete_question(request, qid):
    from .models import QuestionnaireQuestion
    question = get_object_or_404(
        QuestionnaireQuestion.objects.select_related('questionnaire'),
        pk=qid,
    )
    questionnaire = question.questionnaire
    if questionnaire.created_by != request.user:
        messages.error(request, 'Access denied.')
        return redirect('branding:dashboard')

    question.delete()
    messages.success(request, 'Question deleted.')
    return redirect('branding:questionnaire_detail', pk=questionnaire.pk)


@designer_required
@require_POST
def questionnaire_reorder_questions(request, pk):
    from .models import Questionnaire, QuestionnaireQuestion
    questionnaire = get_object_or_404(Questionnaire, pk=pk, created_by=request.user)
    question_ids = request.POST.getlist('question_ids[]')

    if not question_ids:
        try:
            data = json.loads(request.body or '{}')
            question_ids = data.get('question_ids', [])
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid data'}, status=400)

    for idx, qid in enumerate(question_ids):
        QuestionnaireQuestion.objects.filter(pk=qid, questionnaire=questionnaire).update(sort_order=idx)

    return JsonResponse({'ok': True})


@designer_required
def questionnaire_bulk_add(request, pk):
    from .models import Questionnaire, QuestionnaireQuestion
    questionnaire = get_object_or_404(Questionnaire, pk=pk, created_by=request.user)

    if request.method == 'POST':
        bulk_text = request.POST.get('bulk_text', '').strip()
        delimiter = request.POST.get('delimiter', 'newline')
        question_type = request.POST.get('question_type', 'text')
        is_required = request.POST.get('is_required') == 'on'

        if bulk_text:
            if delimiter == 'newline':
                lines = [l.strip() for l in bulk_text.split('\n') if l.strip()]
            elif delimiter == 'numbered':
                import re
                lines = re.split(r'\n\s*\d+[.)]\s*', bulk_text)
                lines = [l.strip() for l in lines if l.strip()]
            else:
                lines = [l.strip() for l in bulk_text.split(delimiter) if l.strip()]

            last_order = questionnaire.questions.order_by('-sort_order').first()
            next_order = (last_order.sort_order + 1) if last_order else 0

            created = 0
            for idx, line in enumerate(lines):
                QuestionnaireQuestion.objects.create(
                    questionnaire=questionnaire,
                    text=line,
                    question_type=question_type,
                    is_required=is_required,
                    sort_order=next_order + idx,
                )
                created += 1

            messages.success(request, f'{created} question(s) added.')
            return redirect('branding:questionnaire_detail', pk=pk)
        messages.error(request, 'No questions to add.')

    return render(request, 'branding/questionnaire/bulk_add.html', {
        'questionnaire': questionnaire,
        'request_obj': questionnaire.request,
    })


@designer_required
def questionnaire_from_template(request, pk, template_id):
    from .models import Questionnaire, QuestionnaireTemplate, QuestionnaireQuestion
    br = get_object_or_404(BrandingRequest, pk=pk, designer=request.user)
    template = get_object_or_404(QuestionnaireTemplate, pk=template_id)

    if request.method == 'POST':
        title = request.POST.get('title', template.name).strip()
        questionnaire = Questionnaire.objects.create(
            request=br,
            title=title,
            description=template.description,
            questionnaire_type='from_template',
            created_by=request.user,
        )

        template_questions = template.questions.all()
        for idx, tq in enumerate(template_questions):
            QuestionnaireQuestion.objects.create(
                questionnaire=questionnaire,
                text=tq.text,
                question_type=tq.question_type,
                is_required=tq.is_required,
                options=tq.options,
                placeholder=tq.placeholder,
                help_text=tq.help_text,
                max_length=tq.max_length,
                sort_order=idx,
            )

        br.log('QUESTIONNAIRE', f'Questionnaire created from template "{template.name}"', actor=request.user)
        messages.success(request, f'Questionnaire created from template "{template.name}".')
        return redirect('branding:questionnaire_detail', pk=questionnaire.pk)

    return redirect('branding:questionnaire_create', request_pk=pk)


@designer_required
def questionnaire_answers(request, pk):
    from .models import Questionnaire
    questionnaire = get_object_or_404(
        Questionnaire.objects.select_related('request'),
        pk=pk,
    )
    br = questionnaire.request
    if br.designer != request.user and not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('branding:dashboard')

    questions = questionnaire.questions.order_by('sort_order')
    answers = questionnaire.answers.select_related('question', 'client').all()

    answer_summary = []
    for q in questions:
        q_answers = answers.filter(question=q)
        response_count = q_answers.count()
        answer_summary.append({
            'question': q,
            'answers': q_answers,
            'response_count': response_count,
            'response_rate': round(response_count / max(1, 1) * 100),
        })

    total_clients = 1
    total_answered = answers.values('client').distinct().count()

    return render(request, 'branding/questionnaire/answers.html', {
        'questionnaire': questionnaire,
        'request_obj': br,
        'answer_summary': answer_summary,
        'total_clients': total_clients,
        'total_answered': total_answered,
    })


@designer_required
def questionnaire_export(request, pk):
    from .models import Questionnaire
    questionnaire = get_object_or_404(Questionnaire, pk=pk)
    br = questionnaire.request
    if br.designer != request.user and not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    answers = questionnaire.answers.select_related('question', 'client').order_by('question__sort_order')
    export_data = []
    for answer in answers:
        export_data.append({
            'question_id': answer.question_id,
            'question_text': answer.question.text,
            'question_type': answer.question.question_type,
            'answer': answer.value,
            'client': str(answer.client),
            'client_id': answer.client_id,
            'answered_at': answer.created_at.isoformat() if answer.created_at else None,
        })

    response = JsonResponse({
        'questionnaire': {
            'id': questionnaire.pk,
            'title': questionnaire.title,
            'request_number': br.request_number,
            'status': questionnaire.status,
        },
        'answers': export_data,
        'total_answers': len(export_data),
        'exported_at': timezone.now().isoformat(),
    }, json_dumps_params={'indent': 2})

    filename = f'questionnaire_{pk}_answers.json'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@designer_required
def questionnaire_smart_suggest(request, pk):
    from .models import Questionnaire
    br = get_object_or_404(BrandingRequest, pk=pk, designer=request.user)

    industry = br.industry or ''
    collection = br.collection
    brand_values = getattr(br, 'brand_values', []) or []

    suggested_questions = []

    industry_templates = {
        'technology': [
            'How do you position your technology vs. competitors?',
            'What is your target technical audience?',
            'How important is innovation messaging?',
        ],
        'healthcare': [
            'What patient demographics do you serve?',
            'How do you balance professionalism with approachability?',
            'What compliance considerations affect your brand?',
        ],
        'finance': [
            'How do you convey trust and reliability?',
            'What is your risk communication approach?',
            'Who are your primary stakeholders?',
        ],
        'retail': [
            'What is your price positioning strategy?',
            'How do you differentiate in-store vs. online?',
            'What emotional connection do you want to create?',
        ],
        'education': [
            'What age groups do you serve?',
            'How do you balance tradition with modernity?',
            'What is your digital learning philosophy?',
        ],
    }

    for key, questions in industry_templates.items():
        if key.lower() in industry.lower():
            suggested_questions.extend(questions)
            break

    if not suggested_questions:
        suggested_questions = [
            'What are your primary brand goals?',
            'Who is your target audience?',
            'What makes you unique in your market?',
            'How do you want customers to feel about your brand?',
        ]

    if collection:
        suggested_questions.append(f'How does your brand relate to the {collection.name} collection?')

    return render(request, 'branding/questionnaire/suggest.html', {
        'request_obj': br,
        'suggested_questions': suggested_questions,
        'industry': industry,
        'collection': collection,
        'brand_values': brand_values,
    })


@designer_required
def questionnaire_templates_list(request):
    from .models import QuestionnaireTemplate
    templates = QuestionnaireTemplate.objects.filter(
        Q(owner=request.user) | Q(is_shared=True)
    ).distinct().select_related('owner').order_by('-created_at')

    category_filter = request.GET.get('category', '')
    if category_filter:
        templates = templates.filter(category=category_filter)

    return render(request, 'branding/questionnaire/templates_list.html', {
        'templates': templates,
        'category_filter': category_filter,
    })


@designer_required
def questionnaire_template_create(request):
    from .models import QuestionnaireTemplate

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        category = request.POST.get('category', 'standard')
        is_shared = request.POST.get('is_shared') == 'on'

        if name:
            template = QuestionnaireTemplate.objects.create(
                name=name,
                description=description,
                category=category,
                is_shared=is_shared,
                owner=request.user,
            )
            messages.success(request, f'Template "{name}" created.')
            return redirect('branding:questionnaire_templates_list')
        messages.error(request, 'Template name is required.')

    return render(request, 'branding/questionnaire/template_create.html', {})


@designer_required
def questionnaire_analytics(request, request_pk):
    br = get_object_or_404(BrandingRequest, pk=request_pk, designer=request.user)
    questionnaires = br.questionnaires.all()

    total = questionnaires.count()
    sent = questionnaires.filter(status='sent').count()
    in_progress = questionnaires.filter(status='in_progress').count()
    completed = questionnaires.filter(status='completed').count()
    draft = questionnaires.filter(status='draft').count()

    completion_rate = round(completed / max(sent + in_progress + completed, 1) * 100)
    avg_reminders = questionnaires.aggregate(
        avg=Avg('email_reminder_count')
    )['avg'] or 0

    from .models import QuestionnaireAnswer
    total_answers = QuestionnaireAnswer.objects.filter(questionnaire__request=br).count()
    avg_answers_per = round(total_answers / max(total, 1), 1)

    by_status = [
        {'status': 'Draft', 'count': draft},
        {'status': 'Sent', 'count': sent},
        {'status': 'In Progress', 'count': in_progress},
        {'status': 'Completed', 'count': completed},
    ]

    timeline_data = list(
        questionnaires.values('created_at__date').annotate(c=Count('id')).order_by('created_at__date')
    )

    return render(request, 'branding/questionnaire/analytics.html', {
        'request_obj': br,
        'questionnaires': questionnaires,
        'total': total,
        'sent': sent,
        'in_progress': in_progress,
        'completed': completed,
        'draft': draft,
        'completion_rate': completion_rate,
        'avg_reminders': round(avg_reminders, 1),
        'total_answers': total_answers,
        'avg_answers_per': avg_answers_per,
        'by_status': by_status,
        'timeline_data': json.dumps(timeline_data),
    })


@designer_required
def decision_points(request, request_pk):
    from .models import DecisionPoint
    br = get_object_or_404(BrandingRequest, pk=request_pk, designer=request.user)
    decision_points = DecisionPoint.objects.filter(
        request=br
    ).select_related('questionnaire').order_by('-created_at')

    status_filter = request.GET.get('status', '')
    if status_filter:
        decision_points = decision_points.filter(status=status_filter)

    if request.method == 'POST' and request.POST.get('action') == 'create_dp':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        dp_type = request.POST.get('dp_type', 'binary')

        if title:
            DecisionPoint.objects.create(
                request=br,
                title=title,
                description=description,
                decision_type=dp_type,
                created_by=request.user,
            )
            br.log('DECISION_POINT', f'Decision point "{title}" created', actor=request.user)
            messages.success(request, f'Decision point "{title}" created.')
            return redirect('branding:decision_points', request_pk=request_pk)
        messages.error(request, 'Title is required.')

    return render(request, 'branding/questionnaire/decisions.html', {
        'request_obj': br,
        'decision_points': decision_points,
        'status_filter': status_filter,
    })


@designer_required
@require_POST
def decision_point_update(request, pk):
    from .models import DecisionPoint
    dp = get_object_or_404(
        DecisionPoint.objects.select_related('request'),
        pk=pk,
    )
    if dp.request.designer != request.user:
        messages.error(request, 'Access denied.')
        return redirect('branding:dashboard')

    new_status = request.POST.get('status', '')
    valid_statuses = ['pending', 'decided', 'deferred', 'cancelled']
    if new_status in valid_statuses:
        dp.status = new_status
        if new_status == 'decided':
            dp.decided_at = timezone.now()
            dp.decided_by = request.user
        dp.save(update_fields=['status', 'decided_at', 'decided_by', 'updated_at'])
        dp.request.log(
            'DECISION_POINT',
            f'Decision point "{dp.title}" status changed to {new_status}',
            actor=request.user,
        )
        messages.success(request, f'Decision point updated to {new_status}.')
    else:
        messages.error(request, 'Invalid status.')

    return redirect('branding:decision_points', request_pk=dp.request.pk)


@designer_required
def preference_profile(request, request_pk):
    br = get_object_or_404(BrandingRequest, pk=request_pk, designer=request.user)
    from .models import PreferenceProfile
    profile, created = PreferenceProfile.objects.get_or_create(
        request=br,
        defaults={'created_by': request.user},
    )

    if request.method == 'POST':
        action = request.POST.get('action', 'save')

        if action == 'save':
            style_preferences = request.POST.getlist('style_preferences')
            color_preferences = request.POST.getlist('color_preferences')
            typography_preferences = request.POST.getlist('typography_preferences')
            tone_of_voice = request.POST.get('tone_of_voice', '').strip()
            target_demographic = request.POST.get('target_demographic', '').strip()
            competitor_notes = request.POST.get('competitor_notes', '').strip()
            additional_context = request.POST.get('additional_context', '').strip()

            profile.style_preferences = style_preferences
            profile.color_preferences = color_preferences
            profile.typography_preferences = typography_preferences
            profile.tone_of_voice = tone_of_voice
            profile.target_demographic = target_demographic
            profile.competitor_notes = competitor_notes
            profile.additional_context = additional_context
            profile.save()
            br.log('PREFERENCE', 'Client preference profile updated', actor=request.user)
            messages.success(request, 'Preference profile saved.')
            return redirect('branding:preference_profile', request_pk=request_pk)

    return render(request, 'branding/questionnaire/profile.html', {
        'request_obj': br,
        'profile': profile,
    })


# ── Client-Facing Views ──────────────────────────────────────────────────

def client_questionnaire(request, token):
    from .models import Questionnaire, QuestionnaireAnswer
    try:
        from .models import QuestionnaireToken
        qt = QuestionnaireToken.objects.select_related('questionnaire', 'questionnaire__request').get(token=token)
    except Exception:
        raise Http404('Invalid questionnaire link.')

    questionnaire = qt.questionnaire
    br = questionnaire.request

    if qt.is_expired:
        messages.error(request, 'This questionnaire link has expired.')
        return render(request, 'branding/questionnaire/client_expired.html', {
            'questionnaire': questionnaire,
        })

    if qt.is_used and questionnaire.status == 'completed':
        messages.info(request, 'You have already completed this questionnaire.')
        return render(request, 'branding/questionnaire/client_completed.html', {
            'questionnaire': questionnaire,
        })

    questions = questionnaire.questions.order_by('sort_order')
    existing_answers = {}
    if qt.client:
        for ans in QuestionnaireAnswer.objects.filter(
            questionnaire=questionnaire, client=qt.client
        ):
            existing_answers[ans.question_id] = ans

    question_data = []
    for q in questions:
        question_data.append({
            'question': q,
            'existing_answer': existing_answers.get(q.pk),
        })

    if questionnaire.status == 'draft':
        questionnaire.status = 'in_progress'
        questionnaire.save(update_fields=['status', 'updated_at'])

    return render(request, 'branding/questionnaire/client_view.html', {
        'questionnaire': questionnaire,
        'request_obj': br,
        'questions': question_data,
        'token': token,
    })


@require_POST
def client_questionnaire_submit(request, token):
    from .models import Questionnaire, QuestionnaireAnswer, QuestionnaireToken
    try:
        qt = QuestionnaireToken.objects.select_related('questionnaire').get(token=token)
    except QuestionnaireToken.DoesNotExist:
        raise Http404('Invalid questionnaire link.')

    questionnaire = qt.questionnaire
    client = qt.client or request.user if request.user.is_authenticated else None

    questions = questionnaire.questions.order_by('sort_order')
    for q in questions:
        answer_value = request.POST.get(f'question_{q.pk}', '').strip()
        if answer_value or not q.is_required:
            QuestionnaireAnswer.objects.update_or_create(
                questionnaire=questionnaire,
                question=q,
                client=client,
                defaults={'value': answer_value},
            )

    questionnaire.status = 'completed'
    questionnaire.completed_at = timezone.now()
    questionnaire.save(update_fields=['status', 'completed_at', 'updated_at'])

    qt.is_used = True
    qt.used_at = timezone.now()
    qt.save(update_fields=['is_used', 'used_at'])

    br = questionnaire.request
    br.log('QUESTIONNAIRE', f'Questionnaire "{questionnaire.title}" completed by client', actor=request.user)

    if br.user:
        _notify(
            br.user, br, 'QUESTIONNAIRE_COMPLETED',
            f'Questionnaire "{questionnaire.title}" has been completed.',
            email_subject=f'[OnWebApp Branding] Questionnaire Completed: {questionnaire.title}',
        )

    messages.success(request, 'Thank you! Your answers have been submitted.')
    return render(request, 'branding/questionnaire/client_thankyou.html', {
        'questionnaire': questionnaire,
        'request_obj': br,
    })


@require_POST
def client_question_answer(request, token, qid):
    from .models import Questionnaire, QuestionnaireQuestion, QuestionnaireAnswer, QuestionnaireToken
    try:
        qt = QuestionnaireToken.objects.select_related('questionnaire').get(token=token)
    except QuestionnaireToken.DoesNotExist:
        return JsonResponse({'error': 'Invalid token'}, status=403)

    question = get_object_or_404(QuestionnaireQuestion, pk=qid, questionnaire=qt.questionnaire)
    client = qt.client or request.user if request.user.is_authenticated else None

    try:
        data = json.loads(request.body or '{}')
        answer_value = data.get('answer', '').strip()
    except json.JSONDecodeError:
        answer_value = request.POST.get('answer', '').strip()

    if question.is_required and not answer_value:
        return JsonResponse({'error': 'This question is required.'}, status=400)

    answer, created = QuestionnaireAnswer.objects.update_or_create(
        questionnaire=qt.questionnaire,
        question=question,
        client=client,
        defaults={'value': answer_value},
    )

    return JsonResponse({
        'ok': True,
        'created': created,
        'question_id': question.pk,
    })


@require_POST
def client_decision_respond(request, token, dp_id):
    from .models import QuestionnaireToken, DecisionPoint, DecisionPointResponse
    try:
        qt = QuestionnaireToken.objects.select_related('questionnaire', 'request').get(token=token)
    except QuestionnaireToken.DoesNotExist:
        return JsonResponse({'error': 'Invalid token'}, status=403)

    dp = get_object_or_404(DecisionPoint, pk=dp_id, request=qt.request)
    client = qt.client or request.user if request.user.is_authenticated else None

    choice = request.POST.get('choice', '').strip()
    notes = request.POST.get('notes', '').strip()

    if not choice:
        return JsonResponse({'error': 'Please select a choice.'}, status=400)

    DecisionPointResponse.objects.update_or_create(
        decision_point=dp,
        client=client,
        defaults={'choice': choice, 'notes': notes},
    )

    responded_count = dp.responses.count()
    total_expected = 1

    if responded_count >= total_expected:
        dp.status = 'decided'
        dp.decided_at = timezone.now()
        dp.save(update_fields=['status', 'decided_at', 'updated_at'])

    return JsonResponse({
        'ok': True,
        'decision_point_id': dp.pk,
        'choice': choice,
    })
