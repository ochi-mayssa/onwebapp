"""Security, tenancy and data-integrity regression tests."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from crm.models import Customer, ServiceRequest
from projects.models import PhaseTask, Project, ProjectPhase
from workload.forms import WorkItemForm
from workload.models import (
    WorkAssignment,
    WorkItem,
    WorkloadAlert,
    WorkloadMetric,
    WorkloadPolicy,
    WorkloadResource,
)
from workload.permissions import (
    GROUP_MANAGERS,
    assignable_resources,
    assignable_users,
    scope_alerts,
    scope_teams,
)
from workload.selectors import resource_utilization_rows
from workload.services import (
    assign_work,
    capture_metrics,
    recommend_assignees,
    sync_service_request,
)
from workload.tests.base import WorkloadTestBase

User = get_user_model()


class WorkspaceTenantTests(WorkloadTestBase):
    """A non-staff ``Workload Managers`` user stays inside their workspace."""

    def setUp(self):
        self.workspace_manager = User.objects.create_user(
            username='workspace-manager',
            email='workspace-manager@example.com',
            password='test-pass-123',
        )
        group, _ = Group.objects.get_or_create(name=GROUP_MANAGERS)
        self.workspace_manager.groups.add(group)

        self.own_team = self.make_team(
            name='Own workspace team',
            lead=self.workspace_manager,
            tenant=self.workspace_manager,
            members=[self.employee],
        )
        self.foreign_team = self.make_team(
            name='Foreign workspace team',
            tenant=self.other,
            members=[self.other],
        )
        self.own_item = self.make_item(
            title='Own workspace work',
            tenant=self.workspace_manager,
            team=self.own_team,
        )
        self.foreign_item = self.make_item(
            title='Foreign workspace work',
            tenant=self.other,
            team=self.foreign_team,
        )
        self.own_resource = self.make_resource(
            self.employee, tenant=self.workspace_manager,
        )
        self.foreign_resource = self.make_resource(
            self.other, tenant=self.other,
        )

    def test_scoped_querysets_exclude_foreign_workspace(self):
        teams = scope_teams(self.own_team.__class__.objects.all(), self.workspace_manager)
        self.assertIn(self.own_team, teams)
        self.assertNotIn(self.foreign_team, teams)

        users = assignable_users(self.workspace_manager)
        self.assertIn(self.employee, users)
        self.assertNotIn(self.other, users)

        resources = assignable_resources(self.workspace_manager)
        self.assertIn(self.own_resource, resources)
        self.assertNotIn(self.foreign_resource, resources)

    def test_forms_only_offer_in_scope_choices(self):
        form = WorkItemForm(actor=self.workspace_manager)
        self.assertIn(self.own_team, form.fields['team'].queryset)
        self.assertNotIn(self.foreign_team, form.fields['team'].queryset)
        self.assertIn(self.employee, form.fields['assignee'].queryset)
        self.assertNotIn(self.other, form.fields['assignee'].queryset)

    def test_web_detail_edit_and_delete_block_foreign_items(self):
        self.client.force_login(self.workspace_manager)
        for name in (
            'workload:work_item_detail',
            'workload:work_item_edit',
        ):
            response = self.client.get(reverse(name, args=[self.foreign_item.pk]))
            self.assertIn(response.status_code, (403, 404), msg=name)

        response = self.client.post(
            reverse('workload:work_item_delete', args=[self.foreign_item.pk]),
        )
        self.assertIn(response.status_code, (403, 404))
        self.assertTrue(WorkItem.objects.filter(pk=self.foreign_item.pk).exists())

    def test_workspace_dashboard_metrics_are_tenant_scoped(self):
        self.client.force_login(self.workspace_manager)
        response = self.client.get(reverse('workload:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['metrics']['total'], 1)

    def test_cross_tenant_team_is_rejected_by_create_form(self):
        self.client.force_login(self.workspace_manager)
        response = self.client.post(
            reverse('workload:work_item_create'),
            {
                'title': 'Cross tenant attempt',
                'category': WorkItem.CATEGORY_HUMAN,
                'priority': WorkItem.PRIORITY_MEDIUM,
                'status': WorkItem.STATUS_NEW,
                'source_module': WorkItem.SOURCE_MANUAL,
                'estimated_hours': '4',
                'actual_hours': '0',
                'team': self.foreign_team.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(WorkItem.objects.filter(title='Cross tenant attempt').exists())

    def test_service_rejects_cross_tenant_resource_assignment(self):
        from django.core.exceptions import ValidationError as DjangoValidationError

        with self.assertRaises(DjangoValidationError):
            assign_work(
                self.own_item,
                resource=self.foreign_resource,
                actor=self.manager,
            )

    def test_service_rejects_out_of_scope_user_and_team(self):
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            assign_work(
                self.own_item,
                user=self.other,
                actor=self.workspace_manager,
            )
        with self.assertRaises(PermissionDenied):
            assign_work(
                self.own_item,
                team=self.foreign_team,
                actor=self.workspace_manager,
            )

    def test_recommendations_do_not_leak_foreign_resources(self):
        rows = recommend_assignees(
            self.own_item, actor=self.workspace_manager,
        )
        resource_ids = {row['resource'].pk for row in rows}
        self.assertNotIn(self.foreign_resource.pk, resource_ids)

    def test_api_hides_foreign_items_and_assignees(self):
        api = APIClient()
        api.force_authenticate(self.workspace_manager)
        listing = api.get(reverse('workload-api:work-item-list'))
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(
            [row['title'] for row in listing.data['results']],
            ['Own workspace work'],
        )

        response = api.post(
            reverse('workload-api:work-item-assign', args=[self.own_item.pk]),
            {'assignee': self.other.pk},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

        resource_response = api.post(
            reverse('workload-api:work-item-assign', args=[self.own_item.pk]),
            {'resource': self.foreign_resource.pk},
            format='json',
        )
        self.assertEqual(resource_response.status_code, 400)

    def test_alert_and_team_actions_are_scoped(self):
        foreign_alert = WorkloadAlert.objects.create(
            alert_type=WorkloadAlert.TYPE_OVERDUE,
            tenant=self.other,
            recipient=self.other,
            message='Foreign alert',
            dedupe_key='foreign-scope-alert',
        )
        self.assertNotIn(
            foreign_alert,
            scope_alerts(WorkloadAlert.objects.all(), self.workspace_manager),
        )

        self.client.force_login(self.workspace_manager)
        self.assertEqual(
            self.client.post(
                reverse('workload:alert_action', args=[foreign_alert.pk, 'acknowledge']),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse('workload:team_edit', args=[self.foreign_team.pk]),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse('workload:resource_edit', args=[self.foreign_resource.pk]),
            ).status_code,
            404,
        )

    def test_integration_sync_is_global_only(self):
        self.client.force_login(self.workspace_manager)
        self.assertEqual(
            self.client.post(reverse('workload:sync_integrations')).status_code,
            403,
        )
        self.client.force_login(self.manager)
        self.assertEqual(
            self.client.post(reverse('workload:sync_integrations')).status_code,
            302,
        )

    def test_policy_list_excludes_foreign_tenant_policy(self):
        own_policy = WorkloadPolicy.objects.create(
            name='Workspace policy', tenant=self.workspace_manager, is_default=False,
        )
        foreign_policy = WorkloadPolicy.objects.create(
            name='Foreign policy', tenant=self.other, is_default=False,
        )
        self.client.force_login(self.workspace_manager)
        response = self.client.get(reverse('workload:policy_list'))
        policies = list(response.context['policies'])
        self.assertIn(own_policy, policies)
        self.assertNotIn(foreign_policy, policies)


class AssignmentIntegrityTests(WorkloadTestBase):
    def test_database_rejects_two_active_assignments_per_item(self):
        item = self.make_item(title='Single active rule')
        first = self.make_resource(self.employee)
        second = self.make_resource(self.other)
        WorkAssignment.objects.create(
            work_item=item, resource=first, status=WorkAssignment.STATUS_ACTIVE,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WorkAssignment.objects.create(
                    work_item=item,
                    resource=second,
                    status=WorkAssignment.STATUS_ACTIVE,
                )

    def test_reassigning_same_resource_reuses_assignment_row(self):
        item = self.make_item(title='Reuse assignment')
        first = assign_work(
            item, user=self.employee, actor=self.manager, allocated_hours=4,
        )
        second = assign_work(
            item, user=self.employee, actor=self.manager, allocated_hours=6,
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            item.assignments.filter(status=WorkAssignment.STATUS_ACTIVE).count(),
            1,
        )
        second.refresh_from_db()
        self.assertEqual(second.allocated_hours, 6)

    def test_recommendations_reflect_updated_utilisation(self):
        item = self.make_item(
            title='Recalculate recommendations', estimated_hours=40,
        )
        self.make_resource(self.employee, weekly=40)
        self.make_resource(self.other, weekly=40)
        assign_work(
            item, user=self.employee, actor=self.manager, allocated_hours=30,
        )
        rows = recommend_assignees(item, actor=self.manager)
        by_user = {row['user']: row for row in rows if row['user']}
        self.assertEqual(by_user[self.employee]['utilization'], 75.0)
        self.assertTrue(by_user[self.employee]['would_overload'])
        self.assertFalse(by_user[self.other]['would_overload'])


class SourceDeletionTests(WorkloadTestBase):
    def setUp(self):
        self.customer = Customer.objects.create(
            user=self.client_user,
            name='Lifecycle Client',
            email='lifecycle-client@example.com',
        )
        self.project = Project.objects.create(
            client=self.client_user,
            title='Lifecycle Project',
            description='Project mirror lifecycle.',
        )
        self.phase = ProjectPhase.objects.create(
            project=self.project,
            phase_type='DEVELOPMENT',
        )

    def test_deleting_project_task_cancels_mirror_and_assignment(self):
        task = PhaseTask.objects.create(
            phase=self.phase,
            name='Task that disappears',
            assigned_to=self.employee,
        )
        item = WorkItem.objects.get(project_task=task)
        self.assertTrue(
            item.assignments.filter(status=WorkAssignment.STATUS_ACTIVE).exists(),
        )
        task.delete()
        item.refresh_from_db()
        self.assertEqual(item.status, WorkItem.STATUS_CANCELLED)
        self.assertIn('deleted', item.cancellation_reason.lower())
        self.assertFalse(
            item.assignments.filter(status=WorkAssignment.STATUS_ACTIVE).exists(),
        )

    def test_service_request_updates_and_rejection_are_mirrored(self):
        request = ServiceRequest.objects.create(
            customer=self.customer,
            service_type='Audit',
            description='Initial description.',
            status='NEW',
        )
        item = WorkItem.objects.get(crm_request=request)
        request.service_type = 'Security audit'
        request.status = 'REVIEW'
        request.save()
        item.refresh_from_db()
        self.assertIn('Security audit', item.title)
        self.assertEqual(item.status, WorkItem.STATUS_NEW)

        request.status = 'REJECTED'
        request.save()
        item.refresh_from_db()
        self.assertEqual(item.status, WorkItem.STATUS_CANCELLED)

    def test_deleting_service_request_cancels_mirror(self):
        request = ServiceRequest.objects.create(
            customer=self.customer,
            service_type='Deletion test',
            description='Will be removed.',
            status='NEW',
        )
        item = WorkItem.objects.get(crm_request=request)
        request.delete()
        item.refresh_from_db()
        self.assertEqual(item.status, WorkItem.STATUS_CANCELLED)

    def test_service_request_sync_is_idempotent(self):
        request = ServiceRequest.objects.create(
            customer=self.customer,
            service_type='Idempotent',
            description='One mirror only.',
            status='NEW',
        )
        for _ in range(3):
            sync_service_request(request)
        self.assertEqual(WorkItem.objects.filter(crm_request=request).count(), 1)

    def test_metrics_capture_is_tenant_scoped(self):
        own = self.make_resource(self.employee, tenant=self.client_user)
        foreign = self.make_resource(self.other, tenant=self.other)
        created = capture_metrics(tenant=self.client_user)
        self.assertGreaterEqual(created, 1)
        resource_rows = WorkloadMetric.objects.filter(
            tenant=self.client_user,
            scope=WorkloadMetric.SCOPE_RESOURCE,
        )
        self.assertEqual(
            set(resource_rows.values_list('resource_id', flat=True)), {own.pk},
        )
        self.assertFalse(resource_rows.filter(resource=foreign).exists())


class QueryBudgetTests(WorkloadTestBase):
    def test_resource_rows_query_count_is_stable(self):
        for index in range(2):
            self.make_resource(
                User.objects.create_user(
                    username=f'budget-{index}',
                    password='test-pass-123',
                ),
            )
        resources = WorkloadResource.objects.select_related(
            'user', 'team', 'capacity',
        ).prefetch_related('skills')
        with CaptureQueriesContext(connection) as first:
            resource_utilization_rows(resources, self.policy)
        first_count = len(first)

        for index in range(2, 5):
            self.make_resource(
                User.objects.create_user(
                    username=f'budget-{index}',
                    password='test-pass-123',
                ),
            )
        resources = WorkloadResource.objects.select_related(
            'user', 'team', 'capacity',
        ).prefetch_related('skills')
        with CaptureQueriesContext(connection) as second:
            resource_utilization_rows(resources, self.policy)
        self.assertEqual(len(second), first_count)
