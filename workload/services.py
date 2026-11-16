"""Business logic for workload capacity, assignment, monitoring and integration.

All mutating operations are transactional and write a ``WorkloadHistory`` entry
so managers can audit who changed what.  Calculations are defensive: missing
capacity falls back to the configured policy default, and missing estimates are
treated as zero rather than producing division errors.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q, Sum, Value
from django.db.models.functions import Coalesce, NullIf
from django.utils import timezone

from .models import (
    DECIMAL_ZERO,
    ResourceCapacity,
    WorkAssignment,
    WorkItem,
    WorkItemAttachment,
    WorkloadAlert,
    WorkloadHistory,
    WorkloadMetric,
    WorkloadPolicy,
    WorkloadResource,
    WorkloadTeam,
)
from .permissions import (
    assignable_resources,
    assignable_users,
    is_global_manager,
    is_manager,
    scope_teams,
)

logger = logging.getLogger(__name__)

MANAGED_ALERT_TYPES = [
    WorkloadAlert.TYPE_OVERLOAD,
    WorkloadAlert.TYPE_UNDERUTILIZED,
    WorkloadAlert.TYPE_OVERDUE,
    WorkloadAlert.TYPE_BLOCKED,
    WorkloadAlert.TYPE_DEADLINE,
    WorkloadAlert.TYPE_UNASSIGNED,
    WorkloadAlert.TYPE_TEAM_CAPACITY,
    WorkloadAlert.TYPE_BOTTLENECK,
]

LEVEL_LABELS = {
    'available': 'Available',
    'balanced': 'Balanced',
    'high': 'High',
    'overloaded': 'Overloaded',
    'unavailable': 'Unavailable',
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _decimal(value):
    if value in (None, ''):
        return DECIMAL_ZERO
    return Decimal(str(value))


def _as_float(value):
    if value is None:
        return 0.0
    return round(float(value), 1)


def _stringify(value):
    if value is None:
        return ''
    if hasattr(value, 'get_full_name'):
        return value.get_full_name() or value.get_username()
    if hasattr(value, 'name'):
        return str(value.name)
    return str(value)[:255]


def log_history(work_item, action, actor=None, field_name='', old_value='', new_value='', note=''):
    return WorkloadHistory.objects.create(
        work_item=work_item,
        actor=actor if actor and actor.is_authenticated else None,
        action=action,
        field_name=field_name,
        old_value=_stringify(old_value),
        new_value=_stringify(new_value),
        note=note or '',
    )


def record_field_changes(work_item, actor, before, after_map, note=''):
    """Write one history row per changed field."""
    created = []
    for field_name, new_value in after_map.items():
        old_value = before.get(field_name)
        if _stringify(old_value) == _stringify(new_value):
            continue
        created.append(
            log_history(
                work_item,
                WorkloadHistory.ACTION_UPDATED,
                actor=actor,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                note=note,
            ),
        )
    return created


def notify_user(user, message, *, project=None, severity=WorkloadAlert.SEVERITY_MEDIUM, notification_type='STATUS'):
    """Create an in-app notification using the platform's existing model."""
    if not user:
        return None
    try:
        from projects.models import WorkflowNotification

        return WorkflowNotification.objects.create(
            project=project,
            recipient=user,
            notification_type=notification_type,
            message=message,
            severity=severity,
        )
    except Exception:  # pragma: no cover - notifications must never break work
        logger.exception('Unable to create workload notification for user %s', user)
        return None


# --------------------------------------------------------------------------- #
# Resources and capacity
# --------------------------------------------------------------------------- #
def get_or_create_resource_for_user(user, *, tenant=None, policy=None, create_capacity=True):
    resource, created = WorkloadResource.objects.get_or_create(
        user=user,
        defaults={
            'name': user.get_full_name() or user.get_username(),
            'kind': WorkloadResource.KIND_PERSON,
            'tenant': tenant,
        },
    )
    if not created and not resource.name:
        resource.name = user.get_full_name() or user.get_username()
        resource.save(update_fields=['name', 'updated_at'])
    if create_capacity:
        policy = policy or WorkloadPolicy.get_for(tenant)
        ResourceCapacity.objects.get_or_create(
            resource=resource,
            defaults={'weekly_hours': policy.default_weekly_hours},
        )
    return resource


def get_or_create_resource_for_team(team, *, policy=None, create_capacity=True):
    resource, created = WorkloadResource.objects.get_or_create(
        team=team,
        defaults={
            'name': team.name,
            'kind': WorkloadResource.KIND_TEAM,
            'tenant': team.tenant,
        },
    )
    if create_capacity:
        policy = policy or WorkloadPolicy.get_for(team.tenant_id)
        ResourceCapacity.objects.get_or_create(
            resource=resource,
            defaults={'weekly_hours': policy.default_weekly_hours},
        )
    return resource


def get_effective_capacity(resource, policy=None):
    """Return ``(available_hours, source, is_assumed)`` without raising."""
    policy = policy or WorkloadPolicy.get_for(resource.tenant_id)
    try:
        capacity = resource.capacity
    except ResourceCapacity.DoesNotExist:
        capacity = None
    if capacity is not None:
        available = capacity.available_hours
        source = 'resource'
    else:
        available = policy.default_weekly_hours or DECIMAL_ZERO
        source = 'policy_default'
    if resource.availability_status in (
        WorkloadResource.AVAILABILITY_UNAVAILABLE,
        WorkloadResource.AVAILABILITY_ON_LEAVE,
    ):
        available = DECIMAL_ZERO
        source = 'availability_status'
    return available, source, source != 'resource'


def assigned_hours_map(resource_ids):
    """Bulk assigned hours for the given resource ids (avoids per-row queries)."""
    ids = list(resource_ids)
    if not ids:
        return {}
    rows = (
        WorkAssignment.objects.filter(
            status=WorkAssignment.STATUS_ACTIVE,
            work_item__status__in=WorkItem.OPEN_STATUSES,
            resource_id__in=ids,
        )
        .values('resource_id')
        .annotate(
            hours=Sum(
                Coalesce(
                    NullIf('allocated_hours', Value(DECIMAL_ZERO)),
                    'work_item__estimated_hours',
                ),
            ),
        )
    )
    result = {row['resource_id']: _decimal(row['hours']) for row in rows}

    # Items assigned directly on WorkItem without an active assignment row still
    # consume capacity (for example imported or admin-created records).
    person_rows = WorkloadResource.objects.filter(
        id__in=ids, kind=WorkloadResource.KIND_PERSON, user__isnull=False,
    ).values('id', 'user_id')
    user_to_resource = {row['user_id']: row['id'] for row in person_rows}
    if user_to_resource:
        direct = (
            WorkItem.objects.filter(
                assignee_id__in=user_to_resource.keys(),
                status__in=WorkItem.OPEN_STATUSES,
            )
            .exclude(assignments__status=WorkAssignment.STATUS_ACTIVE)
            .values('assignee_id')
            .annotate(hours=Sum('estimated_hours'))
        )
        for row in direct:
            resource_id = user_to_resource.get(row['assignee_id'])
            if resource_id:
                result[resource_id] = result.get(resource_id, DECIMAL_ZERO) + _decimal(row['hours'])
    return result


