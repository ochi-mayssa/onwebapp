"""Automatic invoice triggers for project and phase lifecycle events.

The receivers only *schedule* work. Invoice creation itself lives in
``documents.services`` so the same rules apply from signals, the Celery task,
the management command and the staff UI. Every generated document carries an
idempotency key, which makes repeated signals harmless.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from projects.models import Project, ProjectPhase

from .services import (
    trigger_phase_completed,
    trigger_project_completed,
    trigger_project_created,
)

logger = logging.getLogger(__name__)


def _safe_run(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except Exception:
        logger.exception('Invoice automation failed in %s', getattr(func, '__name__', func))


def _run_after_commit(func, *args, **kwargs):
    """Run after the surrounding transaction commits, when there is one."""
    if transaction.get_connection().in_atomic_block:
        transaction.on_commit(lambda: _safe_run(func, *args, **kwargs))
    else:
        _safe_run(func, *args, **kwargs)


# ------------------------------------------------------------------- projects
@receiver(pre_save, sender=Project)
def _remember_project_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._automation_previous_status = None
        return
    previous = Project.objects.filter(pk=instance.pk).values_list('current_status', flat=True).first()
    instance._automation_previous_status = previous


@receiver(post_save, sender=Project)
def _project_billing_triggers(sender, instance, created, **kwargs):
    if created:
        _run_after_commit(trigger_project_created, instance)
        return

    previous = getattr(instance, '_automation_previous_status', None)
    if instance.current_status == 'COMPLETED' and previous != 'COMPLETED':
        _run_after_commit(trigger_project_completed, instance)


# --------------------------------------------------------------------- phases
@receiver(pre_save, sender=ProjectPhase)
def _remember_phase_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._automation_previous_status = None
        instance._automation_previous_approval = None
        return
    previous = ProjectPhase.objects.filter(pk=instance.pk).values(
        'status', 'approval_status',
    ).first() or {}
    instance._automation_previous_status = previous.get('status')
    instance._automation_previous_approval = previous.get('approval_status')


@receiver(post_save, sender=ProjectPhase)
def _phase_billing_triggers(sender, instance, created, **kwargs):
    previous_status = getattr(instance, '_automation_previous_status', None)
    previous_approval = getattr(instance, '_automation_previous_approval', None)

    completed = instance.status == 'COMPLETED' and previous_status != 'COMPLETED'
    approved = instance.approval_status == 'APPROVED' and previous_approval != 'APPROVED'
    if created:
        completed = instance.status == 'COMPLETED'
        approved = instance.approval_status == 'APPROVED'

    if completed or approved:
        _run_after_commit(trigger_phase_completed, instance)
