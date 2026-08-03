from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone

User = get_user_model()


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(max_length=150, blank=True)
    bio = models.TextField(blank=True)
    avatar = models.URLField(blank=True)
    email_verified = models.BooleanField(default=False)
    
    SERVICE_TYPE_CHOICES = [
        ('full_platform', 'Full Platform Services'),
        ('community', 'Community Services'),
    ]
    service_type = models.CharField(
        max_length=20,
        choices=SERVICE_TYPE_CHOICES,
        blank=True,
        null=True,
        help_text="Selected service experience during onboarding"
    )
    
    # Community Needs (JSON list of selected needs)
    community_needs = models.JSONField(default=list, blank=True)
    
    # Project Description
    PROJECT_DESC_CHOICES = [
        ('personal', 'Personal project'),
        ('business', 'Business / Startup'),
        ('community', 'Community / Non-profit'),
        ('other', 'Other'),
    ]
    project_description = models.CharField(max_length=50, choices=PROJECT_DESC_CHOICES, blank=True)
    
    # Timeline
    TIMELINE_CHOICES = [
        ('immediately', 'Immediately'),
        ('1_month', 'Within 1 month'),
        ('3_months', 'Within 3 months'),
        ('exploring', 'Just exploring'),
    ]
    start_timeline = models.CharField(max_length=20, choices=TIMELINE_CHOICES, blank=True)
    
    # Notification Preferences
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    sms_notifications_enabled = models.BooleanField(default=False)
    email_notifications_enabled = models.BooleanField(default=True)
    two_factor_enabled = models.BooleanField(default=False)
    
    # Company Information
    company_name = models.CharField(max_length=200, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    company_size = models.CharField(max_length=50, blank=True, choices=[
        ('1-10', '1-10 employees'),
        ('11-50', '11-50 employees'),
        ('51-200', '51-200 employees'),
        ('201-500', '201-500 employees'),
        ('500+', '500+ employees')
    ])
    country = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.display_name or self.user.username


class ServiceUsage(models.Model):
    """Tracks usage of specific services against plan limits."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='service_usage')
    service_name = models.CharField(max_length=100)
    usage_count = models.IntegerField(default=0)
    limit = models.IntegerField(default=10) # Default limit, can be overridden by plan logic
    
    class Meta:
        unique_together = ('user', 'service_name')
        
    def __str__(self):
        return f"{self.user.username} - {self.service_name}: {self.usage_count}/{self.limit}"
    
    @property
    def percentage(self):
        if self.limit > 0:
            return (self.usage_count / self.limit) * 100
        return 0
        
    @property
    def is_limit_reached(self):
        return self.usage_count >= self.limit


class Service(models.Model):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=100)


class UserERP(models.Model):
    """Stores white-labeled ERPNext site credentials for a user."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='erp_site')
    site_name = models.CharField(max_length=255, unique=True)
    api_key = models.CharField(max_length=255)
    api_secret = models.CharField(max_length=255)
    admin_password = models.CharField(max_length=255)
    status = models.CharField(max_length=20, default='provisioning', choices=[
        ('provisioning', 'Provisioning'),
        ('active', 'Active'),
        ('error', 'Error'),
        ('suspended', 'Suspended')
    ])
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"ERP: {self.site_name} ({self.user.username})"


class Plan(models.Model):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class PlanLimit(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='limits')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='limits')
    max_usage = models.IntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('plan', 'service')

    def __str__(self):
        return f"{self.plan.code} · {self.service.code} → {self.max_usage or 'unlimited'}"


class UserSubscription(models.Model):
    """Represents an active (or past) subscription for a user."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey('payments.PaymentPlan', on_delete=models.SET_NULL, null=True, blank=True)
    stripe_subscription_id = models.CharField(max_length=128, blank=True, null=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.plan.name if self.plan else 'No Plan'}"

    @property
    def status(self):
        if not self.plan:
            return 'Free'
        if not self.start_date:
            return 'Pending'
        now = timezone.now()
        if self.is_active and (not self.end_date or self.end_date >= now):
            return 'Active'
        if self.end_date and self.end_date < now:
            return 'Expired'
        return 'Trial'

    @property
    def next_billing_date(self):
        if not (self.plan and self.start_date and self.is_active):
            return None
        from datetime import timedelta
        return self.start_date + timedelta(days=self.plan.duration_days or 30)

    @property
    def billing_cycle_label(self):
        if not self.plan:
            return 'N/A'
        days = self.plan.duration_days or 30
        if days in (28, 29, 30, 31):
            return 'Monthly'
        if 360 <= days <= 370:
            return 'Yearly'
        return f'{days}-day'

    @property
    def plan_label(self):
        if not self.plan:
            return 'Free'
        name = (self.plan.name or '').strip()
        lower = name.lower()
        if 'premium' in lower:
            return 'Premium'
        if 'basic' in lower or 'starter' in lower:
            return 'Basic'
        return name or 'Custom'

    @property
    def is_premium(self):
        if not self.plan:
            return False
        name = (self.plan.name or '').lower()
        return 'premium' in name or 'advanced' in name


class Subscription(UserSubscription):
    class Meta:
        proxy = True
        verbose_name = 'Subscription'
        verbose_name_plural = 'Subscriptions'


class UserServiceUsage(ServiceUsage):
    class Meta:
        proxy = True
        verbose_name = 'User service usage'
        verbose_name_plural = 'User service usage'


class ActivityLog(models.Model):
    """Record important user actions for audit and activity history."""
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    action = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        uid = self.user.email if self.user else 'anon'
        return f"{uid} - {self.action} @ {self.timestamp.isoformat()}"


class UserApiKey(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_keys')
    name = models.CharField(max_length=100)
    key_prefix = models.CharField(max_length=16)
    key_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.name} ({self.key_prefix}...)"

    @property
    def is_active(self):
        return self.revoked_at is None