def assigned_hours_for_resource(resource):
    return assigned_hours_map([resource.pk]).get(resource.pk, DECIMAL_ZERO)


def classify_utilization(utilization, available_hours, policy):
    if available_hours is not None and available_hours <= 0:
        return 'overloaded' if utilization else 'unavailable'
    if utilization is None:
        return 'unavailable'
    if utilization < float(policy.available_below):
        return 'available'
    if utilization <= float(policy.balanced_max):
        return 'balanced'
    if utilization <= float(policy.high_max):
        return 'high'
    return 'overloaded'


def calculate_utilization(
    resource, policy=None, assigned_hours=None, *, with_assignment_count=True,
):
    """Calculate (assigned / available) * 100 for a single resource."""
    policy = policy or WorkloadPolicy.get_for(resource.tenant_id)
    available, capacity_source, is_assumed = get_effective_capacity(resource, policy)
    if assigned_hours is None:
        assigned_hours = assigned_hours_for_resource(resource)
    assigned_hours = _decimal(assigned_hours)
    available = _decimal(available)

    if available <= 0:
        utilization = None
        level = 'overloaded' if assigned_hours > 0 else 'unavailable'
    else:
        utilization = round(float(assigned_hours / available) * 100, 1)
        level = classify_utilization(utilization, available, policy)

    active_assignments = None
    if with_assignment_count:
        active_assignments = WorkAssignment.objects.filter(
            resource=resource,
            status=WorkAssignment.STATUS_ACTIVE,
            work_item__status__in=WorkItem.OPEN_STATUSES,
        ).count()
    return {
        'resource': resource,
        'assigned_hours': _as_float(assigned_hours),
        'available_hours': _as_float(available),
        'utilization': utilization,
        'utilization_display': '—' if utilization is None else f'{utilization:.1f}%',
        'level': level,
        'level_label': LEVEL_LABELS.get(level, level.title()),
        'has_capacity': not is_assumed,
        'capacity_source': capacity_source,
        'is_assumed_capacity': is_assumed,
        'active_assignments': active_assignments,
        'availability_status': resource.availability_status,
        'skills': [s.name for s in resource.skills.all()],
    }


def team_capacity(
    team, policy=None, *, member_ids=None, resources=None, hours_map=None,
):
    """Aggregate member capacity and assigned hours for a team.

    Callers that render many teams can pass pre-fetched ``member_ids``,
    ``resources`` and a bulk ``hours_map`` to avoid per-team queries.
    """
    policy = policy or WorkloadPolicy.get_for(team.tenant_id)
    if member_ids is None:
        member_ids = [member.id for member in team.members.all()]
    if resources is None:
        resources = list(
            WorkloadResource.objects.filter(
                kind=WorkloadResource.KIND_PERSON,
                user_id__in=member_ids,
                is_active=True,
            ).select_related('capacity'),
        )
    if resources:
        if hours_map is None:
            hours_map = assigned_hours_map([r.pk for r in resources])
        assigned = sum((hours_map.get(r.pk, DECIMAL_ZERO) for r in resources), DECIMAL_ZERO)
        available = sum(
            (get_effective_capacity(r, policy)[0] for r in resources), DECIMAL_ZERO,
        )
        resource_count = len(resources)
    else:
        try:
            team_resource = team.resource
        except WorkloadResource.DoesNotExist:
            team_resource = None
        if team_resource:
            result = calculate_utilization(team_resource, policy)
            return {
                **result,
                'team': team,
                'member_count': len(member_ids),
                'resource_count': 1,
                'active_items': WorkItem.objects.filter(
                    team=team, status__in=WorkItem.OPEN_STATUSES,
                ).count(),
            }
        assigned = DECIMAL_ZERO
        available = DECIMAL_ZERO
        resource_count = 0

    utilization = None
    if available > 0:
        utilization = round(float(assigned / available) * 100, 1)
    level = classify_utilization(utilization, available, policy)
    return {
        'team': team,
        'assigned_hours': _as_float(assigned),
        'available_hours': _as_float(available),
        'utilization': utilization,
        'utilization_display': '—' if utilization is None else f'{utilization:.1f}%',
        'level': level,
        'level_label': LEVEL_LABELS.get(level, level.title()),
        'member_count': len(member_ids),
        'resource_count': resource_count,
        'active_items': WorkItem.objects.filter(
            team=team, status__in=WorkItem.OPEN_STATUSES,
        ).count(),
    }


# --------------------------------------------------------------------------- #
# Work item lifecycle
# --------------------------------------------------------------------------- #
def create_work_item(actor=None, *, skills=None, **fields):
    """Create a work item, defaulting tenant scope for non-manager users."""
    skills = list(skills or [])
    tenant = fields.get('tenant')
    if actor and not is_manager(actor) and tenant is None:
        fields['tenant'] = actor
    item = WorkItem(**fields)
    item.created_by = actor if actor and actor.is_authenticated else fields.get('created_by')
    item.full_clean()
    item.save()
    if skills:
        item.required_skills.set(skills)
    log_history(
        item,
        WorkloadHistory.ACTION_CREATED,
        actor=actor,
        note='Work item created.',
    )
    return item


