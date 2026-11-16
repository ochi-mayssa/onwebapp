"""Views for the workload management workspace."""
from __future__ import annotations

import logging
import os

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    AssignWorkForm,
    BulkActionForm,
    ResourceCapacityForm,
    WorkItemAttachmentForm,
    WorkItemForm,
    WorkItemStatusForm,
    WorkloadPolicyForm,
    WorkloadResourceForm,
    WorkloadTeamForm,
)
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
    admin_required,
    assignable_users,
    can_change_status,
    can_edit_work_item,
    get_role,
    is_admin,
    is_global_manager,
    is_manager,
    login_required_workload,
    manager_required,
    scope_alerts,
    scope_policies,
    scope_resources,
    scope_teams,
    scope_work_items,
)
from .selectors import (
    dashboard_metrics,
    filter_work_items,
    monitoring_snapshot,
    resource_utilization_rows,
    team_capacity_rows,
    work_item_queryset,
)
from .services import (
    acknowledge_alert,
    approve_recommendation,
    assign_work,
    attach_file,
    calculate_utilization,
    cancel_assignment,
    create_work_item_from_service_request,
    log_history,
    record_field_changes,
    refresh_alerts,
    reject_recommendation,
    recommend_assignees,
    resolve_alert,
    store_recommendations,
    sync_from_integrations,
    update_status,
)

logger = logging.getLogger(__name__)
User = get_user_model()


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _navigation_context(user):
    role = get_role(user)
    return {
        'workload_role': role,
        'can_manage_workload': is_manager(user),
        'can_configure_workload': is_admin(user),
        'workload_nav': 'dashboard',
    }


def _scoped_items(user):
    return scope_work_items(work_item_queryset(), user)


def _scoped_item_or_404(user, pk):
    return get_object_or_404(_scoped_items(user), pk=pk)


def _paginate(request, rows, per_page=20):
    paginator = Paginator(rows, per_page)
    return paginator.get_page(request.GET.get('page'))


def _team_from_request(request, user=None):
    team_id = (request.GET.get('team') or '').strip()
    if team_id.isdigit():
        teams = WorkloadTeam.objects.filter(pk=int(team_id))
        if user is not None:
            teams = scope_teams(teams, user)
        return teams.first()
    return None


def _item_summary(queryset):
    today = timezone.localdate()
    return {
        'total': queryset.count(),
        'active': queryset.filter(status__in=WorkItem.OPEN_STATUSES).count(),
        'overdue': queryset.filter(
            due_date__lt=today, status__in=WorkItem.OPEN_STATUSES,
        ).count(),
        'unassigned': queryset.filter(
            status__in=[WorkItem.STATUS_NEW, WorkItem.STATUS_PENDING],
            assignee__isnull=True,
            team__isnull=True,
        ).count(),
        'blocked': queryset.filter(status=WorkItem.STATUS_BLOCKED).count(),
    }


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@login_required_workload
def dashboard(request):
    user = request.user
    manager = is_manager(user)
    global_view = is_global_manager(user)
    tenant = None if global_view else user
    team = _team_from_request(request, user)
    policy = WorkloadPolicy.get_for(tenant)
    items = _scoped_items(user)
    if team is not None:
        items = items.filter(Q(team=team) | Q(assignee__in=team.members.values('id')))
    metrics = dashboard_metrics(
        work_items=items,
        tenant=tenant,
        team=team,
        policy=policy,
    )
    personal = None
    if not manager:
        resource = WorkloadResource.objects.filter(user=user).select_related('capacity').first()
        if resource:
            personal = calculate_utilization(resource, policy)
    my_items = items.filter(
        Q(assignee=user) | Q(assignments__resource__user=user),
        status__in=WorkItem.OPEN_STATUSES,
    ).distinct().order_by('due_date')[:8]
    context = {
        **_navigation_context(user),
        'workload_nav': 'dashboard',
        'metrics': metrics,
        'personal': personal,
        'my_items': my_items,
        'teams': scope_teams(WorkloadTeam.objects.filter(is_active=True), user),
        'selected_team': team,
        'policy': policy,
        'today': timezone.localdate(),
    }
    return render(request, 'workload/dashboard.html', context)


