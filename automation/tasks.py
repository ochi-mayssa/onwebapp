"""Celery entry points for the automation engine.

Workers must run with ``-A websity_project``. Task names are intentionally stable
because they appear in deployment commands and monitoring dashboards.
"""

from __future__ import annotations

import logging

from celery import shared_task

from .execution.engine import run_execution, write_execution_log
from .models import AutomationExecution

logger = logging.getLogger('automation')


@shared_task(
    bind=True,
    name='automation.execute_workflow',
    max_retries=0,
    acks_late=True,
    reject_on_worker_lost=True,
    track_started=True,
)
def execute_workflow_task(self, execution_id: int) -> dict:
    """Execute one automation execution.

    Retries are bounded inside the engine, not by Celery, so a single task cannot
    be redelivered indefinitely. ``acks_late`` means a worker crash will redeliver
    the message; the engine's status/checkpoint logic makes that safe.
    """
    logger.info('Automation task received execution_id=%s task_id=%s', execution_id, self.request.id)
    return run_execution(int(execution_id))


@shared_task(name='automation.record_execution_log')
def record_execution_log_task(execution_id: int, level: str, message: str, payload: dict | None = None) -> bool:
    """Append a redacted execution log entry from a worker or other producer."""
    try:
        execution = AutomationExecution.objects.get(pk=execution_id)
    except AutomationExecution.DoesNotExist:
        logger.warning('Cannot log for missing execution_id=%s', execution_id)
        return False
    if level not in {'debug', 'info', 'warning', 'error'}:
        level = 'info'
    write_execution_log(execution, level, message, payload or {})
    return True
