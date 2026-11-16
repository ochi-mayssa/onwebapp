"""REST API for the workload management module.

The API mirrors the web permissions: administrators/managers may manage every
record, employees read the work assigned to them, and clients only read
explicitly exposed work that belongs to them.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    ResourceCapacity,
    WorkAssignment,
    WorkItem,
    WorkloadAlert,
    WorkloadPolicy,
    WorkloadResource,
    WorkloadSkill,
    WorkloadTeam,
)
from .permissions import (
    assignable_resources,
    assignable_users,
    can_edit_work_item,
    get_role,
    is_admin,
    is_global_manager,
    is_manager,
    scope_alerts,
    scope_policies,
    scope_resources,
    scope_teams,
    scope_work_items,
)
from .selectors import (
    dashboard_metrics,
    filter_work_items,
    resource_utilization_rows,
    work_item_queryset,
)
from .services import (
    acknowledge_alert,
    approve_recommendation,
    assign_work,
    calculate_utilization,
    cancel_assignment,
    recommend_assignees,
    reject_recommendation,
    resolve_alert,
    update_status,
)

User = get_user_model()


def _actor(serializer):
    request = serializer.context.get('request')
    user = getattr(request, 'user', None)
    return user if user is not None and user.is_authenticated else None


def _scoped_users(actor):
    if actor is None:
        return User.objects.filter(is_active=True)
    return assignable_users(actor)


def _scoped_teams(actor):
    queryset = WorkloadTeam.objects.filter(is_active=True)
    if actor is None:
        return queryset
    return scope_teams(queryset, actor)


def _scoped_customers(actor):
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
    from projects.models import Project

    queryset = Project.objects.all()
    if actor is None or is_global_manager(actor):
        return queryset
    if is_manager(actor):
        return queryset.filter(
            Q(client=actor) | Q(workload_items__tenant=actor),
        ).distinct()
    return queryset.filter(client=actor)


# --------------------------------------------------------------------------- #
# Serializers
# --------------------------------------------------------------------------- #
class WorkloadSkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkloadSkill
        fields = ['id', 'name', 'description']


class WorkloadTeamSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)
    lead_name = serializers.SerializerMethodField()
    members = serializers.PrimaryKeyRelatedField(
        many=True, queryset=User.objects.filter(is_active=True), required=False,
    )

    class Meta:
        model = WorkloadTeam
        fields = [
            'id', 'name', 'code', 'department', 'description',
            'lead', 'lead_name', 'members', 'member_count', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        actor = _actor(self)
        users = _scoped_users(actor)
        self.fields['members'].queryset = users
        self.fields['lead'].queryset = users

    def get_lead_name(self, obj):
        if not obj.lead_id:
            return None
        return obj.lead.get_full_name() or obj.lead.get_username()


class ResourceCapacitySerializer(serializers.ModelSerializer):
    available_hours = serializers.DecimalField(
        max_digits=8, decimal_places=2, read_only=True,
    )

    class Meta:
        model = ResourceCapacity
        fields = [
            'id', 'weekly_hours', 'availability_percent', 'time_off_hours',
            'available_hours', 'notes', 'updated_at',
        ]
        read_only_fields = ['available_hours', 'updated_at']


class WorkloadResourceSerializer(serializers.ModelSerializer):
    capacity = ResourceCapacitySerializer(read_only=True)
    skills = serializers.PrimaryKeyRelatedField(
        many=True, queryset=WorkloadSkill.objects.all(), required=False,
    )
    skill_names = serializers.SerializerMethodField()
    utilization = serializers.SerializerMethodField()

    class Meta:
        model = WorkloadResource
        fields = [
            'id', 'name', 'kind', 'user', 'team', 'system_label',
            'skills', 'skill_names', 'availability_status', 'is_active',
            'notes', 'capacity', 'utilization', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        actor = _actor(self)
        self.fields['user'].queryset = _scoped_users(actor)
        self.fields['team'].queryset = _scoped_teams(actor)

    def validate(self, attrs):
        kind = attrs.get('kind', getattr(self.instance, 'kind', WorkloadResource.KIND_PERSON))
        user = attrs.get('user', getattr(self.instance, 'user', None))
        team = attrs.get('team', getattr(self.instance, 'team', None))
        system_label = attrs.get(
            'system_label', getattr(self.instance, 'system_label', ''),
        )
        if kind == WorkloadResource.KIND_PERSON:
            if user is None:
                raise ValidationError({'user': 'An employee resource requires a user account.'})
            if team is not None:
                raise ValidationError({'team': 'Only team resources can link a team.'})
        elif kind == WorkloadResource.KIND_TEAM:
            if team is None:
                raise ValidationError({'team': 'A team resource requires a team.'})
            if user is not None:
                raise ValidationError({'user': 'Only employee resources can link a user.'})
        elif kind == WorkloadResource.KIND_SYSTEM:
            if user is not None or team is not None:
                raise ValidationError(
                    'System resources cannot link a user or a team.',
                )
            if not system_label:
                raise ValidationError(
                    {'system_label': 'A system resource requires a label.'},
                )
        return attrs

    def get_skill_names(self, obj):
        return list(obj.skills.values_list('name', flat=True))

    def get_utilization(self, obj):
        row = calculate_utilization(obj, WorkloadPolicy.get_for(obj.tenant_id))
        return {
            'assigned_hours': row['assigned_hours'],
            'available_hours': row['available_hours'],
            'utilization': row['utilization'],
            'level': row['level'],
            'is_assumed_capacity': row['is_assumed_capacity'],
        }


class WorkAssignmentSerializer(serializers.ModelSerializer):
    resource_name = serializers.SerializerMethodField()
    work_item_title = serializers.CharField(source='work_item.title', read_only=True)
    effective_hours = serializers.DecimalField(
        max_digits=8, decimal_places=2, read_only=True,
    )

    class Meta:
        model = WorkAssignment
        fields = [
            'id', 'work_item', 'work_item_title', 'resource', 'resource_name',
            'role', 'allocated_hours', 'effective_hours', 'status',
            'assigned_by', 'assigned_at', 'approved_by', 'approved_at',
            'notes',
        ]
        read_only_fields = [
            'assigned_by', 'assigned_at', 'approved_by', 'approved_at',
        ]

    def get_resource_name(self, obj):
        return obj.resource.display_owner if obj.resource_id else None


class WorkItemSerializer(serializers.ModelSerializer):
    assignee_name = serializers.SerializerMethodField()
    team_name = serializers.CharField(source='team.name', read_only=True)
    client_name = serializers.CharField(source='client.name', read_only=True)
    project_title = serializers.CharField(source='project.title', read_only=True)
    required_skills = serializers.PrimaryKeyRelatedField(
        many=True, queryset=WorkloadSkill.objects.all(), required=False,
    )
    required_skill_names = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)
    remaining_hours = serializers.DecimalField(
        max_digits=8, decimal_places=2, read_only=True,
    )
    active_assignments = WorkAssignmentSerializer(
        many=True, read_only=True, source='assignments',
    )

    class Meta:
        model = WorkItem
        fields = [
            'id', 'title', 'description', 'category', 'priority', 'status',
            'assignee', 'assignee_name', 'team', 'team_name',
            'client', 'client_name', 'project', 'project_title',
            'automation_workflow', 'source_module', 'external_reference',
            'estimated_hours', 'actual_hours', 'remaining_hours',
            'start_date', 'due_date', 'completed_at',
            'required_skills', 'required_skill_names',
            'created_by', 'is_client_visible', 'automation_eligible',
            'blocked_reason', 'cancellation_reason', 'is_overdue',
            'active_assignments', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'created_by', 'completed_at', 'created_at', 'updated_at',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        actor = _actor(self)
        self.fields['assignee'].queryset = _scoped_users(actor)
        self.fields['team'].queryset = _scoped_teams(actor)
        self.fields['client'].queryset = _scoped_customers(actor)
        self.fields['project'].queryset = _scoped_projects(actor)

    def get_assignee_name(self, obj):
        if not obj.assignee_id:
            return None
        return obj.assignee.get_full_name() or obj.assignee.get_username()

    def get_required_skill_names(self, obj):
        return list(obj.required_skills.values_list('name', flat=True))

    def validate(self, attrs):
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        due = attrs.get('due_date', getattr(self.instance, 'due_date', None))
        if start and due and due < start:
            raise ValidationError({'due_date': 'The due date cannot be earlier than the start date.'})
        team = attrs.get('team', getattr(self.instance, 'team', None))
        assignee = attrs.get('assignee', getattr(self.instance, 'assignee', None))
        if team is not None and assignee is not None and team.tenant_id is not None:
            if not team.members.filter(pk=assignee.pk).exists():
                raise ValidationError(
                    {'assignee': 'The employee is not a member of this workspace team.'},
                )
        return attrs


class WorkloadAlertSerializer(serializers.ModelSerializer):
    alert_type_display = serializers.CharField(
        source='get_alert_type_display', read_only=True,
    )
    work_item_title = serializers.CharField(source='work_item.title', read_only=True)
    resource_name = serializers.CharField(source='resource.name', read_only=True)

    class Meta:
        model = WorkloadAlert
        fields = [
            'id', 'alert_type', 'alert_type_display', 'severity', 'status',
            'work_item', 'work_item_title', 'resource', 'resource_name',
            'team', 'recipient', 'message', 'detail', 'metadata',
            'created_at', 'updated_at', 'acknowledged_at', 'resolved_at',
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'acknowledged_at', 'resolved_at',
        ]


class WorkloadPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkloadPolicy
        fields = [
            'id', 'name', 'tenant', 'is_default',
            'available_below', 'balanced_max', 'high_max',
            'deadline_warning_days', 'team_capacity_warning_percent',
            'bottleneck_threshold', 'default_weekly_hours',
            'auto_assign_enabled', 'auto_reassign_critical',
            'require_approval_for_critical', 'weights',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


# --------------------------------------------------------------------------- #
# Permissions
# --------------------------------------------------------------------------- #
class WorkloadManagerPermission(IsAuthenticated):
    message = 'Manager access is required for this workload operation.'

    def has_permission(self, request, view):
        return super().has_permission(request, view) and is_manager(request.user)


class WorkloadAdminPermission(IsAuthenticated):
    message = 'Administrator access is required for this workload operation.'

    def has_permission(self, request, view):
        return super().has_permission(request, view) and is_admin(request.user)


# --------------------------------------------------------------------------- #
# ViewSets
# --------------------------------------------------------------------------- #
class WorkItemViewSet(viewsets.ModelViewSet):
    serializer_class = WorkItemSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'priority', 'category', 'source_module', 'team', 'assignee']
    search_fields = ['title', 'description', 'external_reference']
    ordering_fields = ['created_at', 'due_date', 'priority', 'status', 'title']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = scope_work_items(work_item_queryset(), self.request.user)
        return filter_work_items(queryset, self.request.query_params)

    def _require_manager(self):
        if not is_manager(self.request.user):
            raise PermissionDenied('Manager access is required for this operation.')

    def _require_editor(self, item):
        if not can_edit_work_item(self.request.user, item):
            raise PermissionDenied('You cannot modify this work item.')

    def _apply_tenant(self, item):
        """Keep the item inside the caller's workspace."""
        user = self.request.user
        if item.client_id and item.client.user_id:
            item.tenant = item.client.user
        elif item.team_id and item.team.tenant_id:
            item.tenant = item.team.tenant
        elif not is_global_manager(user):
            item.tenant = user
        return item

    def perform_create(self, serializer):
        user = self.request.user
        if get_role(user) == 'client':
            raise PermissionDenied('Clients cannot create internal work.')
        item = serializer.save(created_by=user)
        if not is_manager(user):
            item.tenant = user
            if item.assignee_id is None:
                item.assignee = user
            if item.status in (WorkItem.STATUS_NEW, WorkItem.STATUS_PENDING):
                item.status = WorkItem.STATUS_ASSIGNED
        else:
            self._apply_tenant(item)
        item.save()
        if is_manager(user) and (item.assignee_id or item.team_id):
            assign_work(
                item,
                user=item.assignee if item.assignee_id else None,
                team=item.team if item.team_id else None,
                actor=user,
                allocated_hours=item.remaining_hours,
                approve=True,
                notes='Assignment set when the work item was created.',
            )

    def perform_update(self, serializer):
        item = self.get_object()
        self._require_editor(item)
        old_assignee_id = item.assignee_id
        old_team_id = item.team_id
        item = serializer.save()
        self._apply_tenant(item)
        item.save()
        if not is_manager(self.request.user):
            return
        if item.assignee_id and item.assignee_id != old_assignee_id:
            assign_work(
                item, user=item.assignee, actor=self.request.user,
                allocated_hours=item.remaining_hours, approve=True,
                notes='Assignment updated from API.',
            )
        elif item.team_id and item.team_id != old_team_id:
            assign_work(
                item, team=item.team, actor=self.request.user,
                allocated_hours=item.remaining_hours, approve=True,
                notes='Team assignment updated from API.',
            )
        elif not item.assignee_id and not item.team_id:
            for assignment in item.assignments.filter(
                status=WorkAssignment.STATUS_ACTIVE,
            ):
                cancel_assignment(
                    assignment, self.request.user,
                    note='Assignment cleared from API.',
                )

    def perform_destroy(self, instance):
        self._require_manager()
        instance.delete()

    @action(detail=True, methods=['post'])
    def status(self, request, pk=None):
        item = self.get_object()
        self._require_editor(item)
        new_status = request.data.get('status')
        try:
            update_status(
                item,
                new_status,
                actor=request.user,
                note=request.data.get('note', ''),
                actual_hours=request.data.get('actual_hours'),
                blocked_reason=request.data.get('blocked_reason', ''),
            )
        except DjangoValidationError as exc:
            raise ValidationError(getattr(exc, 'message_dict', str(exc)))
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        item = self.get_object()
        self._require_manager()
        assignee_id = request.data.get('assignee')
        team_id = request.data.get('team')
        resource_id = request.data.get('resource')
        assignee = (
            assignable_users(request.user).filter(pk=assignee_id).first()
            if assignee_id else None
        )
        team = (
            scope_teams(WorkloadTeam.objects.all(), request.user)
            .filter(pk=team_id).first()
            if team_id else None
        )
        resource = (
            assignable_resources(request.user).filter(pk=resource_id).first()
            if resource_id else None
        )
        if assignee_id and assignee is None:
            raise ValidationError({'assignee': 'Unknown or out-of-scope employee.'})
        if team_id and team is None:
            raise ValidationError({'team': 'Unknown or out-of-scope team.'})
        if resource_id and resource is None:
            raise ValidationError({'resource': 'Unknown or out-of-scope resource.'})
        if sum(bool(value) for value in (assignee, team, resource)) != 1:
            raise ValidationError(
                'Provide exactly one of assignee, team or resource.',
            )
        try:
            assign_work(
                item,
                user=assignee,
                team=team,
                resource=resource,
                actor=request.user,
                allocated_hours=request.data.get('allocated_hours'),
                role=request.data.get('role', ''),
                notes=request.data.get('notes', ''),
            )
        except DjangoValidationError as exc:
            raise ValidationError(getattr(exc, 'message_dict', str(exc)))
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=['get'])
    def recommendations(self, request, pk=None):
        item = self.get_object()
        self._require_manager()
        rows = recommend_assignees(item, limit=5, actor=request.user)
        return Response([
            {
                'resource_id': row['resource'].pk,
                'resource_name': row['resource'].display_owner,
                'score': row['score'],
                'score_percent': row['score_percent'],
                'utilization': row['utilization'],
                'utilization_after': row['utilization_after'],
                'would_overload': row['would_overload'],
                'matched_skills': row['matched_skills'],
                'reasons': row['reasons'],
            }
            for row in rows
        ])

    @action(detail=True, methods=['post'], url_path='recommendations/(?P<assignment_id>[^/.]+)/(?P<decision>approve|reject)')
    def recommendation_decision(self, request, pk=None, assignment_id=None, decision=None):
        item = self.get_object()
        self._require_manager()
        assignment = WorkAssignment.objects.filter(
            pk=assignment_id,
            work_item=item,
            status=WorkAssignment.STATUS_RECOMMENDED,
        ).first()
        if assignment is None:
            raise ValidationError('Recommendation not found.')
        if decision == 'approve':
            approve_recommendation(assignment, request.user)
        else:
            reject_recommendation(
                assignment, request.user, note=request.data.get('note', ''),
            )
        return Response(self.get_serializer(item).data)


