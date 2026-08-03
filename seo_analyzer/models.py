from django.db import models
from django.conf import settings
from django.utils import timezone
from urllib.parse import urlparse


class SEOTask(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="seo_tasks",
        blank=True,
        null=True,
        help_text="User who initiated the audit (null for anonymous/public demo)",
    )
    url = models.URLField(
        max_length=2000,
        help_text="Root URL to start crawling (must include http/https)",
    )
    domain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="Extracted domain (www.example.com or example.com)",
    )
    max_pages = models.PositiveSmallIntegerField(
        default=50,
        help_text="Maximum number of pages to crawl (capped at 100 for MVP)",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text="Only populated if status = 'failed'",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = "created_at"
        verbose_name = "SEO Audit Task"
        verbose_name_plural = "SEO Audit Tasks"

    def save(self, *args, **kwargs):
        if not self.domain:
            parsed = urlparse(self.url)
            self.domain = parsed.netloc.lower()
        if self.max_pages > 100:
            self.max_pages = 100
        super().save(*args, **kwargs)

    def __str__(self):
        return f"SEO Audit: {self.domain} ({self.status})"


class SEOResult(models.Model):
    task = models.OneToOneField(
        SEOTask,
        on_delete=models.CASCADE,
        related_name="result",
        primary_key=True,
    )

    final_url = models.URLField(max_length=2000, help_text="Final URL after redirects")
    https_status = models.BooleanField(
        default=False,
        help_text="True if root domain has valid, non-expired HTTPS certificate",
    )
    main_status_code = models.PositiveSmallIntegerField(
        help_text="HTTP status code of root URL"
    )
    main_response_time = models.FloatField(help_text="Root URL response time (seconds)")

    health_score = models.DecimalField(
        max_digits=5, decimal_places=2, db_index=True
    )
    technical_score = models.DecimalField(max_digits=5, decimal_places=2)
    on_page_score = models.DecimalField(max_digits=5, decimal_places=2)
    performance_score = models.DecimalField(max_digits=5, decimal_places=2)
    discovery_score = models.DecimalField(max_digits=5, decimal_places=2)
    ai_opportunity_score = models.DecimalField(max_digits=5, decimal_places=2)

    critical_issues = models.PositiveIntegerField(default=0)
    high_issues = models.PositiveIntegerField(default=0)
    medium_issues = models.PositiveIntegerField(default=0)
    low_issues = models.PositiveIntegerField(default=0)
    total_issues = models.PositiveIntegerField(default=0)

    pages_crawled = models.PositiveIntegerField(default=0)
    internal_links_count = models.PositiveIntegerField(default=0)
    broken_internal_links_count = models.PositiveIntegerField(default=0)
    sitemap_entries_found = models.PositiveIntegerField(default=0)
    orphan_pages_count = models.PositiveIntegerField(default=0)
    redirect_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "SEO Audit Result"
        verbose_name_plural = "SEO Audit Results"

    def __str__(self):
        return f"Audit Result: {self.task.domain} (Health: {self.health_score})"


class SEOPageAudit(models.Model):
    task = models.ForeignKey(
        SEOTask,
        on_delete=models.CASCADE,
        related_name="page_audits",
    )
    url = models.URLField(
        max_length=2000,
        db_index=True,
        help_text="Original URL requested",
    )
    final_url = models.URLField(
        max_length=2000,
        blank=True,
        null=True,
        help_text="Final URL after redirects",
    )
    status_code = models.PositiveSmallIntegerField(
        null=True, blank=True, db_index=True
    )
    response_time = models.FloatField(
        null=True, blank=True, help_text="Response time (seconds)"
    )
    page_size = models.PositiveIntegerField(
        null=True, blank=True, help_text="Page size (bytes)"
    )

    title_tag = models.TextField(blank=True, null=True)
    title_tag_length = models.PositiveSmallIntegerField(null=True, blank=True)
    meta_description = models.TextField(blank=True, null=True)
    meta_description_length = models.PositiveSmallIntegerField(null=True, blank=True)
    h1_count = models.PositiveSmallIntegerField(default=0)
    h1_text = models.TextField(blank=True, null=True)
    h2_count = models.PositiveSmallIntegerField(default=0)
    word_count = models.PositiveIntegerField(null=True, blank=True)

    has_canonical = models.BooleanField(default=False)
    canonical_url = models.URLField(max_length=2000, blank=True, null=True)
    is_noindex = models.BooleanField(default=False)

    images_count = models.PositiveSmallIntegerField(default=0)
    images_missing_alt = models.PositiveSmallIntegerField(default=0)
    images_details = models.JSONField(default=list, blank=True)

    videos_count = models.PositiveSmallIntegerField(default=0)
    videos_details = models.JSONField(default=list, blank=True)
    has_video_schema = models.BooleanField(default=False)

    internal_links_count = models.PositiveIntegerField(default=0)
    broken_internal_links_count = models.PositiveIntegerField(default=0)

    has_robots = models.BooleanField(default=False)
    has_sitemap = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["url"]
        verbose_name = "Page Audit"
        verbose_name_plural = "Page Audits"
        constraints = [
            models.UniqueConstraint(
                fields=["task", "final_url"], name="unique_page_per_task_final_url"
            ),
        ]

    def __str__(self):
        return f"Page Audit: {self.final_url or self.url}"


class SEOIssue(models.Model):
    SEVERITY_CHOICES = [
        ("critical", "Critical"),
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]
    CATEGORY_CHOICES = [
        ("general", "General"),
        ("on-page", "On-Page SEO"),
        ("technical", "Technical SEO"),
        ("performance", "Performance"),
        ("discovery", "Discovery"),
    ]

    task = models.ForeignKey(
        SEOTask,
        on_delete=models.CASCADE,
        related_name="issues",
    )
    page_audit = models.ForeignKey(
        SEOPageAudit,
        on_delete=models.CASCADE,
        related_name="issues",
        blank=True,
        null=True,
        help_text="Null if issue is audit-wide (not page-specific)",
    )
    name = models.CharField(max_length=255)
    severity = models.CharField(
        max_length=20, choices=SEVERITY_CHOICES, db_index=True
    )
    category = models.CharField(
        max_length=50, choices=CATEGORY_CHOICES, db_index=True
    )
    description = models.TextField()
    seo_impact = models.TextField(blank=True, null=True)
    business_impact = models.TextField(blank=True, null=True)
    recommended_fix = models.TextField(blank=True, null=True)
    priority = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        blank=True,
        null=True,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=[("open", "Open"), ("resolved", "Resolved")],
        default="open",
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = [
            models.Case(
                models.When(severity="critical", then=0),
                models.When(severity="high", then=1),
                models.When(severity="medium", then=2),
                models.When(severity="low", then=3),
                default=4,
                output_field=models.IntegerField(),
            ),
            "-created_at",
        ]
        verbose_name = "SEO Issue"
        verbose_name_plural = "SEO Issues"
        constraints = [
            models.UniqueConstraint(
                fields=["task", "page_audit", "name"],
                name="unique_issue_per_task_page",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.priority:
            self.priority = self.severity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.severity.upper()}: {self.name}"


class SEOHistoricalReport(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="seo_historical_reports",
        blank=True,
        null=True,
    )
    domain = models.CharField(max_length=255, db_index=True)
    health_score = models.DecimalField(max_digits=5, decimal_places=2)
    technical_score = models.DecimalField(max_digits=5, decimal_places=2)
    on_page_score = models.DecimalField(max_digits=5, decimal_places=2)
    performance_score = models.DecimalField(max_digits=5, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "SEO Historical Report"
        verbose_name_plural = "SEO Historical Reports"

    def __str__(self):
        return f"Historical: {self.domain} ({self.created_at.date()})"


class URLIntelligenceTask(models.Model):
    STATUS_CHOICES = SEOTask.STATUS_CHOICES

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="url_intelligence_tasks",
        blank=True,
        null=True,
    )
    url = models.URLField(max_length=2000, db_index=True)
    target_keyword = models.CharField(max_length=255, blank=True)
    domain = models.CharField(max_length=255, blank=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "URL Intelligence Task"
        verbose_name_plural = "URL Intelligence Tasks"

    def save(self, *args, **kwargs):
        if not self.domain and self.url:
            self.domain = urlparse(self.url).netloc.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"URL Intelligence: {self.url} ({self.status})"


class URLIntelligenceResult(models.Model):
    CANONICAL_STATUS_CHOICES = [
        ("self", "Self-Canonical"),
        ("other", "Canonical to Another URL"),
        ("missing", "Canonical Missing"),
        ("conflict", "Canonical Conflict"),
        ("not_evaluated", "Not Evaluated"),
        ("unknown", "Unknown"),
    ]
    INDEXABILITY_STATUS_CHOICES = [
        ("indexable", "Indexable"),
        ("noindex", "Noindex"),
        ("blocked", "Blocked"),
        ("redirected", "Redirected"),
        ("not_evaluated_auth_required", "Not Evaluated — Authentication Required"),
        ("not_evaluated_access_restricted", "Not Evaluated — Access Restricted"),
        ("not_evaluated_rate_limited", "Not Evaluated — Rate Limited"),
        ("not_found", "Not Indexable — Not Found"),
        ("gone", "Not Indexable — Gone"),
        ("server_error", "Temporarily Unavailable — Server Error"),
        ("error", "Error"),
        ("unknown", "Unknown"),
    ]
    KEYWORD_MATCH_CHOICES = [
        ("yes", "Yes"),
        ("partial", "Partial"),
        ("no", "No"),
        ("not_provided", "Not Provided"),
    ]

    task = models.OneToOneField(
        URLIntelligenceTask,
        on_delete=models.CASCADE,
        related_name="result",
        primary_key=True,
    )
    original_url = models.URLField(max_length=2000)
    final_url = models.URLField(max_length=2000, blank=True)
    http_status_code = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    response_time = models.FloatField(null=True, blank=True)
    https_status = models.BooleanField(default=False)
    redirect_detected = models.BooleanField(default=False)
    redirect_count = models.PositiveSmallIntegerField(default=0)

    protocol = models.CharField(max_length=10, blank=True)
    domain = models.CharField(max_length=255, blank=True, db_index=True)
    subdomain = models.CharField(max_length=255, blank=True)
    path = models.CharField(max_length=2000, blank=True)
    slug = models.CharField(max_length=500, blank=True)
    url_length = models.PositiveSmallIntegerField(default=0)
    url_depth = models.PositiveSmallIntegerField(default=0)
    trailing_slash = models.BooleanField(default=False)
    has_uppercase = models.BooleanField(default=False)
    has_underscores = models.BooleanField(default=False)
    hyphen_count = models.PositiveSmallIntegerField(default=0)
    special_character_count = models.PositiveSmallIntegerField(default=0)
    encoded_space_detected = models.BooleanField(default=False)
    numeric_slug_detected = models.BooleanField(default=False)
    query_params_count = models.PositiveSmallIntegerField(default=0)
    tracking_params_count = models.PositiveSmallIntegerField(default=0)
    functional_params_count = models.PositiveSmallIntegerField(default=0)
    unnecessary_params_count = models.PositiveSmallIntegerField(default=0)
    has_fragment = models.BooleanField(default=False)
    dynamic_url_detected = models.BooleanField(default=False)

    canonical_url = models.URLField(max_length=2000, blank=True)
    canonical_status = models.CharField(
        max_length=30,
        choices=CANONICAL_STATUS_CHOICES,
        default="unknown",
        db_index=True,
    )
    canonical_matches = models.BooleanField(default=False)
    meta_robots = models.CharField(max_length=255, blank=True)
    x_robots_tag = models.CharField(max_length=255, blank=True)
    indexability_status = models.CharField(
        max_length=40,
        choices=INDEXABILITY_STATUS_CHOICES,
        default="unknown",
        db_index=True,
    )

    health_score = models.DecimalField(max_digits=5, decimal_places=2, db_index=True)
    structure_score = models.DecimalField(max_digits=5, decimal_places=2)
    technical_score = models.DecimalField(max_digits=5, decimal_places=2)
    canonical_score = models.DecimalField(max_digits=5, decimal_places=2)
    indexability_score = models.DecimalField(max_digits=5, decimal_places=2)
    seo_friendliness_score = models.DecimalField(max_digits=5, decimal_places=2)
    keyword_relevance_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    keyword_match_status = models.CharField(
        max_length=20,
        choices=KEYWORD_MATCH_CHOICES,
        default="not_provided",
    )

    critical_issues = models.PositiveSmallIntegerField(default=0)
    high_issues = models.PositiveSmallIntegerField(default=0)
    medium_issues = models.PositiveSmallIntegerField(default=0)
    low_issues = models.PositiveSmallIntegerField(default=0)
    informational_issues = models.PositiveSmallIntegerField(default=0)
    total_issues = models.PositiveSmallIntegerField(default=0)

    redirect_chain = models.JSONField(default=list, blank=True)
    parameters_payload = models.JSONField(default=dict, blank=True)
    structure_payload = models.JSONField(default=dict, blank=True)
    quality_checks = models.JSONField(default=list, blank=True)
    recommendations_payload = models.JSONField(default=list, blank=True)
    optimized_url_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "URL Intelligence Result"
        verbose_name_plural = "URL Intelligence Results"

    def __str__(self):
        return f"URL Intelligence Result: {self.domain or self.original_url}"


class URLIntelligenceIssue(models.Model):
    SEVERITY_CHOICES = [
        ("critical", "Critical"),
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
        ("informational", "Informational"),
    ]
    CATEGORY_CHOICES = [
        ("structure", "URL Structure"),
        ("technical", "Technical Accessibility"),
        ("canonical", "Canonical"),
        ("indexability", "Indexability"),
        ("seo", "SEO Friendliness"),
        ("keyword", "Keyword Relevance"),
    ]

    task = models.ForeignKey(
        URLIntelligenceTask,
        on_delete=models.CASCADE,
        related_name="issues",
    )
    name = models.CharField(max_length=255)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, db_index=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, db_index=True)
    evidence = models.TextField(blank=True)
    description = models.TextField()
    seo_impact = models.TextField(blank=True)
    business_impact = models.TextField(blank=True)
    recommended_fix = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=[("open", "Open"), ("resolved", "Resolved")],
        default="open",
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = [
            models.Case(
                models.When(severity="critical", then=0),
                models.When(severity="high", then=1),
                models.When(severity="medium", then=2),
                models.When(severity="low", then=3),
                models.When(severity="informational", then=4),
                default=5,
                output_field=models.IntegerField(),
            ),
            "-created_at",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["task", "name"],
                name="unique_url_intelligence_issue_per_task",
            ),
        ]
        verbose_name = "URL Intelligence Issue"
        verbose_name_plural = "URL Intelligence Issues"

    def __str__(self):
        return f"{self.severity.upper()}: {self.name}"


class SEOMonitoringSnapshot(models.Model):
    ANALYSIS_TYPE_CHOICES = [
        ("website", "Website Checker"),
        ("internal", "Internal Links"),
        ("external", "External Links"),
        ("backlinks", "Backlinks"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="seo_monitoring_snapshots",
        blank=True,
        null=True,
    )
    source_identifier = models.CharField(max_length=64, unique=True)
    website = models.URLField(max_length=2000)
    domain = models.CharField(max_length=255, db_index=True)
    analysis_type = models.CharField(
        max_length=20,
        choices=ANALYSIS_TYPE_CHOICES,
        default="website",
        db_index=True,
    )

    health_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    visibility_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ai_opportunity_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    technical_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    performance_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    content_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    security_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    broken_links = models.PositiveIntegerField(null=True, blank=True)
    redirects = models.PositiveIntegerField(null=True, blank=True)
    internal_links = models.PositiveIntegerField(null=True, blank=True)
    external_links = models.PositiveIntegerField(null=True, blank=True)
    indexed_pages = models.PositiveIntegerField(null=True, blank=True)
    issues_count = models.PositiveIntegerField(null=True, blank=True)
    working_links = models.PositiveIntegerField(null=True, blank=True)
    errors_count = models.PositiveIntegerField(null=True, blank=True)

    tracked_items = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["domain", "analysis_type", "-created_at"]),
        ]
        verbose_name = "SEO Monitoring Snapshot"
        verbose_name_plural = "SEO Monitoring Snapshots"

    def __str__(self):
        return f"{self.domain} [{self.analysis_type}] {self.created_at:%Y-%m-%d %H:%M}"


class SEONotificationEndpoint(models.Model):
    CHANNEL_CHOICES = [
        ("email", "Email Alerts"),
        ("slack", "Slack"),
        ("teams", "Microsoft Teams"),
        ("webhook", "Webhook"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="seo_notification_endpoints",
        blank=True,
        null=True,
    )
    domain = models.CharField(max_length=255, db_index=True)
    channel_type = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    destination = models.CharField(max_length=500)
    is_active = models.BooleanField(default=False)
    configuration = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["domain", "channel_type"]
        verbose_name = "SEO Notification Endpoint"
        verbose_name_plural = "SEO Notification Endpoints"

    def __str__(self):
        return f"{self.domain} -> {self.get_channel_type_display()}"
