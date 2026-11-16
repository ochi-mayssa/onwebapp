"""Web interface, permissions and tenant isolation tests."""
from __future__ import annotations

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from workload.models import (
    WorkAssignment,
    WorkItem,
    WorkItemAttachment,
    WorkloadAlert,
    WorkloadResource,
)
from workload.permissions import (
    ROLE_ADMIN,
    ROLE_CLIENT,
    ROLE_EMPLOYEE,
    ROLE_MANAGER,
    can_edit_work_item,
    can_view_work_item,
    get_role,
    is_admin,
    is_manager,
    scope_alerts,
    scope_resources,
    scope_work_items,
)
from workload.selectors import filter_work_items, trend_series, work_item_queryset
from workload.tests.base import WorkloadTestBase


class RoleAndScopeTests(WorkloadTestBase):
    def test_role_mapping(self):
        self.assertEqual(get_role(self.admin), ROLE_ADMIN)
        self.assertEqual(get_role(self.manager), ROLE_MANAGER)
        self.assertEqual(get_role(self.employee), ROLE_EMPLOYEE)
        self.assertEqual(get_role(self.client_user), ROLE_CLIENT)
        self.assertTrue(is_admin(self.admin))
        self.assertFalse(is_admin(self.manager))
        self.assertTrue(is_manager(self.manager))
        self.assertFalse(is_manager(self.employee))

    def test_manager_sees_all_work_items(self):
        item = self.make_item(title='Manager visible')
        self.assertIn(item, scope_work_items(work_item_queryset(), self.manager))

    def test_employee_scope_is_limited(self):
        mine = self.make_item(title='Assigned to me', assignee=self.employee)
        created = self.make_item(title='Created by me', created_by=self.employee)
        hidden = self.make_item(title='Hidden')
        visible = set(scope_work_items(work_item_queryset(), self.employee))
        self.assertIn(mine, visible)
        self.assertIn(created, visible)
        self.assertNotIn(hidden, visible)

    def test_client_only_sees_explicitly_visible_tenant_records(self):
        visible = self.make_item(
            title='Visible', tenant=self.client_user, is_client_visible=True,
        )
        hidden = self.make_item(title='Hidden', tenant=self.client_user)
        foreign = self.make_item(
            title='Foreign', tenant=self.other, is_client_visible=True,
        )
        scoped = set(scope_work_items(work_item_queryset(), self.client_user))
        self.assertIn(visible, scoped)
        self.assertNotIn(hidden, scoped)
        self.assertNotIn(foreign, scoped)

    def test_object_permissions(self):
        item = self.make_item(assignee=self.employee)
        self.assertTrue(can_view_work_item(self.manager, item))
        self.assertTrue(can_view_work_item(self.employee, item))
        self.assertFalse(can_view_work_item(self.other, item))
        self.assertTrue(can_edit_work_item(self.employee, item))
        self.assertFalse(can_edit_work_item(self.other, item))

    def test_resource_and_alert_scope(self):
        own = self.make_resource(self.employee)
        other = self.make_resource(self.other)
        resources = set(scope_resources(WorkloadResource.objects.all(), self.employee))
        self.assertIn(own, resources)
        self.assertNotIn(other, resources)

        alert = WorkloadAlert.objects.create(
            alert_type=WorkloadAlert.TYPE_OVERDUE,
            recipient=self.employee,
            message='Mine',
            dedupe_key='scope-alert',
        )
        self.assertIn(alert, scope_alerts(WorkloadAlert.objects.all(), self.employee))
        self.assertNotIn(alert, scope_alerts(WorkloadAlert.objects.all(), self.client_user))