class WorkloadResourceViewSet(viewsets.ModelViewSet):
    serializer_class = WorkloadResourceSerializer
    permission_classes = [WorkloadManagerPermission]
    filterset_fields = ['kind', 'availability_status', 'is_active']
    search_fields = ['name', 'user__username', 'team__name', 'system_label']
    ordering_fields = ['name', 'created_at']

    def get_queryset(self):
        return scope_resources(
            WorkloadResource.objects.select_related(
                'user', 'team', 'capacity',
            ).prefetch_related('skills'),
            self.request.user,
        )

    def perform_create(self, serializer):
        resource = serializer.save()
        if resource.team_id and resource.team.tenant_id:
            resource.tenant = resource.team.tenant
        elif not is_global_manager(self.request.user):
            resource.tenant = self.request.user
        else:
            resource.tenant = None
        resource.save(update_fields=['tenant', 'updated_at'])

    def perform_update(self, serializer):
        resource = serializer.save()
        if resource.team_id and resource.team.tenant_id:
            tenant = resource.team.tenant
        elif not is_global_manager(self.request.user):
            tenant = self.request.user
        else:
            # Global operators editing a tenant resource keep its workspace.
            return
        if resource.tenant_id != getattr(tenant, 'pk', None):
            resource.tenant = tenant
            resource.save(update_fields=['tenant', 'updated_at'])

    @action(detail=False, methods=['get'])
    def utilization(self, request):
        rows = resource_utilization_rows(self.get_queryset().filter(is_active=True))
        return Response([
            {
                'resource_id': row['resource'].pk,
                'name': row['resource'].display_owner,
                'assigned_hours': row['assigned_hours'],
                'available_hours': row['available_hours'],
                'utilization': row['utilization'],
                'level': row['level'],
                'is_assumed_capacity': row['is_assumed_capacity'],
                'active_assignments': row['active_assignments'],
            }
            for row in rows
        ])


