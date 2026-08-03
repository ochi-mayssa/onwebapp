"""Enhanced Django admin for the Branding Service."""
import csv

from django.contrib import admin, messages
from django.contrib.admin.actions import delete_selected
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, mark_safe

from .models import (
    AdobeAsset,
    AdobeConnection,
    AssetOrganizerItem,
    BrandCollection,
    BrandGuidelineCheck,
    BrandingAsset,
    BrandingAssetVersion,
    BrandingClientProfile,
    BrandingFeedback,
    BrandingMessage,
    BrandingNotification,
    BrandingRequest,
    BrandingTimeline,
    BrandingWebhook,
    CalendarConnection,
    CalendarEvent,
    CollectionPerformance,
    ColorPalette,
    ConsentRecord,
    CritiqueTemplate,
    DailyAggregate,
    DataExportRequest,
    DesignComment,
    DesignDraft,
    DesignHandoff,
    DesignNote,
    DesignResource,
    DesignTemplate,
    DesignerNote,
    DraftVersion,
    FeedbackRequest,
    FeedbackQuestion,
    FigmaComment,
    FigmaConnection,
    FigmaDesign,
    FontEntry,
    HandoffDeliverable,
    HandoffNote,
    KnowledgeArticle,
    PeerReview,
    PeerReviewFeedback,
    PrivacyAcceptance,
    ProjectReview,
    ShowcaseProject,
    SlackConnection,
    SlackMessage,
    StaffWorkload,
    TimeEntry,
    WebhookDelivery,
    WidgetDefinition,
    StaffDashboard,
    DashboardWidget,
    RoleSwitchLog,
    ProjectWorkflow,
    WorkflowStageLog,
    ClientQuestion,
    FeedbackItem,
    DesignIteration,
    DecisionLog,
    CommunicationEntry,
    DesignConcept,
    ConceptImage,
    ConceptElementRating,
    ConceptAnnotation,
    ConceptFeedback,
    ConceptStickyNote,
    ConceptDecision,
    ConceptDecisionTrail,
    ConceptRefinement,
    ConceptRefinementIteration,
    ConceptComparison,
    ConceptPresentationSession,
    Questionnaire,
    Question,
    QuestionCondition,
    Answer,
    QuestionnaireTemplate,
    DecisionPoint,
    ClientPreferenceProfile,
)


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------

class BrandingAssetInline(admin.TabularInline):
    model = BrandingAsset
    extra = 0
    fields = (
        'file', 'original_name', 'asset_type', 'detected_mime', 'size',
        'scan_status', 'scan_result', 'uploaded_at',
    )
    readonly_fields = (
        'original_name', 'detected_mime', 'size',
        'scan_status', 'scan_result', 'uploaded_at',
    )


