"""Celery tasks for workload monitoring.

The platform ships Celery but keeps ``USE_CELERY=False`` by default.  These
tasks are therefore thin wrappers around the same service functions used by the
management commands, so the module works with or without a running worker.

Reliability notes
-----------------
* Every task is idempotent: alert refreshes deduplicate by key, metric capture
  rewrites the same day's snapshots, and integration sync uses unique source
  links.
* Transient failures retry with exponential backoff.  A terminal failure is
  logged with a stack trace so an operator can re-run the matching management
  command; the broker is never required for the web app to keep working.
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)

RETRY_KWARGS = {
    'bind': True,
    'autoretry_for': (Exception,),
    'max_retries': 3,
    'default_retry_delay': 60,
    'retry_backoff': True,
    'retry_backoff_max': 600,
    'retry_jitter': True,
}


@shared_task(**RETRY_KWARGS)
def refresh_workload_alerts(self, tenant=None):
    from .services import refresh_alerts

    try:
        result = refresh_alerts(tenant=tenant)
    except Exception:
        logger.exception('Scheduled workload alert refresh failed')
        raise
    logger.info('Scheduled workload alert refresh: %s', result)
    return result


@shared_task(**RETRY_KWARGS)
def capture_workload_metrics(self, tenant=None):
    from .services import capture_metrics

    try:
        created = capture_metrics(tenant=tenant)
    except Exception:
        logger.exception('Scheduled workload metric capture failed')
        raise
    logger.info('Scheduled workload metric capture: %s rows', created)
    return {'created': created}


@shared_task(**RETRY_KWARGS)
def sync_workload_integrations(self):
    from .services import sync_from_integrations

    try:
        result = sync_from_integrations()
    except Exception:
        logger.exception('Scheduled workload integration sync failed')
        raise
    logger.info('Scheduled workload integration sync: %s', result)
    return result
