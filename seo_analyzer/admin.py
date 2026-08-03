from django.contrib import admin
from .models import (
    SEOHistoricalReport,
    SEOIssue,
    SEOMonitoringSnapshot,
    SEONotificationEndpoint,
    SEOPageAudit,
    SEOResult,
    SEOTask,
    URLIntelligenceIssue,
    URLIntelligenceResult,
    URLIntelligenceTask,
)


@admin.register(SEOTask)
class SEOTaskAdmin(admin.ModelAdmin):
    list_display = ["domain", "status", "created_at", "user"]
    list_filter = ["status", "created_at"]
    search_fields = ["domain", "url", "user__email", "user__username"]
    readonly_fields = ["created_at", "started_at", "completed_at"]


@admin.register(SEOResult)
class SEOResultAdmin(admin.ModelAdmin):
    list_display = ["task", "health_score", "total_issues", "created_at"]
    list_filter = ["created_at", "health_score"]
    search_fields = ["task__domain"]
    readonly_fields = ["created_at"]


@admin.register(SEOPageAudit)
class SEOPageAuditAdmin(admin.ModelAdmin):
    list_display = ["task", "final_url", "status_code", "word_count"]
    list_filter = ["status_code"]
    search_fields = ["final_url", "url"]
    readonly_fields = ["created_at"]


@admin.register(SEOIssue)
class SEOIssueAdmin(admin.ModelAdmin):
    list_display = ["name", "severity", "category", "task", "status"]
    list_filter = ["severity", "category", "status"]
    search_fields = ["name", "description", "task__domain"]
    readonly_fields = ["created_at"]


@admin.register(SEOHistoricalReport)
class SEOHistoricalReportAdmin(admin.ModelAdmin):
    list_display = ["domain", "health_score", "created_at", "user"]
    list_filter = ["created_at"]
    search_fields = ["domain", "user__email"]
    readonly_fields = ["created_at"]


@admin.register(SEOMonitoringSnapshot)
class SEOMonitoringSnapshotAdmin(admin.ModelAdmin):
    list_display = ["domain", "analysis_type", "health_score", "created_at", "user"]
    list_filter = ["analysis_type", "created_at"]
    search_fields = ["domain", "website", "source_identifier", "user__email"]
    readonly_fields = ["created_at"]


@admin.register(SEONotificationEndpoint)
class SEONotificationEndpointAdmin(admin.ModelAdmin):
    list_display = ["domain", "channel_type", "is_active", "updated_at"]
    list_filter = ["channel_type", "is_active"]
    search_fields = ["domain", "destination", "user__email"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(URLIntelligenceTask)
class URLIntelligenceTaskAdmin(admin.ModelAdmin):
    list_display = ["url", "target_keyword", "status", "created_at", "user"]
    list_filter = ["status", "created_at"]
    search_fields = ["url", "domain", "target_keyword", "user__email"]
    readonly_fields = ["created_at", "started_at", "completed_at"]


@admin.register(URLIntelligenceResult)
class URLIntelligenceResultAdmin(admin.ModelAdmin):
    list_display = [
        "task",
        "health_score",
        "http_status_code",
        "indexability_status",
        "canonical_status",
        "created_at",
    ]
    list_filter = ["canonical_status", "indexability_status", "created_at"]
    search_fields = ["task__url", "domain", "final_url"]
    readonly_fields = ["created_at"]


@admin.register(URLIntelligenceIssue)
class URLIntelligenceIssueAdmin(admin.ModelAdmin):
    list_display = ["name", "severity", "category", "task", "status"]
    list_filter = ["severity", "category", "status"]
    search_fields = ["name", "task__url", "evidence", "description"]
    readonly_fields = ["created_at"]
