from django.contrib import admin
from .models import PerformanceCheck, GA4Property, GA4Report


@admin.register(PerformanceCheck)
class PerformanceCheckAdmin(admin.ModelAdmin):
    list_display = ('website', 'device', 'performance_score', 'status', 'created_at')
    list_filter = ('device', 'status', 'created_at')
    search_fields = ('website', 'url')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)


@admin.register(GA4Property)
class GA4PropertyAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'property_id', 'account_name', 'user', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('display_name', 'property_id', 'account_name')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)


@admin.register(GA4Report)
class GA4ReportAdmin(admin.ModelAdmin):
    list_display = ('property', 'date_range', 'total_users', 'sessions', 'engagement_rate', 'bounce_rate', 'created_at')
    list_filter = ('date_range', 'created_at')
    search_fields = ('property__display_name', 'property__property_id')
    readonly_fields = ('created_at', 'raw_data')
    ordering = ('-created_at',)