class FilterSelectorTests(WorkloadTestBase):
    def test_search_and_filters(self):
        a = self.make_item(title='Alpha website', priority=WorkItem.PRIORITY_HIGH)
        b = self.make_item(title='Beta automation', status=WorkItem.STATUS_BLOCKED)
        self.make_item(title='Gamma')

        self.assertEqual(
            list(filter_work_items(WorkItem.objects.all(), {'q': 'alpha'})),
            [a],
        )
        self.assertEqual(
            list(filter_work_items(WorkItem.objects.all(), {'status': 'BLOCKED'})),
            [b],
        )
        self.assertEqual(
            list(filter_work_items(WorkItem.objects.all(), {'priority': 'HIGH'})),
            [a],
        )
        self.assertEqual(
            filter_work_items(WorkItem.objects.all(), {'unassigned': '1'}).count(),
            2,
        )

    def test_sorting_and_unknown_sort_falls_back(self):
        low = self.make_item(title='Zulu', priority=WorkItem.PRIORITY_LOW)
        high = self.make_item(title='Alpha', priority=WorkItem.PRIORITY_CRITICAL)
        ordered = list(filter_work_items(WorkItem.objects.all(), {'sort': 'priority'}))
        self.assertEqual(ordered[0], high)
        self.assertEqual(ordered[-1], low)
        fallback = filter_work_items(WorkItem.objects.all(), {'sort': 'nonsense'})
        self.assertTrue(fallback.exists())

    def test_trend_series_returns_eight_weeks(self):
        self.make_item(title='Trend item')
        series = trend_series(WorkItem.objects.all())
        self.assertEqual(len(series), 8)
        self.assertGreaterEqual(sum(row['created'] for row in series), 1)

    def test_query_helpers_keep_filters(self):
        from workload.templatetags.workload_tags import clamp_percent, get_item

        self.assertEqual(clamp_percent(140), 100)
        self.assertEqual(clamp_percent(-5), 0)
        self.assertEqual(clamp_percent('bad'), 0)
        self.assertEqual(get_item({'a': 1}, 'a'), 1)