class BrandingTimelineInline(admin.TabularInline):
    model = BrandingTimeline
    extra = 0
    fields = ('event_type', 'action', 'description', 'actor', 'created_at')
    readonly_fields = ('event_type', 'action', 'description', 'actor', 'created_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class BrandingMessageInline(admin.TabularInline):
    model = BrandingMessage
    extra = 0
    fields = ('sender', 'content', 'is_read_by_client', 'is_read_by_staff', 'created_at')
    readonly_fields = ('sender', 'content', 'is_read_by_client', 'is_read_by_staff', 'created_at')
    raw_id_fields = ('sender',)

    def has_add_permission(self, request, obj=None):
        return False


class BrandingFeedbackInline(admin.StackedInline):
    model = BrandingFeedback
    extra = 0
    fields = ('rating', 'comment', 'would_recommend', 'staff_response', 'responded_by', 'created_at')
    readonly_fields = ('rating', 'comment', 'would_recommend', 'created_at')

    def has_add_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Custom filters
# ---------------------------------------------------------------------------

class DateRangeFilter(admin.SimpleListFilter):
    """Filter by created_at date range with predefined options."""
    title = 'date range'
    parameter_name = 'date_range'

    def lookups(self, request, model_admin):
        return (
            ('today', 'Today'),
            ('yesterday', 'Yesterday'),
            ('this_week', 'This week'),
            ('last_7_days', 'Last 7 days'),
            ('last_30_days', 'Last 30 days'),
            ('this_month', 'This month'),
            ('last_month', 'Last month'),
            ('this_year', 'This year'),
        )

    def queryset(self, request, queryset):
        today = timezone.now().date()
        value = self.value()

        if value == 'today':
            return queryset.filter(created_at__date=today)
        elif value == 'yesterday':
            return queryset.filter(created_at__date=today - timezone.timedelta(days=1))
        elif value == 'this_week':
            start = today - timezone.timedelta(days=today.weekday())
            return queryset.filter(created_at__date__gte=start)
        elif value == 'last_7_days':
            return queryset.filter(created_at__date__gte=today - timezone.timedelta(days=7))
        elif value == 'last_30_days':
            return queryset.filter(created_at__date__gte=today - timezone.timedelta(days=30))
        elif value == 'this_month':
            return queryset.filter(created_at__date__year=today.year, created_at__date__month=today.month)
        elif value == 'last_month':
            last_month = today.replace(day=1) - timezone.timedelta(days=1)
            return queryset.filter(created_at__date__year=last_month.year, created_at__date__month=last_month.month)
        elif value == 'this_year':
            return queryset.filter(created_at__date__year=today.year)
        return queryset


class CompletionDateFilter(admin.SimpleListFilter):
    """Filter by completion date range."""
    title = 'completed'
    parameter_name = 'completed_range'

    def lookups(self, request, model_admin):
        return (
            ('last_7_days', 'Last 7 days'),
            ('last_30_days', 'Last 30 days'),
            ('this_month', 'This month'),
            ('never', 'Never completed'),
        )

    def queryset(self, request, queryset):
        today = timezone.now().date()
        value = self.value()

        if value == 'last_7_days':
            return queryset.filter(completed_at__date__gte=today - timezone.timedelta(days=7))
        elif value == 'last_30_days':
            return queryset.filter(completed_at__date__gte=today - timezone.timedelta(days=30))
        elif value == 'this_month':
            return queryset.filter(completed_at__date__year=today.year, completed_at__date__month=today.month)
        elif value == 'never':
            return queryset.filter(completed_at__isnull=True)
        return queryset


# ---------------------------------------------------------------------------
# BrandingRequest Admin (enhanced)
# ---------------------------------------------------------------------------

@admin.register(BrandingRequest)
class BrandingRequestAdmin(admin.ModelAdmin):
    list_display = (
        'request_number_display', 'company_name', 'industry', 'status_badge',
        'priority_display', 'designer_name', 'user_email', 'days_open',
        'created_at',
    )
    list_filter = (
        'status', 'priority', 'industry', 'retention_period',
        DateRangeFilter, CompletionDateFilter, 'anonymized',
    )
    search_fields = (
        'request_number', 'company_name', 'user__username', 'user__email',
        'user__first_name', 'user__last_name', 'designer__username',
        'country', 'industry',
    )
    readonly_fields = (
        'request_number', 'created_at', 'updated_at', 'completed_at',
        'days_open_display',
    )
    inlines = (BrandingAssetInline, BrandingTimelineInline, BrandingMessageInline, BrandingFeedbackInline)
    list_per_page = 25
    list_max_show_all = 100
    date_hierarchy = 'created_at'
    save_on_top = True

    # ── Bulk Actions ──
    actions = [
        'action_bulk_status_pending',
        'action_bulk_status_assigned',
        'action_bulk_status_designing',
        'action_bulk_status_completed',
        'action_bulk_archive',
        'action_bulk_assign_designer',
        'action_export_csv',
        'action_send_status_email',
        'action_send_bulk_notification',
        delete_selected,
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'designer', 'collection')

    # ── Custom display fields ──
    def request_number_display(self, obj):
        url = reverse('admin:branding_brandingrequest_change', args=[obj.pk])
        return format_html('<a href="{}" style="font-weight:700; color:#4f46e5;">{}</a>', url, obj.request_number or '—')
    request_number_display.short_description = 'Request #'
    request_number_display.admin_order_field = 'request_number'

    def status_badge(self, obj):
        colors = {
            'DRAFT': 'draft', 'PENDING_REVIEW': 'pending', 'IN_REVIEW': 'review',
            'ASSIGNED': 'assigned', 'DESIGNING': 'designing', 'WAITING_CLIENT': 'waiting',
            'REVISION': 'revision', 'APPROVED': 'approved', 'COMPLETED': 'completed',
            'ARCHIVED': 'archived',
        }
        css = colors.get(obj.status, 'draft')
        return format_html('<span class="status-badge badge-{}">{}</span>', css, obj.get_status_display())
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'

    def priority_display(self, obj):
        return format_html(
            '<span class="priority-dot priority-{}"></span>{}',
            obj.priority, obj.get_priority_display()
        )
    priority_display.short_description = 'Priority'
    priority_display.admin_order_field = 'priority'

    def designer_name(self, obj):
        if obj.designer:
            return obj.designer.get_full_name() or obj.designer.username
        return '—'
    designer_name.short_description = 'Designer'
    designer_name.admin_order_field = 'designer__username'

    def user_email(self, obj):
        if obj.user and obj.user.email:
            return format_html('<span class="small">{}</span>', obj.user.email)
        return '—'
    user_email.short_description = 'Client'

    def days_open(self, obj):
        if obj.completed_at:
            delta = obj.completed_at - obj.created_at
            return f'{delta.days}d'
        delta = timezone.now() - obj.created_at
        return f'{delta.days}d'
    days_open.short_description = 'Age'

    def days_open_display(self, obj):
        return self.days_open(obj)
    days_open_display.short_description = 'Days Open'

    # ── Bulk Status Actions ──
    def _bulk_status(self, request, queryset, new_status, label):
        count = queryset.exclude(status=new_status).update(status=new_status, updated_at=timezone.now())
        self.message_user(request, f'{count} request(s) updated to {label}.', messages.SUCCESS)

    def action_bulk_status_pending(self, request, queryset):
        self._bulk_status(request, queryset, 'PENDING_REVIEW', 'Pending Review')

    def action_bulk_status_assigned(self, request, queryset):
        self._bulk_status(request, queryset, 'ASSIGNED', 'Assigned')

    def action_bulk_status_designing(self, request, queryset):
        self._bulk_status(request, queryset, 'DESIGNING', 'Designing')

    def action_bulk_status_completed(self, request, queryset):
        count = queryset.exclude(status='COMPLETED').update(
            status='COMPLETED', completed_at=timezone.now(), updated_at=timezone.now()
        )
        self.message_user(request, f'{count} request(s) marked as Completed.', messages.SUCCESS)

    # ── Bulk Archive ──
    def action_bulk_archive(self, request, queryset):
        count = queryset.exclude(status='ARCHIVED').update(
            status='ARCHIVED', updated_at=timezone.now()
        )
        self.message_user(request, f'{count} request(s) archived.', messages.SUCCESS)
    action_bulk_archive.short_description = 'Archive selected'

    # ── Bulk Assign Designer ──
    def action_bulk_assign_designer(self, request, queryset):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        designer_id = request.POST.get('designer_id')
        if not designer_id:
            self.message_user(request, 'No designer selected. Use the dropdown above the action button.', messages.WARNING)
            return
        designer = User.objects.filter(pk=designer_id, is_staff=True).first()
        if not designer:
            self.message_user(request, 'Invalid designer.', messages.ERROR)
            return
        count = queryset.update(designer=designer, updated_at=timezone.now())
        self.message_user(request, f'{count} request(s) assigned to {designer.get_full_name() or designer.username}.', messages.SUCCESS)
    action_bulk_assign_designer.short_description = 'Assign designer to selected'

    # ── Export CSV ──
    def action_export_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="branding_requests_{timezone.now():%Y%m%d_%H%M}.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Request #', 'Company', 'Industry', 'Status', 'Priority',
            'Designer', 'Client Email', 'Country', 'Created', 'Completed',
        ])
        for r in queryset.select_related('user', 'designer'):
            writer.writerow([
                r.request_number, r.company_name, r.industry, r.status,
                r.priority, str(r.designer) if r.designer else '',
                r.user.email if r.user else '', r.country,
                r.created_at.isoformat() if r.created_at else '',
                r.completed_at.isoformat() if r.completed_at else '',
            ])
        return response
    action_export_csv.short_description = 'Export selected to CSV'

    # ── Send Status Email ──
    def action_send_status_email(self, request, queryset):
        from .emails import send_status_update_email
        sent = 0
        for r in queryset:
            if r.user and r.user.email:
                send_status_update_email(r.user, r)
                sent += 1
        self.message_user(request, f'Sent status emails to {sent} client(s).', messages.SUCCESS)
    action_send_status_email.short_description = 'Send status update email'

    # ── Send Bulk Notification ──
    def action_send_bulk_notification(self, request, queryset):
        from .models import BrandingNotification
        title = request.POST.get('notification_title', '')
        body = request.POST.get('notification_body', '')
        if not title or not body:
            self.message_user(request, 'No title/body provided. Use the fields above the action button.', messages.WARNING)
            return
        count = 0
        for r in queryset:
            if r.user:
                BrandingNotification.objects.create(
                    recipient=r.user,
                    request=r,
                    notification_type='SYSTEM',
                    message=body[:500],
                )
                count += 1
        self.message_user(request, f'Sent notification to {count} client(s).', messages.SUCCESS)
    action_send_bulk_notification.short_description = 'Send bulk notification'

    # ── Fieldsets ──
    fieldsets = (
        (None, {
            'fields': (
                'request_number', 'user', 'status', 'priority',
                'current_step', 'estimated_delivery_date', 'completed_at',
                'days_open_display',
            ),
        }),
        ('Step 1 — Company Information', {
            'classes': ('collapse',),
            'fields': ('company_name', 'industry', 'website', 'country', 'business_description'),
        }),
        ('Step 2 — Brand Identity', {
            'classes': ('collapse',),
            'fields': (
                'company_description', 'target_audience',
                'brand_values', 'preferred_colors', 'current_branding',
            ),
        }),
        ('Step 3 — Assets & Notes', {
            'classes': ('collapse',),
            'fields': ('additional_notes',),
        }),
        ('Step 4 — Collection', {'fields': ('collection',)}),
        ('Internal Workflow', {
            'fields': ('designer', 'internal_notes', 'created_at', 'updated_at'),
        }),
        ('GDPR — Consent & Retention', {
            'classes': ('collapse',),
            'fields': (
                'consent_data_processing', 'consent_marketing',
                'consent_analytics', 'consent_third_party', 'consent_timestamp',
                'retention_period', 'anonymized', 'anonymized_at',
                'deletion_requested_at',
            ),
        }),
    )


