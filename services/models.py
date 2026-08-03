from django.conf import settings
from django.db import models
from django.utils import timezone

class SocialUser(models.Model):
    PLATFORM_CHOICES = [
        ('instagram', 'Instagram'),
        ('tiktok', 'TikTok'),
        ('youtube', 'YouTube'),
        ('twitter', 'Twitter'),
    ]
    
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    username = models.CharField(max_length=100)
    platform_id = models.CharField(max_length=100, unique=True)
    followers_count = models.BigIntegerField(default=0)
    following_count = models.BigIntegerField(default=0)
    profile_url = models.URLField(max_length=500, blank=True)
    last_scraped = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.username} ({self.platform})"

class Hashtag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    total_posts = models.IntegerField(default=0)
    avg_engagement = models.FloatField(default=0.0)

    def __str__(self):
        return f"#{self.name}"

class SocialPost(models.Model):
    PLATFORM_CHOICES = [
        ('instagram', 'Instagram'),
        ('tiktok', 'TikTok'),
        ('youtube', 'YouTube'),
        ('twitter', 'Twitter'),
        ('facebook', 'Facebook'),
        ('linkedin', 'LinkedIn'),
    ]
    
    CLASSIFICATION_CHOICES = [
        ('viral', 'Viral'),
        ('normal', 'Normal'),
        ('low', 'Low Engagement'),
    ]

    user = models.ForeignKey(SocialUser, on_delete=models.CASCADE, related_name='posts')
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    post_url = models.URLField(max_length=500, unique=True)
    post_id = models.CharField(max_length=100, unique=True)
    caption = models.TextField(blank=True)
    posted_at = models.DateTimeField()
    
    # Metrics
    likes = models.BigIntegerField(default=0)
    comments = models.BigIntegerField(default=0)
    shares = models.BigIntegerField(default=0)
    views = models.BigIntegerField(default=0) # Video views
    
    # Calculated
    engagement_score = models.BigIntegerField(default=0)
    classification = models.CharField(max_length=20, choices=CLASSIFICATION_CHOICES, default='normal')
    
    hashtags = models.ManyToManyField(Hashtag, related_name='posts', blank=True)
    crawled_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.engagement_score = self.likes + self.comments + self.shares
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.platform} post by {self.user.username} ({self.post_id})"

class PlatformMetrics(models.Model):
    platform = models.CharField(max_length=20, unique=True)
    total_posts_tracked = models.IntegerField(default=0)
    avg_engagement_rate = models.FloatField(default=0.0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.platform} Metrics"


class SocialTrackingSnapshot(models.Model):
    STATUS_CHOICES = [
        ("success", "Success"),
        ("partial", "Partial"),
        ("unavailable", "Unavailable"),
        ("error", "Error"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="social_tracking_snapshots",
        null=True,
        blank=True,
    )
    handle_input = models.CharField(max_length=255)
    normalized_handle = models.CharField(max_length=255, db_index=True)
    detected_platform = models.CharField(max_length=20, blank=True)
    selected_platforms = models.JSONField(default=list, blank=True)
    total_followers = models.BigIntegerField(null=True, blank=True)
    engagement_rate = models.FloatField(null=True, blank=True)
    positive_count = models.IntegerField(default=0)
    neutral_count = models.IntegerField(default=0)
    negative_count = models.IntegerField(default=0)
    data_source = models.CharField(max_length=20, default="database")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="success")
    synced_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-synced_at", "-id"]

    def __str__(self):
        return f"{self.normalized_handle} ({self.detected_platform or 'multi-platform'})"
