"""Database models for the OnWebApp workload management module.

The module is deliberately additive: it reuses ``auth.User``, CRM customers and
service requests, projects and project tasks, and automation workflows.  Nothing
in this file duplicates an existing account or project record.

Tenant model
------------
OnWebApp currently scopes customer data by user account (there is no separate
``Organization`` table).  ``tenant`` therefore points at the workspace owner:

* ``tenant`` is set for client-owned work so a client can only ever read its own
  records.
* Staff (administrators/managers) are platform operators and deliberately see
  every record; the backend helpers in ``workload.permissions`` enforce this.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


DECIMAL_ZERO = Decimal('0')


def default_policy_weights():
    return {
        'skills': 0.40,
        'capacity': 0.30,
        'team': 0.15,
        'deadline': 0.15,
    }


class WorkloadTeam(models.Model):
    """A team/department used for workload ownership and reporting."""

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40, blank=True)
    department = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    lead = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workload_teams_led',
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='workload_teams',
    )
    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='workload_teams_owned',
        help_text='Workspace owner for client-scoped teams. Staff teams are global.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'name'],
                name='uniq_workload_team_name_per_tenant',
            ),
        ]
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['department']),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('workload:team_list')

    @property
    def member_count(self):
        return self.members.count()


class WorkloadSkill(models.Model):
    """A capability that work can require and a resource can provide."""

    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class WorkloadResource(models.Model):
    """A capacity-owning resource: a person, a team, or a system process."""

    KIND_PERSON = 'PERSON'
    KIND_TEAM = 'TEAM'
    KIND_SYSTEM = 'SYSTEM'
    KIND_CHOICES = [
        (KIND_PERSON, _('Employee')),
        (KIND_TEAM, _('Team')),
        (KIND_SYSTEM, _('System / process')),
    ]

    AVAILABILITY_AVAILABLE = 'AVAILABLE'
    AVAILABILITY_PARTIAL = 'PARTIAL'
    AVAILABILITY_UNAVAILABLE = 'UNAVAILABLE'
    AVAILABILITY_ON_LEAVE = 'ON_LEAVE'
    AVAILABILITY_CHOICES = [
        (AVAILABILITY_AVAILABLE, _('Available')),
        (AVAILABILITY_PARTIAL, _('Partially available')),
        (AVAILABILITY_UNAVAILABLE, _('Unavailable')),
        (AVAILABILITY_ON_LEAVE, _('On leave')),
    ]

    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_PERSON)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='workload_resource',
    )
    team = models.OneToOneField(
        WorkloadTeam,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='resource',
    )
    system_label = models.CharField(max_length=150, blank=True)
    skills = models.ManyToManyField(
        WorkloadSkill,
        blank=True,
        related_name='resources',
    )
    availability_status = models.CharField(
        max_length=20,
        choices=AVAILABILITY_CHOICES,
        default=AVAILABILITY_AVAILABLE,
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='workload_resources',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['kind', 'is_active']),
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['availability_status']),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(kind='PERSON', user__isnull=False, team__isnull=True)
                    | Q(kind='TEAM', team__isnull=False, user__isnull=True)
                    | Q(kind='SYSTEM', user__isnull=True, team__isnull=True)
                ),
                name='workload_resource_has_valid_target',
            ),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('workload:resource_list')

    def clean(self):
        super().clean()
        if self.kind == self.KIND_PERSON and not self.user_id:
            raise ValidationError({'user': _('An employee resource requires a user account.')})
        if self.kind == self.KIND_TEAM and not self.team_id:
            raise ValidationError({'team': _('A team resource requires a team.')})
        if self.kind == self.KIND_SYSTEM and not self.system_label:
            raise ValidationError({'system_label': _('A system resource requires a label.')})
        if self.kind != self.KIND_PERSON and self.user_id:
            raise ValidationError({'user': _('Only employee resources can link a user.')})
        if self.kind != self.KIND_TEAM and self.team_id:
            raise ValidationError({'team': _('Only team resources can link a team.')})

    @property
    def is_person(self):
        return self.kind == self.KIND_PERSON

    @property
    def is_team(self):
        return self.kind == self.KIND_TEAM

    @property
    def display_owner(self):
        if self.user_id:
            return self.user.get_full_name() or self.user.get_username()
        if self.team_id:
            return self.team.name
        return self.system_label or self.name

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = self.display_owner
        super().save(*args, **kwargs)


class ResourceCapacity(models.Model):
    """Weekly availability for a workload resource.

    ``available_hours`` is derived: weekly hours scaled by availability percent,
    minus planned time off.  Missing capacity records fall back to the policy's
    default weekly hours and are reported as an assumed capacity, never silently
    treated as an overload.
    """

    resource = models.OneToOneField(
        WorkloadResource,
        on_delete=models.CASCADE,
        related_name='capacity',
    )
    weekly_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('40.00'),
        validators=[MinValueValidator(DECIMAL_ZERO)],
    )
    availability_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('100.00'),
        validators=[MinValueValidator(DECIMAL_ZERO)],
        help_text='Percentage of the working week the resource is available.',
    )
    time_off_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=DECIMAL_ZERO,
        validators=[MinValueValidator(DECIMAL_ZERO)],
        help_text='Hours unavailable in the current planning week (leave, meetings).',
    )
    notes = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Resource capacities'

    def __str__(self):
        return f'{self.resource.name}: {self.available_hours}h available'

    def clean(self):
        super().clean()
        if self.availability_percent is not None and not (
            DECIMAL_ZERO <= self.availability_percent <= Decimal('100')
        ):
            raise ValidationError(
                {'availability_percent': _('Availability must be between 0 and 100.')},
            )

    @property
    def available_hours(self):
        weekly = self.weekly_hours or DECIMAL_ZERO
        percent = self.availability_percent
        if percent is None:
            percent = Decimal('100')
        scaled = weekly * percent / Decimal('100')
        available = scaled - (self.time_off_hours or DECIMAL_ZERO)
        return max(DECIMAL_ZERO, available)


class WorkloadPolicy(models.Model):
    """Configurable thresholds, defaults and assignment weights."""

    name = models.CharField(max_length=120, default='Default workload policy')
    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='workload_policies',
        help_text='Leave empty for the organisation-wide default policy.',
    )
    is_default = models.BooleanField(default=True)

    available_below = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('60.00'),
        help_text='Utilisation below this value is classified as available.',
    )
    balanced_max = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('85.00'),
        help_text='Upper bound of the balanced band.',
    )
    high_max = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('100.00'),
        help_text='Utilisation above this value is overloaded.',
    )
    deadline_warning_days = models.PositiveIntegerField(default=3)
    team_capacity_warning_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('90.00'),
    )
    bottleneck_threshold = models.PositiveIntegerField(
        default=2,
        help_text='Number of blocked/overdue items that makes a team a bottleneck.',
    )
    default_weekly_hours = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('40.00'),
    )
    auto_assign_enabled = models.BooleanField(default=False)
    auto_reassign_critical = models.BooleanField(
        default=False,
        help_text='Allow automatic policies to move critical work between employees.',
    )
    require_approval_for_critical = models.BooleanField(default=True)
    weights = models.JSONField(default=default_policy_weights, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', 'name']
        indexes = [models.Index(fields=['tenant', 'is_default'])]
        verbose_name_plural = 'Workload policies'

    def __str__(self):
        return f'{self.name}{" (default)" if self.is_default else ""}'

    def clean(self):
        super().clean()
        if not (self.available_below < self.balanced_max <= self.high_max):
            raise ValidationError(
                _('Thresholds must satisfy: available below < balanced max <= high max.'),
            )
        for key in ('skills', 'capacity', 'team', 'deadline'):
            value = (self.weights or {}).get(key)
            if value is not None and (value < 0 or value > 1):
                raise ValidationError(
                    {'weights': _('Assignment weights must be between 0 and 1.')},
                )

    @classmethod
    def get_for(cls, tenant=None):
        """Return the effective policy, creating the global default on demand."""
        policy = None
        if tenant is not None:
            policy = cls.objects.filter(tenant=tenant, is_default=True).first()
        if policy is None:
            policy = cls.objects.filter(tenant__isnull=True, is_default=True).first()
        if policy is None:
            policy, _created = cls.objects.get_or_create(
                tenant=None,
                is_default=True,
                defaults={'name': 'Default workload policy'},
            )
        return policy


class WorkItem(models.Model):
    """An individual unit of human, business or system work."""

    CATEGORY_HUMAN = 'HUMAN'
    CATEGORY_BUSINESS = 'BUSINESS'
    CATEGORY_APPLICATION = 'APPLICATION'
    CATEGORY_AUTOMATED = 'AUTOMATED'
    CATEGORY_INFRASTRUCTURE = 'INFRASTRUCTURE'
    CATEGORY_CHOICES = [
        (CATEGORY_HUMAN, _('Human workload')),
        (CATEGORY_BUSINESS, _('Business workload')),
        (CATEGORY_APPLICATION, _('Application workload')),
        (CATEGORY_AUTOMATED, _('Automated workload')),
        (CATEGORY_INFRASTRUCTURE, _('Infrastructure workload')),
    ]

    PRIORITY_LOW = 'LOW'
    PRIORITY_MEDIUM = 'MEDIUM'
    PRIORITY_HIGH = 'HIGH'
    PRIORITY_CRITICAL = 'CRITICAL'
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, _('Low')),
        (PRIORITY_MEDIUM, _('Medium')),
        (PRIORITY_HIGH, _('High')),
        (PRIORITY_CRITICAL, _('Critical')),
    ]

    STATUS_NEW = 'NEW'
    STATUS_PENDING = 'PENDING'
    STATUS_ASSIGNED = 'ASSIGNED'
    STATUS_IN_PROGRESS = 'IN_PROGRESS'
    STATUS_BLOCKED = 'BLOCKED'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_CHOICES = [
        (STATUS_NEW, _('New')),
        (STATUS_PENDING, _('Pending')),
        (STATUS_ASSIGNED, _('Assigned')),
        (STATUS_IN_PROGRESS, _('In progress')),
        (STATUS_BLOCKED, _('Blocked')),
        (STATUS_COMPLETED, _('Completed')),
        (STATUS_CANCELLED, _('Cancelled')),
    ]
    OPEN_STATUSES = [
        STATUS_NEW, STATUS_PENDING, STATUS_ASSIGNED, STATUS_IN_PROGRESS, STATUS_BLOCKED,
    ]
    CLOSED_STATUSES = [STATUS_COMPLETED, STATUS_CANCELLED]

    SOURCE_MANUAL = 'MANUAL'
    SOURCE_CRM = 'CRM'
    SOURCE_PROJECT = 'PROJECT'
    SOURCE_OPERATIONS = 'OPERATIONS'
    SOURCE_ERP = 'ERP'
    SOURCE_AUTOMATION = 'AUTOMATION'
    SOURCE_API = 'API'
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, _('Manual')),
        (SOURCE_CRM, _('CRM')),
        (SOURCE_PROJECT, _('Project management')),
        (SOURCE_OPERATIONS, _('Operations / ERP')),
        (SOURCE_ERP, _('ERP')),
        (SOURCE_AUTOMATION, _('Automation / RPA')),
        (SOURCE_API, _('API')),
    ]

    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='workload_items',
        help_text='Workspace owner. Client tenants can only see their own visible work.',
    )
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_HUMAN,
    )
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM,
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW,
    )

    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workload_work_items',
    )
    team = models.ForeignKey(
        WorkloadTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='work_items',
    )

    client = models.ForeignKey(
        'crm.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workload_items',
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workload_items',
    )
    project_task = models.OneToOneField(
        'projects.PhaseTask',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workload_item',
        help_text='Unique link prevents a project task being duplicated in workload.',
    )
    crm_request = models.OneToOneField(
        'crm.ServiceRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workload_item',
    )
    automation_workflow = models.ForeignKey(
        'automation.AutomationWorkflow',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workload_items',
    )

    source_module = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MANUAL,
    )
    external_reference = models.CharField(
        max_length=180, blank=True,
        help_text='ERP, API or automation identifier for traceability.',
    )

    estimated_hours = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=DECIMAL_ZERO,
        validators=[MinValueValidator(DECIMAL_ZERO)],
    )
    actual_hours = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=DECIMAL_ZERO,
        validators=[MinValueValidator(DECIMAL_ZERO)],
    )
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    required_skills = models.ManyToManyField(
        WorkloadSkill,
        blank=True,
        related_name='work_items',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_workload_items',
    )
    is_client_visible = models.BooleanField(
        default=False,
        help_text='Explicitly expose this item to the linked client.',
    )
    automation_eligible = models.BooleanField(
        default=False,
        help_text='Repetitive work that is a candidate for automation.',
    )
    blocked_reason = models.CharField(max_length=255, blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', 'due_date', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'priority']),
            models.Index(fields=['assignee', 'status']),
            models.Index(fields=['team', 'status']),
            models.Index(fields=['status', 'due_date']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['source_module']),
            models.Index(fields=['project', 'status']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('workload:work_item_detail', args=[self.pk])

    def clean(self):
        super().clean()
        if self.start_date and self.due_date and self.due_date < self.start_date:
            raise ValidationError(
                {'due_date': _('The due date cannot be earlier than the start date.')},
            )
        if self.estimated_hours is not None and self.estimated_hours < 0:
            raise ValidationError({'estimated_hours': _('Estimated hours cannot be negative.')})
        if self.actual_hours is not None and self.actual_hours < 0:
            raise ValidationError({'actual_hours': _('Actual hours cannot be negative.')})

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_COMPLETED and self.completed_at is None:
            self.completed_at = timezone.now()
        elif self.status != self.STATUS_COMPLETED:
            self.completed_at = None
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def is_overdue(self):
        return bool(
            self.is_open
            and self.due_date
            and self.due_date < timezone.localdate()
        )

    @property
    def is_unassigned(self):
        return self.is_open and self.assignee_id is None and self.team_id is None

    @property
    def remaining_hours(self):
        return max(DECIMAL_ZERO, (self.estimated_hours or DECIMAL_ZERO) - (self.actual_hours or DECIMAL_ZERO))

    @property
    def completion_hours(self):
        if not self.completed_at:
            return None
        return (self.completed_at - self.created_at).total_seconds() / 3600

    @property
    def is_automated(self):
        return bool(self.automation_workflow_id or self.category == self.CATEGORY_AUTOMATED)


class WorkAssignment(models.Model):
    """Connects a work item to a capacity-owning resource."""

    STATUS_RECOMMENDED = 'RECOMMENDED'
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_CHOICES = [
        (STATUS_RECOMMENDED, _('Recommended')),
        (STATUS_ACTIVE, _('Active')),
        (STATUS_COMPLETED, _('Completed')),
        (STATUS_REJECTED, _('Rejected')),
        (STATUS_CANCELLED, _('Cancelled')),
    ]

    work_item = models.ForeignKey(
        WorkItem, on_delete=models.CASCADE, related_name='assignments',
    )
    resource = models.ForeignKey(
        WorkloadResource, on_delete=models.CASCADE, related_name='assignments',
    )
    role = models.CharField(max_length=100, blank=True)
    allocated_hours = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=DECIMAL_ZERO,
        validators=[MinValueValidator(DECIMAL_ZERO)],
        help_text='Hours reserved on the resource. Empty means use the item estimate.',
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE,
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workload_assignments_made',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workload_assignments_approved',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-assigned_at']
        indexes = [
            models.Index(fields=['resource', 'status']),
            models.Index(fields=['work_item', 'status']),
            models.Index(fields=['status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['work_item', 'resource'],
                condition=Q(status='ACTIVE'),
                name='uniq_active_assignment_per_resource',
            ),
            models.UniqueConstraint(
                fields=['work_item'],
                condition=Q(status='ACTIVE'),
                name='uniq_active_assignment_per_work_item',
            ),
        ]

    def __str__(self):
        return f'{self.work_item.title} -> {self.resource.name}'

    @property
    def effective_hours(self):
        if self.allocated_hours and self.allocated_hours > 0:
            return self.allocated_hours
        return self.work_item.estimated_hours or DECIMAL_ZERO


class WorkloadAlert(models.Model):
    """Persisted operational alert with deduplication for safe re-scans."""

    TYPE_OVERLOAD = 'OVERLOAD'
    TYPE_UNDERUTILIZED = 'UNDERUTILIZED'
    TYPE_OVERDUE = 'OVERDUE'
    TYPE_BLOCKED = 'BLOCKED'
    TYPE_DEADLINE = 'DEADLINE'
    TYPE_UNASSIGNED = 'UNASSIGNED'
    TYPE_TEAM_CAPACITY = 'TEAM_CAPACITY'
    TYPE_BOTTLENECK = 'BOTTLENECK'
    TYPE_CHOICES = [
        (TYPE_OVERLOAD, _('Overloaded employee')),
        (TYPE_UNDERUTILIZED, _('Underutilized resource')),
        (TYPE_OVERDUE, _('Overdue work')),
        (TYPE_BLOCKED, _('Blocked work')),
        (TYPE_DEADLINE, _('Approaching deadline')),
        (TYPE_UNASSIGNED, _('Unassigned work')),
        (TYPE_TEAM_CAPACITY, _('Team capacity issue')),
        (TYPE_BOTTLENECK, _('Repeated bottleneck')),
    ]

    SEVERITY_LOW = 'LOW'
    SEVERITY_MEDIUM = 'MEDIUM'
    SEVERITY_HIGH = 'HIGH'
    SEVERITY_CRITICAL = 'CRITICAL'
    SEVERITY_CHOICES = [
        (SEVERITY_LOW, _('Low')),
        (SEVERITY_MEDIUM, _('Medium')),
        (SEVERITY_HIGH, _('High')),
        (SEVERITY_CRITICAL, _('Critical')),
    ]

    STATUS_OPEN = 'OPEN'
    STATUS_ACKNOWLEDGED = 'ACKNOWLEDGED'
    STATUS_RESOLVED = 'RESOLVED'
    STATUS_CHOICES = [
        (STATUS_OPEN, _('Open')),
        (STATUS_ACKNOWLEDGED, _('Acknowledged')),
        (STATUS_RESOLVED, _('Resolved')),
    ]

    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='workload_alerts',
    )
    alert_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    severity = models.CharField(
        max_length=10, choices=SEVERITY_CHOICES, default=SEVERITY_MEDIUM,
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN,
    )
    work_item = models.ForeignKey(
        WorkItem, on_delete=models.CASCADE, null=True, blank=True,
        related_name='alerts',
    )
    resource = models.ForeignKey(
        WorkloadResource, on_delete=models.CASCADE, null=True, blank=True,
        related_name='alerts',
    )
    team = models.ForeignKey(
        WorkloadTeam, on_delete=models.CASCADE, null=True, blank=True,
        related_name='alerts',
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_workload_alerts',
    )
    message = models.CharField(max_length=255)
    detail = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    dedupe_key = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acknowledged_workload_alerts',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'severity']),
            models.Index(fields=['tenant', 'alert_type', 'status']),
            models.Index(fields=['recipient', 'status']),
        ]

    def __str__(self):
        return f'{self.get_alert_type_display()}: {self.message}'


class WorkloadHistory(models.Model):
    """Append-only audit trail for work items and assignments."""

    ACTION_CREATED = 'CREATED'
    ACTION_UPDATED = 'UPDATED'
    ACTION_ASSIGNED = 'ASSIGNED'
    ACTION_REASSIGNED = 'REASSIGNED'
    ACTION_STATUS_CHANGED = 'STATUS_CHANGED'
    ACTION_COMMENTED = 'COMMENTED'
    ACTION_ALERT = 'ALERT'
    ACTION_CHOICES = [
        (ACTION_CREATED, _('Created')),
        (ACTION_UPDATED, _('Updated')),
        (ACTION_ASSIGNED, _('Assigned')),
        (ACTION_REASSIGNED, _('Reassigned')),
        (ACTION_STATUS_CHANGED, _('Status changed')),
        (ACTION_COMMENTED, _('Commented')),
        (ACTION_ALERT, _('Alert raised')),
    ]

    work_item = models.ForeignKey(
        WorkItem, on_delete=models.CASCADE, related_name='history',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workload_history',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    field_name = models.CharField(max_length=80, blank=True)
    old_value = models.CharField(max_length=255, blank=True)
    new_value = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['work_item', '-created_at']),
            models.Index(fields=['actor']),
        ]

    def __str__(self):
        return f'{self.work_item_id}: {self.get_action_display()}'


class WorkloadMetric(models.Model):
    """Point-in-time snapshot used for trend analytics."""

    SCOPE_ORG = 'ORG'
    SCOPE_TEAM = 'TEAM'
    SCOPE_RESOURCE = 'RESOURCE'
    SCOPE_CHOICES = [
        (SCOPE_ORG, _('Organisation')),
        (SCOPE_TEAM, _('Team')),
        (SCOPE_RESOURCE, _('Resource')),
    ]

    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='workload_metrics',
    )
    metric_date = models.DateField(default=timezone.localdate)
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, default=SCOPE_ORG)
    team = models.ForeignKey(
        WorkloadTeam, on_delete=models.CASCADE, null=True, blank=True,
        related_name='metrics',
    )
    resource = models.ForeignKey(
        WorkloadResource, on_delete=models.CASCADE, null=True, blank=True,
        related_name='metrics',
    )
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-metric_date', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'scope', 'metric_date']),
            models.Index(fields=['resource', 'metric_date']),
            models.Index(fields=['team', 'metric_date']),
        ]
        verbose_name_plural = 'Workload metrics'

    def __str__(self):
        return f'{self.get_scope_display()} metrics for {self.metric_date}'


class WorkItemAttachment(models.Model):
    """File attached to a work item, served through an access-controlled view."""

    work_item = models.ForeignKey(
        WorkItem, on_delete=models.CASCADE, related_name='attachments',
    )
    file = models.FileField(upload_to='workload/attachments/%Y/%m/')
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workload_attachments',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.original_name or self.file.name

    def save(self, *args, **kwargs):
        if not self.original_name and self.file:
            self.original_name = self.file.name.rsplit('/', 1)[-1]
        super().save(*args, **kwargs)
