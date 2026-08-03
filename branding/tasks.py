"""Celery tasks for the Branding Service app."""
import json
import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger('branding.security')


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    time_limit=120,
    soft_time_limit=90,
)
def scan_asset_for_virus(self, asset_id):
    """Async virus scan of a BrandingAsset using ClamAV.

    Updates the asset's scan_status and scan_result fields.
    """
    from .models import BrandingAsset
    from .file_security import scanner, log_virus_detected, log_suspicious_upload

    try:
        asset = BrandingAsset.objects.get(pk=asset_id)
    except BrandingAsset.DoesNotExist:
        logger.error('scan_asset_for_virus: asset %s not found', asset_id)
        return

    # Mark as scanning (if still pending)
    if asset.scan_status != BrandingAsset.SCAN_PENDING:
        return

    # Ensure file is accessible
    if not asset.file:
        BrandingAsset.objects.filter(pk=asset_id).update(
            scan_status=BrandingAsset.SCAN_ERROR,
            scan_result='File not found on disk',
        )
        return

    try:
        is_clean, virus_name, error = scanner.scan_file(asset.file)

        if not is_clean:
            BrandingAsset.objects.filter(pk=asset_id).update(
                scan_status=BrandingAsset.SCAN_INFECTED,
                scan_result=f'Virus detected: {virus_name}',
            )
            log_virus_detected(
                asset.request.user,
                asset.original_name,
                virus_name,
            )
            logger.critical(
                'VIRUS DETECTED asset=%s file=%s virus=%s user=%s',
                asset_id, asset.original_name, virus_name,
                asset.request.user.username,
            )
        elif error:
            BrandingAsset.objects.filter(pk=asset_id).update(
                scan_status=BrandingAsset.SCAN_ERROR,
                scan_result=error,
            )
            logger.warning('Scan error asset=%s: %s', asset_id, error)
        else:
            BrandingAsset.objects.filter(pk=asset_id).update(
                scan_status=BrandingAsset.SCAN_CLEAN,
                scan_result='Clean',
            )
            logger.info('Scan clean asset=%s file=%s', asset_id, asset.original_name)

    except Exception as exc:
        BrandingAsset.objects.filter(pk=asset_id).update(
            scan_status=BrandingAsset.SCAN_ERROR,
            scan_result=f'Scan failed: {exc}',
        )
        logger.error('Scan failed asset=%s: %s', asset_id, exc)
        # Retry on transient errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)


@shared_task
def scan_pending_assets(batch_size=50):
    """Periodic task to scan any assets still in PENDING status.

    Useful as a safety net for assets uploaded before the async scan
    was configured, or after a worker restart.
    """
    from .models import BrandingAsset

    pending = BrandingAsset.objects.filter(
        scan_status=BrandingAsset.SCAN_PENDING,
    )[:batch_size]

    scanned = 0
    for asset in pending:
        scan_asset_for_virus.delay(asset.pk)
        scanned += 1

    if scanned:
        logger.info('Queued %d pending assets for virus scanning', scanned)
    return scanned


# ---------------------------------------------------------------------------
# GDPR tasks
# ---------------------------------------------------------------------------

@shared_task(name='branding.tasks.anonymize_expired_requests')
def task_anonymize_expired_requests(batch_size=100):
    """Periodic task: anonymize all requests whose retention period has expired.

    Scheduled to run daily via Celery Beat.
    """
    from .gdpr import anonymize_expired_requests

    count = anonymize_expired_requests(batch_size=batch_size)
    if count:
        logger.info('[GDPR] Auto-anonymized %d expired requests', count)
    return count


@shared_task(
    name='branding.tasks.process_data_export',
    bind=True,
    max_retries=2,
    time_limit=300,
    soft_time_limit=240,
)
def task_process_data_export(self, export_request_id):
    """Process a pending data export request.

    Generates the export file and marks the request as ready.
    """
    from .models import DataExportRequest
    from .export import export_user_data_json

    try:
        req = DataExportRequest.objects.get(pk=export_request_id)
    except DataExportRequest.DoesNotExist:
        logger.error('[GDPR] Export request %s not found', export_request_id)
        return

    if req.status != DataExportRequest.STATUS_PENDING:
        return

    req.status = DataExportRequest.STATUS_PROCESSING
    req.save(update_fields=['status'])

    try:
        data = export_user_data_json(req.user)
        content = json.dumps(data, indent=2, default=str)

        # Write to file
        filename = f'export_{req.user.pk}_{timezone.now():%Y%m%d_%H%M%S}.json'
        from django.core.files.base import ContentFile
        req.file.save(filename, ContentFile(content.encode('utf-8')), save=False)
        req.status = DataExportRequest.STATUS_READY
        req.completed_at = timezone.now()
        req.expires_at = timezone.now() + timezone.timedelta(days=30)
        req.save(update_fields=['status', 'file', 'completed_at', 'expires_at'])

        # Notify user
        try:
            from .models import BrandingNotification
            BrandingNotification.objects.create(
                user=req.user,
                notification_type='SYSTEM',
                title='Data Export Ready',
                message='Your data export is ready for download. It will be available for 30 days.',
            )
        except Exception:
            pass

        logger.info('[GDPR] Export request %s completed for user %s', export_request_id, req.user.pk)

    except Exception as exc:
        req.status = DataExportRequest.STATUS_ERROR
        req.error_message = str(exc)[:500]
        req.save(update_fields=['status', 'error_message'])
        logger.error('[GDPR] Export request %s failed: %s', export_request_id, exc)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)


@shared_task(name='branding.tasks.cleanup_expired_exports')
def task_cleanup_expired_exports():
    """Delete export files that have passed their expiry date."""
    from .models import DataExportRequest

    expired = DataExportRequest.objects.filter(
        status=DataExportRequest.STATUS_READY,
        expires_at__lt=timezone.now(),
    )

    count = 0
    for req in expired:
        if req.file:
            req.file.delete(save=False)
        req.status = DataExportRequest.STATUS_EXPIRED
        req.save(update_fields=['status', 'file'])
        count += 1

    if count:
        logger.info('[GDPR] Cleaned up %d expired export files', count)
    return count
