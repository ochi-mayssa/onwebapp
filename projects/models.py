from django.db import models
from django.conf import settings
from django.urls import reverse

class Project(models.Model):
    STATUS_CHOICES = [
        ('PLANNING', 'Planning'),
        ('DESIGN', 'Design'),
        ('DEVELOPMENT', 'Development'),
        ('DELIVERY', 'Delivery'),
        ('COMPLETED', 'Completed'),
        ('ON_HOLD', 'On Hold'),
        ('CANCELLED', 'Cancelled'),
        ('DELAYED', 'Delayed'),
    ]
    
    PHASE_CHOICES = [
        ('PLANNING', 'Planning & Requirements'),
        ('DESIGN', 'Design Drafts'),
        ('DEVELOPMENT', 'Development'),
        ('TESTING', 'Testing & QA'),
        ('LAUNCH', 'Launch'),
        ('COMPLETED', 'Completed'),
        ('ON_HOLD', 'On Hold'),
        ('CANCELLED', 'Cancelled'),
    ]

    PROJECT_TYPE_CHOICES = [
        ('WEBSITE', 'Website Builder'),
        ('BRANDING', 'Brand Assist'),
        ('AUTOMATION', 'Industrial Automation'),
        ('IOT', 'IoT Integration'),
        ('SOCIAL', 'Social Media Analytics'),
        ('CUSTOM', 'Custom Project'),
    ]

    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='projects')
    title = models.CharField(max_length=200)
    description = models.TextField()
    project_type = models.CharField(max_length=20, choices=PROJECT_TYPE_CHOICES, default='WEBSITE')
    current_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PLANNING')
    current_phase = models.CharField(max_length=20, choices=PHASE_CHOICES, default='PLANNING')
    progress_percentage = models.PositiveIntegerField(default=0)
    preview_url = models.URLField(blank=True, null=True)
    expected_delivery_date = models.DateField(blank=True, null=True)
    
    # Brand Identity
    brand_color = models.CharField(max_length=7, default='#000000')
    brand_logo = models.ImageField(upload_to='project_logos/', blank=True, null=True)
    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
    ]
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='MEDIUM')
    assigned_team = models.CharField(max_length=100, blank=True)
    
    # Agile Plan Management
    AGILE_STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('AWAITING_APPROVAL', 'Awaiting Client Approval'),
        ('APPROVED', 'Approved'),
        ('CHANGES_REQUESTED', 'Changes Requested'),
    ]
    agile_status = models.CharField(max_length=20, choices=AGILE_STATUS_CHOICES, default='DRAFT')
    agile_plan_file = models.FileField(upload_to='agile_plans/', blank=True, null=True)
    agile_plan_approved_at = models.DateTimeField(blank=True, null=True)
    agile_plan_rejection_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def workflow_status(self):
        """Alias for current_status to meet strict workflow requirements."""
        return self.current_status

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        """Return canonical URL for a Project detail page."""
        try:
            return reverse('projects:project_detail', args=[self.pk])
        except Exception:
            # Fallback to preview_url when available or root
            if getattr(self, 'preview_url', None):
                return self.preview_url
            return '/'

