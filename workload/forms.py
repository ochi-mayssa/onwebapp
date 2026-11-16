"""Forms for workload management, styled for the OnWebApp design system."""
from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import (
    ResourceCapacity,
    WorkItem,
    WorkItemAttachment,
    WorkloadPolicy,
    WorkloadResource,
    WorkloadSkill,
    WorkloadTeam,
)
from .permissions import (
    assignable_resources,
    assignable_users,
    is_global_manager,
    is_manager,
    scope_teams,
)

User = get_user_model()


def _scoped_users(actor):
    """Active users the actor may pick as an assignee/team member."""
    if actor is None:
        return User.objects.filter(is_active=True).order_by(
            'first_name', 'last_name', 'username',
        )
    return assignable_users(actor)


def _scoped_active_teams(actor):
    teams = WorkloadTeam.objects.filter(is_active=True)
    if actor is None:
        return teams
    return scope_teams(teams, actor)


def _scoped_resources(actor):
    """Resources an actor may assign work to."""
    if actor is None:
        return WorkloadResource.objects.filter(is_active=True)
    return assignable_resources(actor)


def _scoped_customers(actor):
    """CRM customers the actor may link to workload items.

    Workspace managers only see customers they own or that already belong to
    work in their workspace; global operators see every customer.
    """
    from crm.models import Customer

    queryset = Customer.objects.all()
    if actor is None or is_global_manager(actor):
        return queryset
    if is_manager(actor):
        return queryset.filter(
            Q(user=actor)
            | Q(workload_items__tenant=actor)
            | Q(service_requests__workload_item__tenant=actor),
        ).distinct()
    return queryset.filter(user=actor)


def _scoped_projects(actor):
    """Projects the actor may link to workload items."""
    from projects.models import Project

    queryset = Project.objects.all()
    if actor is None or is_global_manager(actor):
        return queryset
    if is_manager(actor):
        return queryset.filter(
            Q(client=actor) | Q(workload_items__tenant=actor),
        ).distinct()
    return queryset.filter(client=actor)


