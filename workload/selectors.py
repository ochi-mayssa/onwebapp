"""Read-side queries, filtering and analytics for workload management."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Case, Count, IntegerField, Q, When
from django.db.models.functions import TruncWeek
from django.utils import timezone

from .models import (
    DECIMAL_ZERO,
    WorkAssignment,
    WorkItem,
    WorkloadAlert,
    WorkloadPolicy,
    WorkloadResource,
    WorkloadTeam,
)
from .services import (
    LEVEL_LABELS,
    assigned_hours_map,
    calculate_utilization,
    classify_utilization,
    get_effective_capacity,
    team_capacity,
)

PRIORITY_RANK = {
    WorkItem.PRIORITY_CRITICAL: 0,
    WorkItem.PRIORITY_HIGH: 1,
    WorkItem.PRIORITY_MEDIUM: 2,
    WorkItem.PRIORITY_LOW: 3,
}

SORT_OPTIONS = {
    'due': ('due_date', 'priority_rank'),
    '-due': ('-due_date',),
    'priority': ('priority_rank', 'due_date'),
    '-priority': ('-priority_rank',),
    'created': ('created_at',),
    '-created': ('-created_at',),
    'title': ('title',),
    '-title': ('-title',),
    'status': ('status', 'due_date'),
}


def work_item_queryset():
    return WorkItem.objects.select_related(
        'assignee', 'team', 'client', 'project', 'created_by', 'automation_workflow',
    ).prefetch_related(
        'required_skills', 'attachments', 'assignments__resource',
    )


def resource_queryset():
    return WorkloadResource.objects.select_related(
        'user', 'team', 'capacity',
    ).prefetch_related('skills')


def filter_work_items(queryset, params):
    """Apply the documented list filters and safe sorting."""
    q = (params.get('q') or '').strip()
    if q:
        queryset = queryset.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(external_reference__icontains=q)
            | Q(project__title__icontains=q)
            | Q(client__name__icontains=q)
            | Q(assignee__username__icontains=q)
            | Q(assignee__first_name__icontains=q)
            | Q(assignee__last_name__icontains=q)
        )

    for key, field in (
        ('status', 'status'),
        ('priority', 'priority'),
        ('category', 'category'),
        ('source', 'source_module'),
    ):
        value = (params.get(key) or '').strip()
        if value:
            queryset = queryset.filter(**{field: value})

    team_id = (params.get('team') or '').strip()
    if team_id.isdigit():
        queryset = queryset.filter(team_id=int(team_id))
    assignee_id = (params.get('assignee') or '').strip()
    if assignee_id == 'unassigned':
        queryset = queryset.filter(assignee__isnull=True, team__isnull=True)
    elif assignee_id.isdigit():
        queryset = queryset.filter(
            Q(assignee_id=int(assignee_id))
            | Q(assignments__resource__user_id=int(assignee_id), assignments__status=WorkAssignment.STATUS_ACTIVE)
        ).distinct()
    project_id = (params.get('project') or '').strip()
    if project_id.isdigit():
        queryset = queryset.filter(project_id=int(project_id))
    client_id = (params.get('client') or '').strip()
    if client_id.isdigit():
        queryset = queryset.filter(client_id=int(client_id))

    if params.get('overdue') in ('1', 'true', 'on'):
        queryset = queryset.filter(
            due_date__lt=timezone.localdate(),
            status__in=WorkItem.OPEN_STATUSES,
        )
    if params.get('blocked') in ('1', 'true', 'on'):
        queryset = queryset.filter(status=WorkItem.STATUS_BLOCKED)
    if params.get('unassigned') in ('1', 'true', 'on'):
        queryset = queryset.filter(assignee__isnull=True, team__isnull=True).filter(
            status__in=[WorkItem.STATUS_NEW, WorkItem.STATUS_PENDING],
        )
    if params.get('automation') in ('1', 'true', 'on'):
        queryset = queryset.filter(automation_eligible=True)
    due_before = (params.get('due_before') or '').strip()
    if due_before:
        queryset = queryset.filter(due_date__lte=due_before)
    due_after = (params.get('due_after') or '').strip()
    if due_after:
        queryset = queryset.filter(due_date__gte=due_after)

    sort = (params.get('sort') or '-created').strip()
    order = SORT_OPTIONS.get(sort, SORT_OPTIONS['-created'])
    if sort in ('due', 'priority', '-priority'):
        queryset = queryset.annotate(
            priority_rank=Case(
                When(priority=WorkItem.PRIORITY_CRITICAL, then=0),
                When(priority=WorkItem.PRIORITY_HIGH, then=1),
                When(priority=WorkItem.PRIORITY_MEDIUM, then=2),
                default=3,
                output_field=IntegerField(),
            ),
        )
    return queryset.order_by(*order)


def resource_utilization_rows(resources=None, policy=None):
    """Bulk utilisation rows (three queries regardless of resource count)."""
    policy = policy or WorkloadPolicy.get_for()
    if resources is None:
        resources = resource_queryset().filter(is_active=True)
    resources = list(resources)
    if not resources:
        return []

    ids = [r.pk for r in resources]
    hours_map = assigned_hours_map(ids)
    counts = {
        row['resource_id']: row['count']
        for row in WorkAssignment.objects.filter(
            resource_id__in=ids,
            status=WorkAssignment.STATUS_ACTIVE,
            work_item__status__in=WorkItem.OPEN_STATUSES,
        )
        .values('resource_id')
        .annotate(count=Count('id'))
    }

    rows = []
    for resource in resources:
        available, capacity_source, is_assumed = get_effective_capacity(resource, policy)
        assigned = hours_map.get(resource.pk, DECIMAL_ZERO)
        available = Decimal(str(available or 0))
        assigned = Decimal(str(assigned or 0))
        if available <= 0:
            utilization = None
            level = 'overloaded' if assigned > 0 else 'unavailable'
        else:
            utilization = round(float(assigned / available) * 100, 1)
            level = classify_utilization(utilization, available, policy)
        rows.append({
            'resource': resource,
            'assigned_hours': round(float(assigned), 1),
            'available_hours': round(float(available), 1),
            'utilization': utilization,
            'utilization_display': '—' if utilization is None else f'{utilization:.1f}%',
            'level': level,
            'level_label': LEVEL_LABELS.get(level, level.title()),
            'has_capacity': not is_assumed,
            'is_assumed_capacity': is_assumed,
            'capacity_source': capacity_source,
            'active_assignments': counts.get(resource.pk, 0),
            'availability_status': resource.availability_status,
            'skills': [s.name for s in resource.skills.all()],
        })
    return rows


def team_capacity_rows(teams=None, policy=None):
    policy = policy or WorkloadPolicy.get_for()
    if teams is None:
        teams = WorkloadTeam.objects.filter(is_active=True).select_related(
            'lead',
        ).prefetch_related('members')
    teams = list(teams)

    # Fetch every member and resource once, then reuse the maps for each team.
    member_ids_by_team = {}
    all_member_ids = set()
    for team in teams:
        ids = [member.id for member in team.members.all()]
        member_ids_by_team[team.pk] = ids
        all_member_ids.update(ids)
    resources = list(
        WorkloadResource.objects.filter(
            kind=WorkloadResource.KIND_PERSON,
            user_id__in=all_member_ids,
            is_active=True,
        ).select_related('capacity'),
    )
    resources_by_user = defaultdict(list)
    for resource in resources:
        resources_by_user[resource.user_id].append(resource)
    hours_map = assigned_hours_map([r.pk for r in resources])

    rows = []
    for team in teams:
        member_ids = member_ids_by_team[team.pk]
        team_resources = [
            resource
            for user_id in member_ids
            for resource in resources_by_user.get(user_id, [])
        ]
        summary = team_capacity(
            team,
            policy,
            member_ids=member_ids,
            resources=team_resources,
            hours_map=hours_map,
        )
        summary['members'] = list(team.members.all())[:12]
        summary['open_items'] = summary.get('active_items', 0)
        rows.append(summary)
    rows.sort(key=lambda row: (row['utilization'] or -1), reverse=True)
    return rows


def department_rows(teams=None, policy=None):
    """Aggregate unique member capacity by department."""
    policy = policy or WorkloadPolicy.get_for()
    if teams is None:
        teams = WorkloadTeam.objects.filter(is_active=True).prefetch_related('members')
    teams = list(teams)
    departments = defaultdict(set)
    for team in teams:
        key = team.department or 'Unassigned'
        departments[key].update(member.id for member in team.members.all())

    all_user_ids = set().union(*departments.values()) if departments else set()
    resources = list(
        WorkloadResource.objects.filter(
            kind=WorkloadResource.KIND_PERSON,
            user_id__in=all_user_ids,
            is_active=True,
        ).select_related('capacity'),
    )
    resources_by_user = defaultdict(list)
    for resource in resources:
        resources_by_user[resource.user_id].append(resource)
    hours_map = assigned_hours_map([r.pk for r in resources])

    rows = []
    for department, user_ids in departments.items():
        dept_resources = [
            resource
            for user_id in user_ids
            for resource in resources_by_user.get(user_id, [])
        ]
        if not dept_resources:
            continue
        assigned = sum(
            (hours_map.get(r.pk, DECIMAL_ZERO) for r in dept_resources),
            DECIMAL_ZERO,
        )
        available = sum(
            (Decimal(str(get_effective_capacity(r, policy)[0] or 0)) for r in dept_resources),
            DECIMAL_ZERO,
        )
        utilization = round(float(assigned / available) * 100, 1) if available > 0 else None
        level = classify_utilization(utilization, available, policy)
        rows.append({
            'department': department,
            'people': len(dept_resources),
            'assigned_hours': round(float(assigned), 1),
            'available_hours': round(float(available), 1),
            'utilization': utilization,
            'utilization_display': '—' if utilization is None else f'{utilization:.1f}%',
            'level': level,
            'level_label': LEVEL_LABELS.get(level, level.title()),
        })
    rows.sort(key=lambda row: (row['utilization'] or -1), reverse=True)
    return rows


def _choice_counts(queryset, field, choices):
    counts = {row[field]: row['count'] for row in queryset.values(field).annotate(count=Count('id'))}
    total = sum(counts.values()) or 1
    rows = []
    for value, label in choices:
        count = counts.get(value, 0)
        rows.append({
            'value': value,
            'label': str(label),
            'count': count,
            'percent': round(count / total * 100, 1),
        })
    return rows


def _avg_completion_hours(items):
    rows = items.filter(completed_at__isnull=False).values_list('created_at', 'completed_at')
    durations = [
        (completed - created).total_seconds() / 3600
        for created, completed in rows
        if created and completed
    ]
    if not durations:
        return None
    return round(sum(durations) / len(durations), 1)


def _on_time_rate(items):
    completed = items.filter(status=WorkItem.STATUS_COMPLETED, due_date__isnull=False, completed_at__isnull=False)
    rows = list(completed.values_list('due_date', 'completed_at'))
    if not rows:
        return None, 0, 0
    on_time = sum(1 for due, completed in rows if timezone.localtime(completed).date() <= due)
    return round(on_time / len(rows) * 100, 1), on_time, len(rows)


def trend_series(items, weeks=8):
    """Created/completed counts for the last N weeks, ready for CSS bars."""
    today = timezone.localdate()
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    start_dt = timezone.make_aware(datetime.combine(start, time.min))
    created_rows = {
        row['week'].date(): row['count']
        for row in items.filter(created_at__gte=start_dt)
        .annotate(week=TruncWeek('created_at'))
        .values('week')
        .annotate(count=Count('id'))
    }
    completed_rows = {
        row['week'].date(): row['count']
        for row in items.filter(completed_at__gte=start_dt)
        .annotate(week=TruncWeek('completed_at'))
        .values('week')
        .annotate(count=Count('id'))
    }
    series = []
    max_value = 1
    for index in range(weeks):
        week_start = start + timedelta(weeks=index)
        created = created_rows.get(week_start, 0)
        completed = completed_rows.get(week_start, 0)
        max_value = max(max_value, created, completed)
        series.append({
            'week_start': week_start,
            'label': week_start.strftime('%b %d'),
            'created': created,
            'completed': completed,
        })
    for row in series:
        row['created_height'] = round(row['created'] / max_value * 100, 1)
        row['completed_height'] = round(row['completed'] / max_value * 100, 1)
    return series


def automation_candidates(limit=20, items=None):
    if items is None:
        items = WorkItem.objects.all()
    return (
        items.filter(
            status__in=WorkItem.OPEN_STATUSES,
            automation_eligible=True,
            automation_workflow__isnull=True,
        )
        .select_related('assignee', 'team')
        .order_by('-priority', 'due_date')[:limit]
    )


def live_operational_alerts(
    items, *, policy=None, resources=None, teams=None,
    resource_rows=None, team_rows=None,
):
    """Compute the operational alert lists shown on dashboards (no writes)."""
    policy = policy or WorkloadPolicy.get_for()
    today = timezone.localdate()
    warning = today + timedelta(days=policy.deadline_warning_days)
    open_items = items.filter(status__in=WorkItem.OPEN_STATUSES)
    if resources is None:
        resources = resource_queryset().filter(kind=WorkloadResource.KIND_PERSON, is_active=True)
    if resource_rows is None:
        resource_rows = resource_utilization_rows(resources, policy)
    if teams is None:
        teams = WorkloadTeam.objects.filter(is_active=True)
    if team_rows is None:
        team_rows = team_capacity_rows(teams, policy)

    return {
        'overloaded_resources': [r for r in resource_rows if r['level'] == 'overloaded'],
        'underutilized_resources': [
            r for r in resource_rows
            if r['level'] == 'available' and r['active_assignments']
        ],
        'overdue_items': list(
            open_items.filter(due_date__lt=today).select_related('assignee', 'team')[:50],
        ),
        'deadline_items': list(
            open_items.filter(due_date__gte=today, due_date__lte=warning)
            .select_related('assignee', 'team')[:50],
        ),
        'blocked_items': list(
            open_items.filter(status=WorkItem.STATUS_BLOCKED).select_related('assignee', 'team')[:50],
        ),
        'unassigned_items': list(
            open_items.filter(
                status__in=[WorkItem.STATUS_NEW, WorkItem.STATUS_PENDING],
                assignee__isnull=True,
                team__isnull=True,
            ).select_related('client', 'project')[:50],
        ),
        'team_capacity_issues': [
            row for row in team_rows
            if row['utilization'] is not None
            and row['utilization'] > float(policy.team_capacity_warning_percent)
        ],
        'team_rows': team_rows,
        'resource_rows': resource_rows,
        'automation_candidates': list(automation_candidates(items=items)),
    }


def dashboard_metrics(
    *, tenant=None, team=None, work_items=None, policy=None,
    resource_rows=None, team_rows=None,
):
    """Build every dashboard metric from live database records."""
    policy = policy or WorkloadPolicy.get_for(tenant)
    items = work_items if work_items is not None else WorkItem.objects.all()
    if work_items is None and tenant is not None:
        items = items.filter(tenant=tenant)
    if team is not None:
        items = items.filter(
            Q(team=team) | Q(assignee__in=team.members.values('id')),
        )

    total = items.count()
    active = items.filter(status__in=WorkItem.OPEN_STATUSES).count()
    completed = items.filter(status=WorkItem.STATUS_COMPLETED).count()
    cancelled = items.filter(status=WorkItem.STATUS_CANCELLED).count()
    blocked = items.filter(status=WorkItem.STATUS_BLOCKED).count()
    overdue = items.filter(
        due_date__lt=timezone.localdate(), status__in=WorkItem.OPEN_STATUSES,
    ).count()
    pending_assignments = items.filter(
        status__in=[WorkItem.STATUS_NEW, WorkItem.STATUS_PENDING],
        assignee__isnull=True,
        team__isnull=True,
    ).count()
    unassigned = items.filter(
        status__in=WorkItem.OPEN_STATUSES,
        assignee__isnull=True,
        team__isnull=True,
    ).count()
    due_soon = items.filter(
        due_date__gte=timezone.localdate(),
        due_date__lte=timezone.localdate() + timedelta(days=policy.deadline_warning_days),
        status__in=WorkItem.OPEN_STATUSES,
    ).count()

    if resource_rows is None:
        resources = resource_queryset().filter(
            kind=WorkloadResource.KIND_PERSON, is_active=True,
        )
        if tenant is not None:
            resources = resources.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True, user=tenant),
            )
        resource_rows = resource_utilization_rows(resources, policy)
    total_available = sum(row['available_hours'] for row in resource_rows)
    total_assigned = sum(row['assigned_hours'] for row in resource_rows)
    overall_utilization = (
        round(total_assigned / total_available * 100, 1) if total_available > 0 else None
    )

    teams = WorkloadTeam.objects.filter(is_active=True)
    if tenant is not None:
        teams = teams.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
    if team is not None:
        teams = teams.filter(pk=team.pk)
    if team_rows is None:
        team_rows = team_capacity_rows(teams, policy)

    avg_completion = _avg_completion_hours(items)
    on_time_rate, on_time_count, completed_with_due = _on_time_rate(items)
    automated_count = items.filter(
        Q(category=WorkItem.CATEGORY_AUTOMATED) | Q(automation_workflow__isnull=False),
    ).count()
    automation_rate = round(automated_count / total * 100, 1) if total else None
    candidates_count = items.filter(
        status__in=WorkItem.OPEN_STATUSES,
        automation_eligible=True,
        automation_workflow__isnull=True,
    ).count()

    alerts = WorkloadAlert.objects.all()
    if tenant is not None:
        alerts = alerts.filter(
            Q(tenant=tenant) | Q(tenant__isnull=True, recipient=tenant),
        )
    thirty_days_ago = timezone.now() - timedelta(days=30)
    overload_frequency = alerts.filter(
        alert_type=WorkloadAlert.TYPE_OVERLOAD, created_at__gte=thirty_days_ago,
    ).count()
    bottleneck_frequency = alerts.filter(
        alert_type=WorkloadAlert.TYPE_BOTTLENECK, created_at__gte=thirty_days_ago,
    ).count()

    live = live_operational_alerts(
        items,
        policy=policy,
        teams=teams,
        resource_rows=resource_rows,
        team_rows=team_rows,
    )

    return {
        'total': total,
        'active': active,
        'completed': completed,
        'cancelled': cancelled,
        'blocked': blocked,
        'overdue': overdue,
        'pending_assignments': pending_assignments,
        'unassigned': unassigned,
        'due_soon': due_soon,
        'automation_eligible': items.filter(automation_eligible=True).count(),
        'overall_utilization': overall_utilization,
        'overall_utilization_display': (
            '—' if overall_utilization is None else f'{overall_utilization:.1f}%'
        ),
        'total_available_hours': round(total_available, 1),
        'total_assigned_hours': round(total_assigned, 1),
        'resource_count': len(resource_rows),
        'avg_completion_hours': avg_completion,
        'avg_completion_display': (
            '—' if avg_completion is None else f'{avg_completion:.1f}h'
        ),
        'on_time_rate': on_time_rate,
        'on_time_count': on_time_count,
        'completed_with_due': completed_with_due,
        'automation_rate': automation_rate,
        'automation_candidates_count': candidates_count,
        'overload_frequency': overload_frequency,
        'bottleneck_frequency': bottleneck_frequency,
        'priority_distribution': _choice_counts(items, 'priority', WorkItem.PRIORITY_CHOICES),
        'category_distribution': _choice_counts(items, 'category', WorkItem.CATEGORY_CHOICES),
        'status_distribution': _choice_counts(items, 'status', WorkItem.STATUS_CHOICES),
        'employee_distribution': sorted(
            resource_rows, key=lambda row: (row['utilization'] or -1), reverse=True,
        )[:25],
        'team_distribution': team_rows,
        'department_distribution': department_rows(teams, policy),
        'trend': trend_series(items),
        'live_alerts': live,
        'stored_alerts': list(
            alerts.filter(status__in=[WorkloadAlert.STATUS_OPEN, WorkloadAlert.STATUS_ACKNOWLEDGED])
            .select_related('work_item', 'resource', 'team', 'recipient')[:10],
        ),
    }


def monitoring_snapshot(*, tenant=None, team=None, work_items=None, policy=None):
    policy = policy or WorkloadPolicy.get_for(tenant)
    items = work_items if work_items is not None else WorkItem.objects.all()
    if work_items is None and tenant is not None:
        items = items.filter(tenant=tenant)
    if team is not None:
        items = items.filter(Q(team=team) | Q(assignee__in=team.members.values('id')))
    resources = resource_queryset().filter(kind=WorkloadResource.KIND_PERSON, is_active=True)
    if tenant is not None:
        resources = resources.filter(Q(tenant=tenant) | Q(tenant__isnull=True, user=tenant))
    teams = WorkloadTeam.objects.filter(is_active=True)
    if tenant is not None:
        teams = teams.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
    if team is not None:
        teams = teams.filter(pk=team.pk)
    resource_rows = resource_utilization_rows(resources, policy)
    team_rows = team_capacity_rows(teams, policy)
    snapshot = live_operational_alerts(
        items,
        policy=policy,
        resource_rows=resource_rows,
        team_rows=team_rows,
    )
    snapshot['policy'] = policy
    return snapshot