# --------------------------------------------------------------------------- #
# Work items
# --------------------------------------------------------------------------- #
@login_required_workload
def work_item_list(request):
    user = request.user
    base = _scoped_items(user)
    items = filter_work_items(base, request.GET)
    page_obj = _paginate(request, items, 20)
    context = {
        **_navigation_context(user),
        'workload_nav': 'items',
        'page_obj': page_obj,
        'items': page_obj.object_list,
        'summary': _item_summary(base),
        'status_choices': WorkItem.STATUS_CHOICES,
        'priority_choices': WorkItem.PRIORITY_CHOICES,
        'category_choices': WorkItem.CATEGORY_CHOICES,
        'source_choices': WorkItem.SOURCE_CHOICES,
        'teams': scope_teams(WorkloadTeam.objects.filter(is_active=True), user),
        'assignable_users': (
            assignable_users(user)
            if is_manager(user) else []
        ),
        'filters': request.GET,
        'sort_options': [
            ('-created', 'Newest first'),
            ('due', 'Due date'),
            ('priority', 'Priority'),
            ('title', 'Title'),
            ('status', 'Status'),
        ],
    }
    return render(request, 'workload/work_item_list.html', context)


@login_required_workload
def work_item_create(request):
    user = request.user
    if get_role(user) == 'client':
        raise PermissionDenied('Clients cannot create internal work items.')
    form = WorkItemForm(request.POST or None, actor=user)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        item.created_by = user
        if not is_manager(user):
            item.tenant = user
            item.assignee = user
            item.team = None
            item.is_client_visible = False
            if item.status in (WorkItem.STATUS_NEW, WorkItem.STATUS_PENDING):
                item.status = WorkItem.STATUS_ASSIGNED
        elif item.client_id and item.client.user_id:
            item.tenant = item.client.user
        elif item.team_id and item.team.tenant_id:
            item.tenant = item.team.tenant
        elif not is_global_manager(user):
            item.tenant = user
        item.save()
        form.save_m2m()
        log_history(item, 'CREATED', actor=user, note='Work item created.')
        if is_manager(user):
            if form.cleaned_data.get('assignee'):
                assign_work(
                    item,
                    user=form.cleaned_data['assignee'],
                    actor=user,
                    allocated_hours=item.remaining_hours,
                    approve=True,
                )
            elif form.cleaned_data.get('team'):
                assign_work(
                    item,
                    team=form.cleaned_data['team'],
                    actor=user,
                    allocated_hours=item.remaining_hours,
                    approve=True,
                )
        messages.success(request, f'Work item “{item.title}” created.')
        return redirect('workload:work_item_detail', pk=item.pk)

    context = {
        **_navigation_context(user),
        'workload_nav': 'items',
        'form': form,
        'is_create': True,
    }
    return render(request, 'workload/work_item_form.html', context)


@manager_required
def work_item_edit(request, pk):
    item = _scoped_item_or_404(request.user, pk)
    before = {
        'title': item.title,
        'description': item.description,
        'category': item.category,
        'priority': item.priority,
        'status': item.status,
        'assignee': item.assignee,
        'team': item.team,
        'client': item.client,
        'project': item.project,
        'estimated_hours': item.estimated_hours,
        'actual_hours': item.actual_hours,
        'start_date': item.start_date,
        'due_date': item.due_date,
        'is_client_visible': item.is_client_visible,
        'automation_eligible': item.automation_eligible,
    }
    old_assignee_id = item.assignee_id
    old_team_id = item.team_id
    form = WorkItemForm(request.POST or None, instance=item, actor=request.user)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        if item.client_id and item.client.user_id:
            item.tenant = item.client.user
        elif item.team_id and item.team.tenant_id:
            item.tenant = item.team.tenant
        elif not is_global_manager(request.user):
            item.tenant = request.user
        item.save()
        form.save_m2m()
        after = {
            key: getattr(item, key) for key in before
        }
        record_field_changes(item, request.user, before, after)
        if item.assignee_id and item.assignee_id != old_assignee_id:
            assign_work(
                item, user=item.assignee, actor=request.user,
                allocated_hours=item.remaining_hours, approve=True,
                notes='Assignment updated from edit form.',
            )
        elif item.team_id and item.team_id != old_team_id:
            assign_work(
                item, team=item.team, actor=request.user,
                allocated_hours=item.remaining_hours, approve=True,
                notes='Team assignment updated from edit form.',
            )
        elif not item.assignee_id and not item.team_id:
            # Clearing the owner must release any reserved capacity.
            for assignment in item.assignments.filter(
                status=WorkAssignment.STATUS_ACTIVE,
            ):
                cancel_assignment(
                    assignment, request.user,
                    note='Assignment cleared from the edit form.',
                )
            if item.status in (WorkItem.STATUS_ASSIGNED, WorkItem.STATUS_IN_PROGRESS):
                item.status = WorkItem.STATUS_PENDING
                item.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Work item updated.')
        return redirect('workload:work_item_detail', pk=item.pk)

    context = {
        **_navigation_context(request.user),
        'workload_nav': 'items',
        'form': form,
        'item': item,
        'is_create': False,
    }
    return render(request, 'workload/work_item_form.html', context)


