from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class SocialProvider(models.Model):
    PROVIDER_CHOICES = [
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('tiktok', 'TikTok'),
        ('youtube', 'YouTube'),
        ('google_reviews', 'Google Reviews'),
    ]

    name = models.CharField(max_length=50, choices=PROVIDER_CHOICES, unique=True)
    enabled = models.BooleanField(default=True)
    
    # Placeholder token fields for future use (currently using env vars)
    api_key = models.CharField(max_length=255, blank=True, help_text="API Key (placeholder)")
    api_secret = models.CharField(max_length=255, blank=True, help_text="API Secret (placeholder)")
    access_token = models.TextField(blank=True, help_text="Access Token (placeholder)")
    refresh_token = models.TextField(blank=True, help_text="Refresh Token (placeholder)")
    
    last_sync_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return self.get_name_display()

class SocialStreamConfig(models.Model):
    project = models.OneToOneField('projects.Project', on_delete=models.CASCADE, related_name='social_stream_config')
    enabled_providers = models.ManyToManyField(SocialProvider, blank=True)
    
    # Filter thresholds
    min_sentiment_score = models.FloatField(default=0.7, help_text="Minimum sentiment score to display (0.0 to 1.0)")
    auto_approve = models.BooleanField(default=True, help_text="Automatically approve events with high sentiment score")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Social Stream Config for {self.project.title}"

class SocialEvent(models.Model):
    EVENT_TYPE_CHOICES = [
        ('comment', 'Comment'),
        ('review', 'Review'),
        ('post', 'Post'),
        ('share', 'Share'),
        ('mention', 'Mention'),
        ('like', 'Like'),
    ]

    provider = models.ForeignKey(SocialProvider, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    external_id = models.CharField(max_length=255, unique=True, help_text="ID from the external platform")
    
    author_name = models.CharField(max_length=255)
    author_avatar_url = models.URLField(max_length=500, blank=True, null=True)
    text = models.TextField(blank=True)
    url = models.URLField(max_length=500, blank=True, null=True)
    
    sentiment_score = models.FloatField(default=0.0)
    
    raw_json = models.JSONField(default=dict, blank=True)
    
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    occurred_at = models.DateTimeField(help_text="When the event actually happened on the platform")

    class Meta:
        ordering = ['-occurred_at']
        indexes = [
            models.Index(fields=['provider', 'external_id']),
            models.Index(fields=['sentiment_score']),
        ]

    def __str__(self):
        return f"{self.provider.name} - {self.author_name}: {self.text[:30]}"
