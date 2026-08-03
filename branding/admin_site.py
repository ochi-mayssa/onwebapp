"""Custom admin site for the Branding Service.

Provides a dashboard homepage with stats, recent activity,
system health widgets, and quick-action buttons.
"""
import json
import os
import shutil

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.options import ModelAdmin
from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone
from django.utils.html import format_html
from django.urls import path, reverse


class BrandingAdminSite(admin.AdminSite):
    """Custom admin site with a dashboard homepage."""
    site_header = 'OnWebApp Branding Admin'
    site_title = 'Branding Admin'
    index_title = 'Branding Service Dashboard'
    index_template = 'admin/branding_dashboard.html'

    def get_urls(self):
        custom_urls = [
            path('branding-dashboard/', self.admin_view(self.branding_dashboard), name='branding_dashboard'),
        ]
        return custom_urls + super().get_urls()

    def branding_dashboard(self, request):
        """Custom branding admin dashboard."""
        from django.contrib.auth import get_user_model
        from ..models import (
            BrandingRequest, BrandingAsset, BrandingMessage,
            BrandingFeedback, BrandingWebhook, BrandingNotification,
            DailyAggregate, StaffWorkload, CollectionPerformance,
        )

        User = get_user_model()
        now = timezone.now()
        today = now.date()
        thirty_days_ago = today - timezone.timedelta(days=30)
        seven_days_ago = today - timezone.timedelta(days=7)

        # ── Quick Stats ──
        total_requests = BrandingRequest.objects.count()
        active_requests = BrandingRequest.objects.exclude(status__in=['COMPLETED', 'ARCHIVED', 'DRAFT']).count()
        pending_review = BrandingRequest.objects.filter(status='PENDING_REVIEW').count()
        in_review = BrandingRequest.objects.filter(status='IN_REVIEW').count()
        completed_30d = BrandingRequest.objects.filter(
            status='COMPLETED', completed_at__date__gte=thirty_days_ago
        ).count()
        new_7d = BrandingRequest.objects.filter(
            created_at__date__gte=seven_days_ago
        ).count()
        total_users = User.objects.count()
        total_staff = User.objects.filter(is_staff=True).count()

        # ── Status Distribution ──
        status_dist = list(
            BrandingRequest.objects.values('status')
            .annotate(count=Count('id'))
            .order_by('status')
        )

        # ── Recent Requests ──
        recent_requests = BrandingRequest.objects.select_related('user', 'designer').order_by('-created_at')[:10]

        # ── Pending Messages ──
        unread_messages = BrandingMessage.objects.filter(
            is_read_by_staff=False
        ).select_related('request', 'sender').order_by('-created_at')[:5]

        # ── Recent Feedback ──
        recent_feedback = BrandingFeedback.objects.select_related('request').order_by('-created_at')[:5]

        # ── System Health ──
        from ..models import WebhookDelivery
        failed_webhooks = WebhookDelivery.objects.filter(status='failed').count()
        total_webhooks = BrandingWebhook.objects.filter(is_active=True).count()

        # ── Storage ──
        storage_used = _get_storage_usage()
        storage_limit = _get_storage_limit()
        storage_pct = round((storage_used / storage_limit * 100) if storage_limit > 0 else 0, 1)

        # ── Activity (last 7 days) ──
        activity_data = list(
            BrandingRequest.objects.filter(created_at__date__gte=seven_days_ago)
            .annotate(date=timezone.functions.TruncDate('created_at'))
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date')
        )

        context = {
            **self.each_context(request),
            'title': 'Branding Service Dashboard',
            # Stats
            'total_requests': total_requests,
            'active_requests': active_requests,
            'pending_review': pending_review,
            'in_review': in_review,
            'completed_30d': completed_30d,
            'new_7d': new_7d,
            'total_users': total_users,
            'total_staff': total_staff,
            # Data
            'status_distribution': json.dumps(status_dist),
            'recent_requests': recent_requests,
            'unread_messages': unread_messages,
            'recent_feedback': recent_feedback,
            # System
            'failed_webhooks': failed_webhooks,
            'active_webhooks': total_webhooks,
            'storage_used': storage_used,
            'storage_limit': storage_limit,
            'storage_pct': storage_pct,
            'storage_used_display': _format_bytes(storage_used),
            'storage_limit_display': _format_bytes(storage_limit),
            'activity_data': json.dumps(activity_data),
        }
        return render(request, 'admin/branding_dashboard.html', context)

    def index(self, request, extra_context=None):
        """Override the admin index to redirect to our dashboard."""
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(reverse('admin:branding_dashboard'))


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _get_storage_usage():
    """Calculate total storage used by branding uploads."""
    try:
        from ..models import BrandingAsset
        total = sum(asset.file.size for asset in BrandingAsset.objects.all() if asset.file)
        return total
    except Exception:
        return 0


def _get_storage_limit():
    """Get storage limit (default 10GB)."""
    return getattr(settings, 'BRANDING_STORAGE_LIMIT', 10 * 1024 * 1024 * 1024)


def _format_bytes(size):
    """Format bytes to human readable."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


# Create the custom admin site instance
branding_admin_site = BrandingAdminSite(name='branding_admin')