@login_required_workload
def work_item_detail(request, pk):
    user = request.user
    item = _scoped_item_or_404(user, pk)
    assignments = item.assignments.select_related(
        'resource__user', 'assigned_by', 'approved_by',
    ).all()
    recommendations = []
    if is_manager(user):
        recommendations = recommend_assignees(item, limit=5, actor=user)
    context = {
        **_navigation_context(user),
        'workload_nav': 'items',
        'item': item,
        'assignments': assignments,
        'active_assignment': assignments.filter(status=WorkAssignment.STATUS_ACTIVE).first(),
        'pending_recommendations': assignments.filter(
            status=WorkAssignment.STATUS_RECOMMENDED,
        ),
        'recommendations': recommendations,
        'history': item.history.select_related('actor')[:30],
        'attachments': item.attachments.select_related('uploaded_by'),
        'status_form': WorkItemStatusForm(initial={'status': item.status}),
        'assign_form': AssignWorkForm(actor=user) if is_manager(user) else None,
        'attachment_form': WorkItemAttachmentForm(),
        'can_edit': can_edit_work_item(user, item),
        'can_change_status': can_change_status(user, item),
    }
    return render(request, 'workload/work_item_detail.html', context)


@manager_required
@require_POST
def work_item_delete(request, pk):
    item = _scoped_item_or_404(request.user, pk)
    title = item.title
    item.delete()
    messages.success(request, f'Work item “{title}” deleted.')
    return redirect('workload:work_item_list')


@login_required_workload
@require_POST
def work_item_status(request, pk):
    item = _scoped_item_or_404(request.user, pk)
    if not can_change_status(request.user, item):
        raise PermissionDenied('You cannot update this work item.')
    form = WorkItemStatusForm(request.POST)
    if form.is_valid():
        try:
            update_status(
                item,
                form.cleaned_data['status'],
                actor=request.user,
                note=form.cleaned_data.get('note', ''),
                actual_hours=form.cleaned_data.get('actual_hours'),
                blocked_reason=form.cleaned_data.get('blocked_reason', ''),
            )
            messages.success(request, 'Status updated.')
        except (PermissionDenied, ValidationError, ValueError) as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, 'Could not update status: ' + form.errors.as_text())
    return redirect('workload:work_item_detail', pk=item.pk)


@manager_required
@require_POST
def work_item_assign(request, pk):
    item = _scoped_item_or_404(request.user, pk)
    form = AssignWorkForm(request.POST, actor=request.user)
    if form.is_valid():
        try:
            assign_work(
                item,
                user=form.cleaned_data.get('assignee'),
                team=form.cleaned_data.get('team'),
                resource=form.cleaned_data.get('resource'),
                actor=request.user,
                allocated_hours=form.cleaned_data.get('allocated_hours'),
                role=form.cleaned_data.get('role', ''),
                notes=form.cleaned_data.get('notes', ''),
                approve=True,
            )
            messages.success(request, 'Work assigned.')
        except (PermissionDenied, ValidationError, ValueError) as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, 'Assignment failed: ' + form.errors.as_text())
    return redirect('workload:work_item_detail', pk=item.pk)


@manager_required
@require_POST
def work_item_recommend(request, pk):
    item = _scoped_item_or_404(request.user, pk)
    created = store_recommendations(item, request.user, limit=3)
    if created:
        messages.success(request, f'{len(created)} recommendation(s) ready for review.')
    else:
        messages.info(request, 'No additional recommendation was found.')
    return redirect('workload:work_item_detail', pk=item.pk)


@manager_required
@require_POST
def recommendation_action(request, pk, action):
    assignment = get_object_or_404(
        WorkAssignment.objects.select_related('work_item', 'resource'),
        pk=pk,
        status=WorkAssignment.STATUS_RECOMMENDED,
    )
    if not scope_work_items(WorkItem.objects.filter(pk=assignment.work_item_id), request.user).exists():
        raise PermissionDenied('This recommendation is outside your workload scope.')
    if action == 'approve':
        approve_recommendation(assignment, request.user)
        messages.success(request, 'Recommendation approved and work assigned.')
    elif action == 'reject':
        reject_recommendation(assignment, request.user, note=request.POST.get('note', ''))
        messages.info(request, 'Recommendation rejected.')
    else:
        raise Http404('Unknown action.')
    return redirect('workload:work_item_detail', pk=assignment.work_item_id)