# ---------------------------------------------------------------------------
# Other Model Admins
# ---------------------------------------------------------------------------

@admin.register(BrandCollection)
class BrandCollectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'industry', 'is_active', 'sort_order')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'description', 'industry')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('is_active', 'sort_order')
    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'category', 'industry', 'description',
                       'style_tags', 'examples', 'preview_image', 'accent_color',
                       'is_active', 'sort_order'),
        }),
        ('Preview Kit', {
            'classes': ('collapse',),
            'fields': (
                'hero_image', 'logo_image', 'typography_image', 'business_card_image',
                'presentation_image', 'letterhead_image', 'email_signature_image',
                'social_media_image', 'brand_guidelines_image',
                'color_palette', 'fonts',
            ),
        }),
    )


@admin.register(BrandingAsset)
class BrandingAssetAdmin(admin.ModelAdmin):
    list_display = ('original_name', 'request', 'asset_type', 'detected_mime', 'size', 'scan_status', 'uploaded_at')
    list_filter = ('asset_type', 'scan_status', 'uploaded_at')
    search_fields = ('original_name', 'request__request_number', 'request__company_name')
    raw_id_fields = ('request',)
    readonly_fields = ('detected_mime', 'file_hash', 'scan_status', 'scan_result', 'uploaded_at')


@admin.register(BrandingTimeline)
class BrandingTimelineAdmin(admin.ModelAdmin):
    list_display = ('request', 'event_type', 'action', 'actor', 'created_at')
    list_filter = ('event_type', 'created_at')
    search_fields = ('action', 'description', 'request__request_number')
    raw_id_fields = ('request', 'actor')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'


@admin.register(BrandingAssetVersion)
class BrandingAssetVersionAdmin(admin.ModelAdmin):
    list_display = ('asset', 'version_number', 'original_name', 'size', 'uploaded_by', 'created_at')
    raw_id_fields = ('asset', 'uploaded_by')
    readonly_fields = ('created_at',)


