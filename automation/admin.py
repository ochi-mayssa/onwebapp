from django.contrib import admin

from .models import (
    AutomationExecution,
    AutomationRequest,
    AutomationWorkflow,
    BillingEvent,
    ExecutionLog,
    IntegrationConnection,
    Plan,
    Subscription,
    UsageRecord,
    WorkflowVersion,
)


@admin.register(AutomationRequest)
class AutomationRequestAdmin(admin.ModelAdmin):
    list_display = ('title', 'customer', 'status', 'is_approved', 'created_at')
    list_filter = ('status', 'is_approved')
    search_fields = ('title', 'customer__name', 'description')


@admin.register(AutomationWorkflow)
class AutomationWorkflowAdmin(admin.ModelAdmin):
    list_display = ('title', 'customer', 'status', 'trigger', 'created_at')
    list_filter = ('status', 'trigger')
    search_fields = ('title', 'customer__name')


@admin.register(WorkflowVersion)
class WorkflowVersionAdmin(admin.ModelAdmin):
    list_display = ('workflow', 'version_number', 'approved', 'created_at')
    list_filter = ('approved',)


@admin.register(IntegrationConnection)
class IntegrationConnectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'customer', 'provider', 'status', 'updated_at')
    list_filter = ('provider', 'status')


@admin.register(AutomationExecution)
class AutomationExecutionAdmin(admin.ModelAdmin):
    list_display = ('workflow', 'status', 'trigger', 'attempt_count', 'created_at')
    list_filter = ('status', 'trigger')


@admin.register(ExecutionLog)
class ExecutionLogAdmin(admin.ModelAdmin):
    list_display = ('execution', 'level', 'created_at')
    list_filter = ('level',)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'currency', 'max_active_workflows', 'monthly_execution_limit', 'is_active')
    list_filter = ('is_active', 'currency')
    search_fields = ('name', 'slug')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'plan', 'status', 'payment_status', 'provider', 'created_at')
    list_filter = ('status', 'payment_status', 'provider')
    search_fields = ('customer__name', 'provider_subscription_id')


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ('subscription', 'metric', 'used_count', 'limit_value', 'recorded_at')
    list_filter = ('metric', 'usage_window')


@admin.register(BillingEvent)
class BillingEventAdmin(admin.ModelAdmin):
    list_display = ('subscription', 'provider', 'event_type', 'processed', 'created_at')
    list_filter = ('provider', 'processed', 'event_type')