def update_status(work_item, status, actor=None, *, note='', actual_hours=None, blocked_reason=''):
    """Change status with permission checks, audit history and alert cleanup."""
    valid = {choice[0] for choice in WorkItem.STATUS_CHOICES}
    if status not in valid:
        raise ValidationError({'status': 'Unknown work item status.'})
    from .permissions import can_change_status

    if actor is not None and not can_change_status(actor, work_item):
        raise PermissionDenied('You cannot change the status of this work item.')

    with transaction.atomic():
        item = WorkItem.objects.select_for_update().get(pk=work_item.pk)
        old_status = item.status
        old_actual = item.actual_hours
        item.status = status
        update_fields = ['status', 'updated_at', 'completed_at']
        if actual_hours is not None:
            item.actual_hours = _decimal(actual_hours)
            update_fields.append('actual_hours')
        if status == WorkItem.STATUS_BLOCKED:
            item.blocked_reason = (blocked_reason or note or item.blocked_reason)[:255]
            update_fields.append('blocked_reason')
        elif status != WorkItem.STATUS_BLOCKED and item.blocked_reason:
            item.blocked_reason = ''
            update_fields.append('blocked_reason')
        if status == WorkItem.STATUS_CANCELLED:
            item.cancellation_reason = (note or item.cancellation_reason)[:255]
            update_fields.append('cancellation_reason')

        item.save(update_fields=update_fields)
        if status == WorkItem.STATUS_COMPLETED:
            item.assignments.filter(status=WorkAssignment.STATUS_ACTIVE).update(
                status=WorkAssignment.STATUS_COMPLETED,
            )
        log_history(
            item,
            WorkloadHistory.ACTION_STATUS_CHANGED,
            actor=actor,
            field_name='status',
            old_value=old_status,
            new_value=status,
            note=note,
        )
        if actual_hours is not None and _stringify(old_actual) != _stringify(item.actual_hours):
            log_history(
                item,
                WorkloadHistory.ACTION_UPDATED,
                actor=actor,
                field_name='actual_hours',
                old_value=old_actual,
                new_value=item.actual_hours,
            )
        if status in WorkItem.CLOSED_STATUSES:
            resolve_work_item_alerts(item)
        work_item.refresh_from_db()
        return work_item


def resolve_work_item_alerts(item):
    now = timezone.now()
    return WorkloadAlert.objects.filter(
        work_item=item,
        status__in=[WorkloadAlert.STATUS_OPEN, WorkloadAlert.STATUS_ACKNOWLEDGED],
        alert_type__in=[
            WorkloadAlert.TYPE_OVERDUE,
            WorkloadAlert.TYPE_DEADLINE,
            WorkloadAlert.TYPE_BLOCKED,
            WorkloadAlert.TYPE_UNASSIGNED,
        ],
    ).update(status=WorkloadAlert.STATUS_RESOLVED, resolved_at=now)


# --------------------------------------------------------------------------- #
# Assignment
# --------------------------------------------------------------------------- #
def _resolve_assignment_resource(*, user=None, team=None, resource=None, tenant=None, policy=None):
    if resource is not None:
        return resource
    if user is not None:
        return get_or_create_resource_for_user(user, tenant=tenant, policy=policy)
    if team is not None:
        return get_or_create_resource_for_team(team, policy=policy)
    raise ValidationError('Choose an employee, a team, or a resource to assign.')


def _validate_assignment_scope(actor, *, user=None, team=None, resource=None):
    """Reject targets that a workspace manager is not allowed to assign.

    The web forms and API already narrow their querysets; this is the service
    layer backstop so a direct call can never reach another workspace.
    """
    if actor is None or not getattr(actor, 'is_authenticated', False):
        return
    if is_global_manager(actor):
        return
    if user is not None and not assignable_users(actor).filter(pk=user.pk).exists():
        raise PermissionDenied(
            'The selected employee is outside your workspace.',
        )
    if team is not None and not scope_teams(
        WorkloadTeam.objects.filter(pk=team.pk), actor,
    ).exists():
        raise PermissionDenied('The selected team is outside your workspace.')
    if resource is not None and not assignable_resources(actor).filter(
        pk=resource.pk,
    ).exists():
        raise PermissionDenied('The selected resource is outside your workspace.')


def _validate_assignment_tenant(item, resource):
    """Reject assignments that cross a workspace boundary.

    A resource without a tenant is a shared/platform resource and may serve any
    workspace.  A tenant-owned resource may only serve work from that same
    tenant; global work cannot silently consume another workspace's capacity.
    """
    item_tenant_id = item.tenant_id
    resource_tenant_id = resource.tenant_id

    if not resource_tenant_id:
        return
    if item_tenant_id == resource_tenant_id:
        return
    raise ValidationError(
        'The selected resource belongs to a different workspace than this work item.',
    )


def assign_work(
    work_item,
    *,
    user=None,
    team=None,
    resource=None,
    actor=None,
    allocated_hours=None,
    role='',
    notes='',
    automatic=False,
    approve=True,
):
    """Assign a work item, replacing any active assignment.

    ``automatic=True`` is used by integrations and requires the policy to allow
    moving critical work.  Manual manager reassignment is always permitted.
    """
    if not automatic and actor is not None and not is_manager(actor):
        raise PermissionDenied('Only managers can assign work.')
    if automatic and actor is not None and not is_manager(actor):
        raise PermissionDenied('Automatic assignment requires manager privileges.')
    _validate_assignment_scope(actor, user=user, team=team, resource=resource)

    with transaction.atomic():
        item = WorkItem.objects.select_for_update().get(pk=work_item.pk)
        policy = WorkloadPolicy.get_for(item.tenant_id)
        resource = _resolve_assignment_resource(
            user=user, team=team, resource=resource, tenant=item.tenant, policy=policy,
        )
        existing_active = list(
            item.assignments.select_related('resource__user')
            .filter(status=WorkAssignment.STATUS_ACTIVE)
            .exclude(resource=resource)
        )
        current_assignee_changes = bool(
            item.assignee_id and item.assignee_id != resource.user_id,
        )
        if (
            automatic
            and item.priority == WorkItem.PRIORITY_CRITICAL
            and (existing_active or current_assignee_changes)
            and not policy.auto_reassign_critical
        ):
            raise PermissionDenied(
                'Critical work cannot be reassigned automatically under the current policy.',
            )
        _validate_assignment_tenant(item, resource)

        old_assignee = item.assignee
        current = item.assignments.filter(
            resource=resource, status=WorkAssignment.STATUS_ACTIVE,
        ).first()

        # One active resource at a time keeps capacity accounting unambiguous.
        item.assignments.filter(status=WorkAssignment.STATUS_ACTIVE).exclude(
            resource=resource,
        ).update(status=WorkAssignment.STATUS_CANCELLED)

        hours = _decimal(allocated_hours) if allocated_hours not in (None, '') else item.remaining_hours
        if current:
            current.role = role or current.role
            current.allocated_hours = hours
            current.notes = notes or current.notes
            if approve:
                current.status = WorkAssignment.STATUS_ACTIVE
            current.save()
            assignment = current
            created = False
        else:
            assignment = WorkAssignment.objects.create(
                work_item=item,
                resource=resource,
                role=role,
                allocated_hours=hours,
                status=WorkAssignment.STATUS_ACTIVE if approve else WorkAssignment.STATUS_RECOMMENDED,
                assigned_by=actor if actor and actor.is_authenticated else None,
                approved_by=actor if approve and actor and actor.is_authenticated else None,
                approved_at=timezone.now() if approve and actor and actor.is_authenticated else None,
                notes=notes,
            )
            created = True

        if not approve:
            log_history(
                item,
                WorkloadHistory.ACTION_ASSIGNED,
                actor=actor,
                field_name='recommendation',
                new_value=resource.name,
                note=notes or 'Assignment recommended.',
            )
            return assignment

        if resource.is_team:
            item.team = resource.team
            item.assignee = None
        else:
            item.assignee = resource.user
            if not item.team_id and resource.user_id:
                memberships = list(
                    resource.user.workload_teams.filter(is_active=True)[:2],
                )
                if len(memberships) == 1:
                    item.team = memberships[0]

        if item.status in (WorkItem.STATUS_NEW, WorkItem.STATUS_PENDING):
            item.status = WorkItem.STATUS_ASSIGNED
        item.save(update_fields=['assignee', 'team', 'status', 'updated_at'])
        log_history(
            item,
            WorkloadHistory.ACTION_REASSIGNED if existing_active or old_assignee else WorkloadHistory.ACTION_ASSIGNED,
            actor=actor,
            field_name='assignee',
            old_value=old_assignee or '',
            new_value=resource.display_owner,
            note=notes or f'Assigned {hours}h.',
        )
        WorkloadAlert.objects.filter(
            work_item=item,
            alert_type=WorkloadAlert.TYPE_UNASSIGNED,
            status__in=[WorkloadAlert.STATUS_OPEN, WorkloadAlert.STATUS_ACKNOWLEDGED],
        ).update(status=WorkloadAlert.STATUS_RESOLVED, resolved_at=timezone.now())

        if created and actor is not None and resource.user_id and resource.user_id != getattr(actor, 'id', None):
            notify_user(
                resource.user,
                f'You have been assigned "{item.title}" ({hours}h, due '
                f'{item.due_date or "no date"}).',
                project=item.project,
                severity=(
                    WorkloadAlert.SEVERITY_HIGH
                    if item.priority in (WorkItem.PRIORITY_HIGH, WorkItem.PRIORITY_CRITICAL)
                    else WorkloadAlert.SEVERITY_MEDIUM
                ),
            )
        return assignment