@manager_required
@require_POST
def work_item_bulk(request):
    ids = request.POST.getlist('ids')
    if not ids:
        messages.warning(request, 'Select at least one work item.')
        return redirect('workload:work_item_list')
    form = BulkActionForm(request.POST, actor=request.user)
    if not form.is_valid():
        messages.error(request, 'Bulk action failed: ' + form.errors.as_text())
        return redirect('workload:work_item_list')

    items = _scoped_items(request.user).filter(pk__in=ids)
    action = form.cleaned_data['action']
    count = 0
    with transaction.atomic():
        for item in items:
            try:
                if action == BulkActionForm.ACTION_STATUS:
                    update_status(
                        item, form.cleaned_data['status'], actor=request.user,
                        note=form.cleaned_data.get('note', ''),
                    )
                elif action == BulkActionForm.ACTION_ASSIGN:
                    assign_work(
                        item,
                        user=form.cleaned_data.get('assignee'),
                        team=form.cleaned_data.get('team'),
                        actor=request.user,
                        allocated_hours=item.remaining_hours,
                        notes=form.cleaned_data.get('note', ''),
                    )
                else:
                    update_status(
                        item, WorkItem.STATUS_CANCELLED, actor=request.user,
                        note=form.cleaned_data.get('note', 'Bulk cancellation'),
                    )
                count += 1
            except PermissionDenied:
                logger.warning('Bulk action skipped for item %s', item.pk)
    messages.success(request, f'Bulk action applied to {count} work item(s).')
    return redirect('workload:work_item_list')


@login_required_workload
@require_POST
def attachment_upload(request, pk):
    item = _scoped_item_or_404(request.user, pk)
    if not can_edit_work_item(request.user, item):
        raise PermissionDenied('You cannot attach files to this work item.')
    form = WorkItemAttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        attach_file(item, form.cleaned_data['file'], actor=request.user)
        messages.success(request, 'Attachment uploaded.')
    else:
        messages.error(request, 'Upload failed: ' + form.errors.as_text())
    return redirect('workload:work_item_detail', pk=item.pk)


@login_required_workload
def attachment_download(request, pk):
    from .models import WorkItemAttachment

    attachment = get_object_or_404(
        WorkItemAttachment.objects.select_related('work_item'), pk=pk,
    )
    if not _scoped_items(request.user).filter(pk=attachment.work_item_id).exists():
        raise PermissionDenied('This attachment is outside your workload scope.')
    try:
        return FileResponse(
            attachment.file.open('rb'),
            as_attachment=True,
            filename=attachment.original_name or os.path.basename(attachment.file.name),
        )
    except FileNotFoundError as exc:
        raise Http404('Attachment file is missing.') from exc


# --------------------------------------------------------------------------- #
# Resources and teams
# --------------------------------------------------------------------------- #
@manager_required
def resource_list(request):
    user = request.user
    tenant = None if is_global_manager(user) else user
    policy = WorkloadPolicy.get_for(tenant)
    resources = scope_resources(
        WorkloadResource.objects.select_related(
            'user', 'team', 'capacity',
        ).prefetch_related('skills'),
        user,
    )
    kind = (request.GET.get('kind') or '').strip()
    if kind:
        resources = resources.filter(kind=kind)
    q = (request.GET.get('q') or '').strip()
    if q:
        resources = resources.filter(
            Q(name__icontains=q)
            | Q(user__username__icontains=q)
            | Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
            | Q(team__name__icontains=q)
        )
    rows = resource_utilization_rows(resources, policy)
    page_obj = _paginate(request, rows, 25)
    context = {
        **_navigation_context(request.user),
        'workload_nav': 'resources',
        'page_obj': page_obj,
        'rows': page_obj.object_list,
        'kind_choices': WorkloadResource.KIND_CHOICES,
        'filters': request.GET,
        'policy': policy,
    }
    return render(request, 'workload/resource_list.html', context)