class StyledModelForm(forms.ModelForm):
    """Apply Bootstrap classes without changing the platform's base template."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', 'form-check-input')
            elif isinstance(widget, forms.SelectMultiple):
                widget.attrs.setdefault('class', 'form-select')
            elif isinstance(widget, (forms.Select, forms.NullBooleanSelect)):
                widget.attrs.setdefault('class', 'form-select')
            elif isinstance(widget, forms.FileInput):
                widget.attrs.setdefault('class', 'form-control')
            else:
                widget.attrs.setdefault('class', 'form-control')
            if isinstance(widget, forms.DateInput):
                widget.input_type = 'date'
            if field.required:
                widget.attrs.setdefault('required', 'required')


class WorkItemForm(StyledModelForm):
    required_skills = forms.ModelMultipleChoiceField(
        queryset=WorkloadSkill.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'size': 6}),
        help_text='Hold Ctrl/Cmd to select more than one skill.',
    )

    class Meta:
        model = WorkItem
        fields = [
            'title',
            'description',
            'category',
            'priority',
            'status',
            'assignee',
            'team',
            'client',
            'project',
            'automation_workflow',
            'source_module',
            'external_reference',
            'estimated_hours',
            'actual_hours',
            'start_date',
            'due_date',
            'required_skills',
            'is_client_visible',
            'automation_eligible',
            'blocked_reason',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'blocked_reason': forms.TextInput(),
        }
        help_texts = {
            'estimated_hours': 'Used for capacity calculations until the work is complete.',
            'actual_hours': 'Hours already spent. Update while reporting progress.',
            'automation_eligible': 'Mark repetitive work that could be automated.',
        }

    def __init__(self, *args, **kwargs):
        actor = kwargs.pop('actor', None)
        super().__init__(*args, **kwargs)
        self.fields['assignee'].queryset = _scoped_users(actor)
        self.fields['assignee'].required = False
        self.fields['team'].queryset = _scoped_active_teams(actor)
        self.fields['team'].required = False
        self.fields['client'].queryset = _scoped_customers(actor)
        self.fields['client'].required = False
        self.fields['project'].queryset = _scoped_projects(actor)
        self.fields['project'].required = False
        self.fields['automation_workflow'].required = False
        self.fields['source_module'].required = False
        self.fields['estimated_hours'].widget.attrs.update({'min': '0', 'step': '0.25'})
        self.fields['actual_hours'].widget.attrs.update({'min': '0', 'step': '0.25'})

    def clean(self):
        cleaned = super().clean()
        team = cleaned.get('team')
        assignee = cleaned.get('assignee')
        if team is not None and assignee is not None and team.tenant_id is not None:
            # Global/platform teams can host anyone; tenant teams only host
            # members of their own workspace.
            if not team.members.filter(pk=assignee.pk).exists():
                raise forms.ValidationError(
                    'The selected employee is not a member of this workspace team.',
                )
        return cleaned


class WorkItemStatusForm(forms.Form):
    status = forms.ChoiceField(choices=WorkItem.STATUS_CHOICES)
    actual_hours = forms.DecimalField(
        required=False, min_value=0, max_digits=7, decimal_places=2,
        widget=forms.NumberInput(attrs={'min': '0', 'step': '0.25'}),
        help_text='Optional progress update in hours.',
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
        help_text='Optional note for the audit trail.',
    )
    blocked_reason = forms.CharField(
        required=False,
        max_length=255,
        help_text='Required when moving work to Blocked.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')
        self.fields['status'].widget.attrs['class'] = 'form-select'

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('status') == WorkItem.STATUS_BLOCKED and not (
            cleaned.get('blocked_reason') or cleaned.get('note')
        ):
            raise forms.ValidationError('Explain why the work is blocked.')
        return cleaned


class AssignWorkForm(forms.Form):
    assignee = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('first_name', 'username'),
        required=False,
    )
    team = forms.ModelChoiceField(
        queryset=WorkloadTeam.objects.filter(is_active=True), required=False,
    )
    resource = forms.ModelChoiceField(
        queryset=WorkloadResource.objects.filter(is_active=True).order_by('name'),
        required=False,
        help_text='Use this for system processes or pre-configured team resources.',
    )
    allocated_hours = forms.DecimalField(
        required=False, min_value=0, max_digits=7, decimal_places=2,
        widget=forms.NumberInput(attrs={'min': '0', 'step': '0.25'}),
        help_text='Leave empty to reserve the item’s remaining estimate.',
    )
    role = forms.CharField(required=False, max_length=100)
    notes = forms.CharField(
        required=False, max_length=255,
        widget=forms.TextInput(),
    )

    def __init__(self, *args, **kwargs):
        actor = kwargs.pop('actor', None)
        super().__init__(*args, **kwargs)
        self.fields['assignee'].queryset = _scoped_users(actor)
        self.fields['team'].queryset = _scoped_active_teams(actor)
        self.fields['resource'].queryset = _scoped_resources(actor).order_by('name')
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault('class', 'form-select')
            else:
                field.widget.attrs.setdefault('class', 'form-control')

    def clean(self):
        cleaned = super().clean()
        targets = [key for key in ('assignee', 'team', 'resource') if cleaned.get(key)]
        if len(targets) != 1:
            raise forms.ValidationError(
                'Choose exactly one assignment target: an employee, a team, or a resource.',
            )
        return cleaned


class BulkActionForm(forms.Form):
    ACTION_STATUS = 'status'
    ACTION_ASSIGN = 'assign'
    ACTION_CANCEL = 'cancel'
    ACTION_CHOICES = [
        (ACTION_STATUS, 'Update status'),
        (ACTION_ASSIGN, 'Assign to employee or team'),
        (ACTION_CANCEL, 'Cancel work'),
    ]

    action = forms.ChoiceField(choices=ACTION_CHOICES)
    status = forms.ChoiceField(choices=WorkItem.STATUS_CHOICES, required=False)
    assignee = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True), required=False,
    )
    team = forms.ModelChoiceField(
        queryset=WorkloadTeam.objects.filter(is_active=True), required=False,
    )
    note = forms.CharField(required=False, max_length=255)

    def __init__(self, *args, **kwargs):
        actor = kwargs.pop('actor', None)
        super().__init__(*args, **kwargs)
        self.fields['assignee'].queryset = _scoped_users(actor)
        self.fields['team'].queryset = _scoped_active_teams(actor)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault('class', 'form-select')
            else:
                field.widget.attrs.setdefault('class', 'form-control')

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get('action')
        if action == self.ACTION_STATUS and not cleaned.get('status'):
            raise forms.ValidationError('Choose the new status.')
        if action == self.ACTION_ASSIGN and not (
            cleaned.get('assignee') or cleaned.get('team')
        ):
            raise forms.ValidationError('Choose an employee or a team.')
        if action == self.ACTION_ASSIGN and cleaned.get('assignee') and cleaned.get('team'):
            raise forms.ValidationError('Choose either an employee or a team, not both.')
        return cleaned


class WorkloadResourceForm(StyledModelForm):
    class Meta:
        model = WorkloadResource
        fields = [
            'kind', 'user', 'team', 'system_label', 'name',
            'skills', 'availability_status', 'is_active', 'notes',
        ]
        widgets = {'notes': forms.Textarea(attrs={'rows': 3})}
        help_texts = {
            'name': 'Optional display label. Defaults to the user, team, or system label.',
            'system_label': 'Required for system/process resources.',
        }

    def __init__(self, *args, **kwargs):
        actor = kwargs.pop('actor', None)
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = _scoped_users(actor)
        self.fields['user'].required = False
        self.fields['team'].queryset = _scoped_active_teams(actor)
        self.fields['team'].required = False
        self.fields['skills'].queryset = WorkloadSkill.objects.all()
        self.fields['skills'].required = False
        self.fields['name'].required = False


class ResourceCapacityForm(StyledModelForm):
    class Meta:
        model = ResourceCapacity
        fields = ['weekly_hours', 'availability_percent', 'time_off_hours', 'notes']
        help_texts = {
            'weekly_hours': 'Contracted hours in a normal week.',
            'availability_percent': 'Percentage of the week actually available for work.',
            'time_off_hours': 'Hours unavailable this planning week.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('weekly_hours', 'availability_percent', 'time_off_hours'):
            self.fields[name].widget.attrs.update({'min': '0', 'step': '0.5'})
        self.fields['availability_percent'].widget.attrs.update({'max': '100'})


class WorkloadTeamForm(StyledModelForm):
    class Meta:
        model = WorkloadTeam
        fields = ['name', 'code', 'department', 'description', 'lead', 'members', 'is_active']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        actor = kwargs.pop('actor', None)
        super().__init__(*args, **kwargs)
        self.fields['lead'].queryset = _scoped_users(actor)
        self.fields['lead'].required = False
        self.fields['members'].queryset = _scoped_users(actor)
        self.fields['members'].required = False


class WorkloadPolicyForm(StyledModelForm):
    weight_skills = forms.DecimalField(
        min_value=0, max_value=1, decimal_places=2, max_digits=3,
        initial=0.40, label='Skill match weight',
    )
    weight_capacity = forms.DecimalField(
        min_value=0, max_value=1, decimal_places=2, max_digits=3,
        initial=0.30, label='Available capacity weight',
    )
    weight_team = forms.DecimalField(
        min_value=0, max_value=1, decimal_places=2, max_digits=3,
        initial=0.15, label='Team responsibility weight',
    )
    weight_deadline = forms.DecimalField(
        min_value=0, max_value=1, decimal_places=2, max_digits=3,
        initial=0.15, label='Deadline urgency weight',
    )

    class Meta:
        model = WorkloadPolicy
        fields = [
            'name', 'is_default',
            'available_below', 'balanced_max', 'high_max',
            'deadline_warning_days', 'team_capacity_warning_percent',
            'bottleneck_threshold', 'default_weekly_hours',
            'auto_assign_enabled', 'auto_reassign_critical',
            'require_approval_for_critical',
        ]
        help_texts = {
            'available_below': 'Default 60: below this percentage is Available.',
            'balanced_max': 'Default 85: 60–85% is Balanced.',
            'high_max': 'Default 100: 86–100% is High; above 100% is Overloaded.',
            'auto_assign_enabled': 'Allow policies to suggest/assign automatically.',
            'auto_reassign_critical': 'Off by default to protect critical work.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        weights = getattr(self.instance, 'weights', None) or {}
        for key in ('skills', 'capacity', 'team', 'deadline'):
            field_name = f'weight_{key}'
            if self.instance and self.instance.pk and self.instance.weights:
                self.fields[field_name].initial = self.instance.weights.get(key, 0.0)
        for name in (
            'available_below', 'balanced_max', 'high_max',
            'team_capacity_warning_percent', 'default_weekly_hours',
        ):
            self.fields[name].widget.attrs.update({'min': '0', 'step': '0.5'})

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.weights = {
            'skills': float(self.cleaned_data['weight_skills']),
            'capacity': float(self.cleaned_data['weight_capacity']),
            'team': float(self.cleaned_data['weight_team']),
            'deadline': float(self.cleaned_data['weight_deadline']),
        }
        if commit:
            instance.save()
        return instance


class WorkItemAttachmentForm(StyledModelForm):
    class Meta:
        model = WorkItemAttachment
        fields = ['file']

    def clean_file(self):
        upload = self.cleaned_data['file']
        if upload and upload.size > 10 * 1024 * 1024:
            raise forms.ValidationError('Attachments must be 10 MB or smaller.')
        return upload