def reassign_work(work_item, *, actor, **kwargs):
    return assign_work(work_item, actor=actor, automatic=False, approve=True, **kwargs)


def recommend_assignees(
    work_item, *, policy=None, limit=5, exclude_resource_ids=None, actor=None,
):
    """Score active employees by skills, headroom, team and deadline urgency."""
    policy = policy or WorkloadPolicy.get_for(work_item.tenant_id)
    exclude_ids = set(exclude_resource_ids or [])
    required_ids = set(work_item.required_skills.values_list('id', flat=True))
    team_member_ids = set()
    if work_item.team_id:
        team_member_ids = {member.id for member in work_item.team.members.all()}

    resources_qs = (
        WorkloadResource.objects.filter(
            kind=WorkloadResource.KIND_PERSON,
            is_active=True,
            user__isnull=False,
            user__is_active=True,
        )
        .exclude(pk__in=exclude_ids)
        .select_related('user', 'capacity')
        .prefetch_related('skills')
    )
    if work_item.tenant_id:
        resources_qs = resources_qs.filter(
            Q(tenant=work_item.tenant_id) | Q(tenant__isnull=True),
        )
    elif actor is not None and not is_global_manager(actor):
        # A workspace manager must never see another tenant's resources, even
        # when the work item itself is global.
        resources_qs = resources_qs.filter(tenant__isnull=True)
    resources = list(resources_qs)
    assigned_by_resource = assigned_hours_map([r.pk for r in resources])

    weights = policy.weights or {}
    weight_sum = sum(float(weights.get(k, 0) or 0) for k in ('skills', 'capacity', 'team', 'deadline')) or 1.0
    today = timezone.localdate()
    warning_days = policy.deadline_warning_days
    if work_item.due_date:
        days_left = (work_item.due_date - today).days
        if days_left < 0:
            deadline_score = 1.0
        elif days_left <= warning_days:
            deadline_score = 0.9
        elif days_left <= warning_days * 2:
            deadline_score = 0.5
        else:
            deadline_score = 0.2
    else:
        deadline_score = 0.3

    results = []
    for resource in resources:
        if resource.availability_status in (
            WorkloadResource.AVAILABILITY_UNAVAILABLE,
            WorkloadResource.AVAILABILITY_ON_LEAVE,
        ):
            continue
        utilization = calculate_utilization(
            resource,
            policy,
            assigned_hours=assigned_by_resource.get(resource.pk, DECIMAL_ZERO),
            with_assignment_count=False,
        )
        resource_skill_ids = {s.id for s in resource.skills.all()}
        if required_ids:
            matched = required_ids & resource_skill_ids
            skill_score = len(matched) / len(required_ids)
            matched_names = [s.name for s in resource.skills.all() if s.id in matched]
        else:
            skill_score = 1.0
            matched_names = []
        headroom = max(0.0, float(utilization['available_hours']) - float(utilization['assigned_hours']))
        available = float(utilization['available_hours'])
        capacity_score = headroom / available if available > 0 else 0.0
        team_score = 1.0 if resource.user_id in team_member_ids else 0.0
        projected = float(utilization['assigned_hours']) + float(work_item.remaining_hours)
        projected_util = round(projected / available * 100, 1) if available > 0 else None
        would_overload = available <= 0 or (projected_util is not None and projected_util > float(policy.high_max))
        score = (
            skill_score * float(weights.get('skills', 0) or 0)
            + capacity_score * float(weights.get('capacity', 0) or 0)
            + team_score * float(weights.get('team', 0) or 0)
            + deadline_score * float(weights.get('deadline', 0) or 0)
        ) / weight_sum

        reasons = []
        if matched_names:
            reasons.append(f'Matches {", ".join(matched_names)}')
        if capacity_score >= 0.5:
            reasons.append('Has meaningful free capacity')
        elif utilization['level'] in ('high', 'overloaded'):
            reasons.append('Currently at or above capacity')
        if team_score:
            reasons.append('Member of the responsible team')
        if would_overload:
            reasons.append('Would exceed 100% utilisation')

        results.append({
            'resource': resource,
            'user': resource.user,
            'score': round(score, 4),
            'score_percent': round(score * 100, 1),
            'skill_score': round(skill_score * 100, 1),
            'capacity_score': round(capacity_score * 100, 1),
            'team_score': round(team_score * 100, 1),
            'matched_skills': matched_names,
            'utilization': utilization['utilization'],
            'utilization_after': projected_util,
            'level': utilization['level'],
            'would_overload': would_overload,
            'is_current': resource.user_id == work_item.assignee_id,
            'reasons': reasons,
        })

    results.sort(key=lambda row: (row['would_overload'], -row['score']))
    return results[:limit]