class ProjectPhase(models.Model):
    PHASE_TYPE_CHOICES = [
        ('PLANNING', 'Planning & Requirements'),
        ('DESIGN', 'Design Drafts'),
        ('DEVELOPMENT', 'Development'),
        ('TESTING', 'Testing & QA'),
        ('LAUNCH', 'Launch'),
    ]
    
    STATUS_CHOICES = [
        ('NOT_STARTED', 'Not Started'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('DELAYED', 'Delayed'),
    ]

    APPROVAL_STATUS_CHOICES = [
        ('NOT_REQUIRED', 'Not Required'),
        ('AWAITING_CLIENT', 'Awaiting Client Approval'),
        ('APPROVED', 'Approved'),
        ('CHANGES_REQUESTED', 'Changes Requested'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='phases')
    phase_type = models.CharField(max_length=20, choices=PHASE_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NOT_STARTED')
    progress = models.PositiveIntegerField(default=0)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS_CHOICES, default='NOT_REQUIRED')
    ready_for_review = models.BooleanField(default=False)
    approved_at = models.DateTimeField(blank=True, null=True)
    client_visible_notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    assignee_role = models.CharField(max_length=100, blank=True)
    due_date = models.DateField(blank=True, null=True)
    is_locked = models.BooleanField(default=True, help_text="Locked until Agile Plan is approved")

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.project.title} - {self.get_phase_type_display()}"

class PhaseAssignment(models.Model):
    """Explicit assignment of a team member to a phase with role and visibility control."""
    phase = models.ForeignKey(ProjectPhase, on_delete=models.CASCADE, related_name='assignments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='phase_assignments')
    role = models.CharField(max_length=100, help_text="e.g. Designer, Developer, QA")
    responsibility = models.TextField(blank=True, help_text="Short description of responsibilities")
    is_visible = models.BooleanField(default=True, help_text="Visible to client")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.phase} ({self.role})"

class PhaseTask(models.Model):
    STATUS_CHOICES = [
        ('TODO', 'To Do'),
        ('IN_PROGRESS', 'In Progress'),
        ('BLOCKED', 'Blocked'),
        ('READY_FOR_REVIEW', 'Ready for Review'),
        ('COMPLETED', 'Completed'),
    ]
    
    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical'),
    ]

    phase = models.ForeignKey(ProjectPhase, on_delete=models.CASCADE, related_name='tasks')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='TODO')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='MEDIUM')
    due_date = models.DateField(blank=True, null=True)
    is_completed = models.BooleanField(default=False) # Deprecated, keeping for backward compat temporarily
    completed_at = models.DateTimeField(blank=True, null=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.status == 'COMPLETED' and not self.is_completed:
            self.is_completed = True
            from django.utils import timezone
            if not self.completed_at:
                self.completed_at = timezone.now()
        elif self.status != 'COMPLETED' and self.is_completed:
            self.is_completed = False
            self.completed_at = None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class ProjectDeliverable(models.Model):
    phase = models.ForeignKey(ProjectPhase, on_delete=models.CASCADE, related_name='deliverables')
    name = models.CharField(max_length=200)
    file = models.FileField(upload_to='project_deliverables/', blank=True, null=True)
    link = models.URLField(blank=True, null=True)
    version = models.CharField(max_length=50, default='v1.0')
    created_at = models.DateTimeField(auto_now_add=True)
    client_visible = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class ProjectFeedback(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('REVIEWED', 'Reviewed'),
        ('IMPLEMENTED', 'Implemented'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='feedback')
    phase = models.ForeignKey(ProjectPhase, on_delete=models.CASCADE, related_name='feedback', null=True, blank=True)
    content = models.TextField()
    attachment = models.FileField(upload_to='project_feedback/', blank=True, null=True)
    is_resolved = models.BooleanField(default=False)
    is_admin_response = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback on {self.phase}"

class ClientAsset(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='assets')
    name = models.CharField(max_length=200)
    file = models.FileField(upload_to='client_assets/')
    description = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class BrandAsset(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending Review'),
        ('APPROVED', 'Approved'),
        ('DECLINED', 'Declined'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='brand_assets')
    name = models.CharField(max_length=200)
    file = models.FileField(upload_to='brand_assets/')
    version = models.CharField(max_length=50, default='v1')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    client_feedback = models.TextField(blank=True, help_text='Reason for rejection or comments')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class ProjectActivity(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='activities')
    content = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.content

class WorkflowNotification(models.Model):
    """
    Audit log for all automated notifications sent by the workflow system.
    """
    TYPE_CHOICES = [
        ('DELAY', 'Delay Alert'),
        ('APPROVAL', 'Approval Needed'),
        ('STATUS', 'Status Update'),
        ('REPORT', 'Report Generated'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workflow_notifications')
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    message = models.TextField()
    severity = models.CharField(max_length=10, choices=[('LOW', 'Low'), ('MEDIUM', 'Medium'), ('HIGH', 'High'), ('CRITICAL', 'Critical')], default='MEDIUM')
    is_read = models.BooleanField(default=False)
    sent_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-sent_at']
        
    def __str__(self):
        return f"{self.get_notification_type_display()} for {self.recipient.username}"

class Invoice(models.Model):
    """
    Automated invoice generation for projects and subscriptions.
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ISSUED', 'Issued'),
        ('PAID', 'Paid'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='invoices', null=True, blank=True)
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='invoices')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    issued_date = models.DateField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)
    pdf_file = models.FileField(upload_to='invoices/', blank=True, null=True)
    
    def __str__(self):
        return f"Invoice #{self.id} - {self.client.username} - {self.amount}"

class KPIHistory(models.Model):
    """
    Historical snapshot of KPIs for trend analysis.
    """
    date = models.DateField(auto_now_add=True)
    completion_rate = models.FloatField()
    avg_delay_days = models.FloatField()
    avg_phase_duration_days = models.FloatField(default=0.0)
    pending_approvals = models.IntegerField()
    active_projects = models.IntegerField()
    
    class Meta:
        ordering = ['-date']
        
    def __str__(self):
        return f"KPI Snapshot - {self.date}"
