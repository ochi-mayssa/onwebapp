"""Django admin registration for workload management."""
from django.contrib import admin
from django.utils.html import format_html

from .models import (
    ResourceCapacity,
    WorkAssignment,
    WorkItem,
    WorkItemAttachment,
    WorkloadAlert,
    WorkloadHistory,
    WorkloadMetric,
    WorkloadPolicy,
    WorkloadResource,
    WorkloadSkill,
    WorkloadTeam,
)


class ResourceCapacityInline(admin.StackedInline):
    model = ResourceCapacity
    extra = 0
    max_num = 1
    can_delete = False


class WorkloadTeamMembersInline(admin.TabularInline):
    model = WorkloadTeam.members.through
    extra = 0
    verbose_name = 'member'
    verbose_name_plural = 'members'


class WorkAssignmentInline(admin.TabularInline):
    model = WorkAssignment
    extra = 0
    fields = ('resource', 'role', 'allocated_hours', 'status', 'assigned_by')
    autocomplete_fields = ('resource',)


class WorkItemAttachmentInline(admin.TabularInline):
    model = WorkItemAttachment
    extra = 0
    fields = ('file', 'original_name', 'uploaded_by', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(WorkloadSkill)
class WorkloadSkillAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)


@admin.register(WorkloadTeam)
class WorkloadTeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'lead', 'member_count', 'is_active')
    list_filter = ('is_active', 'department')
    search_fields = ('name', 'code', 'department')
    autocomplete_fields = ('lead',)
    inlines = [WorkloadTeamMembersInline]

    @admin.display(description='Members')
    def member_count(self, obj):
        return obj.members.count()


@admin.register(WorkloadResource)
class WorkloadResourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'display_owner', 'availability_status', 'is_active')
    list_filter = ('kind', 'availability_status', 'is_active')
    search_fields = ('name', 'user__username', 'team__name', 'system_label')
    autocomplete_fields = ('user', 'team')
    filter_horizontal = ('skills',)
    inlines = [ResourceCapacityInline]


@admin.register(WorkloadPolicy)
class WorkloadPolicyAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'tenant', 'is_default', 'available_below', 'balanced_max',
        'high_max', 'auto_assign_enabled',
    )
    list_filter = ('is_default', 'auto_assign_enabled', 'auto_reassign_critical')
    search_fields = ('name',)
    autocomplete_fields = ('tenant',)


@admin.register(WorkItem)
class WorkItemAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'status', 'priority', 'category', 'assignee', 'team',
        'due_date', 'estimated_hours', 'source_module', 'is_overdue',
    )
    list_filter = (
        'status', 'priority', 'category', 'source_module', 'automation_eligible',
        'is_client_visible',
    )
    search_fields = ('title', 'description', 'external_reference')
    autocomplete_fields = ('assignee', 'team', 'client', 'project', 'created_by')
    filter_horizontal = ('required_skills',)
    date_hierarchy = 'due_date'
    inlines = [WorkAssignmentInline, WorkItemAttachmentInline]
    readonly_fields = ('created_at', 'updated_at', 'completed_at')

    @admin.display(boolean=True, description='Overdue')
    def is_overdue(self, obj):
        return obj.is_overdue


@admin.register(WorkAssignment)
class WorkAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        'work_item', 'resource', 'allocated_hours', 'status', 'assigned_by',
        'assigned_at',
    )
    list_filter = ('status',)
    search_fields = ('work_item__title', 'resource__name')
    autocomplete_fields = ('work_item', 'resource', 'assigned_by', 'approved_by')


class WorkloadHistoryInline(admin.TabularInline):
    model = WorkloadHistory
    extra = 0
    fields = ('action', 'actor', 'field_name', 'old_value', 'new_value', 'note', 'created_at')
    readonly_fields = ('created_at',)
    can_delete = False


@admin.register(WorkloadAlert)
class WorkloadAlertAdmin(admin.ModelAdmin):
    list_display = (
        'alert_type', 'severity', 'status', 'recipient', 'resource', 'team',
        'created_at',
    )
    list_filter = ('alert_type', 'severity', 'status')
    search_fields = ('message', 'dedupe_key')
    autocomplete_fields = ('work_item', 'resource', 'team', 'recipient')
    readonly_fields = ('dedupe_key', 'created_at', 'updated_at')


@admin.register(WorkloadHistory)
class WorkloadHistoryAdmin(admin.ModelAdmin):
    list_display = ('work_item', 'action', 'actor', 'field_name', 'created_at')
    list_filter = ('action',)
    search_fields = ('work_item__title', 'note')
    autocomplete_fields = ('work_item', 'actor')
    readonly_fields = ('created_at',)


@admin.register(WorkloadMetric)
class WorkloadMetricAdmin(admin.ModelAdmin):
    list_display = ('metric_date', 'scope', 'tenant', 'team', 'resource')
    list_filter = ('scope', 'metric_date')
    date_hierarchy = 'metric_date'


@admin.register(WorkItemAttachment)
class WorkItemAttachmentAdmin(admin.ModelAdmin):
    list_display = ('work_item', 'original_name', 'uploaded_by', 'created_at', 'file_link')
    search_fields = ('work_item__title', 'original_name')
    autocomplete_fields = ('work_item', 'uploaded_by')
    readonly_fields = ('created_at',)

    @admin.display(description='File')
    def file_link(self, obj):
        if not obj.file:
            return '—'
        return format_html('<a href="{}">{}</a>', obj.file.url, obj.original_name or obj.file.name)
