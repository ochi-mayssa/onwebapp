from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class Customer(models.Model):
    """
    Represents a customer in the CRM system.
    Can be an individual or a company.
    Links to the Django User model if they have an account.
    """
    CUSTOMER_TYPE_CHOICES = [
        ('INDIVIDUAL', 'Individual'),
        ('COMPANY', 'Company'),
    ]

    LIFECYCLE_STAGE_CHOICES = [
        ('LEAD', 'Lead'),
        ('QUALIFIED_LEAD', 'Qualified Lead'),
        ('ACTIVE_CLIENT', 'Active Client'),
        ('RETAINED_CLIENT', 'Retained Client'),
        ('CHURNED', 'Churned'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='crm_customer',
        help_text="Link to the registered user account if applicable."
    )
    name = models.CharField(max_length=255, help_text="Full name or Company name")
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=50, blank=True)
    customer_type = models.CharField(max_length=20, choices=CUSTOMER_TYPE_CHOICES, default='INDIVIDUAL')
    lifecycle_stage = models.CharField(max_length=20, choices=LIFECYCLE_STAGE_CHOICES, default='LEAD')
    
    # Company details (if applicable)
    company_name = models.CharField(max_length=255, blank=True, help_text="For individuals representing a company")
    industry = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    
    # Tracking
    source = models.CharField(max_length=100, blank=True, help_text="Where did this customer come from?")
    notes = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_customers',
        limit_choices_to={'is_staff': True}
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Health Intelligence
    current_health_score = models.IntegerField(default=70, help_text="Calculated 0-100 score")
    health_trend = models.CharField(
        max_length=10, 
        choices=[('UP', 'Improving'), ('DOWN', 'Declining'), ('STABLE', 'Stable')],
        default='STABLE'
    )
    last_health_calc = models.DateTimeField(null=True, blank=True)

    # ERP Integration
    erp_site_name = models.CharField(
        max_length=100, 
        blank=True, 
        help_text="ERPNext site name (e.g., 'demo' for demo.erpnext.com)"
    )
    erp_api_key = models.CharField(
        max_length=255, 
        blank=True, 
        help_text="ERPNext API Key"
    )
    erp_api_secret = models.CharField(
        max_length=255, 
        blank=True, 
        help_text="ERPNext API Secret"
    )

    def __str__(self):
        return f"{self.name} ({self.get_lifecycle_stage_display()})"

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Customer Profile"
        verbose_name_plural = "Customer Profiles"


class Interaction(models.Model):
    """
    Records any interaction with the customer (Email, Call, Meeting, etc.)
    """
    INTERACTION_TYPE_CHOICES = [
        ('EMAIL', 'Email'),
        ('CALL', 'Phone Call'),
        ('MEETING', 'Meeting'),
        ('NOTE', 'Internal Note'),
        ('TICKET', 'Support Ticket'),
        ('SYSTEM', 'System Notification'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='interactions')
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    interaction_type = models.CharField(max_length=20, choices=INTERACTION_TYPE_CHOICES, default='NOTE')
    summary = models.CharField(max_length=255)
    details = models.TextField(blank=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_interaction_type_display()} - {self.customer.name} - {self.date.strftime('%Y-%m-%d')}"


class ServiceRequest(models.Model):
    """
    Tracks specific service requests from customers before they become full Projects.
    """
    STATUS_CHOICES = [
        ('NEW', 'New'),
        ('REVIEW', 'Under Review'),
        ('PROPOSAL', 'Proposal Sent'),
        ('ACCEPTED', 'Accepted'),
        ('REJECTED', 'Rejected'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='service_requests')
    service_type = models.CharField(max_length=100, help_text="e.g., Website, RPA, Branding")
    description = models.TextField()
    budget_range = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NEW')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Link to actual project if converted
    converted_project = models.ForeignKey(
        'projects.Project', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='crm_request'
    )

    def __str__(self):
        return f"{self.service_type} for {self.customer.name}"


class CRMWorkflow(models.Model):
    """
    Defines automated workflows for customer lifecycle and health management.
    """
    TRIGGER_CHOICES = [
        ('LIFECYCLE_CHANGE', 'Lifecycle Stage Change'),
        ('HEALTH_SCORE_DROP', 'Health Score Drops Below'),
        ('HEALTH_SCORE_RISE', 'Health Score Rises Above'),
        ('INACTIVITY', 'No Interaction For (Days)'),
        ('INVOICE_OVERDUE', 'Invoice Overdue'),
        ('PROPOSAL_UPDATE', 'Proposal Status Change'),
    ]

    name = models.CharField(max_length=100)
    trigger_type = models.CharField(max_length=30, choices=TRIGGER_CHOICES, default='LIFECYCLE_CHANGE')
    trigger_value = models.CharField(max_length=50, blank=True, help_text="Threshold value (e.g., '50' for score, '14' for days, 'ACTIVE' for stage)")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.get_trigger_type_display()})"