@admin.register(BrandingMessage)
class BrandingMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'request', 'sender', 'parent', 'is_read_by_client', 'is_read_by_staff', 'created_at')
    list_filter = ('is_read_by_client', 'is_read_by_staff', 'created_at')
    search_fields = ('content', 'sender__username', 'request__request_number')
    raw_id_fields = ('request', 'sender', 'parent')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BrandingNotification)
class BrandingNotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'recipient', 'request', 'notification_type', 'message_short', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('recipient__username', 'message', 'request__request_number')
    raw_id_fields = ('recipient', 'request')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'

    def message_short(self, obj):
        return obj.message[:80] + '...' if len(obj.message) > 80 else obj.message
    message_short.short_description = 'Message'


@admin.register(BrandingClientProfile)
class BrandingClientProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'default_industry', 'default_country', 'created_at')
    search_fields = ('user__username', 'user__email')
    raw_id_fields = ('user',)
    filter_horizontal = ('favorite_collections',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BrandingFeedback)
class BrandingFeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'request', 'rating_display', 'would_recommend', 'responded_by', 'created_at')
    list_filter = ('rating', 'would_recommend', 'created_at')
    search_fields = ('request__request_number', 'request__company_name', 'comment')
    raw_id_fields = ('request', 'responded_by')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'

    def rating_display(self, obj):
        stars = '★' * obj.rating + '☆' * (5 - obj.rating)
        return format_html('<span class="star">{}</span> ({})', stars, obj.rating)
    rating_display.short_description = 'Rating'


@admin.register(BrandingWebhook)
class BrandingWebhookAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'is_active', 'failure_count', 'last_triggered_at', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'url')
    readonly_fields = ('last_triggered_at', 'failure_count', 'created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('name', 'url', 'is_active')}),
        ('Events', {'fields': ('events',), 'description': 'Select which events trigger this webhook.'}),
        ('Security', {'fields': ('secret',), 'description': 'Shared secret for HMAC-SHA256 signing.'}),
        ('Stats', {'fields': ('last_triggered_at', 'failure_count', 'created_at', 'updated_at')}),
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields
        return ('last_triggered_at', 'failure_count')


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ('id', 'webhook', 'event_type', 'status', 'status_code', 'attempt', 'created_at')
    list_filter = ('status', 'event_type', 'created_at')
    search_fields = ('webhook__name', 'event_type')
    raw_id_fields = ('webhook',)
    readonly_fields = ('webhook', 'event_type', 'payload', 'status', 'status_code',
                       'response_body', 'attempt', 'created_at', 'completed_at')
    date_hierarchy = 'created_at'


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'consent_type', 'action', 'ip_address', 'created_at')
    list_filter = ('consent_type', 'action', 'created_at')
    search_fields = ('user__username', 'user__email', 'ip_address')
    raw_id_fields = ('user', 'request')
    readonly_fields = ('user', 'request', 'consent_type', 'action', 'ip_address',
                       'user_agent', 'created_at')
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(DataExportRequest)
class DataExportRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'export_format', 'requested_at', 'completed_at', 'expires_at')
    list_filter = ('status', 'export_format')
    search_fields = ('user__username', 'user__email')
    raw_id_fields = ('user',)
    readonly_fields = ('user', 'status', 'export_format', 'file', 'error_message',
                       'requested_at', 'completed_at', 'expires_at')
    date_hierarchy = 'requested_at'

    def has_add_permission(self, request):
        return False


@admin.register(PrivacyAcceptance)
class PrivacyAcceptanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'page', 'version', 'accepted', 'ip_address', 'created_at')
    list_filter = ('page', 'accepted', 'version')
    search_fields = ('user__username', 'user__email')
    raw_id_fields = ('user',)
    readonly_fields = ('user', 'page', 'version', 'accepted', 'ip_address', 'created_at')


@admin.register(DailyAggregate)
class DailyAggregateAdmin(admin.ModelAdmin):
    list_display = ('date', 'total_requests', 'new_requests', 'completed_requests',
                    'avg_completion_days', 'satisfaction_avg')
    list_filter = ('date',)
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'date'


@admin.register(StaffWorkload)
class StaffWorkloadAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'assigned_count', 'in_progress_count',
                    'completed_count', 'messages_sent', 'avg_response_hours')
    list_filter = ('date',)
    search_fields = ('user__username', 'user__email')
    raw_id_fields = ('user',)
    date_hierarchy = 'date'


@admin.register(CollectionPerformance)
class CollectionPerformanceAdmin(admin.ModelAdmin):
    list_display = ('collection', 'date', 'times_selected', 'times_completed', 'avg_satisfaction')
    list_filter = ('date', 'collection')
    search_fields = ('collection__name',)
    raw_id_fields = ('collection',)
    date_hierarchy = 'date'