def store_recommendations(work_item, actor, *, limit=3):
    """Persist the top recommendations as reviewable assignment rows."""
    if not is_manager(actor):
        raise PermissionDenied('Only managers can generate assignment recommendations.')
    recommendations = recommend_assignees(work_item, limit=limit, actor=actor)
    with transaction.atomic():
        work_item.assignments.filter(
            status=WorkAssignment.STATUS_RECOMMENDED,
        ).update(status=WorkAssignment.STATUS_REJECTED)
        created = []
        for row in recommendations:
            if row['is_current']:
                continue
            assignment = WorkAssignment.objects.create(
                work_item=work_item,
                resource=row['resource'],
                role='Recommended',
                allocated_hours=work_item.remaining_hours,
                status=WorkAssignment.STATUS_RECOMMENDED,
                assigned_by=actor,
                notes='; '.join(row['reasons'])[:255],
            )
            created.append((assignment, row))
        log_history(
            work_item,
            WorkloadHistory.ACTION_UPDATED,
            actor=actor,
            field_name='recommendations',
            note=f'{len(created)} assignment recommendation(s) generated.',
        )
    return created


def approve_recommendation(assignment, actor):
    if not is_manager(actor):
        raise PermissionDenied('Only managers can approve recommendations.')
    with transaction.atomic():
        assignment = WorkAssignment.objects.select_for_update().select_related(
            'work_item', 'resource__user',
        ).get(pk=assignment.pk)
        item = WorkItem.objects.select_for_update().get(pk=assignment.work_item_id)
        _validate_assignment_scope(
            actor, resource=assignment.resource,
        )
        _validate_assignment_tenant(item, assignment.resource)
        item.assignments.filter(status=WorkAssignment.STATUS_RECOMMENDED).exclude(
            pk=assignment.pk,
        ).update(status=WorkAssignment.STATUS_REJECTED)
        item.assignments.filter(status=WorkAssignment.STATUS_ACTIVE).exclude(
            resource=assignment.resource,
        ).update(status=WorkAssignment.STATUS_CANCELLED)
        assignment.status = WorkAssignment.STATUS_ACTIVE
        assignment.approved_by = actor
        assignment.approved_at = timezone.now()
        if not assignment.allocated_hours:
            assignment.allocated_hours = item.remaining_hours
        assignment.save()

        resource = assignment.resource
        if resource.is_team and resource.team_id:
            item.team = resource.team
            item.assignee = None
        else:
            item.assignee = resource.user
            if not item.team_id and resource.user_id:
                memberships = list(resource.user.workload_teams.filter(is_active=True)[:2])
                if len(memberships) == 1:
                    item.team = memberships[0]
        if item.status in (WorkItem.STATUS_NEW, WorkItem.STATUS_PENDING):
            item.status = WorkItem.STATUS_ASSIGNED
        item.save(update_fields=['assignee', 'team', 'status', 'updated_at'])
        log_history(
            item,
            WorkloadHistory.ACTION_ASSIGNED,
            actor=actor,
            field_name='assignee',
            new_value=resource.display_owner,
            note='Assignment recommendation approved.',
        )
        if resource.user_id:
            notify_user(
                resource.user,
                f'Assignment approved: "{item.title}" is now on your workload.',
                project=item.project,
                severity=WorkloadAlert.SEVERITY_MEDIUM,
            )
        return assignment


def reject_recommendation(assignment, actor, note=''):
    if not is_manager(actor):
        raise PermissionDenied('Only managers can reject recommendations.')
    assignment.status = WorkAssignment.STATUS_REJECTED
    assignment.notes = (note or assignment.notes)[:255]
    assignment.save(update_fields=['status', 'notes'])
    log_history(
        assignment.work_item,
        WorkloadHistory.ACTION_UPDATED,
        actor=actor,
        field_name='recommendation',
        old_value=assignment.resource.display_owner,
        note=note or 'Assignment recommendation rejected.',
    )
    return assignment


def cancel_assignment(assignment, actor, note=''):
    if not is_manager(actor):
        raise PermissionDenied('Only managers can cancel assignments.')
    assignment.status = WorkAssignment.STATUS_CANCELLED
    assignment.save(update_fields=['status'])
    item = assignment.work_item
    if item.assignments.filter(status=WorkAssignment.STATUS_ACTIVE).exists() is False:
        if item.assignee_id == assignment.resource.user_id:
            item.assignee = None
        item.save(update_fields=['assignee', 'updated_at'])
    log_history(item, WorkloadHistory.ACTION_UPDATED, actor=actor, note=note or 'Assignment cancelled.')
    return assignment


# --------------------------------------------------------------------------- #
# Integrations
# --------------------------------------------------------------------------- #
PROJECT_TASK_STATUS_MAP = {
    'TODO': WorkItem.STATUS_NEW,
    'IN_PROGRESS': WorkItem.STATUS_IN_PROGRESS,
    'BLOCKED': WorkItem.STATUS_BLOCKED,
    'READY_FOR_REVIEW': WorkItem.STATUS_IN_PROGRESS,
    'COMPLETED': WorkItem.STATUS_COMPLETED,
}


def _customer_for_project_client(client):
    if not client:
        return None
    try:
        from crm.models import Customer

        customer = Customer.objects.filter(user=client).first()
        if customer is not None:
            return customer
        # Only fall back to an email match when the customer is not already
        # owned by a different user account; otherwise linking it would expose
        # another workspace's CRM record.
        by_email = Customer.objects.filter(email__iexact=client.email).first()
        if by_email is not None and by_email.user_id in (None, client.pk):
            return by_email
        return None
    except Exception:  # pragma: no cover
        return None


def cancel_mirrored_work_item(work_item, reason):
    """Cancel a workload mirror when its source is deleted or cancelled."""
    if work_item is None:
        return None
    with transaction.atomic():
        item = WorkItem.objects.select_for_update().get(pk=work_item.pk)
        if item.status in WorkItem.CLOSED_STATUSES:
            return item
        old_status = item.status
        item.status = WorkItem.STATUS_CANCELLED
        item.cancellation_reason = (reason or 'Source record was cancelled.')[:255]
        item.save(update_fields=[
            'status', 'cancellation_reason', 'completed_at', 'updated_at',
        ])
        item.assignments.filter(status=WorkAssignment.STATUS_ACTIVE).update(
            status=WorkAssignment.STATUS_CANCELLED,
        )
        resolve_work_item_alerts(item)
        log_history(
            item,
            WorkloadHistory.ACTION_STATUS_CHANGED,
            field_name='status',
            old_value=old_status,
            new_value=WorkItem.STATUS_CANCELLED,
            note=item.cancellation_reason,
        )
        return item


