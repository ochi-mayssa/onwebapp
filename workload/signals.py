"""Cross-module integration receivers for workload.

Project tasks and CRM service requests are mirrored into workload records through
``post_save`` signals.  The unique ``OneToOneField`` links in ``WorkItem`` make
the mirroring idempotent, so re-saving a project task updates the same workload
item instead of creating a duplicate.  Deleting a source record cancels (rather
than silently orphaning) its workload mirror.

The signals are guarded by ``WORKLOAD_SYNC_SIGNALS`` (default ``True``) so a
deployment can disable live mirroring and rely on the management command
``sync_workload_integrations`` instead.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _should_sync():
    return getattr(settings, 'WORKLOAD_SYNC_SIGNALS', True)


@receiver(post_save, dispatch_uid='workload.sync_project_task')
def sync_project_task_receiver(sender, instance, **kwargs):
    if not _should_sync():
        return
    # Import lazily to avoid an app-registry circular import at startup.
    from projects.models import PhaseTask

    if sender is not PhaseTask:
        return
    if not instance.phase_id:
        return
    try:
        from .services import sync_project_task

        sync_project_task(instance)
    except Exception:  # pragma: no cover - integrations must never break saves
        logger.exception('Workload sync failed for project task %s', instance.pk)


@receiver(post_save, dispatch_uid='workload.sync_service_request')
def sync_service_request_receiver(sender, instance, **kwargs):
    if not _should_sync():
        return
    from crm.models import ServiceRequest

    if sender is not ServiceRequest:
        return
    try:
        from .services import sync_service_request

        sync_service_request(instance)
    except Exception:  # pragma: no cover - integrations must never break saves
        logger.exception('Workload sync failed for service request %s', instance.pk)


@receiver(pre_delete, dispatch_uid='workload.cancel_project_task_mirror')
def cancel_project_task_mirror_receiver(sender, instance, **kwargs):
    if not _should_sync():
        return
    from projects.models import PhaseTask

    if sender is not PhaseTask:
        return
    try:
        from .services import cancel_mirrored_work_item

        item = getattr(instance, 'workload_item', None)
        if item is not None:
            cancel_mirrored_work_item(item, 'Project task was deleted.')
    except Exception:  # pragma: no cover - integrations must never break deletes
        logger.exception('Could not cancel workload mirror for project task %s', instance.pk)


@receiver(pre_delete, dispatch_uid='workload.cancel_service_request_mirror')
def cancel_service_request_mirror_receiver(sender, instance, **kwargs):
    if not _should_sync():
        return
    from crm.models import ServiceRequest

    if sender is not ServiceRequest:
        return
    try:
        from .services import cancel_mirrored_work_item

        item = getattr(instance, 'workload_item', None)
        if item is not None:
            cancel_mirrored_work_item(item, 'CRM service request was deleted.')
    except Exception:  # pragma: no cover - integrations must never break deletes
        logger.exception('Could not cancel workload mirror for service request %s', instance.pk)
