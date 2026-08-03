from django.db import models


class Link(models.Model):
    INTERNAL = 'internal'
    EXTERNAL = 'external'
    BACK = 'back'

    LINK_TYPE_CHOICES = [
        (INTERNAL, 'Internal'),
        (EXTERNAL, 'External'),
        (BACK, 'Back'),
    ]

    title = models.CharField(max_length=200)
    url = models.URLField(max_length=2000)
    link_type = models.CharField(max_length=20, choices=LINK_TYPE_CHOICES, default=EXTERNAL)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.link_type})"


class IoTDevice(models.Model):
    name = models.CharField(max_length=100)
    device_id = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, default='active')
    location = models.CharField(max_length=100, blank=True)
    last_active = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.device_id})"


class SocialAccount(models.Model):
    PLATFORM_CHOICES = [
        ('twitter', 'Twitter'),
        ('linkedin', 'LinkedIn'),
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('other', 'Other'),
    ]

    platform = models.CharField(max_length=50, choices=PLATFORM_CHOICES)
    username = models.CharField(max_length=100)
    url = models.URLField(blank=True)
    followers_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.platform} - {self.username}"


class SecurityAudit(models.Model):
    score = models.IntegerField(help_text="Security score from 0 to 100")
    status = models.CharField(max_length=50, default='All systems secure')
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-checked_at']
        get_latest_by = 'checked_at'

    def __str__(self):
        return f"Audit {self.checked_at.date()} - Score: {self.score}"