@admin.register(DesignerNote)
class DesignerNoteAdmin(admin.ModelAdmin):
    list_display = ('designer', 'author', 'content_short', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('designer__username', 'designer__email', 'content', 'author__username')
    raw_id_fields = ('designer', 'author')
    readonly_fields = ('created_at', 'updated_at')

    def content_short(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
    content_short.short_description = 'Content'


@admin.register(ProjectReview)
class ProjectReviewAdmin(admin.ModelAdmin):
    list_display = ('request', 'reviewer', 'status', 'checklist_progress_display', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('request__request_number', 'request__company_name', 'reviewer__username', 'notes')
    raw_id_fields = ('request', 'reviewer')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'

    def checklist_progress_display(self, obj):
        checked, total = obj.checklist_progress
        return f'{checked}/{total} ({obj.checklist_percentage}%)'
    checklist_progress_display.short_description = 'Checklist'


# ────────────────────────────────────────────────────────────────────────────
# Designer Workflow Tools
# ────────────────────────────────────────────────────────────────────────────

@admin.register(DesignDraft)
class DesignDraftAdmin(admin.ModelAdmin):
    list_display = ('title', 'request', 'designer', 'is_submitted', 'version_count', 'created_at')
    list_filter = ('is_submitted', 'created_at')
    search_fields = ('title', 'request__request_number', 'designer__username')
    raw_id_fields = ('request', 'designer')
    readonly_fields = ('created_at', 'updated_at')

    def version_count(self, obj):
        return obj.version_count
    version_count.short_description = 'Versions'


@admin.register(DraftVersion)
class DraftVersionAdmin(admin.ModelAdmin):
    list_display = ('draft', 'version_number', 'version_type', 'original_name', 'size', 'uploaded_by', 'created_at')
    list_filter = ('version_type', 'created_at')
    search_fields = ('original_name', 'draft__title')
    raw_id_fields = ('draft', 'uploaded_by')
    readonly_fields = ('created_at',)


@admin.register(FeedbackRequest)
class FeedbackRequestAdmin(admin.ModelAdmin):
    list_display = ('subject', 'request', 'designer', 'status', 'question_count', 'client_responded_at', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('subject', 'request__request_number', 'designer__username')
    raw_id_fields = ('request', 'designer')
    readonly_fields = ('created_at', 'updated_at', 'client_responded_at')

    def question_count(self, obj):
        return obj.questions.count()
    question_count.short_description = 'Questions'


@admin.register(FeedbackQuestion)
class FeedbackQuestionAdmin(admin.ModelAdmin):
    list_display = ('feedback_request', 'sort_order', 'question', 'is_answered', 'answered_at')
    list_filter = ('answered_at',)
    raw_id_fields = ('feedback_request',)

    def is_answered(self, obj):
        return obj.is_answered
    is_answered.boolean = True
    is_answered.short_description = 'Answered'


@admin.register(DesignResource)
class DesignResourceAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'shared_level', 'owner', 'collection', 'download_count', 'is_active', 'created_at')
    list_filter = ('category', 'shared_level', 'is_active', 'created_at')
    search_fields = ('title', 'owner__username')
    raw_id_fields = ('owner', 'collection')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ('designer', 'request', 'phase', 'duration_display', 'date', 'is_timer_running', 'created_at')
    list_filter = ('phase', 'date', 'is_timer_running')
    search_fields = ('designer__username', 'request__request_number', 'description')
    raw_id_fields = ('request', 'designer')
    readonly_fields = ('created_at', 'updated_at')

    def duration_display(self, obj):
        return obj.duration_display
    duration_display.short_description = 'Duration'


@admin.register(DesignNote)
class DesignNoteAdmin(admin.ModelAdmin):
    list_display = ('title', 'request', 'author', 'category', 'is_pinned', 'created_at')
    list_filter = ('category', 'is_pinned', 'created_at')
    search_fields = ('title', 'content', 'request__request_number')
    raw_id_fields = ('request', 'author')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DesignTemplate)
class DesignTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'owner', 'is_team_shared', 'use_count', 'created_at')
    list_filter = ('category', 'is_team_shared', 'created_at')
    search_fields = ('name', 'content', 'owner__username')
    raw_id_fields = ('owner',)
    readonly_fields = ('created_at', 'updated_at')


# ────────────────────────────────────────────────────────────────────────────
# Collaboration Features
# ────────────────────────────────────────────────────────────────────────────

@admin.register(CritiqueTemplate)
class CritiqueTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'created_by', 'use_count', 'created_at')
    list_filter = ('category', 'created_at')
    search_fields = ('name', 'description')
    raw_id_fields = ('created_by',)
    readonly_fields = ('created_at',)


@admin.register(PeerReview)
class PeerReviewAdmin(admin.ModelAdmin):
    list_display = ('request', 'reviewer', 'requested_by', 'status', 'due_date', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('request__request_number', 'reviewer__username', 'requested_by__username')
    raw_id_fields = ('request', 'reviewer', 'requested_by', 'draft', 'critique_template')
    readonly_fields = ('created_at', 'updated_at', 'completed_at')


@admin.register(PeerReviewFeedback)
class PeerReviewFeedbackAdmin(admin.ModelAdmin):
    list_display = ('review', 'author', 'category', 'rating', 'is_resolved', 'created_at')
    list_filter = ('category', 'is_resolved', 'created_at')
    search_fields = ('content', 'author__username')
    raw_id_fields = ('review', 'author')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DesignComment)
class DesignCommentAdmin(admin.ModelAdmin):
    list_display = ('request', 'author', 'tag', 'is_resolved', 'is_pinned', 'created_at')
    list_filter = ('tag', 'is_resolved', 'is_pinned', 'created_at')
    search_fields = ('content', 'author__username', 'request__request_number')
    raw_id_fields = ('request', 'author', 'parent', 'resolved_by')
    readonly_fields = ('created_at', 'updated_at', 'resolved_at')
    filter_horizontal = ('mentions',)