def sync_project_task(task):
    """Create or update the workload mirror of a project task (idempotent)."""
    if not task.phase_id or not task.phase.project_id:
        return None
    project = task.phase.project
    client = _customer_for_project_client(project.client)
    defaults = {
        'title': task.name,
        'description': task.description or '',
        'category': WorkItem.CATEGORY_HUMAN,
        'priority': task.priority if task.priority in dict(WorkItem.PRIORITY_CHOICES) else WorkItem.PRIORITY_MEDIUM,
        'status': PROJECT_TASK_STATUS_MAP.get(task.status, WorkItem.STATUS_NEW),
        'due_date': task.due_date,
        'project': project,
        'client': client,
        'source_module': WorkItem.SOURCE_PROJECT,
        'tenant': project.client if project.client_id else None,
        'external_reference': f'project-task:{task.pk}',
    }
    with transaction.atomic():
        item, created = WorkItem.objects.get_or_create(
            project_task=task,
            defaults=defaults,
        )
        if not created:
            changed = [
                field for field, value in defaults.items()
                if getattr(item, field) != value
            ]
            for field in changed:
                setattr(item, field, defaults[field])
            if changed:
                item.save()
                log_history(
                    item,
                    WorkloadHistory.ACTION_UPDATED,
                    field_name='project_task',
                    note='Synchronised from project task.',
                )
        else:
            log_history(
                item,
                WorkloadHistory.ACTION_CREATED,
                note='Created from project task.',
            )

        if task.assigned_to_id:
            current_active = item.assignments.select_related('resource').filter(
                status=WorkAssignment.STATUS_ACTIVE,
            ).first()
            already_assigned = (
                current_active is not None
                and current_active.resource.user_id == task.assigned_to_id
            )
            if not already_assigned:
                try:
                    assign_work(
                        item,
                        user=task.assigned_to,
                        actor=None,
                        automatic=True,
                        approve=True,
                        notes='Synchronised from project task assignee.',
                    )
                except (PermissionDenied, ValidationError) as exc:
                    # A policy may deliberately protect critical work from
                    # automatic reassignment.  Keep the synced item but leave
                    # the existing assignment untouched.
                    logger.warning(
                        'Project task %s not auto-assigned: %s', task.pk, exc,
                    )
        return item


def sync_all_project_tasks(batch_size=500):
    from projects.models import PhaseTask

    count = 0
    errors = 0
    qs = PhaseTask.objects.select_related(
        'phase__project__client', 'assigned_to',
    ).order_by('pk')
    for task in qs.iterator(chunk_size=batch_size):
        try:
            sync_project_task(task)
            count += 1
        except Exception:
            errors += 1
            logger.exception('Failed to sync project task %s into workload', task.pk)
    return {'synced': count, 'errors': errors}


def _service_request_fields(service_request, client):
    return {
        'title': f'{service_request.service_type} request - {client.name}',
        'description': service_request.description or '',
        'client': client,
        'tenant': client.user if client and client.user_id else None,
    }


def create_work_item_from_service_request(service_request):
    """Create/update the CRM mirror without duplicating workload items."""
    return sync_service_request(service_request)


def sync_service_request(service_request):
    """Keep the CRM mirror in sync; cancel it when the request is rejected."""
    try:
        client = service_request.customer
    except Exception:  # pragma: no cover
        return None
    if client is None:
        return None
    item = WorkItem.objects.filter(crm_request=service_request).first()

    if item is None:
        if service_request.status != 'NEW':
            return None
        defaults = {
            **_service_request_fields(service_request, client),
            'category': WorkItem.CATEGORY_BUSINESS,
            'priority': WorkItem.PRIORITY_MEDIUM,
            'status': WorkItem.STATUS_NEW,
            'source_module': WorkItem.SOURCE_CRM,
            'external_reference': f'crm-service-request:{service_request.pk}',
        }
        item = WorkItem.objects.create(crm_request=service_request, **defaults)
        log_history(item, WorkloadHistory.ACTION_CREATED, note='Created from CRM service request.')
        return item

    if service_request.status == 'REJECTED':
        cancel_mirrored_work_item(item, 'CRM service request was rejected.')
        return item

    # Mirror only fields the CRM owns.  Workload-managed fields (status,
    # estimates, visibility, assignments) are deliberately preserved.
    updates = _service_request_fields(service_request, client)
    changed = [
        field for field, value in updates.items()
        if getattr(item, field) != value
    ]
    if changed:
        for field in changed:
            setattr(item, field, updates[field])
        item.save(update_fields=[*changed, 'updated_at'])
        log_history(
            item,
            WorkloadHistory.ACTION_UPDATED,
            field_name='crm_request',
            note='Synchronised from CRM service request.',
        )
    return item


def sync_all_service_requests():
    from crm.models import ServiceRequest

    count = 0
    errors = 0
    for service_request in ServiceRequest.objects.select_related('customer__user').iterator():
        try:
            if sync_service_request(service_request):
                count += 1
        except Exception:
            errors += 1
            logger.exception('Failed to sync service request %s into workload', service_request.pk)
    return {'synced': count, 'errors': errors}


def sync_from_integrations():
    return {
        'projects': sync_all_project_tasks(),
        'crm': sync_all_service_requests(),
    }


# --------------------------------------------------------------------------- #
# Monitoring and alerts
# --------------------------------------------------------------------------- #
def _alert_severity_for_item(item):
    if item.priority == WorkItem.PRIORITY_CRITICAL:
        return WorkloadAlert.SEVERITY_CRITICAL
    if item.priority == WorkItem.PRIORITY_HIGH:
        return WorkloadAlert.SEVERITY_HIGH
    return WorkloadAlert.SEVERITY_MEDIUM


def _recipient_for_item(item):
    if item.assignee_id:
        return item.assignee
    if item.team_id and item.team.lead_id:
        return item.team.lead
    if item.created_by_id:
        return item.created_by
    return None