class WorkloadTeamViewSet(viewsets.ModelViewSet):
    serializer_class = WorkloadTeamSerializer
    permission_classes = [WorkloadManagerPermission]
    filterset_fields = ['department', 'is_active']
    search_fields = ['name', 'code', 'department']

    def get_queryset(self):
        return scope_teams(
            WorkloadTeam.objects.select_related('lead').prefetch_related('members'),
            self.request.user,
        )

    def perform_create(self, serializer):
        team = serializer.save()
        team.tenant = None if is_global_manager(self.request.user) else self.request.user
        team.save(update_fields=['tenant', 'updated_at'])


class WorkloadAlertViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WorkloadAlertSerializer
    permission_classes = [WorkloadManagerPermission]
    filterset_fields = ['alert_type', 'severity', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        return scope_alerts(
            WorkloadAlert.objects.select_related(
                'work_item', 'resource', 'team', 'recipient',
            ),
            self.request.user,
        )

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        acknowledge_alert(alert, request.user)
        return Response(self.get_serializer(alert).data)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        alert = self.get_object()
        resolve_alert(alert, request.user)
        return Response(self.get_serializer(alert).data)


class WorkloadPolicyViewSet(viewsets.ModelViewSet):
    serializer_class = WorkloadPolicySerializer
    permission_classes = [WorkloadAdminPermission]

    def get_queryset(self):
        return scope_policies(WorkloadPolicy.objects.all(), self.request.user)

    def perform_create(self, serializer):
        policy = serializer.save()
        if policy.is_default:
            WorkloadPolicy.objects.filter(
                tenant=policy.tenant, is_default=True,
            ).exclude(pk=policy.pk).update(is_default=False)


class WorkloadDashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def metrics(self, request):
        user = request.user
        tenant = None if is_global_manager(user) else user
        items = scope_work_items(work_item_queryset(), user)
        data = dashboard_metrics(
            work_items=items,
            tenant=tenant,
        )
        # Drop Django model instances so the payload is JSON serialisable.
        serialisable = {
            key: value for key, value in data.items()
            if key not in {'employee_distribution', 'team_distribution',
                           'department_distribution', 'live_alerts',
                           'stored_alerts', 'trend'}
        }
        return Response(serialisable)
