"""Alert generation, monitoring and dashboard metric tests."""
from __future__ import annotations

from django.core.exceptions import PermissionDenied

from workload.models import WorkAssignment, WorkItem, WorkloadAlert
from workload.selectors import dashboard_metrics, live_operational_alerts
from workload.services import (
    acknowledge_alert,
    assign_work,
    refresh_alerts,
    resolve_alert,
    update_status,
)
from workload.tests.base import WorkloadTestBase


class AlertRefreshTests(WorkloadTestBase):
    def test_refresh_creates_each_managed_alert_type(self):
        employee_resource = self.make_resource(self.employee)
        overdue = self.make_item(
            title='Overdue', status=WorkItem.STATUS_IN_PROGRESS,
            assignee=self.employee, due_date=self.due(-1),
        )
        blocked = self.make_item(
            title='Blocked', status=WorkItem.STATUS_BLOCKED,
            blocked_reason='Waiting on client',
        )
        unassigned = self.make_item(title='Unassigned', status=WorkItem.STATUS_NEW)
        deadline = self.make_item(
            title='Deadline', status=WorkItem.STATUS_IN_PROGRESS,
            assignee=self.employee, due_date=self.due(2), estimated_hours=8,
        )
        WorkAssignment.objects.create(
            work_item=deadline, resource=employee_resource, allocated_hours=8,
            status=WorkAssignment.STATUS_ACTIVE,
        )

        result = refresh_alerts(policy=self.policy)
        self.assertGreaterEqual(result['created'], 4)
        types = set(WorkloadAlert.objects.values_list('alert_type', flat=True))
        self.assertIn(WorkloadAlert.TYPE_OVERDUE, types)
        self.assertIn(WorkloadAlert.TYPE_BLOCKED, types)
        self.assertIn(WorkloadAlert.TYPE_UNASSIGNED, types)
        self.assertIn(WorkloadAlert.TYPE_DEADLINE, types)
        self.assertEqual(alerts_for(overdue).count(), 1)
        self.assertEqual(alerts_for(blocked).count(), 1)
        self.assertEqual(alerts_for(unassigned).count(), 1)

    def test_refresh_is_idempotent_and_dedupes_by_key(self):
        self.make_item(
            title='Overdue', status=WorkItem.STATUS_IN_PROGRESS,
            due_date=self.due(-2),
        )
        first = refresh_alerts(policy=self.policy)
        self.assertEqual(first['created'], 1)
        second = refresh_alerts(policy=self.policy)
        self.assertEqual(second['created'], 0)
        self.assertEqual(second['updated'], 1)
        self.assertEqual(
            WorkloadAlert.objects.filter(alert_type=WorkloadAlert.TYPE_OVERDUE).count(),
            1,
        )

    def test_refresh_resolves_stale_alerts(self):
        item = self.make_item(
            title='Was overdue', status=WorkItem.STATUS_IN_PROGRESS,
            due_date=self.due(-2),
        )
        refresh_alerts(policy=self.policy)
        alert = WorkloadAlert.objects.get(
            alert_type=WorkloadAlert.TYPE_OVERDUE, work_item=item,
        )
        item.due_date = None
        item.save(update_fields=['due_date', 'updated_at'])

        result = refresh_alerts(policy=self.policy)
        alert.refresh_from_db()
        self.assertEqual(alert.status, WorkloadAlert.STATUS_RESOLVED)
        self.assertGreaterEqual(result['resolved'], 1)

    def test_overload_alert_uses_capacity_and_severity(self):
        resource = self.make_resource(self.employee, weekly=40)
        item = self.make_item(title='Too much', estimated_hours=50)
        assign_work(
            item, resource=resource, actor=self.manager, allocated_hours=50,
        )
        refresh_alerts(policy=self.policy)
        alert = WorkloadAlert.objects.get(alert_type=WorkloadAlert.TYPE_OVERLOAD)
        self.assertEqual(alert.resource, resource)
        self.assertEqual(alert.severity, WorkloadAlert.SEVERITY_CRITICAL)
        self.assertEqual(alert.metadata['utilization'], 125.0)

    def test_underutilized_alert_only_for_resources_with_active_work(self):
        resource = self.make_resource(self.employee, weekly=40)
        item = self.make_item(title='Light work', estimated_hours=8)
        assign_work(item, resource=resource, actor=self.manager, allocated_hours=8)
        refresh_alerts(policy=self.policy)
        alert = WorkloadAlert.objects.get(alert_type=WorkloadAlert.TYPE_UNDERUTILIZED)
        self.assertEqual(alert.resource, resource)
        self.assertEqual(alert.severity, WorkloadAlert.SEVERITY_LOW)

    def test_team_capacity_and_bottleneck_alerts(self):
        team = self.make_team(
            members=[self.employee], name='Capacity team', lead=self.manager,
        )
        resource = self.make_resource(self.employee, weekly=40)
        heavy = self.make_item(title='Heavy', estimated_hours=38, team=team)
        assign_work(heavy, resource=resource, actor=self.manager, allocated_hours=38)

        self.make_item(title='Blocked one', status=WorkItem.STATUS_BLOCKED, team=team)
        self.make_item(title='Blocked two', status=WorkItem.STATUS_BLOCKED, team=team)

        refresh_alerts(policy=self.policy)
        capacity_alert = WorkloadAlert.objects.get(
            alert_type=WorkloadAlert.TYPE_TEAM_CAPACITY,
        )
        self.assertEqual(capacity_alert.team, team)
        self.assertEqual(capacity_alert.recipient, self.manager)
        bottleneck = WorkloadAlert.objects.get(
            alert_type=WorkloadAlert.TYPE_BOTTLENECK,
        )
        self.assertGreaterEqual(bottleneck.metadata['blocked_or_overdue'], 2)

    def test_completing_work_resolves_its_alerts(self):
        item = self.make_item(
            title='Finish me', status=WorkItem.STATUS_BLOCKED,
            due_date=self.due(-1),
        )
        refresh_alerts(policy=self.policy)
        self.assertTrue(
            WorkloadAlert.objects.filter(work_item=item).exists(),
        )
        update_status(item, WorkItem.STATUS_COMPLETED, actor=self.manager)
        self.assertFalse(
            WorkloadAlert.objects.filter(
                work_item=item,
                status__in=[WorkloadAlert.STATUS_OPEN, WorkloadAlert.STATUS_ACKNOWLEDGED],
            ).exists(),
        )


