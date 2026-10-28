from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .execution.engine import (
    enqueue_workflow_execution,
    quota_status,
    run_execution,
    write_execution_log,
)
from .execution.errors import BillingRequired, ExecutionRejected, QuotaExceeded
from .models import AutomationExecution, ExecutionLog, IntegrationConnection, UsageRecord
from .security.ssrf import SafeHTTPResponse
from .testing import (
    make_customer,
    make_plan,
    make_subscription,
    make_user,
    make_workflow,
)

TEST_FERNET_KEY = Fernet.generate_key().decode()


class AutomationFixtures:
    def setUp(self):
        self.user = make_user('execution-owner')
        self.customer = make_customer(self.user)
        self.plan = make_plan('essential', limit=10)
        self.subscription = make_subscription(self.customer, self.plan)
        self.workflow = make_workflow(self.customer, user=self.user)


@override_settings(
    AUTOMATION_EXECUTION_MODE='inline',
    AUTOMATION_CREDENTIAL_ENCRYPTION_KEY=TEST_FERNET_KEY,
    AUTOMATION_RETRY_BACKOFF_SECONDS=0,
    AUTOMATION_ALLOW_PRIVATE_OUTBOUND=False,
)
class ExecutionEngineTests(AutomationFixtures, TestCase):
    @patch('automation.execution.actions._send_email')
    def test_email_execution_succeeds_and_meters_usage(self, send_email):
        execution, created = enqueue_workflow_execution(
            self.workflow,
            execution_key='exec-success',
        )
        self.assertTrue(created)
        execution.refresh_from_db()

        self.assertEqual(execution.status, 'succeeded')
        self.assertEqual(execution.attempt_count, 1)
        self.assertEqual(execution.usage_count, 1)
        self.assertIsNotNone(execution.completed_at)
        self.assertGreaterEqual(execution.duration_seconds, 0)
        self.assertEqual(send_email.call_count, 1)

        usage = UsageRecord.objects.get(
            subscription=self.subscription,
            metric='execution_count',
        )
        self.assertEqual(usage.used_count, 1)
        self.assertEqual(usage.limit_value, 10)
        self.assertTrue(ExecutionLog.objects.filter(execution=execution, level='info').exists())
        self.assertEqual(quota_status(self.subscription).used, 1)

    @override_settings(AUTOMATION_EXECUTION_MODE='celery')
    @patch('automation.tasks.execute_workflow_task.delay')
    def test_celery_mode_enqueues_task_without_inline_execution(self, delay):
        execution, created = enqueue_workflow_execution(
            self.workflow,
            execution_key='celery-key',
        )
        self.assertTrue(created)
        delay.assert_called_once_with(execution.pk)
        execution.refresh_from_db()
        self.assertEqual(execution.status, 'queued')
        self.assertEqual(UsageRecord.objects.get(subscription=self.subscription).used_count, 1)

    @patch('automation.execution.actions._send_email')
    def test_duplicate_execution_key_does_not_double_charge_or_rerun(self, send_email):
        first, created = enqueue_workflow_execution(
            self.workflow,
            execution_key='idempotent-key',
            dispatch=False,
        )
        second, second_created = enqueue_workflow_execution(
            self.workflow,
            execution_key='idempotent-key',
            dispatch=False,
        )
        self.assertTrue(created)
        self.assertFalse(second_created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(UsageRecord.objects.get(subscription=self.subscription).used_count, 1)
        self.assertEqual(send_email.call_count, 0)

        run_execution(first.pk)
        run_execution(first.pk)  # duplicate task delivery
        first.refresh_from_db()
        self.assertEqual(first.status, 'succeeded')
        self.assertEqual(first.attempt_count, 1)
        self.assertEqual(send_email.call_count, 1)

    @patch('automation.execution.actions._send_email')
    def test_recent_running_execution_is_not_executed_twice(self, send_email):
        execution, _ = enqueue_workflow_execution(
            self.workflow,
            execution_key='concurrent-key',
            dispatch=False,
        )
        # Simulate a second worker receiving the same task while the first is
        # still executing it.
        AutomationExecution.objects.filter(pk=execution.pk).update(
            status='running',
            started_at=timezone.now(),
            attempt_count=1,
        )

        result = run_execution(execution.pk)

        self.assertEqual(result['status'], 'running')
        self.assertTrue(result.get('duplicate'))
        self.assertEqual(send_email.call_count, 0)
        execution.refresh_from_db()
        self.assertEqual(execution.status, 'running')
        self.assertEqual(execution.attempt_count, 1)

    @override_settings(AUTOMATION_STALE_EXECUTION_SECONDS=60)
    @patch('automation.execution.actions._send_email')
    def test_stale_running_execution_is_taken_over(self, send_email):
        execution, _ = enqueue_workflow_execution(
            self.workflow,
            execution_key='stale-key',
            dispatch=False,
        )
        AutomationExecution.objects.filter(pk=execution.pk).update(
            status='running',
            started_at=timezone.now() - timedelta(seconds=120),
            attempt_count=1,
        )

        result = run_execution(execution.pk)

        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(send_email.call_count, 1)
        execution.refresh_from_db()
        self.assertEqual(execution.status, 'succeeded')
        self.assertEqual(execution.attempt_count, 2)
        self.assertTrue(execution.logs.filter(message__icontains='stale').exists())

    @patch('automation.execution.actions._send_email')
    def test_retryable_failure_is_bounded(self, send_email):
        send_email.side_effect = RuntimeError('SMTP unavailable')
        execution, _ = enqueue_workflow_execution(
            self.workflow,
            execution_key='retry-key',
            dispatch=False,
        )
        with override_settings(AUTOMATION_MAX_EXECUTION_ATTEMPTS=2):
            result = run_execution(execution.pk)

        execution.refresh_from_db()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(execution.status, 'failed')
        self.assertEqual(execution.attempt_count, 2)
        self.assertEqual(execution.failure_code, 'email_delivery_failed')
        self.assertEqual(send_email.call_count, 2)
        self.assertTrue(execution.logs.filter(message__icontains='retry').exists())

    @patch('automation.execution.actions._send_email')
    def test_non_retryable_action_failure_stops_after_one_attempt(self, send_email):
        self.workflow.config = {'steps': [{
            'type': 'email',
            'config': {'to': 'not-an-email', 'subject': 'x', 'body': 'y'},
        }]}
        self.workflow.save(update_fields=['config'])
        execution, _ = enqueue_workflow_execution(
            self.workflow,
            execution_key='nonretry-key',
            dispatch=False,
        )
        run_execution(execution.pk)
        execution.refresh_from_db()
        self.assertEqual(execution.status, 'failed')
        self.assertEqual(execution.attempt_count, 1)
        self.assertEqual(execution.failure_code, 'invalid_action_config')
        self.assertEqual(send_email.call_count, 0)

    def test_unapproved_action_type_never_executes(self):
        self.workflow.config = {'steps': [{'type': 'python', 'config': {'code': 'print(1)'}}]}
        self.workflow.save(update_fields=['config'])
        execution, _ = enqueue_workflow_execution(
            self.workflow,
            execution_key='python-key',
            dispatch=False,
        )
        run_execution(execution.pk)
        execution.refresh_from_db()
        self.assertEqual(execution.status, 'failed')
        self.assertEqual(execution.failure_code, 'invalid_configuration')

    def test_quota_is_enforced_server_side(self):
        self.plan.monthly_execution_limit = 1
        self.plan.save(update_fields=['monthly_execution_limit'])
        enqueue_workflow_execution(self.workflow, execution_key='quota-1', dispatch=False)
        with self.assertRaises(QuotaExceeded):
            enqueue_workflow_execution(self.workflow, execution_key='quota-2', dispatch=False)
        self.assertEqual(UsageRecord.objects.get(subscription=self.subscription).used_count, 1)

    def test_inactive_subscription_blocks_execution(self):
        self.subscription.is_active = False
        self.subscription.save(update_fields=['is_active'])
        with self.assertRaises(BillingRequired):
            enqueue_workflow_execution(self.workflow, execution_key='inactive-key', dispatch=False)

    def test_non_active_workflow_cannot_be_triggered(self):
        self.workflow.status = 'paused'
        self.workflow.save(update_fields=['status'])
        with self.assertRaises(ExecutionRejected) as caught:
            enqueue_workflow_execution(self.workflow, execution_key='paused-key', dispatch=False)
        self.assertEqual(caught.exception.code, 'workflow_not_active')

    def test_task_rejects_cross_tenant_subscription(self):
        other_user = make_user('other-owner')
        other_customer = make_customer(other_user, name='Other Co')
        other_subscription = make_subscription(other_customer, self.plan)
        execution = AutomationExecution.objects.create(
            workflow=self.workflow,
            subscription=other_subscription,
            status='queued',
            trigger='manual',
            execution_key='tenant-mismatch-key',
        )
        result = run_execution(execution.pk)
        execution.refresh_from_db()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(execution.failure_code, 'tenant_mismatch')
        self.assertFalse(execution.logs.filter(level='info').exists())

    def test_http_action_blocks_private_destination(self):
        connection = IntegrationConnection.objects.create(
            customer=self.customer,
            name='Private API',
            provider='custom',
            status='active',
        )
        connection.set_credentials({'token': 'never-log-this-token'})
        connection.save()
        self.workflow.config = {'steps': [{
            'type': 'http_request',
            'config': {
                'method': 'POST',
                'url': 'http://127.0.0.1/internal',
                'connection_id': connection.pk,
            },
        }]}
        self.workflow.save(update_fields=['config'])
        execution, _ = enqueue_workflow_execution(
            self.workflow,
            execution_key='ssrf-key',
            dispatch=False,
        )
        run_execution(execution.pk)
        execution.refresh_from_db()
        self.assertEqual(execution.status, 'failed')
        self.assertEqual(execution.failure_code, 'ssrf_blocked')
        self.assertNotIn('never-log-this-token', str(list(execution.logs.values_list('message', 'payload'))))

    @patch('automation.execution.actions.safe_http_request')
    def test_http_action_uses_encrypted_connection_credentials(self, request_mock):
        request_mock.return_value = SafeHTTPResponse(
            status_code=200,
            url='https://api.example.test/hook',
            headers={'Content-Type': 'application/json'},
            body=b'{"ok": true}',
        )
        connection = IntegrationConnection.objects.create(
            customer=self.customer,
            name='API',
            provider='custom',
            status='active',
        )
        connection.set_credentials({'token': 'secret-from-vault'})
        connection.save()
        self.workflow.config = {'steps': [{
            'type': 'http_request',
            'config': {
                'method': 'POST',
                'url': 'https://api.example.test/hook',
                'connection_id': connection.pk,
                'json': {'hello': 'world'},
            },
        }]}
        self.workflow.save(update_fields=['config'])
        execution, _ = enqueue_workflow_execution(
            self.workflow,
            execution_key='http-key',
            dispatch=False,
        )
        run_execution(execution.pk)
        execution.refresh_from_db()

        self.assertEqual(execution.status, 'succeeded')
        self.assertEqual(request_mock.call_count, 1)
        _, kwargs = request_mock.call_args
        self.assertEqual(kwargs['headers']['authorization'], 'Bearer secret-from-vault')
        self.assertEqual(kwargs['headers']['idempotency-key'], 'http-key')

    def test_logs_are_redacted_before_storage(self):
        execution, _ = enqueue_workflow_execution(
            self.workflow,
            execution_key='redaction-key',
            dispatch=False,
        )
        write_execution_log(
            execution,
            'error',
            'Authorization: Bearer super-secret',
            {'token': 'super-secret', 'safe': 'kept'},
        )
        log = execution.logs.last()
        self.assertNotIn('super-secret', log.message)
        self.assertEqual(log.payload['token'], '***REDACTED***')
        self.assertEqual(log.payload['safe'], 'kept')


@override_settings(
    AUTOMATION_EXECUTION_MODE='inline',
    AUTOMATION_CREDENTIAL_ENCRYPTION_KEY=TEST_FERNET_KEY,
    AUTOMATION_RETRY_BACKOFF_SECONDS=0,
)
class TriggerEndpointTests(AutomationFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_public_automation_page_shows_pricing_plans(self):
        response = self.client.get(reverse('home:automation_home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Automation That Scales With Your Business')
        self.assertContains(response, 'Starter')
        self.assertContains(response, 'Enterprise')
        self.assertContains(response, 'Custom')
        self.assertContains(response, '$29')
        self.assertContains(response, '$199')
        self.assertContains(response, 'Get Started')
        self.assertContains(response, 'Choose Enterprise')
        self.assertContains(response, 'Discuss Your Project')
        # Custom plan routes to the public RPA consultation form, which is
        # reachable without an account.
        self.assertContains(response, reverse('home:rpa_solutions') + '#consultation')

    @patch('automation.execution.actions._send_email')
    def test_trigger_endpoint_is_idempotent(self, send_email):
        url = reverse('automation:workflow_trigger', args=[self.workflow.pk])
        response = self.client.post(url, HTTP_IDEMPOTENCY_KEY='endpoint-key', HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.json()['created'])
        second = self.client.post(url, HTTP_IDEMPOTENCY_KEY='endpoint-key', HTTP_ACCEPT='application/json')
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()['created'])
        self.assertEqual(UsageRecord.objects.get(subscription=self.subscription).used_count, 1)
        self.assertEqual(send_email.call_count, 1)

    def test_other_tenant_cannot_trigger_or_read_execution(self):
        other_user = make_user('intruder')
        make_customer(other_user, name='Intruder Co')
        execution = AutomationExecution.objects.create(
            workflow=self.workflow,
            status='queued',
            trigger='manual',
            execution_key='other-execution',
        )
        self.client.force_login(other_user)
        self.assertEqual(
            self.client.post(reverse('automation:workflow_trigger', args=[self.workflow.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse('automation:execution_status', args=[execution.pk])).status_code,
            404,
        )

    @patch('automation.execution.actions._send_email')
    def test_quota_exceeded_returns_429(self, send_email):
        self.plan.monthly_execution_limit = 1
        self.plan.save(update_fields=['monthly_execution_limit'])
        url = reverse('automation:workflow_trigger', args=[self.workflow.pk])
        self.assertEqual(
            self.client.post(url, HTTP_IDEMPOTENCY_KEY='q1', HTTP_ACCEPT='application/json').status_code,
            202,
        )
        second = self.client.post(url, HTTP_IDEMPOTENCY_KEY='q2', HTTP_ACCEPT='application/json')
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()['code'], 'quota_exceeded')


@override_settings(AUTOMATION_STALE_EXECUTION_SECONDS=60)
class RequeueStaleExecutionsCommandTests(AutomationFixtures, TestCase):
    def _running_execution(self, key: str, seconds_ago: int):
        execution, _ = enqueue_workflow_execution(
            self.workflow,
            execution_key=key,
            dispatch=False,
        )
        AutomationExecution.objects.filter(pk=execution.pk).update(
            status='running',
            started_at=timezone.now() - timedelta(seconds=seconds_ago),
            attempt_count=1,
        )
        return execution

    @patch('automation.management.commands.requeue_stale_executions.dispatch_execution')
    def test_requeues_only_stale_running_executions(self, dispatch):
        stale = self._running_execution('stale-running', seconds_ago=120)
        fresh = self._running_execution('fresh-running', seconds_ago=5)

        out = StringIO()
        call_command('requeue_stale_executions', stdout=out)

        dispatch.assert_called_once_with(stale.pk)
        stale.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(stale.status, 'queued')
        self.assertIsNone(stale.started_at)
        self.assertEqual(fresh.status, 'running')
        self.assertIn(str(stale.pk), out.getvalue())

    @patch('automation.management.commands.requeue_stale_executions.dispatch_execution')
    def test_dry_run_changes_nothing(self, dispatch):
        stale = self._running_execution('dry-run-stale', seconds_ago=120)

        out = StringIO()
        call_command('requeue_stale_executions', '--dry-run', stdout=out)

        dispatch.assert_not_called()
        stale.refresh_from_db()
        self.assertEqual(stale.status, 'running')
        self.assertIn('would be requeued', out.getvalue())

