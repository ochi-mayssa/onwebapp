"""Celery tasks for the documents billing automation."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    acks_late=True,
    time_limit=600,
    soft_time_limit=540,
)
def generate_due_invoices(self):
    """Create drafts for recurring billing profiles that are due today."""
    from .services import run_due_billing_profiles

    summary = run_due_billing_profiles()
    logger.info('Recurring invoice run finished: %s', summary)
    return summary
