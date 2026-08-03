from django.contrib import admin
from .models import Project, ProjectPhase, PhaseTask, ProjectDeliverable, ProjectFeedback, ClientAsset, BrandAsset, ProjectActivity, WorkflowNotification, Invoice, KPIHistory

class PhaseTaskInline(admin.TabularInline):
    model = PhaseTask
    extra = 1

class ProjectPhaseInline(admin.TabularInline):
    model = ProjectPhase
    extra = 0
    show_change_link = True

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'client', 'current_status', 'progress_percentage', 'created_at')
    list_filter = ('current_status', 'created_at')
    search_fields = ('title', 'client__username', 'client__email')
    inlines = [ProjectPhaseInline]

@admin.register(ProjectPhase)
class ProjectPhaseAdmin(admin.ModelAdmin):
    list_display = ('project', 'phase_type', 'status', 'start_date', 'end_date')
    list_filter = ('phase_type', 'status')
    inlines = [PhaseTaskInline]

admin.site.register(ProjectDeliverable)
admin.site.register(ProjectFeedback)
admin.site.register(ClientAsset)
admin.site.register(BrandAsset)
admin.site.register(ProjectActivity)

@admin.register(WorkflowNotification)
class WorkflowNotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'notification_type', 'project', 'is_read', 'sent_at')
    list_filter = ('notification_type', 'is_read', 'sent_at')
    search_fields = ('recipient__username', 'recipient__email', 'message', 'project__title')

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'amount', 'status', 'issued_date', 'due_date')
    list_filter = ('status', 'issued_date')
    search_fields = ('client__username', 'client__email')

@admin.register(KPIHistory)
class KPIHistoryAdmin(admin.ModelAdmin):
    list_display = ('date', 'completion_rate', 'active_projects')
    list_filter = ('date',)
