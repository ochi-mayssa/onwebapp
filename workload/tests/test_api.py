"""REST API authentication, permissions and action tests."""
from __future__ import annotations

import json

from django.urls import reverse
from rest_framework.test import APIClient

from workload.models import (
    WorkAssignment,
    WorkItem,
    WorkloadAlert,
    WorkloadPolicy,
)
from workload.tests.base import WorkloadTestBase


class WorkloadApiTests(WorkloadTestBase):
    def setUp(self):
        self.api = APIClient()
        self.item = self.make_item(
            title='API item', assignee=self.employee,
            status=WorkItem.STATUS_IN_PROGRESS,
        )
        self.resource = self.make_resource(self.employee)
        self.other_resource = self.make_resource(self.other)

    def auth(self, user):
        self.api.force_authenticate(user=user)
        return self.api

    # ------------------------------------------------------------------ #
    # Work items
    # ------------------------------------------------------------------ #
    def test_authentication_is_required(self):
        response = self.api.get(reverse('workload-api:work-item-list'))
        self.assertIn(response.status_code, (401, 403))

    def test_manager_lists_all_items_with_pagination(self):
        self.make_item(title='Second')
        response = self.auth(self.manager).get(reverse('workload-api:work-item-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(len(response.data['results']), 2)

    def test_employee_only_lists_own_scope(self):
        self.make_item(title='Hidden item')
        response = self.auth(self.employee).get(reverse('workload-api:work-item-list'))
        self.assertEqual(response.status_code, 200)
        titles = [row['title'] for row in response.data['results']]
        self.assertEqual(titles, ['API item'])

    def test_client_only_lists_exposed_records(self):
        self.make_item(
            title='Visible client item', tenant=self.client_user,
            is_client_visible=True,
        )
        self.make_item(title='Internal item')
        response = self.auth(self.client_user).get(reverse('workload-api:work-item-list'))
        self.assertEqual(response.status_code, 200)
        titles = [row['title'] for row in response.data['results']]
        self.assertEqual(titles, ['Visible client item'])

    def test_manager_creates_item(self):
        response = self.auth(self.manager).post(
            reverse('workload-api:work-item-list'),
            {'title': 'Created through API', 'priority': 'HIGH'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        item = WorkItem.objects.get(title='Created through API')
        self.assertEqual(item.created_by, self.manager)
        self.assertEqual(item.priority, WorkItem.PRIORITY_HIGH)

    def test_employee_creation_is_self_assigned_and_scoped(self):
        response = self.auth(self.employee).post(
            reverse('workload-api:work-item-list'),
            {'title': 'Employee API item'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        item = WorkItem.objects.get(title='Employee API item')
        self.assertEqual(item.tenant, self.employee)
        self.assertEqual(item.assignee, self.employee)
        self.assertEqual(item.status, WorkItem.STATUS_ASSIGNED)

    def test_client_cannot_create_items(self):
        response = self.auth(self.client_user).post(
            reverse('workload-api:work-item-list'),
            {'title': 'Not allowed'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_employee_cannot_edit_someone_elses_item(self):
        foreign = self.make_item(
            title='Foreign', assignee=self.other, tenant=self.employee,
        )
        response = self.auth(self.employee).patch(
            reverse('workload-api:work-item-detail', args=[foreign.pk]),
            {'title': 'Hijacked'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_employee_edits_own_item(self):
        response = self.auth(self.employee).patch(
            reverse('workload-api:work-item-detail', args=[self.item.pk]),
            {'title': 'Updated title'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.title, 'Updated title')

    def test_delete_requires_manager(self):
        url = reverse('workload-api:work-item-detail', args=[self.item.pk])
        self.assertEqual(
            self.auth(self.employee).delete(url).status_code, 403,
        )
        self.assertEqual(
            self.auth(self.manager).delete(url).status_code, 204,
        )
        self.assertFalse(WorkItem.objects.filter(pk=self.item.pk).exists())

    def test_filters_and_search(self):
        self.make_item(title='Alpha searchable')
        response = self.auth(self.manager).get(
            reverse('workload-api:work-item-list'),
            {'search': 'searchable'},
        )
        self.assertEqual(response.data['count'], 1)
        response = self.auth(self.manager).get(
            reverse('workload-api:work-item-list'),
            {'status': WorkItem.STATUS_IN_PROGRESS},
        )
        self.assertEqual(response.data['count'], 1)

    def test_status_action(self):
        response = self.auth(self.employee).post(
            reverse('workload-api:work-item-status', args=[self.item.pk]),
            {'status': WorkItem.STATUS_COMPLETED, 'actual_hours': '5'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, WorkItem.STATUS_COMPLETED)

        invalid = self.auth(self.manager).post(
            reverse('workload-api:work-item-status', args=[self.item.pk]),
            {'status': 'NOT_REAL'},
            format='json',
        )
        self.assertEqual(invalid.status_code, 400)

    def test_assign_action_and_permissions(self):
        url = reverse('workload-api:work-item-assign', args=[self.item.pk])
        self.assertEqual(
            self.auth(self.employee).post(
                url, {'assignee': self.other.pk}, format='json',
            ).status_code,
            403,
        )
        response = self.auth(self.manager).post(
            url, {'assignee': self.other.pk, 'allocated_hours': '4'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.assignee, self.other)
        self.assertTrue(
            self.item.assignments.filter(
                resource=self.other_resource,
                status=WorkAssignment.STATUS_ACTIVE,
            ).exists(),
        )

    def test_recommendations_action(self):
        self.make_item(title='Needs recommendation')
        item = WorkItem.objects.get(title='Needs recommendation')
        url = reverse('workload-api:work-item-recommendations', args=[item.pk])
        response = self.auth(self.manager).get(url)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.data), 1)
        self.assertIn('score_percent', response.data[0])
        self.assertEqual(self.auth(self.employee).get(url).status_code, 404)

    # ------------------------------------------------------------------ #
    # Resources, teams, alerts, policies, dashboard
    # ------------------------------------------------------------------ #
    def test_resource_endpoints_are_manager_only(self):
        url = reverse('workload-api:resource-list')
        self.assertEqual(self.auth(self.employee).get(url).status_code, 403)
        response = self.auth(self.manager).get(url)
        self.assertEqual(response.status_code, 200)
        utilization = self.auth(self.manager).get(
            reverse('workload-api:resource-utilization'),
        )
        self.assertEqual(utilization.status_code, 200)
        self.assertTrue(utilization.data)

    def test_team_endpoints(self):
        self.make_team(name='API team', members=[self.employee])
        url = reverse('workload-api:team-list')
        self.assertEqual(self.auth(self.employee).get(url).status_code, 403)
        response = self.auth(self.manager).get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_alert_acknowledge_endpoint(self):
        alert = WorkloadAlert.objects.create(
            alert_type=WorkloadAlert.TYPE_OVERDUE,
            message='API alert',
            dedupe_key='api-alert',
        )
        list_url = reverse('workload-api:alert-list')
        self.assertEqual(self.auth(self.manager).get(list_url).status_code, 200)
        response = self.auth(self.manager).post(
            reverse('workload-api:alert-acknowledge', args=[alert.pk]),
        )
        self.assertEqual(response.status_code, 200)
        alert.refresh_from_db()
        self.assertEqual(alert.status, WorkloadAlert.STATUS_ACKNOWLEDGED)

    def test_policy_endpoints_are_admin_only(self):
        url = reverse('workload-api:policy-list')
        self.assertEqual(self.auth(self.manager).get(url).status_code, 403)
        response = self.auth(self.admin).get(url)
        self.assertEqual(response.status_code, 200)
        created = self.auth(self.admin).post(
            url, {'name': 'API policy', 'is_default': False}, format='json',
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(WorkloadPolicy.objects.filter(name='API policy').exists())

    def test_dashboard_metrics_are_json_serialisable(self):
        assign_work_item = self.item
        from workload.services import assign_work

        assign_work(
            assign_work_item, resource=self.resource, actor=self.manager,
            allocated_hours=20,
        )
        response = self.auth(self.manager).get(
            reverse('workload-api:dashboard-metrics'),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 1)
        self.assertNotIn('live_alerts', response.data)
        json.dumps(response.data)
