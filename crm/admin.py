from django.contrib import admin
from .models import Customer, Interaction, ServiceRequest, CRMWorkflow, WorkflowStep


class CRMAdminMixin:
    """Allow CRM staff to access the admin dashboard and CRM models."""
    def has_module_permission(self, request):
        return bool(request.user and request.user.is_active and request.user.is_staff)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)

@admin.register(Customer)
class CustomerAdmin(CRMAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'email', 'lifecycle_stage', 'current_health_score', 'health_trend', 'assigned_to', 'created_at')
    list_filter = ('lifecycle_stage', 'health_trend', 'customer_type', 'created_at')
    search_fields = ('name', 'email', 'company_name')

@admin.register(Interaction)
class InteractionAdmin(CRMAdminMixin, admin.ModelAdmin):
    list_display = ('customer', 'interaction_type', 'agent', 'date')
    list_filter = ('interaction_type', 'date')
    search_fields = ('customer__name', 'summary')

@admin.register(ServiceRequest)
class ServiceRequestAdmin(CRMAdminMixin, admin.ModelAdmin):
    list_display = ('customer', 'service_type', 'status', 'created_at')
    list_filter = ('status', 'service_type')
    search_fields = ('customer__name', 'description')

class WorkflowStepInline(admin.TabularInline):
    model = WorkflowStep
    extra = 1

@admin.register(CRMWorkflow)
class CRMWorkflowAdmin(CRMAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'trigger_type', 'trigger_value', 'is_active')
    list_filter = ('trigger_type', 'is_active')
    inlines = [WorkflowStepInline]
