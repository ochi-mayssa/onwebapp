"""Cross-module integration, metric snapshots and management commands."""
from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

from crm.models import Customer, ServiceRequest
from projects.models import PhaseTask, Project, ProjectPhase
from workload.models import (
    WorkAssignment,
    WorkItem,
    WorkloadAlert,
    WorkloadMetric,
)
from workload.services import (
    assign_work,
    build_metric_snapshot,
    capture_metrics,
    create_work_item_from_service_request,
    sync_from_integrations,
    sync_project_task,
)
from workload.tests.base import WorkloadTestBase


class ProjectIntegrationTests(WorkloadTestBase):
    def setUp(self):
        self.customer = Customer.objects.create(
            user=self.client_user,
            name='Integration Client',
            email='integration-client@example.com',
        )
        self.project = Project.objects.create(
            client=self.client_user,
            title='Integration Website',
            description='A project used for workload mirroring.',
        )
        self.phase = ProjectPhase.objects.create(
            project=self.project,
            phase_type='DEVELOPMENT',
        )

    def test_project_task_is_mirrored_once_and_updated(self):
        task = PhaseTask.objects.create(
            phase=self.phase,
            name='Build the homepage',
            description='Hero and nav',
            priority='HIGH',
            due_date=self.due(5),
            assigned_to=self.employee,
        )
        item = WorkItem.objects.get(project_task=task)
        self.assertEqual(item.project, self.project)
        self.assertEqual(item.client, self.customer)
        self.assertEqual(item.tenant, self.client_user)
        self.assertEqual(item.source_module, WorkItem.SOURCE_PROJECT)
        self.assertEqual(item.priority, WorkItem.PRIORITY_HIGH)
        self.assertEqual(item.external_reference, f'project-task:{task.pk}')
        self.assertEqual(item.assignee, self.employee)
        self.assertTrue(
            item.assignments.filter(status=WorkAssignment.STATUS_ACTIVE).exists(),
        )

        task.name = 'Build the homepage v2'
        task.priority = 'CRITICAL'
        task.save()
        self.assertEqual(WorkItem.objects.filter(project_task=task).count(), 1)
        item.refresh_from_db()
        self.assertEqual(item.title, 'Build the homepage v2')
        self.assertEqual(item.priority, WorkItem.PRIORITY_CRITICAL)

        sync_project_task(task)
        self.assertEqual(WorkItem.objects.filter(project_task=task).count(), 1)

    def test_project_task_status_mapping(self):
        task = PhaseTask.objects.create(
            phase=self.phase, name='Blocked task', status='BLOCKED',
        )
        item = WorkItem.objects.get(project_task=task)
        self.assertEqual(item.status, WorkItem.STATUS_BLOCKED)
        task.status = 'COMPLETED'
        task.save()
        item.refresh_from_db()
        self.assertEqual(item.status, WorkItem.STATUS_COMPLETED)
        self.assertIsNotNone(item.completed_at)


class CrmIntegrationTests(WorkloadTestBase):
    def setUp(self):
        self.customer = Customer.objects.create(
            user=self.client_user,
            name='CRM Client',
            email='crm-client@example.com',
        )

    def test_new_service_request_creates_business_work_item(self):
        request = ServiceRequest.objects.create(
            customer=self.customer,
            service_type='Website redesign',
            description='Refresh the marketing site.',
            status='NEW',
        )
        item = WorkItem.objects.get(crm_request=request)
        self.assertEqual(item.category, WorkItem.CATEGORY_BUSINESS)
        self.assertEqual(item.source_module, WorkItem.SOURCE_CRM)
        self.assertEqual(item.client, self.customer)
        self.assertEqual(item.tenant, self.client_user)
        self.assertIn('CRM Client', item.title)

        self.assertIsNotNone(create_work_item_from_service_request(request))
        self.assertEqual(WorkItem.objects.filter(crm_request=request).count(), 1)

    def test_non_new_service_request_is_ignored(self):
        request = ServiceRequest.objects.create(
            customer=self.customer,
            service_type='Audit',
            description='Already converted.',
            status='CONVERTED',
        )
        self.assertFalse(WorkItem.objects.filter(crm_request=request).exists())
        self.assertIsNone(create_work_item_from_service_request(request))

    def test_sync_from_integrations_runs_both_connectors(self):
        result = sync_from_integrations()
        self.assertIn('projects', result)
        self.assertIn('crm', result)
        self.assertIn('synced', result['projects'])
        self.assertIn('errors', result['crm'])


