from django.db import models
from django.conf import settings

# Create your models here.

class ConsultationRequest(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    matricule = models.CharField(max_length=32, unique=True, blank=True)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    company = models.CharField(max_length=100, blank=True)
    topic = models.CharField(max_length=50, choices=[
        ('community', 'Community Management'),
        ('industrial', 'Industrial Automation'),
        ('integration', 'System Integration'),
        ('other', 'Other')
    ], default='other')
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.topic}"

    def save(self, *args, **kwargs):
        if not self.matricule:
            import uuid
            base = uuid.uuid4().hex[:10].upper()
            matricule = f"C-{base}"
            while ConsultationRequest.objects.filter(matricule=matricule).exists():
                base = uuid.uuid4().hex[:10].upper()
                matricule = f"C-{base}"
            self.matricule = matricule
        super().save(*args, **kwargs)

class WebsiteBuildRequest(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    company = models.CharField(max_length=100, blank=True)
    website_type = models.CharField(max_length=50)
    features = models.JSONField(default=list)  # Store features as a list of strings
    budget = models.CharField(max_length=50, blank=True)
    timeline = models.CharField(max_length=50, blank=True)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='pending', choices=[
        ('pending', 'Pending'),
        ('reviewed', 'Reviewed'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected')
    ])

    def __str__(self):
        return f"Website Request: {self.website_type} by {self.name}"
