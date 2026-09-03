from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class PerformanceCheck(models.Model):
    DEVICE_CHOICES = [
        ('mobile', _('Mobile')),
        ('desktop', _('Desktop')),
    ]

    STATUS_CHOICES = [
        ('excellent', _('Excellent')),
        ('good', _('Good')),
        ('needs_improvement', _('Needs Improvement')),
        ('poor', _('Poor')),
    ]

    website = models.CharField(max_length=255, verbose_name=_('Website'))
    url = models.URLField(max_length=500, verbose_name=_('URL'))
    device = models.CharField(max_length=10, choices=DEVICE_CHOICES, verbose_name=_('Device'))
    performance_score = models.IntegerField(default=0, verbose_name=_('Performance Score'))
    fcp = models.FloatField(null=True, blank=True, verbose_name=_('First Contentful Paint (ms)'))
    lcp = models.FloatField(null=True, blank=True, verbose_name=_('Largest Contentful Paint (ms)'))
    inp = models.FloatField(null=True, blank=True, verbose_name=_('Interaction to Next Paint (ms)'))
    cls = models.FloatField(null=True, blank=True, verbose_name=_('Cumulative Layout Shift'))
    ttfb = models.FloatField(null=True, blank=True, verbose_name=_('Time to First Byte (ms)'))
    speed_index = models.FloatField(null=True, blank=True, verbose_name=_('Speed Index (ms)'))
    total_blocking_time = models.FloatField(null=True, blank=True, verbose_name=_('Total Blocking Time (ms)'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='good', verbose_name=_('Status'))
    recommendations = models.JSONField(default=list, blank=True, verbose_name=_('Recommendations'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))

    class Meta:
        verbose_name = _('Performance Check')
        verbose_name_plural = _('Performance Checks')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['url', 'device']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"{self.website} ({self.device}) - {self.performance_score}/100"

    def get_metric_status(self, metric_name, value):
        if value is None:
            return 'N/A'

        thresholds = {
            'lcp': {'good': 2500, 'poor': 4000},
            'fcp': {'good': 1800, 'poor': 3000},
            'cls': {'good': 0.1, 'poor': 0.25},
            'inp': {'good': 200, 'poor': 500},
            'ttfb': {'good': 800, 'poor': 1800},
            'speed_index': {'good': 3400, 'poor': 5800},
            'total_blocking_time': {'good': 200, 'poor': 600},
        }

        if metric_name not in thresholds:
            return 'N/A'

        t = thresholds[metric_name]
        if value <= t['good']:
            return 'Good'
        elif value <= t['poor']:
            return 'Needs Improvement'
        else:
            return 'Poor'


class GA4Property(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ga4_properties',
        verbose_name=_('User'),
    )
    property_id = models.CharField(max_length=50, verbose_name=_('GA4 Property ID'))
    display_name = models.CharField(max_length=255, verbose_name=_('Display Name'))
    account_name = models.CharField(max_length=255, blank=True, verbose_name=_('Account Name'))
    access_token = models.TextField(verbose_name=_('Access Token'))
    refresh_token = models.TextField(verbose_name=_('Refresh Token'))
    token_expires_at = models.DateTimeField(verbose_name=_('Token Expires At'))
    is_active = models.BooleanField(default=True, verbose_name=_('Active'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))

    class Meta:
        verbose_name = _('GA4 Property')
        verbose_name_plural = _('GA4 Properties')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active'], name='ga4prop_user_active_idx'),
            models.Index(fields=['property_id'], name='ga4prop_propid_idx'),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.property_id})"


class GA4Report(models.Model):
    DATE_RANGE_CHOICES = [
        ('7d', _('Last 7 Days')),
        ('30d', _('Last 30 Days')),
        ('90d', _('Last 90 Days')),
    ]

    property = models.ForeignKey(
        GA4Property,
        on_delete=models.CASCADE,
        related_name='reports',
        verbose_name=_('GA4 Property'),
    )
    date_range = models.CharField(max_length=10, choices=DATE_RANGE_CHOICES, default='30d', verbose_name=_('Date Range'))
    total_users = models.BigIntegerField(default=0, verbose_name=_('Total Users'))
    sessions = models.BigIntegerField(default=0, verbose_name=_('Sessions'))
    screen_page_views = models.BigIntegerField(default=0, verbose_name=_('Screen Page Views'))
    avg_session_duration = models.FloatField(default=0, verbose_name=_('Avg Session Duration (s)'))
    engagement_rate = models.FloatField(default=0, verbose_name=_('Engagement Rate (%)'))
    bounce_rate = models.FloatField(default=0, verbose_name=_('Bounce Rate (%)'))
    sessions_per_user = models.FloatField(default=0, verbose_name=_('Sessions Per User'))
    trends = models.JSONField(default=list, blank=True, verbose_name=_('Period Comparison Trends'))
    traffic_sources = models.JSONField(default=list, blank=True, verbose_name=_('Traffic Sources'))
    raw_data = models.JSONField(default=dict, blank=True, verbose_name=_('Raw API Data'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))

    class Meta:
        verbose_name = _('GA4 Report')
        verbose_name_plural = _('GA4 Reports')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['property', '-created_at'], name='ga4report_prop_created_idx'),
            models.Index(fields=['date_range'], name='ga4report_daterange_idx'),
        ]

    def __str__(self):
        return f"GA4 Report - {self.property.display_name} ({self.date_range})"
