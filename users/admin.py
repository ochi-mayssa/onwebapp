from django.contrib import admin
from .models import (
    UserProfile,
    UserSubscription,
    ActivityLog,
    Plan,
    Service,
    PlanLimit,
    UserServiceUsage,
)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_name', 'created_at')
    search_fields = ('user__email', 'user__username', 'display_name')

@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'is_active', 'start_date', 'end_date')
    list_filter = ('is_active', 'plan')
    search_fields = ('user__email', 'user__username', 'plan__name')

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'timestamp')
    list_filter = ('timestamp',)
    search_fields = ('user__email', 'action', 'metadata')


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('code', 'name')
    search_fields = ('code', 'name')


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')


@admin.register(PlanLimit)
class PlanLimitAdmin(admin.ModelAdmin):
    list_display = ('plan', 'service', 'max_usage')
    list_filter = ('plan', 'service')
    search_fields = ('plan__name', 'service__name')


@admin.register(UserServiceUsage)
class UserServiceUsageAdmin(admin.ModelAdmin):
    list_display = ('user', 'service_name', 'usage_count', 'limit')
    list_filter = ('service_name',)
    search_fields = ('user__email', 'user__username', 'service_name')