class WorkflowStep(models.Model):
    """
    Steps within a workflow (e.g., Send Email, Create Task).
    """
    ACTION_CHOICES = [
        ('EMAIL', 'Send Email'),
        ('TASK', 'Create Task'),
        ('NOTIFICATION', 'Send Notification'),
        ('CHANGE_STAGE', 'Change Lifecycle Stage'),
        ('ASSIGN_USER', 'Assign/Reassign User'),
        ('CREATE_PROJECT', 'Create Project'),
        ('SCHEDULE_MEETING', 'Schedule Meeting'),
    ]

    workflow = models.ForeignKey(CRMWorkflow, on_delete=models.CASCADE, related_name='steps')
    step_order = models.PositiveIntegerField(default=1)
    action_type = models.CharField(max_length=20, choices=ACTION_CHOICES)
    action_details = models.JSONField(help_text="Config: {'template': '...', 'title': '...', 'stage': '...'}")
    
    class Meta:
        ordering = ['step_order']

    def __str__(self):
        return f"{self.workflow.name} - Step {self.step_order}: {self.get_action_type_display()}"


# Client Tracking Models for ERP Integration

class ClientTracking(models.Model):
    """
    Links users to their ERP instances for tracking
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='client_tracking')
    erp_customer_id = models.CharField(max_length=255, help_text="Customer ID in ERPNext")
    erp_site_name = models.CharField(max_length=255, help_text="ERPNext site name")
    api_key = models.CharField(max_length=255, help_text="Encrypted API key")
    api_secret = models.CharField(max_length=255, help_text="Encrypted API secret")
    last_sync = models.DateTimeField(auto_now=True)
    realtime_enabled = models.BooleanField(default=True, help_text="Enable real-time updates")
    notification_email = models.EmailField(blank=True, help_text="Email for notifications")

    class Meta:
        verbose_name = "Client Tracking"
        verbose_name_plural = "Client Tracking"

    def __str__(self):
        return f"{self.user.username} - {self.erp_site_name}"

    def get_erp_client(self):
        """Get ERPNext client instance"""
        from .erp_sync import ERPNextClient
        return ERPNextClient(self.user)


class OrderSnapshot(models.Model):
    """
    Cached snapshot of ERPNext orders for fast access
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('ON_HOLD', 'On Hold'),
    ]

    client = models.ForeignKey(ClientTracking, on_delete=models.CASCADE, related_name='orders')
    erp_order_id = models.CharField(max_length=255, help_text="Order ID in ERPNext")
    product = models.CharField(max_length=255, help_text="Product or service name")
    qty = models.IntegerField(default=0, help_text="Quantity ordered")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='PENDING')
    progress_percent = models.IntegerField(default=0, help_text="Completion percentage")
    target_date = models.DateField(null=True, blank=True, help_text="Target completion date")
    actual_completion_date = models.DateField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Order Snapshot"
        verbose_name_plural = "Order Snapshots"
        ordering = ['-last_updated']
        unique_together = ['client', 'erp_order_id']

    def __str__(self):
        return f"{self.erp_order_id} - {self.product}"

    @property
    def is_overdue(self):
        """Check if order is overdue"""
        if self.target_date and self.status != 'COMPLETED':
            from django.utils import timezone
            return timezone.now().date() > self.target_date
        return False

    @property
    def days_overdue(self):
        """Calculate days overdue"""
        if self.is_overdue:
            from django.utils import timezone
            return (timezone.now().date() - self.target_date).days
        return 0


