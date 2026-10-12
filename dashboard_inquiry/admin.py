from django.contrib import admin

from .models import DashboardInquiry


@admin.register(DashboardInquiry)
class DashboardInquiryAdmin(admin.ModelAdmin):
    list_display = ('reference', 'name', 'email', 'company', 'package', 'status', 'created_at')
    list_filter = ('package', 'status', 'created_at')
    search_fields = ('reference', 'name', 'email', 'company', 'message')
    readonly_fields = ('reference', 'created_at')
    date_hierarchy = 'created_at'
