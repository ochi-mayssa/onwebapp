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


class APIRequest(models.Model):
    """A client-submitted request for an existing, third-party, or custom API."""

    REQUEST_TYPE_CHOICES = [
        ('existing', 'Existing API'),
        ('third_party', 'Third-Party API Integration'),
        ('custom', 'Custom API Development'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
    ]
    BUDGET_CHOICES = [
        ('undecided', 'Not sure yet'),
        ('under-1k', 'Under $1,000'),
        ('1k-5k', '$1,000 - $5,000'),
        ('5k-20k', '$5,000 - $20,000'),
        ('20k-plus', '$20,000+'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='api_requests',
    )
    reference = models.CharField(max_length=32, unique=True, blank=True, editable=False)
    full_name = models.CharField(max_length=120)
    business_email = models.EmailField()
    company_name = models.CharField(max_length=120, blank=True)
    request_type = models.CharField(max_length=30, choices=REQUEST_TYPE_CHOICES)
    api_name_or_category = models.CharField(max_length=150)
    use_case = models.TextField()
    required_features = models.TextField()
    expected_usage = models.CharField(max_length=150, blank=True)
    budget_range = models.CharField(max_length=30, blank=True, choices=BUDGET_CHOICES)
    additional_requirements = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    internal_notes = models.TextField(
        blank=True,
        help_text='Staff-only notes. Never shown to clients.',
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_api_requests',
        verbose_name='Assigned to',
    )
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'API request'
        verbose_name_plural = 'API requests'

    def __str__(self):
        return f'{self.reference} - {self.full_name} ({self.get_request_type_display()})'

    def save(self, *args, **kwargs):
        import uuid
        new_reference = False
        if not self.reference:
            base = uuid.uuid4().hex[:10].upper()
            reference = f'API-{base}'
            while APIRequest.objects.filter(reference=reference).exists():
                base = uuid.uuid4().hex[:10].upper()
                reference = f'API-{base}'
            self.reference = reference
            new_reference = True
        super().save(*args, **kwargs)
        if new_reference:
            APIRequestStatusLog.objects.create(
                request=self, from_status='', to_status=self.status,
                note='Request submitted',
            )

    def change_status(self, new_status, changed_by=None, note=''):
        """Transition status, log the change, and notify the client.

        Shared by the custom admin page (and reusable elsewhere). Returns
        True if the status actually changed.
        """
        from .notifications import notify_client_status_change

        old_status = self.status
        if old_status == new_status:
            return False
        self.status = new_status
        self.save(update_fields=['status', 'updated_at'])
        APIRequestStatusLog.objects.create(
            request=self, from_status=old_status, to_status=new_status,
            changed_by=changed_by, note=note or '',
        )
        notify_client_status_change(self, old_status, new_status)
        return True


class APIRequestStatusLog(models.Model):
    """Status-transition history for an API request (staff-visible)."""

    request = models.ForeignKey(
        APIRequest, on_delete=models.CASCADE, related_name='status_logs',
    )
    from_status = models.CharField(
        max_length=20, choices=APIRequest.STATUS_CHOICES, blank=True,
    )
    to_status = models.CharField(max_length=20, choices=APIRequest.STATUS_CHOICES)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='api_request_status_changes',
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.request.reference}: {self.from_status or "(new)"} -> {self.to_status}'
