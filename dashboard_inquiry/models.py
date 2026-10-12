import uuid

from django.conf import settings
from django.db import models

# Starting prices shown on the Dashboard Development pricing cards and echoed
# on the quote form. The final quote scales with scope/complexity.
PACKAGE_PRICES = {
    'starter': 2500,
    'business': 6500,
    'enterprise': 15000,
}


class DashboardInquiry(models.Model):
    """A quote / requirements request raised from the Dashboard Development pricing CTAs."""

    PACKAGE_CHOICES = [
        ('starter', 'Starter'),
        ('business', 'Business'),
        ('enterprise', 'Enterprise'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('reviewed', 'Reviewed'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]

    BUDGET_CHOICES = [
        ('u5', 'Under $5k'),
        ('5-15', '$5k – $15k'),
        ('15-40', '$15k – $40k'),
        ('40+', '$40k or more'),
        ('unsure', 'Not sure yet'),
    ]

    TIMELINE_CHOICES = [
        ('asap', 'As soon as possible'),
        ('1-2m', '1–2 months'),
        ('3-6m', '3–6 months'),
        ('flexible', 'Flexible'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    reference = models.CharField(max_length=32, unique=True, blank=True, editable=False)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    company = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    package = models.CharField(max_length=20, choices=PACKAGE_CHOICES, default='business')
    message = models.TextField(blank=True)
    data_sources = models.CharField(max_length=255, blank=True)
    budget = models.CharField(max_length=50, choices=BUDGET_CHOICES, blank=True)
    timeline = models.CharField(max_length=50, choices=TIMELINE_CHOICES, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference} — {self.get_package_display()} — {self.name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            base = uuid.uuid4().hex[:10].upper()
            reference = f"DD-{base}"
            while DashboardInquiry.objects.filter(reference=reference).exists():
                base = uuid.uuid4().hex[:10].upper()
                reference = f"DD-{base}"
            self.reference = reference
        super().save(*args, **kwargs)