@manager_required
def resource_create(request):
    form = WorkloadResourceForm(request.POST or None, actor=request.user)
    capacity_form = ResourceCapacityForm(request.POST or None, prefix='capacity')
    if request.method == 'POST' and form.is_valid() and capacity_form.is_valid():
        with transaction.atomic():
            resource = form.save(commit=False)
            if resource.team_id and resource.team.tenant_id:
                resource.tenant = resource.team.tenant
            elif not is_global_manager(request.user):
                resource.tenant = request.user
            else:
                resource.tenant = None
            resource.save()
            form.save_m2m()
            capacity = capacity_form.save(commit=False)
            capacity.resource = resource
            capacity.full_clean()
            capacity.save()
        messages.success(request, f'Resource “{resource.name}” created.')
        return redirect('workload:resource_list')
    context = {
        **_navigation_context(request.user),
        'workload_nav': 'resources',
        'form': form,
        'capacity_form': capacity_form,
        'is_create': True,
    }
    return render(request, 'workload/resource_form.html', context)


@manager_required
def resource_edit(request, pk):
    resource = get_object_or_404(
        scope_resources(
            WorkloadResource.objects.select_related('user', 'team'),
            request.user,
        ),
        pk=pk,
    )
    try:
        capacity_instance = resource.capacity
    except ResourceCapacity.DoesNotExist:
        capacity_instance = None
    form = WorkloadResourceForm(request.POST or None, instance=resource, actor=request.user)
    capacity_form = ResourceCapacityForm(
        request.POST or None, instance=capacity_instance, prefix='capacity',
    )
    if request.method == 'POST' and form.is_valid() and capacity_form.is_valid():
        with transaction.atomic():
            resource = form.save()
            capacity = capacity_form.save(commit=False)
            capacity.resource = resource
            capacity.full_clean()
            capacity.save()
        messages.success(request, 'Resource updated.')
        return redirect('workload:resource_list')
    context = {
        **_navigation_context(request.user),
        'workload_nav': 'resources',
        'form': form,
        'capacity_form': capacity_form,
        'resource': resource,
        'is_create': False,
    }
    return render(request, 'workload/resource_form.html', context)


@manager_required
def team_list(request):
    user = request.user
    tenant = None if is_global_manager(user) else user
    policy = WorkloadPolicy.get_for(tenant)
    teams = scope_teams(
        WorkloadTeam.objects.select_related('lead').prefetch_related('members'),
        user,
    )
    rows = team_capacity_rows(teams, policy)
    context = {
        **_navigation_context(request.user),
        'workload_nav': 'teams',
        'rows': rows,
        'policy': policy,
    }
    return render(request, 'workload/team_list.html', context)


@manager_required
def team_create(request):
    form = WorkloadTeamForm(request.POST or None, actor=request.user)
    if request.method == 'POST' and form.is_valid():
        team = form.save(commit=False)
        team.tenant = None if is_global_manager(request.user) else request.user
        team.save()
        form.save_m2m()
        messages.success(request, f'Team “{team.name}” created.')
        return redirect('workload:team_list')
    context = {
        **_navigation_context(request.user),
        'workload_nav': 'teams',
        'form': form,
        'is_create': True,
    }
    return render(request, 'workload/team_form.html', context)