def alerts_for(item):
    return WorkloadAlert.objects.filter(work_item=item)


class AlertActionTests(WorkloadTestBase):
    def test_acknowledge_and_resolve_require_manager(self):
        alert = WorkloadAlert.objects.create(
            alert_type=WorkloadAlert.TYPE_OVERDUE,
            message='Overdue',
            dedupe_key='manual-alert-1',
        )
        with self.assertRaises(PermissionDenied):
            acknowledge_alert(alert, self.employee)

        acknowledge_alert(alert, self.manager)
        alert.refresh_from_db()
        self.assertEqual(alert.status, WorkloadAlert.STATUS_ACKNOWLEDGED)
        self.assertEqual(alert.acknowledged_by, self.manager)
        self.assertIsNotNone(alert.acknowledged_at)

        with self.assertRaises(PermissionDenied):
            resolve_alert(alert, self.employee)
        resolve_alert(alert, self.manager)
        alert.refresh_from_db()
        self.assertEqual(alert.status, WorkloadAlert.STATUS_RESOLVED)
        self.assertIsNotNone(alert.resolved_at)


class DashboardMetricTests(WorkloadTestBase):
    def test_dashboard_metrics_are_derived_from_database_rows(self):
        resource = self.make_resource(self.employee, weekly=40)
        unassigned = self.make_item(
            title='Unassigned', status=WorkItem.STATUS_NEW, due_date=self.due(1),
        )
        overdue = self.make_item(
            title='Overdue', status=WorkItem.STATUS_IN_PROGRESS,
            assignee=self.employee, due_date=self.due(-1),
        )
        blocked = self.make_item(
            title='Blocked', status=WorkItem.STATUS_BLOCKED, due_date=self.due(10),
        )
        completed = self.make_item(
            title='Done', status=WorkItem.STATUS_COMPLETED,
        )
        cancelled = self.make_item(
            title='Cancelled', status=WorkItem.STATUS_CANCELLED,
        )
        assign_work(overdue, resource=resource, actor=self.manager, allocated_hours=20)

        metrics = dashboard_metrics(policy=self.policy)

        self.assertEqual(metrics['total'], 5)
        self.assertEqual(metrics['active'], 3)
        self.assertEqual(metrics['completed'], 1)
        self.assertEqual(metrics['cancelled'], 1)
        self.assertEqual(metrics['blocked'], 1)
        self.assertEqual(metrics['overdue'], 1)
        self.assertEqual(metrics['pending_assignments'], 1)
        self.assertEqual(metrics['unassigned'], 2)  # unassigned + blocked without owner
        self.assertEqual(metrics['due_soon'], 1)
        self.assertEqual(metrics['overall_utilization'], 50.0)
        self.assertEqual(metrics['overall_utilization_display'], '50.0%')
        self.assertEqual(metrics['total_available_hours'], 40.0)
        self.assertEqual(metrics['total_assigned_hours'], 20.0)
        self.assertEqual(metrics['resource_count'], 1)
        self.assertTrue(metrics['employee_distribution'])
        self.assertEqual(len(metrics['trend']), 8)
        self.assertIn('value', metrics['priority_distribution'][0])
        self.assertIsNotNone(unassigned.pk)
        self.assertIsNotNone(blocked.pk)
        self.assertIsNotNone(completed.pk)
        self.assertIsNotNone(cancelled.pk)

    def test_metrics_respect_tenant_scope(self):
        tenant = self.client_user
        self.make_item(title='Mine', tenant=tenant)
        self.make_item(title='Someone else')
        metrics = dashboard_metrics(tenant=tenant, policy=self.policy)
        self.assertEqual(metrics['total'], 1)

    def test_live_operational_alerts_are_computed_without_writes(self):
        resource = self.make_resource(self.employee, weekly=40)
        item = self.make_item(title='Overloaded', estimated_hours=45)
        assign_work(item, resource=resource, actor=self.manager, allocated_hours=45)
        self.make_item(
            title='Overdue', status=WorkItem.STATUS_IN_PROGRESS, due_date=self.due(-1),
        )
        before = WorkloadAlert.objects.count()
        snapshot = live_operational_alerts(
            WorkItem.objects.all(), policy=self.policy,
        )
        self.assertEqual(WorkloadAlert.objects.count(), before)
        self.assertEqual(len(snapshot['overloaded_resources']), 1)
        self.assertEqual(len(snapshot['overdue_items']), 1)

    def test_work_item_completion_sets_timestamp_and_clears_on_reopen(self):
        item = self.make_item(status=WorkItem.STATUS_IN_PROGRESS)
        update_status(item, WorkItem.STATUS_COMPLETED, actor=self.manager)
        item.refresh_from_db()
        self.assertIsNotNone(item.completed_at)
        self.assertEqual(item.status, WorkItem.STATUS_COMPLETED)
        update_status(item, WorkItem.STATUS_IN_PROGRESS, actor=self.manager)
        item.refresh_from_db()
        self.assertIsNone(item.completed_at)

    def test_unknown_status_is_rejected(self):
        from django.core.exceptions import ValidationError

        item = self.make_item()
        with self.assertRaises(ValidationError):
            update_status(item, 'NOT_A_STATUS', actor=self.manager)

    def test_non_owner_cannot_change_status(self):
        item = self.make_item(assignee=self.employee)
        with self.assertRaises(PermissionDenied):
            update_status(item, WorkItem.STATUS_COMPLETED, actor=self.other)