@admin.register(DesignHandoff)
class DesignHandoffAdmin(admin.ModelAdmin):
    list_display = ('title', 'request', 'designer', 'status', 'handed_off_to', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('title', 'request__request_number', 'designer__username')
    raw_id_fields = ('request', 'designer', 'handed_off_to')
    readonly_fields = ('created_at', 'updated_at', 'handed_off_at')


@admin.register(HandoffDeliverable)
class HandoffDeliverableAdmin(admin.ModelAdmin):
    list_display = ('handoff', 'deliverable_type', 'original_name', 'size', 'uploaded_by', 'created_at')
    list_filter = ('deliverable_type', 'created_at')
    search_fields = ('original_name', 'handoff__title')
    raw_id_fields = ('handoff', 'uploaded_by')
    readonly_fields = ('created_at',)


@admin.register(HandoffNote)
class HandoffNoteAdmin(admin.ModelAdmin):
    list_display = ('handoff', 'title', 'note_type', 'author', 'created_at')
    list_filter = ('note_type', 'created_at')
    search_fields = ('title', 'content')
    raw_id_fields = ('handoff', 'author')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(KnowledgeArticle)
class KnowledgeArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'author', 'is_published', 'is_featured', 'view_count', 'helpful_count', 'created_at')
    list_filter = ('category', 'is_published', 'is_featured', 'created_at')
    search_fields = ('title', 'content', 'author__username')
    raw_id_fields = ('author', 'collection')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ShowcaseProject)
class ShowcaseProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'designer', 'category', 'client_name', 'project_year', 'is_featured', 'view_count', 'like_count', 'created_at')
    list_filter = ('category', 'is_featured', 'is_published', 'created_at')
    search_fields = ('title', 'description', 'designer__username', 'client_name')
    raw_id_fields = ('request', 'designer')
    readonly_fields = ('created_at', 'updated_at')


# ────────────────────────────────────────────────────────────────────────────
# Designer Integrations
# ────────────────────────────────────────────────────────────────────────────

@admin.register(FigmaConnection)
class FigmaConnectionAdmin(admin.ModelAdmin):
    list_display = ('user', 'figma_email', 'is_active', 'last_synced', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('figma_email', 'user__username')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(FigmaDesign)
class FigmaDesignAdmin(admin.ModelAdmin):
    list_display = ('figma_file_name', 'connection', 'request', 'sync_status', 'last_synced')
    list_filter = ('sync_status', 'created_at')
    search_fields = ('figma_file_name', 'figma_file_key')
    raw_id_fields = ('connection', 'request')
    readonly_fields = ('last_synced', 'created_at')


@admin.register(FigmaComment)
class FigmaCommentAdmin(admin.ModelAdmin):
    list_display = ('design', 'author_name', 'resolved', 'figma_created_at')
    list_filter = ('resolved', 'figma_created_at')
    search_fields = ('author_name', 'message')
    raw_id_fields = ('design',)


@admin.register(AdobeConnection)
class AdobeConnectionAdmin(admin.ModelAdmin):
    list_display = ('user', 'adobe_email', 'is_active', 'last_synced', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('adobe_email', 'user__username')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AdobeAsset)
class AdobeAssetAdmin(admin.ModelAdmin):
    list_display = ('asset_name', 'asset_type', 'library_name', 'connection', 'created_at')
    list_filter = ('asset_type', 'created_at')
    search_fields = ('asset_name', 'library_name')
    raw_id_fields = ('connection', 'request')
    readonly_fields = ('created_at',)


@admin.register(ColorPalette)
class ColorPaletteAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'is_public', 'use_count', 'created_at')
    list_filter = ('is_public', 'created_at')
    search_fields = ('name', 'owner__username')
    raw_id_fields = ('owner', 'request')
    readonly_fields = ('created_at',)


@admin.register(FontEntry)
class FontEntryAdmin(admin.ModelAdmin):
    list_display = ('name', 'family', 'owner', 'is_public', 'created_at')
    list_filter = ('is_public', 'created_at')
    search_fields = ('name', 'family')
    raw_id_fields = ('owner', 'request')
    readonly_fields = ('created_at',)


@admin.register(AssetOrganizerItem)
class AssetOrganizerItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'item_type', 'folder', 'owner', 'created_at')
    list_filter = ('item_type', 'folder', 'created_at')
    search_fields = ('name', 'folder')
    raw_id_fields = ('owner', 'request')
    readonly_fields = ('created_at',)


@admin.register(BrandGuidelineCheck)
class BrandGuidelineCheckAdmin(admin.ModelAdmin):
    list_display = ('check_name', 'request', 'result', 'checker', 'checked_at')
    list_filter = ('result', 'checked_at')
    search_fields = ('check_name', 'details')
    raw_id_fields = ('request', 'checker')
    readonly_fields = ('checked_at',)


@admin.register(SlackConnection)
class SlackConnectionAdmin(admin.ModelAdmin):
    list_display = ('user', 'workspace_name', 'channel_name', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('workspace_name', 'user__username')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SlackMessage)
class SlackMessageAdmin(admin.ModelAdmin):
    list_display = ('connection', 'message_type', 'channel', 'sent_at')
    list_filter = ('message_type', 'sent_at')
    search_fields = ('text', 'channel')
    raw_id_fields = ('connection', 'request')
    readonly_fields = ('sent_at',)


@admin.register(CalendarConnection)
class CalendarConnectionAdmin(admin.ModelAdmin):
    list_display = ('user', 'provider', 'calendar_name', 'is_active', 'last_synced', 'created_at')
    list_filter = ('provider', 'is_active', 'created_at')
    search_fields = ('calendar_name', 'user__username')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = ('title', 'event_type', 'connection', 'start_time', 'all_day', 'synced')
    list_filter = ('event_type', 'all_day', 'synced', 'start_time')
    search_fields = ('title', 'description')
    raw_id_fields = ('connection', 'request')
    readonly_fields = ('created_at', 'updated_at')