class WebViewTests(WorkloadTestBase):
    def setUp(self):
        self.item = self.make_item(
            title='Viewable', assignee=self.employee,
            status=WorkItem.STATUS_IN_PROGRESS,
        )
        self.resource = self.make_resource(self.employee)

    def login(self, user):
        self.client.force_login(user)

    def test_anonymous_is_redirected_to_login(self):
        for name in ('dashboard', 'work_item_list'):
            response = self.client.get(reverse(f'workload:{name}'))
            self.assertEqual(response.status_code, 302)

    def test_manager_can_open_every_main_page(self):
        self.login(self.manager)
        for name in (
            'dashboard', 'work_item_list', 'monitoring', 'resource_list',
            'team_list', 'policy_list', 'alert_list',
        ):
            response = self.client.get(reverse(f'workload:{name}'))
            self.assertEqual(response.status_code, 200, msg=name)
        detail = self.client.get(
            reverse('workload:work_item_detail', args=[self.item.pk]),
        )
        self.assertEqual(detail.status_code, 200)

    def test_employee_cannot_open_manager_pages(self):
        self.login(self.employee)
        for name in ('resource_list', 'team_list', 'monitoring', 'alert_list'):
            response = self.client.get(reverse(f'workload:{name}'))
            self.assertEqual(response.status_code, 403, msg=name)

    def test_client_cannot_create_work_items(self):
        self.login(self.client_user)
        response = self.client.get(reverse('workload:work_item_create'))
        self.assertEqual(response.status_code, 403)

    def test_employee_creates_scoped_self_assigned_item(self):
        self.login(self.employee)
        response = self.client.post(
            reverse('workload:work_item_create'),
            {
                'title': 'Employee task',
                'description': 'Do it',
                'category': WorkItem.CATEGORY_HUMAN,
                'priority': WorkItem.PRIORITY_MEDIUM,
                'status': WorkItem.STATUS_NEW,
                'source_module': WorkItem.SOURCE_MANUAL,
                'estimated_hours': '4',
                'actual_hours': '0',
            },
        )
        self.assertEqual(response.status_code, 302)
        item = WorkItem.objects.get(title='Employee task')
        self.assertEqual(item.tenant, self.employee)
        self.assertEqual(item.assignee, self.employee)
        self.assertEqual(item.status, WorkItem.STATUS_ASSIGNED)

    def test_manager_creates_item_and_assigns_owner(self):
        self.login(self.manager)
        response = self.client.post(
            reverse('workload:work_item_create'),
            {
                'title': 'Manager task',
                'category': WorkItem.CATEGORY_BUSINESS,
                'priority': WorkItem.PRIORITY_HIGH,
                'status': WorkItem.STATUS_NEW,
                'source_module': WorkItem.SOURCE_MANUAL,
                'assignee': self.employee.pk,
                'estimated_hours': '6',
                'actual_hours': '0',
            },
        )
        self.assertEqual(response.status_code, 302)
        item = WorkItem.objects.get(title='Manager task')
        self.assertEqual(item.assignee, self.employee)
        self.assertTrue(
            item.assignments.filter(status=WorkAssignment.STATUS_ACTIVE).exists(),
        )

    def test_employee_status_update(self):
        self.login(self.employee)
        response = self.client.post(
            reverse('workload:work_item_status', args=[self.item.pk]),
            {'status': WorkItem.STATUS_COMPLETED, 'actual_hours': '7'},
        )
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, WorkItem.STATUS_COMPLETED)
        self.assertEqual(self.item.actual_hours, 7)

    def test_other_employee_cannot_view_item(self):
        self.login(self.other)
        response = self.client.get(
            reverse('workload:work_item_detail', args=[self.item.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_manager_assigns_and_edits_item(self):
        self.login(self.manager)
        response = self.client.post(
            reverse('workload:work_item_assign', args=[self.item.pk]),
            {'assignee': self.other.pk, 'allocated_hours': '3'},
        )
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.assignee, self.other)

        edit = self.client.post(
            reverse('workload:work_item_edit', args=[self.item.pk]),
            {
                'title': 'Edited title',
                'description': 'Updated',
                'category': WorkItem.CATEGORY_HUMAN,
                'priority': WorkItem.PRIORITY_CRITICAL,
                'status': WorkItem.STATUS_IN_PROGRESS,
                'assignee': self.other.pk,
                'source_module': WorkItem.SOURCE_MANUAL,
                'estimated_hours': '8',
                'actual_hours': '1',
            },
        )
        self.assertEqual(edit.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.title, 'Edited title')
        self.assertEqual(self.item.priority, WorkItem.PRIORITY_CRITICAL)

    def test_bulk_status_update(self):
        second = self.make_item(title='Second')
        self.login(self.manager)
        response = self.client.post(
            reverse('workload:work_item_bulk'),
            {
                'ids': [self.item.pk, second.pk],
                'action': 'status',
                'status': WorkItem.STATUS_CANCELLED,
                'note': 'Batch cancellation',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(self.item.status, WorkItem.STATUS_CANCELLED)
        self.assertEqual(second.status, WorkItem.STATUS_CANCELLED)

    def test_delete_requires_manager_and_post(self):
        self.login(self.manager)
        self.assertEqual(
            self.client.get(
                reverse('workload:work_item_delete', args=[self.item.pk]),
            ).status_code,
            405,
        )
        self.login(self.employee)
        self.assertEqual(
            self.client.post(
                reverse('workload:work_item_delete', args=[self.item.pk]),
            ).status_code,
            403,
        )
        self.login(self.manager)
        response = self.client.post(
            reverse('workload:work_item_delete', args=[self.item.pk]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(WorkItem.objects.filter(pk=self.item.pk).exists())

    def test_attachment_upload_and_download(self):
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, True)
        self.login(self.employee)
        upload = SimpleUploadedFile(
            'notes.txt', b'attachment-body', content_type='text/plain',
        )
        with override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse('workload:attachment_upload', args=[self.item.pk]),
                {'file': upload},
            )
            self.assertEqual(response.status_code, 302)
            attachment = WorkItemAttachment.objects.get(work_item=self.item)
            self.assertEqual(attachment.original_name, 'notes.txt')

            download = self.client.get(
                reverse('workload:attachment_download', args=[attachment.pk]),
            )
            self.assertEqual(download.status_code, 200)
            self.assertEqual(
                b''.join(download.streaming_content), b'attachment-body',
            )

    def test_refresh_monitoring_creates_alerts(self):
        self.make_item(
            title='Overdue', status=WorkItem.STATUS_IN_PROGRESS,
            due_date=self.due(-1),
        )
        self.login(self.manager)
        response = self.client.post(reverse('workload:refresh_monitoring'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(WorkloadAlert.objects.exists())

    def test_alert_actions(self):
        alert = WorkloadAlert.objects.create(
            alert_type=WorkloadAlert.TYPE_BLOCKED,
            message='Blocked work',
            dedupe_key='web-alert-action',
        )
        self.login(self.manager)
        response = self.client.post(
            reverse('workload:alert_action', args=[alert.pk, 'acknowledge']),
        )
        self.assertEqual(response.status_code, 302)
        alert.refresh_from_db()
        self.assertEqual(alert.status, WorkloadAlert.STATUS_ACKNOWLEDGED)

        response = self.client.post(
            reverse('workload:alert_action', args=[alert.pk, 'resolve']),
        )
        alert.refresh_from_db()
        self.assertEqual(alert.status, WorkloadAlert.STATUS_RESOLVED)