class InvoiceSnapshot(models.Model):
    """
    Cached snapshot of ERPNext invoices
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ISSUED', 'Issued'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue'),
        ('CANCELLED', 'Cancelled'),
    ]

    client = models.ForeignKey(ClientTracking, on_delete=models.CASCADE, related_name='invoices')
    erp_invoice_id = models.CharField(max_length=255, help_text="Invoice ID in ERPNext")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='ISSUED')
    issue_date = models.DateField()
    due_date = models.DateField()
    payment_date = models.DateField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Invoice Snapshot"
        verbose_name_plural = "Invoice Snapshots"
        ordering = ['-issue_date']
        unique_together = ['client', 'erp_invoice_id']

    def __str__(self):
        return f"{self.erp_invoice_id} - ${self.amount}"

    @property
    def is_overdue(self):
        """Check if invoice is overdue"""
        if self.status in ['ISSUED', 'OVERDUE']:
            from django.utils import timezone
            return timezone.now().date() > self.due_date
        return False

    @property
    def days_overdue(self):
        """Calculate days overdue"""
        if self.is_overdue:
            from django.utils import timezone
            return (timezone.now().date() - self.due_date).days
        return 0


class StockAllocation(models.Model):
    """
    Tracks allocated resources/stock for clients
    """
    client = models.ForeignKey(ClientTracking, on_delete=models.CASCADE, related_name='stock_allocations')
    item_code = models.CharField(max_length=255, help_text="ERPNext item code")
    item_name = models.CharField(max_length=255, help_text="Item name")
    allocated_qty = models.IntegerField(default=0, help_text="Quantity allocated to client")
    available_qty = models.IntegerField(default=0, help_text="Total available quantity")
    unit_rate = models.DecimalField(max_digits=10, decimal_places=2, help_text="Unit price")
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Stock Allocation"
        verbose_name_plural = "Stock Allocations"
        unique_together = ['client', 'item_code']

    def __str__(self):
        return f"{self.item_name} - {self.allocated_qty} allocated"

    @property
    def utilization_percent(self):
        """Calculate utilization percentage"""
        if self.available_qty > 0:
            return int((self.allocated_qty / self.available_qty) * 100)
        return 0


class ClientNotification(models.Model):
    """
    Notification preferences and history for clients
    """
    NOTIFICATION_TYPES = [
        ('ORDER_STATUS', 'Order Status Changes'),
        ('INVOICE_DUE', 'Invoice Due Reminders'),
        ('PAYMENT_RECEIVED', 'Payment Confirmations'),
        ('DELIVERY_UPDATE', 'Delivery Updates'),
        ('SYSTEM_MAINTENANCE', 'System Maintenance'),
    ]

    client = models.ForeignKey(ClientTracking, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=False)
    in_app_enabled = models.BooleanField(default=True)
    frequency = models.CharField(max_length=50, default='immediate',
                               choices=[('immediate', 'Immediate'), ('daily', 'Daily'), ('weekly', 'Weekly')])

    class Meta:
        verbose_name = "Client Notification"
        verbose_name_plural = "Client Notifications"
        unique_together = ['client', 'notification_type']

    def __str__(self):
        return f"{self.client.user.username} - {self.notification_type}"


class NotificationLog(models.Model):
    """
    Log of all notifications sent to clients
    """
    client = models.ForeignKey(ClientTracking, on_delete=models.CASCADE, related_name='notification_logs')
    notification_type = models.CharField(max_length=50, choices=ClientNotification.NOTIFICATION_TYPES)
    message = models.TextField()
    sent_via = models.CharField(max_length=50, choices=[('email', 'Email'), ('sms', 'SMS'), ('in_app', 'In-App')])
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, default='sent',
                            choices=[('sent', 'Sent'), ('delivered', 'Delivered'), ('failed', 'Failed')])

    class Meta:
        verbose_name = "Notification Log"
        verbose_name_plural = "Notification Logs"
        ordering = ['-sent_at']

    def __str__(self):
        return f"{self.client.user.username} - {self.notification_type} - {self.sent_at}"