def refresh_alerts(*, tenant=None, policy=None, actor=None):
    """Recompute operational alerts with dedupe keys and auto-resolution."""
    policy = policy or WorkloadPolicy.get_for(tenant)
    today = timezone.localdate()
    week = today.isocalendar()
    week_key = f'{week[0]}-W{week[1]:02d}'
    desired = {}

    active_items = WorkItem.objects.filter(status__in=WorkItem.OPEN_STATUSES)
    if tenant is not None:
        active_items = active_items.filter(
            Q(tenant=tenant) | Q(tenant__isnull=True, assignee=tenant),
        )
    active_items = active_items.select_related(
        'assignee', 'team__lead', 'project',
    ).annotate(
        has_active_assignment=Exists(
            WorkAssignment.objects.filter(
                work_item=OuterRef('pk'),
                status=WorkAssignment.STATUS_ACTIVE,
            ),
        ),
    )

    resources = WorkloadResource.objects.filter(
        kind=WorkloadResource.KIND_PERSON,
        is_active=True,
        user__isnull=False,
    ).select_related('user', 'capacity')
    if tenant is not None:
        resources = resources.filter(
            Q(tenant=tenant) | Q(tenant__isnull=True, user=tenant),
        )

    from .selectors import resource_utilization_rows

    for row in resource_utilization_rows(resources, policy):
        resource = row['resource']
        if row['level'] == 'overloaded':
            key = f'overload:resource:{resource.pk}:{week_key}'
            desired[key] = {
                'alert_type': WorkloadAlert.TYPE_OVERLOAD,
                'severity': (
                    WorkloadAlert.SEVERITY_CRITICAL
                    if (row['utilization'] or 0) >= 125
                    else WorkloadAlert.SEVERITY_HIGH
                ),
                'resource': resource,
                'recipient': resource.user,
                'tenant': resource.tenant,
                'message': (
                    f'{resource.display_owner} is overloaded at '
                    f'{row["utilization_display"]} ({row["assigned_hours"]}h of '
                    f'{row["available_hours"]}h).'
                ),
                'metadata': {
                    'utilization': row['utilization'],
                    'assigned_hours': row['assigned_hours'],
                    'available_hours': row['available_hours'],
                },
            }
        elif row['level'] == 'available' and row['active_assignments']:
            key = f'underutilized:resource:{resource.pk}:{week_key}'
            desired[key] = {
                'alert_type': WorkloadAlert.TYPE_UNDERUTILIZED,
                'severity': WorkloadAlert.SEVERITY_LOW,
                'resource': resource,
                'recipient': resource.user,
                'tenant': resource.tenant,
                'message': (
                    f'{resource.display_owner} is underutilized at '
                    f'{row["utilization_display"]} ({row["assigned_hours"]}h of '
                    f'{row["available_hours"]}h).'
                ),
                'metadata': {
                    'utilization': row['utilization'],
                    'assigned_hours': row['assigned_hours'],
                    'available_hours': row['available_hours'],
                },
            }

    for item in active_items:
        if item.due_date and item.due_date < today:
            key = f'overdue:item:{item.pk}'
            desired[key] = {
                'alert_type': WorkloadAlert.TYPE_OVERDUE,
                'severity': _alert_severity_for_item(item),
                'work_item': item,
                'recipient': _recipient_for_item(item),
                'tenant': item.tenant,
                'message': f'"{item.title}" is overdue (due {item.due_date}).',
                'metadata': {'due_date': item.due_date.isoformat()},
            }
        elif item.due_date and today <= item.due_date <= today + timedelta(days=policy.deadline_warning_days):
            key = f'deadline:item:{item.pk}'
            desired[key] = {
                'alert_type': WorkloadAlert.TYPE_DEADLINE,
                'severity': _alert_severity_for_item(item),
                'work_item': item,
                'recipient': _recipient_for_item(item),
                'tenant': item.tenant,
                'message': (
                    f'"{item.title}" is due in '
                    f'{(item.due_date - today).days} day(s) ({item.due_date}).'
                ),
                'metadata': {'due_date': item.due_date.isoformat()},
            }
        if item.status == WorkItem.STATUS_BLOCKED:
            key = f'blocked:item:{item.pk}'
            desired[key] = {
                'alert_type': WorkloadAlert.TYPE_BLOCKED,
                'severity': _alert_severity_for_item(item),
                'work_item': item,
                'recipient': _recipient_for_item(item),
                'tenant': item.tenant,
                'message': f'"{item.title}" is blocked.',
                'metadata': {'reason': item.blocked_reason},
            }
        if (
            item.status in (WorkItem.STATUS_NEW, WorkItem.STATUS_PENDING)
            and item.assignee_id is None
            and item.team_id is None
            and not item.has_active_assignment
        ):
            key = f'unassigned:item:{item.pk}'
            desired[key] = {
                'alert_type': WorkloadAlert.TYPE_UNASSIGNED,
                'severity': _alert_severity_for_item(item),
                'work_item': item,
                'recipient': item.created_by,
                'tenant': item.tenant,
                'message': f'"{item.title}" has no assignee.',
                'metadata': {'priority': item.priority},
            }

    teams = WorkloadTeam.objects.filter(is_active=True)
    if tenant is not None:
        teams = teams.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
    teams = list(
        teams.select_related('lead').prefetch_related('members'),
    )
    for team in teams:
        member_ids = [member.id for member in team.members.all()]
        summary = team_capacity(team, policy, member_ids=member_ids)
        if summary['available_hours'] and summary['utilization'] is not None and summary['utilization'] > float(policy.team_capacity_warning_percent):
            key = f'team_capacity:team:{team.pk}:{week_key}'
            desired[key] = {
                'alert_type': WorkloadAlert.TYPE_TEAM_CAPACITY,
                'severity': (
                    WorkloadAlert.SEVERITY_CRITICAL
                    if summary['utilization'] > 100
                    else WorkloadAlert.SEVERITY_HIGH
                ),
                'team': team,
                'recipient': team.lead,
                'tenant': team.tenant,
                'message': (
                    f'{team.name} is at {summary["utilization_display"]} capacity '
                    f'({summary["assigned_hours"]}h of {summary["available_hours"]}h).'
                ),
                'metadata': {
                    key: value for key, value in summary.items() if key != 'team'
                },
            }

        member_ids = [member.id for member in team.members.all()]
        problem_items = active_items.filter(
            Q(team=team)
            | Q(assignee_id__in=member_ids)
            | Q(status=WorkItem.STATUS_BLOCKED, team=team)
            | Q(due_date__lt=today, team=team),
        ).distinct()
        blocked_or_overdue = problem_items.filter(
            Q(status=WorkItem.STATUS_BLOCKED) | Q(due_date__lt=today),
        ).count()
        if blocked_or_overdue >= policy.bottleneck_threshold:
            key = f'bottleneck:team:{team.pk}:{week_key}'
            desired[key] = {
                'alert_type': WorkloadAlert.TYPE_BOTTLENECK,
                'severity': WorkloadAlert.SEVERITY_HIGH,
                'team': team,
                'recipient': team.lead,
                'tenant': team.tenant,
                'message': (
                    f'{team.name} has {blocked_or_overdue} blocked or overdue items '
                    f'this week.'
                ),
                'metadata': {'blocked_or_overdue': blocked_or_overdue},
            }

    created_count = 0
    updated_count = 0
    with transaction.atomic():
        for key, data in desired.items():
            existing = WorkloadAlert.objects.filter(dedupe_key=key).first()
            if existing:
                for field, value in data.items():
                    setattr(existing, field, value)
                existing.status = WorkloadAlert.STATUS_OPEN
                existing.resolved_at = None
                existing.save()
                updated_count += 1
            else:
                alert = WorkloadAlert.objects.create(dedupe_key=key, **data)
                created_count += 1
                if alert.recipient_id:
                    notify_user(
                        alert.recipient,
                        alert.message,
                        project=alert.work_item.project if alert.work_item_id else None,
                        severity=alert.severity,
                        notification_type=(
                            'DELAY'
                            if alert.alert_type in (
                                WorkloadAlert.TYPE_OVERDUE,
                                WorkloadAlert.TYPE_DEADLINE,
                            )
                            else 'STATUS'
                        ),
                    )

        stale = WorkloadAlert.objects.filter(
            status__in=[WorkloadAlert.STATUS_OPEN, WorkloadAlert.STATUS_ACKNOWLEDGED],
            alert_type__in=MANAGED_ALERT_TYPES,
        )
        if tenant is not None:
            stale = stale.filter(tenant=tenant)
        if desired:
            stale = stale.exclude(dedupe_key__in=desired.keys())
        resolved_count = stale.update(
            status=WorkloadAlert.STATUS_RESOLVED,
            resolved_at=timezone.now(),
        )

    logger.info(
        'Workload alert refresh: %s created, %s updated, %s resolved',
        created_count, updated_count, resolved_count,
    )
    return {
        'created': created_count,
        'updated': updated_count,
        'resolved': resolved_count,
        'open': WorkloadAlert.objects.filter(status=WorkloadAlert.STATUS_OPEN).count(),
    }