# ═══════════════════════════════════════════════════════════════════════════
# Unified Staff Dashboard
# ═══════════════════════════════════════════════════════════════════════════

@admin.register(WidgetDefinition)
class WidgetDefinitionAdmin(admin.ModelAdmin):
    list_display = ('label', 'widget_type', 'category', 'icon', 'default_width', 'default_height', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('label', 'description')
    ordering = ('category', 'label')


@admin.register(StaffDashboard)
class StaffDashboardAdmin(admin.ModelAdmin):
    list_display = ('user', 'layout', 'columns', 'compact_mode', 'show_sidebar', 'allow_role_switch', 'updated_at')
    list_filter = ('layout', 'compact_mode', 'show_sidebar', 'allow_role_switch')
    search_fields = ('user__username', 'user__email')
    raw_id_fields = ('user',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DashboardWidget)
class DashboardWidgetAdmin(admin.ModelAdmin):
    list_display = ('dashboard', 'widget_def', 'title', 'col', 'row', 'width', 'height', 'is_visible', 'is_collapsed')
    list_filter = ('is_visible', 'is_collapsed', 'widget_def__category')
    search_fields = ('title', 'dashboard__user__username')
    raw_id_fields = ('dashboard', 'widget_def')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(RoleSwitchLog)
class RoleSwitchLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'from_role', 'to_role', 'switched_at', 'ip_address')
    list_filter = ('from_role', 'to_role')
    search_fields = ('user__username', 'user__email')
    raw_id_fields = ('user',)
    readonly_fields = ('switched_at',)


# ═══════════════════════════════════════════════════════════════════════════
# Designer Workflow System
# ═══════════════════════════════════════════════════════════════════════════

@admin.register(ProjectWorkflow)
class ProjectWorkflowAdmin(admin.ModelAdmin):
    list_display = ('request', 'current_stage', 'stage_started_at', 'is_escalated', 'stage_days', 'updated_at')
    list_filter = ('current_stage', 'is_escalated')
    search_fields = ('request__request_number', 'request__company_name')
    raw_id_fields = ('request',)
    readonly_fields = ('created_at', 'updated_at', 'stage_started_at')


@admin.register(WorkflowStageLog)
class WorkflowStageLogAdmin(admin.ModelAdmin):
    list_display = ('workflow', 'from_stage', 'to_stage', 'duration_seconds', 'moved_by', 'created_at')
    list_filter = ('from_stage', 'to_stage')
    raw_id_fields = ('workflow', 'moved_by')
    readonly_fields = ('created_at',)


@admin.register(ClientQuestion)
class ClientQuestionAdmin(admin.ModelAdmin):
    list_display = ('workflow', 'category', 'question', 'is_required', 'is_answered', 'asked_at', 'answered_at')
    list_filter = ('category', 'is_required', 'is_answered')
    search_fields = ('question', 'answer')
    raw_id_fields = ('workflow', 'asked_by')
    readonly_fields = ('asked_at', 'answered_at')


@admin.register(FeedbackItem)
class FeedbackItemAdmin(admin.ModelAdmin):
    list_display = ('workflow', 'title', 'category', 'status', 'client', 'created_at')
    list_filter = ('status', 'category')
    search_fields = ('title', 'content', 'internal_notes')
    raw_id_fields = ('workflow', 'request', 'client')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DesignIteration)
class DesignIterationAdmin(admin.ModelAdmin):
    list_display = ('workflow', 'version_number', 'title', 'is_current', 'created_by', 'created_at')
    list_filter = ('is_current',)
    search_fields = ('title', 'description', 'change_notes')
    raw_id_fields = ('workflow', 'request', 'created_by')
    readonly_fields = ('created_at',)


@admin.register(DecisionLog)
class DecisionLogAdmin(admin.ModelAdmin):
    list_display = ('workflow', 'category', 'decision', 'decided_by', 'is_confirmed', 'created_at')
    list_filter = ('category', 'is_confirmed')
    search_fields = ('decision', 'rationale')
    raw_id_fields = ('workflow', 'request', 'decided_by')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(CommunicationEntry)
class CommunicationEntryAdmin(admin.ModelAdmin):
    list_display = ('workflow', 'interaction_type', 'title', 'author', 'is_from_client', 'is_action_item', 'action_taken', 'created_at')
    list_filter = ('interaction_type', 'is_from_client', 'is_action_item', 'action_taken')
    search_fields = ('title', 'content')
    raw_id_fields = ('workflow', 'request', 'author')
    readonly_fields = ('created_at',)


# ═══════════════════════════════════════════════════════════════════════════
# Concept Presentation Admin
# ═══════════════════════════════════════════════════════════════════════════

@admin.register(DesignConcept)
class DesignConceptAdmin(admin.ModelAdmin):
    list_display = ('title', 'request', 'designer', 'status', 'is_designer_top_pick', 'is_client_favorite', 'designer_ranking', 'client_ranking', 'overall_score', 'created_at')
    list_filter = ('status', 'is_designer_top_pick', 'is_client_favorite')
    search_fields = ('title', 'description', 'request__request_number')
    raw_id_fields = ('request', 'designer')
    readonly_fields = ('overall_score', 'total_ratings', 'presented_at', 'decided_at', 'created_at', 'updated_at')
    filter_horizontal = ()


@admin.register(ConceptImage)
class ConceptImageAdmin(admin.ModelAdmin):
    list_display = ('concept', 'image_type', 'caption', 'sort_order', 'created_at')
    list_filter = ('image_type',)
    raw_id_fields = ('concept',)


