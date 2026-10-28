"""Bounded, idempotent workflow execution engine.

The engine deliberately stays small and deterministic:

1. a trigger reserves quota and creates an ``AutomationExecution`` atomically;
2. a Celery (or explicitly configured inline) task calls ``run_execution``;
3. steps are read from an approved registry and executed in order;
4. completed steps are checkpointed so a retry does not replay side effects;
5. every log entry is redacted before it reaches the database.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import AutomationExecution, AutomationWorkflow, ExecutionLog, Subscription, UsageRecord
from ..security.redaction import redact_mapping, redact_text
from .actions import ActionContext, get_action
from .errors import (
    ActionError,
    AutomationExecutionError,
    BillingRequired,
    ExecutionConfigurationError,
    ExecutionRejected,
    ExecutionTimeout,
    QuotaExceeded,
)

logger = logging.getLogger('automation')

TERMINAL_STATUSES = {'succeeded', 'failed', 'timed_out', 'cancelled'}
DEFAULT_EXECUTION_TIMEOUT = 60
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF = 2.0
DEFAULT_MAX_STEPS = 20
DEFAULT_MAX_PAYLOAD_BYTES = 64 * 1024
DEFAULT_STALE_EXECUTION_SECONDS = 900


@dataclass(frozen=True)
class QuotaStatus:
    used: int
    limit: int
    window: str

    @property
    def remaining(self) -> int | None:
        return None if self.limit <= 0 else max(0, self.limit - self.used)

    @property
    def exceeded(self) -> bool:
        return self.limit > 0 and self.used >= self.limit


def usage_window(now=None) -> str:
    return (now or timezone.now()).strftime('%Y-%m')


def active_subscription_for(customer):
    return (
        Subscription.objects.filter(customer=customer, status='active', is_active=True)
        .order_by('-created_at')
        .first()
    )


def quota_status(subscription: Subscription, *, now=None) -> QuotaStatus:
    window = usage_window(now)
    limit = int(subscription.plan.monthly_execution_limit or 0)
    usage = UsageRecord.objects.filter(
        subscription=subscription,
        metric='execution_count',
        usage_window=window,
    ).first()
    return QuotaStatus(used=usage.used_count if usage else 0, limit=limit, window=window)


def _reserve_usage_locked(subscription: Subscription, *, now=None) -> UsageRecord:
    """Increment the quota row while the caller holds a transaction.

    ``0`` means unlimited for plans configured that way. The check and increment
    happen under ``select_for_update`` so concurrent triggers cannot overshoot.
    """
    window = usage_window(now)
    limit = int(subscription.plan.monthly_execution_limit or 0)
    usage, _ = UsageRecord.objects.select_for_update().get_or_create(
        subscription=subscription,
        metric='execution_count',
        usage_window=window,
        defaults={'used_count': 0, 'limit_value': limit},
    )
    if usage.limit_value != limit:
        usage.limit_value = limit
    if limit > 0 and usage.used_count >= limit:
        usage.save(update_fields=['limit_value'])
        raise QuotaExceeded(used=usage.used_count, limit=limit, window=window)
    usage.used_count += 1
    usage.save(update_fields=['used_count', 'limit_value'])
    return usage


def _active_subscription_locked(customer):
    return (
        Subscription.objects.select_for_update()
        .filter(customer=customer, status='active', is_active=True)
        .order_by('-created_at')
        .first()
    )


def _normalise_payload(payload: Any) -> dict[str, Any]:
    if payload in (None, ''):
        return {}
    if not isinstance(payload, dict):
        raise ExecutionRejected('Execution payload must be a JSON object.', code='invalid_payload')
    encoded = repr(payload)
    max_bytes = int(getattr(settings, 'AUTOMATION_MAX_PAYLOAD_BYTES', DEFAULT_MAX_PAYLOAD_BYTES))
    if len(encoded.encode('utf-8')) > max_bytes:
        raise ExecutionRejected('Execution payload is too large.', code='invalid_payload')
    return payload


def enqueue_workflow_execution(
    workflow: AutomationWorkflow,
    *,
    trigger: str = 'manual',
    payload: dict[str, Any] | None = None,
    execution_key: str | None = None,
    dispatch: bool = True,
) -> tuple[AutomationExecution, bool]:
    """Create (or return) an execution and reserve quota.

    Returns ``(execution, created)``. Supplying the same ``execution_key`` twice
    returns the original execution without reserving additional usage.

    Raises ``BillingRequired``/``QuotaExceeded``/``ExecutionRejected`` before any
    execution row is created.
    """
    if workflow.status != 'active':
        raise ExecutionRejected('Workflow is not active.', code='workflow_not_active')
    if trigger not in dict(AutomationExecution.TRIGGER_CHOICES):
        raise ExecutionRejected('Unknown trigger.', code='invalid_trigger')

    key = (execution_key or uuid.uuid4().hex).strip()
    if not key or len(key) > 128:
        raise ExecutionRejected('Execution key must be 1-128 characters.', code='invalid_execution_key')
    clean_payload = _normalise_payload(payload)

    existing = AutomationExecution.objects.filter(execution_key=key).first()
    if existing:
        if existing.workflow_id != workflow.id:
            raise ExecutionRejected('Execution key is already used by another workflow.', code='execution_key_conflict')
        return existing, False

    try:
        with transaction.atomic():
            subscription = _active_subscription_locked(workflow.customer)
            if not subscription or not subscription.is_currently_active:
                raise BillingRequired('An active subscription is required to execute workflows.')
            _reserve_usage_locked(subscription)
            execution = AutomationExecution.objects.create(
                workflow=workflow,
                subscription=subscription,
                status='queued',
                trigger=trigger,
                execution_key=key,
                payload=clean_payload,
                usage_count=1,
            )
    except IntegrityError:
        # Concurrent duplicate key: return the winner without double-counting usage.
        existing = AutomationExecution.objects.filter(execution_key=key).first()
        if existing:
            if existing.workflow_id != workflow.id:
                raise ExecutionRejected('Execution key is already used by another workflow.', code='execution_key_conflict')
            return existing, False
        raise

    if dispatch:
        try:
            dispatch_execution(execution.pk)
        except Exception:
            # The execution is safely persisted as queued so an operator can retry.
            logger.exception('Could not dispatch execution %s', execution.pk)
            raise ExecutionRejected('Execution queue is unavailable.', code='queue_unavailable')
    return execution, True


def dispatch_execution(execution_id: int) -> None:
    mode = str(getattr(settings, 'AUTOMATION_EXECUTION_MODE', 'inline')).lower()
    if mode == 'celery':
        from ..tasks import execute_workflow_task

        execute_workflow_task.delay(execution_id)
        return
    if mode == 'inline':
        # Call the engine directly. This keeps local/test execution independent of
        # Celery task binding and never silently acknowledges queued work.
        run_execution(execution_id)
        return
    raise ExecutionRejected('AUTOMATION_EXECUTION_MODE must be celery or inline.', code='queue_unavailable')


def write_execution_log(execution: AutomationExecution, level: str, message: str, payload: dict | None = None) -> None:
    ExecutionLog.objects.create(
        execution=execution,
        level=level,
        message=redact_text(message)[:8000],
        payload=redact_mapping(payload or {}),
    )


def _log(execution_id: int, level: str, message: str, payload: dict | None = None) -> None:
    try:
        execution = AutomationExecution.objects.get(pk=execution_id)
        write_execution_log(execution, level, message, payload)
    except Exception:
        # Logging must never turn a successful or retryable action into an
        # unhandled worker failure; fall back to the redacting application log.
        logger.warning('Could not persist execution log for execution %s', execution_id)


def parse_steps(workflow: AutomationWorkflow) -> list[dict[str, Any]]:
    config = workflow.config or {}
    if not isinstance(config, dict):
        raise ExecutionConfigurationError('Workflow config must be an object.')
    raw_steps = config.get('steps')
    if raw_steps is None and 'action' in config:
        raw_steps = [config['action']]
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ExecutionConfigurationError('Workflow must define at least one execution step.')

    max_steps = int(getattr(settings, 'AUTOMATION_MAX_STEPS', DEFAULT_MAX_STEPS))
    if len(raw_steps) > max_steps:
        raise ExecutionConfigurationError('Workflow has too many steps.')

    steps: list[dict[str, Any]] = []
    for index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            raise ExecutionConfigurationError('Each workflow step must be an object.')
        unknown = set(raw_step) - {'type', 'config', 'name'}
        if unknown:
            raise ExecutionConfigurationError('Workflow step contains unsupported keys.')
        action_type = raw_step.get('type')
        action_config = raw_step.get('config', {})
        if not isinstance(action_config, dict):
            raise ExecutionConfigurationError('Workflow step config must be an object.')
        get_action(action_type)
        steps.append({'type': action_type, 'config': action_config, 'index': index})
    return steps


def _tenant_error(execution: AutomationExecution) -> str | None:
    workflow = execution.workflow
    if execution.subscription_id and execution.subscription:
        if execution.subscription.customer_id != workflow.customer_id:
            return 'Execution subscription does not belong to the workflow customer.'
    if workflow.request_id and workflow.request:
        if workflow.request.customer_id != workflow.customer_id:
            return 'Workflow request does not belong to the workflow customer.'
    return None


def _finish(
    execution_id: int,
    status: str,
    *,
    code: str = '',
    message: str = '',
    result: dict | None = None,
    completed_at=None,
) -> None:
    now = completed_at or timezone.now()
    with transaction.atomic():
        execution = AutomationExecution.objects.select_for_update().get(pk=execution_id)
        started = execution.started_at
        execution.status = status
        execution.completed_at = now
        execution.duration_seconds = max(0.0, (now - started).total_seconds()) if started else 0.0
        execution.failure_code = code[:64]
        execution.error_message = redact_text(message)[:8000]
        execution.next_retry_at = None
        if result is not None:
            execution.result = redact_mapping(result)
        execution.save(update_fields=[
            'status', 'completed_at', 'duration_seconds', 'failure_code',
            'error_message', 'next_retry_at', 'result',
        ])


def _fail(execution_id: int, code: str, message: str, result: dict | None = None) -> None:
    _log(execution_id, 'error', message, {'failure_code': code})
    _finish(execution_id, 'failed', code=code, message=message, result=result)


def _execution_timeout_seconds() -> float:
    try:
        return max(1.0, float(getattr(settings, 'AUTOMATION_EXECUTION_TIMEOUT_SECONDS', DEFAULT_EXECUTION_TIMEOUT)))
    except (TypeError, ValueError):
        return float(DEFAULT_EXECUTION_TIMEOUT)


def _max_attempts() -> int:
    try:
        return max(1, int(getattr(settings, 'AUTOMATION_MAX_EXECUTION_ATTEMPTS', DEFAULT_MAX_ATTEMPTS)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_ATTEMPTS


def _retry_backoff_seconds() -> float:
    try:
        return max(0.0, float(getattr(settings, 'AUTOMATION_RETRY_BACKOFF_SECONDS', DEFAULT_RETRY_BACKOFF)))
    except (TypeError, ValueError):
        return DEFAULT_RETRY_BACKOFF


def _stale_execution_seconds() -> float:
    """How long a ``running`` row may stay untouched before another worker may take it over.

    A row younger than this belongs to a live worker; executing it again would
    replay side effects. Keep the window comfortably larger than the execution
    timeout so an in-flight retry is never stolen.
    """
    try:
        return max(
            1.0,
            float(getattr(settings, 'AUTOMATION_STALE_EXECUTION_SECONDS', DEFAULT_STALE_EXECUTION_SECONDS)),
        )
    except (TypeError, ValueError):
        return float(DEFAULT_STALE_EXECUTION_SECONDS)


def run_execution(execution_id: int) -> dict[str, Any]:
    """Execute a queued execution. Safe to call repeatedly (idempotent)."""
    execution = (
        AutomationExecution.objects.select_related('workflow', 'workflow__request', 'subscription')
        .filter(pk=execution_id)
        .first()
    )
    if execution is None:
        logger.warning('Execution %s does not exist', execution_id)
        return {'status': 'missing', 'execution_id': execution_id}
    if execution.status == 'succeeded':
        return {'status': 'succeeded', 'execution_id': execution_id, 'duplicate': True}
    if execution.status in {'cancelled', 'timed_out'}:
        return {'status': execution.status, 'execution_id': execution_id, 'duplicate': True}

    tenant_error = _tenant_error(execution)
    if tenant_error:
        _fail(execution_id, 'tenant_mismatch', tenant_error)
        return {'status': 'failed', 'execution_id': execution_id, 'failure_code': 'tenant_mismatch'}

    workflow = execution.workflow
    if workflow.status != 'active':
        _fail(execution_id, 'workflow_not_active', 'Workflow is no longer active.')
        return {'status': 'failed', 'execution_id': execution_id, 'failure_code': 'workflow_not_active'}

    subscription = execution.subscription or active_subscription_for(workflow.customer)
    if not subscription or subscription.customer_id != workflow.customer_id or not subscription.is_currently_active:
        _fail(execution_id, 'subscription_inactive', 'An active subscription is required to execute workflows.')
        return {'status': 'failed', 'execution_id': execution_id, 'failure_code': 'subscription_inactive'}

    try:
        steps = parse_steps(workflow)
    except ExecutionConfigurationError as exc:
        _fail(execution_id, exc.code, str(exc))
        return {'status': 'failed', 'execution_id': execution_id, 'failure_code': exc.code}

    timeout_seconds = _execution_timeout_seconds()
    deadline = time.monotonic() + timeout_seconds
    max_attempts = _max_attempts()
    backoff = _retry_backoff_seconds()

    result = dict(execution.result or {})
    completed_steps = {int(index) for index in (result.get('completed_steps') or []) if str(index).isdigit()}
    step_results = list(result.get('steps') or [])

    for attempt in range(max_attempts):
        if attempt:
            subscription.refresh_from_db(fields=['status', 'is_active', 'billing_period_end'])
            if not subscription.is_currently_active:
                _fail(execution_id, 'subscription_inactive', 'Subscription is no longer active.')
                return {'status': 'failed', 'execution_id': execution_id, 'failure_code': 'subscription_inactive'}

        now = timezone.now()
        with transaction.atomic():
            current = AutomationExecution.objects.select_for_update().select_related('workflow', 'subscription').get(pk=execution_id)
            if current.status == 'succeeded':
                return {'status': 'succeeded', 'execution_id': execution_id, 'duplicate': True}
            if current.status == 'cancelled':
                return {'status': 'cancelled', 'execution_id': execution_id, 'duplicate': True}
            if current.status in {'timed_out', 'failed'}:
                return {'status': current.status, 'execution_id': execution_id, 'duplicate': True}
            if current.status == 'running':
                stale_seconds = _stale_execution_seconds()
                started = current.started_at
                if started and (now - started).total_seconds() <= stale_seconds:
                    # Another worker owns this execution. This is the critical
                    # duplicate-delivery guard: do not execute side effects twice.
                    return {'status': 'running', 'execution_id': execution_id, 'duplicate': True}
                # Stale running row (worker lost): take it over.
                _log(execution_id, 'warning', 'Taking over a stale running execution.')
            if current.attempt_count >= max_attempts:
                break
            current.status = 'running'
            current.attempt_count += 1
            current.started_at = current.started_at or now
            current.next_retry_at = None
            current.save(update_fields=['status', 'attempt_count', 'started_at', 'next_retry_at'])

        _log(execution_id, 'info', f'Execution attempt {attempt + 1}/{max_attempts} started.', {'attempt': attempt + 1})

        context = ActionContext(
            execution=current,
            workflow=workflow,
            customer=workflow.customer,
        )

        try:
            for step in steps:
                index = step['index']
                if index in completed_steps:
                    continue
                if time.monotonic() > deadline:
                    raise ExecutionTimeout('Execution exceeded its time limit.')

                handler = get_action(step['type'])
                with transaction.atomic():
                    current = AutomationExecution.objects.select_for_update().get(pk=execution_id)
                    current.current_step = index
                    current.save(update_fields=['current_step'])

                _log(
                    execution_id,
                    'info',
                    f'Starting step {index + 1}/{len(steps)} ({step["type"]}).',
                    {'step': index, 'type': step['type'], 'config': redact_mapping(step['config'])},
                )
                detail = handler.execute(step['config'], context) or {}
                completed_steps.add(index)
                step_results.append({
                    'step': index,
                    'type': step['type'],
                    'status': 'succeeded',
                    'detail': redact_mapping(detail),
                })
                result = {'completed_steps': sorted(completed_steps), 'steps': step_results}
                with transaction.atomic():
                    current = AutomationExecution.objects.select_for_update().get(pk=execution_id)
                    current.result = redact_mapping(result)
                    current.save(update_fields=['result'])
                _log(execution_id, 'info', f'Step {index + 1} completed.', {'step': index, 'type': step['type']})

            _finish(execution_id, 'succeeded', result=result)
            _log(execution_id, 'info', 'Execution succeeded.', {'steps_completed': len(completed_steps)})
            return {'status': 'succeeded', 'execution_id': execution_id, 'attempts': attempt + 1}

        except ExecutionTimeout as exc:
            _log(execution_id, 'error', str(exc), {'failure_code': exc.code})
            _finish(execution_id, 'timed_out', code=exc.code, message=str(exc), result=result)
            return {'status': 'timed_out', 'execution_id': execution_id, 'failure_code': exc.code}

        except ActionError as exc:
            retryable = bool(getattr(exc, 'retryable', False))
            _log(
                execution_id,
                'warning' if retryable else 'error',
                f'Action failed: {exc}',
                {'failure_code': exc.code, 'retryable': retryable, 'attempt': attempt + 1},
            )
            if retryable and attempt + 1 < max_attempts and time.monotonic() < deadline:
                retry_at = timezone.now() + timedelta(seconds=backoff)
                with transaction.atomic():
                    current = AutomationExecution.objects.select_for_update().get(pk=execution_id)
                    current.status = 'queued'
                    current.next_retry_at = retry_at
                    current.error_message = redact_text(str(exc))[:8000]
                    current.failure_code = exc.code[:64]
                    current.result = redact_mapping(result)
                    current.save(update_fields=['status', 'next_retry_at', 'error_message', 'failure_code', 'result'])
                _log(execution_id, 'warning', 'Execution scheduled for retry.', {'retry_at': retry_at.isoformat()})
                if backoff:
                    time.sleep(backoff)
                continue
            _finish(execution_id, 'failed', code=exc.code, message=str(exc), result=result)
            return {'status': 'failed', 'execution_id': execution_id, 'failure_code': exc.code}

        except ExecutionConfigurationError as exc:
            _finish(execution_id, 'failed', code=exc.code, message=str(exc), result=result)
            _log(execution_id, 'error', f'Execution configuration error: {exc}', {'failure_code': exc.code})
            return {'status': 'failed', 'execution_id': execution_id, 'failure_code': exc.code}

        except AutomationExecutionError as exc:
            _finish(execution_id, 'failed', code=exc.code, message=str(exc), result=result)
            _log(execution_id, 'error', f'Execution failed: {exc}', {'failure_code': exc.code})
            return {'status': 'failed', 'execution_id': execution_id, 'failure_code': exc.code}

        except Exception as exc:
            # Never persist a raw exception message: it can contain request/credential data.
            logger.error('Unexpected execution failure for %s (%s)', execution_id, exc.__class__.__name__)
            _finish(
                execution_id,
                'failed',
                code='unexpected_error',
                message='Unexpected execution error.',
                result=result,
            )
            _log(execution_id, 'error', 'Unexpected execution error.', {'failure_code': 'unexpected_error'})
            return {'status': 'failed', 'execution_id': execution_id, 'failure_code': 'unexpected_error'}

    _finish(execution_id, 'failed', code='retry_exhausted', message='Execution retry limit reached.', result=result)
    _log(execution_id, 'error', 'Execution retry limit reached.', {'failure_code': 'retry_exhausted'})
    return {'status': 'failed', 'execution_id': execution_id, 'failure_code': 'retry_exhausted'}