@manager_required
def team_edit(request, pk):
    team = get_object_or_404(
        scope_teams(WorkloadTeam.objects.all(), request.user),
        pk=pk,
    )
    form = WorkloadTeamForm(request.POST or None, instance=team, actor=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Team updated.')
        return redirect('workload:team_list')
    context = {
        **_navigation_context(request.user),
        'workload_nav': 'teams',
        'form': form,
        'team': team,
        'is_create': False,
    }
    return render(request, 'workload/team_form.html', context)


# --------------------------------------------------------------------------- #
# Monitoring and alerts
# --------------------------------------------------------------------------- #
@manager_required
def monitoring(request):
    user = request.user
    tenant = None if is_global_manager(user) else user
    team = _team_from_request(request, user)
    policy = WorkloadPolicy.get_for(tenant)
    snapshot = monitoring_snapshot(tenant=tenant, team=team, policy=policy)
    stored_alerts = scope_alerts(
        WorkloadAlert.objects.select_related(
            'work_item', 'resource', 'team', 'recipient',
        ),
        user,
    ).filter(
        status__in=[WorkloadAlert.STATUS_OPEN, WorkloadAlert.STATUS_ACKNOWLEDGED],
    )
    if team is not None:
        stored_alerts = stored_alerts.filter(
            Q(team=team) | Q(work_item__team=team) | Q(resource__team=team),
        )
    context = {
        **_navigation_context(user),
        'workload_nav': 'monitoring',
        'snapshot': snapshot,
        'stored_alerts': stored_alerts[:50],
        'teams': scope_teams(WorkloadTeam.objects.filter(is_active=True), user),
        'selected_team': team,
        'policy': policy,
    }
    return render(request, 'workload/monitoring.html', context)


@manager_required
@require_POST
def refresh_monitoring(request):
    tenant = None if is_global_manager(request.user) else request.user
    result = refresh_alerts(tenant=tenant, actor=request.user)
    messages.success(
        request,
        f'Alerts refreshed: {result["created"]} created, '
        f'{result["updated"]} updated, {result["resolved"]} resolved.',
    )
    return redirect('workload:monitoring')


@manager_required
@require_POST
def sync_integrations_view(request):
    # Integration sync rewrites platform-wide project/CRM mirrors, so it stays
    # a global operator action; workspace managers cannot trigger it.
    if not is_global_manager(request.user):
        raise PermissionDenied(
            'Only platform administrators can run a full integration sync.',
        )
    result = sync_from_integrations()
    messages.success(
        request,
        'Integration sync complete: '
        f'{result["projects"]["synced"]} project task(s), '
        f'{result["crm"]["synced"]} CRM request(s).',
    )
    if result['projects']['errors'] or result['crm']['errors']:
        messages.warning(request, 'Some records could not be synchronised; see logs.')
    return redirect('workload:monitoring')


@manager_required
def alert_list(request):
    alerts = scope_alerts(
        WorkloadAlert.objects.select_related(
            'work_item', 'resource', 'team', 'recipient', 'acknowledged_by',
        ),
        request.user,
    )
    status = (request.GET.get('status') or '').strip()
    if status:
        alerts = alerts.filter(status=status)
    alert_type = (request.GET.get('type') or '').strip()
    if alert_type:
        alerts = alerts.filter(alert_type=alert_type)
    page_obj = _paginate(request, alerts, 30)
    context = {
        **_navigation_context(request.user),
        'workload_nav': 'monitoring',
        'page_obj': page_obj,
        'alerts': page_obj.object_list,
        'status_choices': WorkloadAlert.STATUS_CHOICES,
        'type_choices': WorkloadAlert.TYPE_CHOICES,
        'filters': request.GET,
    }
    return render(request, 'workload/alert_list.html', context)


@manager_required
@require_POST
def alert_action(request, pk, action):
    alert = get_object_or_404(
        scope_alerts(WorkloadAlert.objects.all(), request.user),
        pk=pk,
    )
    if action == 'acknowledge':
        acknowledge_alert(alert, request.user)
        messages.success(request, 'Alert acknowledged.')
    elif action == 'resolve':
        resolve_alert(alert, request.user)
        messages.success(request, 'Alert resolved.')
    else:
        raise Http404('Unknown alert action.')
    return redirect('workload:alert_list')


# --------------------------------------------------------------------------- #
# Policies
# --------------------------------------------------------------------------- #
@manager_required
def policy_list(request):
    policies = scope_policies(WorkloadPolicy.objects.all(), request.user)
    context = {
        **_navigation_context(request.user),
        'workload_nav': 'policies',
        'policies': policies,
    }
    return render(request, 'workload/policy_list.html', context)


@admin_required
def policy_create(request):
    form = WorkloadPolicyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        policy = form.save(commit=False)
        policy.tenant = None
        if policy.is_default:
            WorkloadPolicy.objects.filter(tenant__isnull=True, is_default=True).update(
                is_default=False,
            )
        policy.save()
        messages.success(request, 'Workload policy created.')
        return redirect('workload:policy_list')
    context = {
        **_navigation_context(request.user),
        'workload_nav': 'policies',
        'form': form,
        'is_create': True,
    }
    return render(request, 'workload/policy_form.html', context)


@admin_required
def policy_edit(request, pk):
    policy = get_object_or_404(WorkloadPolicy, pk=pk)
    form = WorkloadPolicyForm(request.POST or None, instance=policy)
    if request.method == 'POST' and form.is_valid():
        policy = form.save(commit=False)
        if policy.is_default:
            WorkloadPolicy.objects.filter(
                tenant=policy.tenant, is_default=True,
            ).exclude(pk=policy.pk).update(is_default=False)
        policy.save()
        messages.success(request, 'Workload policy updated.')
        return redirect('workload:policy_list')
    context = {
        **_navigation_context(request.user),
        'workload_nav': 'policies',
        'form': form,
        'policy': policy,
        'is_create': False,
    }
    return render(request, 'workload/policy_form.html', context)