class MetricCaptureTests(WorkloadTestBase):
    def setUp(self):
        self.resource = self.make_resource(self.employee, weekly=40)
        self.item = self.make_item(title='Measured work', estimated_hours=20)
        assign_work(
            self.item, resource=self.resource, actor=self.manager,
            allocated_hours=20,
        )

    def test_capture_metrics_writes_serialisable_snapshots(self):
        created = capture_metrics()
        self.assertGreaterEqual(created, 2)
        org = WorkloadMetric.objects.get(scope=WorkloadMetric.SCOPE_ORG)
        self.assertEqual(org.metric_date, timezone.localdate())
        self.assertEqual(org.data['total'], 1)
        self.assertEqual(org.data['overall_utilization'], 50.0)
        self.assertIn('captured_at', org.data)
        self.assertNotIn('employee_distribution', org.data)
        self.assertNotIn('live_alerts', org.data)
        self.assertNotIn('team_distribution', org.data)
        json.dumps(org.data)

        resource_metric = WorkloadMetric.objects.get(
            scope=WorkloadMetric.SCOPE_RESOURCE,
        )
        self.assertEqual(resource_metric.resource, self.resource)
        self.assertEqual(resource_metric.data['utilization'], 50.0)

    def test_capture_is_idempotent_per_day(self):
        capture_metrics()
        count = WorkloadMetric.objects.count()
        capture_metrics()
        self.assertEqual(WorkloadMetric.objects.count(), count)

    def test_build_metric_snapshot_coerces_values_and_drops_models(self):
        payload = build_metric_snapshot({
            'total': 3,
            'overall_utilization': Decimal('66.7'),
            'week_start': date(2026, 1, 5),
            'timestamp': datetime(2026, 1, 5, 9, 30),
            'clock': time(9, 30),
            'employee_distribution': [self.resource],
            'live_alerts': [{'work_item': self.item}],
            'safe': {'nested': Decimal('1.5')},
        })
        self.assertEqual(payload['total'], 3)
        self.assertEqual(payload['overall_utilization'], 66.7)
        self.assertEqual(payload['week_start'], '2026-01-05')
        self.assertTrue(payload['timestamp'].startswith('2026-01-05T09:30'))
        self.assertTrue(payload['clock'].startswith('09:30'))
        self.assertEqual(payload['safe'], {'nested': 1.5})
        self.assertNotIn('employee_distribution', payload)
        self.assertNotIn('live_alerts', payload)
        json.dumps(payload)


class ManagementCommandTests(WorkloadTestBase):
    def test_refresh_alerts_command(self):
        self.make_item(
            title='Overdue command', status=WorkItem.STATUS_IN_PROGRESS,
            due_date=self.due(-1),
        )
        out = StringIO()
        call_command('refresh_workload_alerts', stdout=out)
        self.assertIn('Workload alerts refreshed', out.getvalue())
        self.assertTrue(WorkloadAlert.objects.exists())

    def test_capture_metrics_command(self):
        self.make_resource(self.employee)
        out = StringIO()
        call_command('capture_workload_metrics', stdout=out)
        self.assertIn('Captured', out.getvalue())
        self.assertTrue(WorkloadMetric.objects.exists())

    def test_sync_integrations_command(self):
        out = StringIO()
        call_command('sync_workload_integrations', stdout=out)
        self.assertIn('integration sync complete', out.getvalue())

    def test_unknown_tenant_raises_command_error(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command('refresh_workload_alerts', tenant='does-not-exist')