def acknowledge_alert(alert, actor):
    if not is_manager(actor):
        raise PermissionDenied('Only managers can acknowledge workload alerts.')
    alert.status = WorkloadAlert.STATUS_ACKNOWLEDGED
    alert.acknowledged_at = timezone.now()
    alert.acknowledged_by = actor
    alert.save(update_fields=['status', 'acknowledged_at', 'acknowledged_by', 'updated_at'])
    return alert


def resolve_alert(alert, actor):
    if not is_manager(actor):
        raise PermissionDenied('Only managers can resolve workload alerts.')
    alert.status = WorkloadAlert.STATUS_RESOLVED
    alert.resolved_at = timezone.now()
    alert.save(update_fields=['status', 'resolved_at', 'updated_at'])
    return alert


METRIC_SNAPSHOT_DROP_KEYS = frozenset({
    'employee_distribution',
    'team_distribution',
    'department_distribution',
    'live_alerts',
    'stored_alerts',
})


def _json_safe(value):
    """Coerce a dashboard value into something ``JSONField`` can store.

    Dashboard metrics mix scalars with model instances (resource rows, live
    alerts).  Snapshots only keep primitives, so anything that is not directly
    serialisable degrades to ``None`` instead of raising on save.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return None


def build_metric_snapshot(metrics, *, captured_at=None):
    """Turn ``dashboard_metrics`` output into a JSON-safe snapshot payload."""
    snapshot = {
        key: _json_safe(value)
        for key, value in metrics.items()
        if key not in METRIC_SNAPSHOT_DROP_KEYS
    }
    snapshot['captured_at'] = (captured_at or timezone.now()).isoformat()
    return snapshot


def capture_metrics(*, tenant=None):
    """Persist org/team/resource metric snapshots for trend reporting."""
    from .selectors import dashboard_metrics, resource_utilization_rows, team_capacity_rows

    today = timezone.localdate()
    policy = WorkloadPolicy.get_for(tenant)

    resources = WorkloadResource.objects.filter(
        kind=WorkloadResource.KIND_PERSON, is_active=True,
    )
    if tenant is not None:
        resources = resources.filter(
            Q(tenant=tenant) | Q(tenant__isnull=True, user=tenant),
        )
    teams = WorkloadTeam.objects.filter(is_active=True)
    if tenant is not None:
        teams = teams.filter(Q(tenant=tenant) | Q(tenant__isnull=True))

    # Compute the shared row sets once and reuse them for the org snapshot,
    # resource rows and team rows instead of querying three times.
    resource_rows = resource_utilization_rows(resources, policy)
    team_rows = team_capacity_rows(teams, policy)

    with transaction.atomic():
        metrics = dashboard_metrics(
            tenant=tenant,
            policy=policy,
            resource_rows=resource_rows,
            team_rows=team_rows,
        )
        WorkloadMetric.objects.filter(tenant=tenant, metric_date=today).delete()
        created = 0
        WorkloadMetric.objects.create(
            tenant=tenant,
            metric_date=today,
            scope=WorkloadMetric.SCOPE_ORG,
            data=build_metric_snapshot(metrics),
        )
        created += 1
        for row in resource_rows:
            WorkloadMetric.objects.create(
                tenant=tenant,
                metric_date=today,
                scope=WorkloadMetric.SCOPE_RESOURCE,
                resource=row['resource'],
                data={
                    'assigned_hours': row['assigned_hours'],
                    'available_hours': row['available_hours'],
                    'utilization': row['utilization'],
                    'level': row['level'],
                },
            )
            created += 1
        for row in team_rows:
            WorkloadMetric.objects.create(
                tenant=tenant,
                metric_date=today,
                scope=WorkloadMetric.SCOPE_TEAM,
                team=row['team'],
                data={
                    'assigned_hours': row['assigned_hours'],
                    'available_hours': row['available_hours'],
                    'utilization': row['utilization'],
                    'level': row['level'],
                },
            )
            created += 1
    return created


# --------------------------------------------------------------------------- #
# Attachments
# --------------------------------------------------------------------------- #
def attach_file(work_item, uploaded_file, actor=None):
    attachment = WorkItemAttachment.objects.create(
        work_item=work_item,
        file=uploaded_file,
        original_name=getattr(uploaded_file, 'name', '')[:255],
        uploaded_by=actor if actor and actor.is_authenticated else None,
    )
    log_history(
        work_item,
        WorkloadHistory.ACTION_UPDATED,
        actor=actor,
        field_name='attachment',
        new_value=attachment.original_name,
    )
    return attachment