@admin.register(ConceptElementRating)
class ConceptElementRatingAdmin(admin.ModelAdmin):
    list_display = ('concept', 'client', 'element', 'score', 'created_at')
    list_filter = ('element', 'score')
    raw_id_fields = ('concept', 'client')


@admin.register(ConceptAnnotation)
class ConceptAnnotationAdmin(admin.ModelAdmin):
    list_display = ('concept', 'client', 'annotation_type', 'text', 'is_resolved', 'created_at')
    list_filter = ('annotation_type', 'is_resolved')
    search_fields = ('text',)
    raw_id_fields = ('concept', 'client', 'resolved_by')
    readonly_fields = ('resolved_at',)


@admin.register(ConceptFeedback)
class ConceptFeedbackAdmin(admin.ModelAdmin):
    list_display = ('concept', 'client', 'overall_rating', 'title', 'created_at')
    list_filter = ('overall_rating',)
    search_fields = ('title', 'feedback_text')
    raw_id_fields = ('concept', 'client')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ConceptStickyNote)
class ConceptStickyNoteAdmin(admin.ModelAdmin):
    list_display = ('concept', 'author', 'text', 'color', 'is_pinned', 'is_resolved', 'created_at')
    list_filter = ('color', 'is_pinned', 'is_resolved')
    raw_id_fields = ('concept', 'author')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ConceptDecision)
class ConceptDecisionAdmin(admin.ModelAdmin):
    list_display = ('concept', 'client', 'decision', 'decided_at')
    list_filter = ('decision',)
    search_fields = ('notes',)
    raw_id_fields = ('concept', 'client')
    readonly_fields = ('decided_at',)


@admin.register(ConceptDecisionTrail)
class ConceptDecisionTrailAdmin(admin.ModelAdmin):
    list_display = ('concept', 'action', 'performed_by', 'timestamp')
    search_fields = ('action',)
    raw_id_fields = ('request', 'concept', 'performed_by')
    readonly_fields = ('timestamp',)


@admin.register(ConceptRefinement)
class ConceptRefinementAdmin(admin.ModelAdmin):
    list_display = ('concept', 'client', 'title', 'priority', 'status', 'created_at')
    list_filter = ('status', 'priority')
    search_fields = ('title', 'description')
    raw_id_fields = ('concept', 'client')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ConceptRefinementIteration)
class ConceptRefinementIterationAdmin(admin.ModelAdmin):
    list_display = ('refinement', 'version_number', 'created_by', 'client_approved', 'created_at')
    list_filter = ('client_approved',)
    raw_id_fields = ('refinement', 'created_by')
    readonly_fields = ('created_at',)


@admin.register(ConceptComparison)
class ConceptComparisonAdmin(admin.ModelAdmin):
    list_display = ('title', 'request', 'created_by', 'created_at')
    raw_id_fields = ('request', 'created_by')
    filter_horizontal = ('concepts',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ConceptPresentationSession)
class ConceptPresentationSessionAdmin(admin.ModelAdmin):
    list_display = ('title', 'request', 'scheduled_at', 'status', 'duration_minutes', 'created_by', 'created_at')
    list_filter = ('status',)
    search_fields = ('title', 'description')
    raw_id_fields = ('request', 'created_by')
    filter_horizontal = ('attendees',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Questionnaire)
class QuestionnaireAdmin(admin.ModelAdmin):
    list_display = ('title', 'request', 'client', 'status', 'phase', 'completion_percent', 'created_at')
    list_filter = ('status', 'phase')
    search_fields = ('title', 'request__request_number')
    raw_id_fields = ('request', 'client', 'designer')
    readonly_fields = ('share_token', 'email_sent_at', 'completed_at', 'created_at', 'updated_at')
    actions = ['send_questionnaire', 'mark_completed']


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('questionnaire', 'text', 'question_type', 'category', 'importance', 'is_required', 'sort_order')
    list_filter = ('question_type', 'category', 'importance', 'is_required')
    raw_id_fields = ('questionnaire',)
    readonly_fields = ('created_at', 'updated_at')
    actions = ['toggle_active', 'toggle_required']


@admin.register(QuestionCondition)
class QuestionConditionAdmin(admin.ModelAdmin):
    list_display = ('question', 'depends_on', 'condition_type', 'condition_value')
    raw_id_fields = ('question', 'depends_on')


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ('question', 'client', 'get_display_value', 'version', 'created_at')
    list_filter = ('question__question_type', 'is_skipped')
    search_fields = ('text_value',)
    raw_id_fields = ('question', 'client')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(QuestionnaireTemplate)
class QuestionnaireTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'phase', 'industry', 'is_active', 'use_count', 'created_at')
    list_filter = ('phase', 'is_active')
    search_fields = ('name', 'description')
    readonly_fields = ('use_count', 'created_at', 'updated_at')


@admin.register(DecisionPoint)
class DecisionPointAdmin(admin.ModelAdmin):
    list_display = ('title', 'request', 'status', 'category', 'importance', 'deadline', 'decided_at')
    list_filter = ('status', 'category', 'importance')
    search_fields = ('title', 'description')
    raw_id_fields = ('request', 'questionnaire')
    readonly_fields = ('decided_at', 'notified_at', 'created_at', 'updated_at')


@admin.register(ClientPreferenceProfile)
class ClientPreferenceProfileAdmin(admin.ModelAdmin):
    list_display = ('client', 'total_questionnaires_completed', 'last_updated')
    search_fields = ('client__username', 'client__email')
    raw_id_fields = ('client',)
    readonly_fields = ('last_updated', 'created_at')
