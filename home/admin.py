from django.contrib import admin
from django.contrib.auth import get_user_model

from .models import ConsultationRequest, APIRequest, APIRequestStatusLog
from .notifications import notify_client_status_change

User = get_user_model()


@admin.register(ConsultationRequest)
class ConsultationRequestAdmin(admin.ModelAdmin):
    list_display = ('matricule', 'name', 'email', 'company', 'topic', 'created_at')
    list_filter = ('topic', 'created_at')
    search_fields = ('matricule', 'name', 'email', 'company', 'message')
    readonly_fields = ('matricule', 'created_at',)


class APIRequestStatusLogInline(admin.TabularInline):
    model = APIRequestStatusLog
    extra = 0
    can_delete = False
    fields = ('from_status', 'to_status', 'changed_by', 'note', 'created_at')
    readonly_fields = ('from_status', 'to_status', 'changed_by', 'note', 'created_at')
    ordering = ('-created_at',)


@admin.register(APIRequest)
class APIRequestAdmin(admin.ModelAdmin):
    list_display = (
        'reference', 'full_name', 'request_type', 'status',
        'assigned_to', 'is_archived', 'created_at',
    )
    list_filter = ('status', 'request_type', 'is_archived', 'created_at')
    search_fields = (
        'reference', 'full_name', 'business_email', 'company_name',
        'api_name_or_category', 'use_case', 'required_features',
    )
    date_hierarchy = 'created_at'
    readonly_fields = ('reference', 'created_at', 'updated_at')
    raw_id_fields = ('user', 'assigned_to')
    inlines = (APIRequestStatusLogInline,)
    actions = ('mark_archived', 'mark_unarchived')
    fieldsets = (
        ('Request', {
            'fields': (('reference', 'status'), ('user', 'assigned_to'), 'is_archived'),
        }),
        ('Client', {
            'fields': (('full_name', 'business_email'), 'company_name'),
        }),
        ('Requirements', {
            'fields': (
                'request_type', 'api_name_or_category', 'use_case',
                'required_features', ('expected_usage', 'budget_range'),
                'additional_requirements',
            ),
        }),
        ('Internal', {
            'fields': ('internal_notes',),
            'description': 'Staff-only. Never shown to clients.',
        }),
        ('Timestamps', {
            'fields': (('created_at', 'updated_at'),),
        }),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'assigned_to':
            kwargs['queryset'] = User.objects.filter(is_staff=True, is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        old_status = None
        if change:
            old_status = (
                APIRequest.objects.filter(pk=obj.pk)
                .values_list('status', flat=True).first()
            )
        super().save_model(request, obj, form, change)
        if change and old_status and old_status != obj.status:
            APIRequestStatusLog.objects.create(
                request=obj, from_status=old_status, to_status=obj.status,
                changed_by=request.user,
            )
            notify_client_status_change(obj, old_status, obj.status)

    def mark_archived(self, request, queryset):
        updated = queryset.update(is_archived=True)
        self.message_user(request, f'{updated} request(s) archived.')
    mark_archived.short_description = 'Archive selected API requests'

    def mark_unarchived(self, request, queryset):
        updated = queryset.update(is_archived=False)
        self.message_user(request, f'{updated} request(s) restored.')
    mark_unarchived.short_description = 'Restore selected API requests'
