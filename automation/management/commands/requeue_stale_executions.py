"""Re-dispatch executions abandoned by a crashed worker.

Celery's ``acks_late`` redelivers a message when a worker dies, but a broker or
worker restart can still leave a row stuck in ``running``. This command only
touches rows older than ``AUTOMATION_STALE_EXECUTION_SECONDS`` so it can never
race a live worker. Run it from cron/systemd if Celery beat is unavailable.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from automation.execution.engine import _stale_execution_seconds, dispatch_execution
from automation.models import AutomationExecution


class Command(BaseCommand):
    help = 'Re-queue automation executions stuck in running past the stale threshold.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='List stale executions without changing or dispatching them.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Maximum number of executions to process in one run (default: 100).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = max(1, int(options['limit']))
        cutoff = timezone.now() - timedelta(seconds=_stale_execution_seconds())

        candidates = list(
            AutomationExecution.objects.filter(
                status='running',
                started_at__lt=cutoff,
            )
            .order_by('started_at')
            .values_list('pk', flat=True)[:limit]
        )

        if not candidates:
            self.stdout.write('No stale running executions found.')
            return

        if dry_run:
            self.stdout.write(f'{len(candidates)} execution(s) would be requeued.')
            self.stdout.write('Execution ids: ' + ', '.join(str(pk) for pk in candidates))
            return

        requeued: list[int] = []
        failed: list[tuple[int, str]] = []
        for execution_id in candidates:
            # Conditional update: if another process finished or took it over
            # between the query and here, leave it alone.
            changed = AutomationExecution.objects.filter(
                pk=execution_id,
                status='running',
                started_at__lt=cutoff,
            ).update(status='queued', started_at=None, next_retry_at=None)
            if not changed:
                continue
            try:
                dispatch_execution(execution_id)
            except Exception as exc:  # noqa: BLE001 - operator command must continue
                # Leave the row queued so it can be retried after the queue recovers.
                failed.append((execution_id, exc.__class__.__name__))
                continue
            requeued.append(execution_id)

        if requeued:
            self.stdout.write(self.style.SUCCESS(f'Requeued {len(requeued)} execution(s).'))
            self.stdout.write('Execution ids: ' + ', '.join(str(pk) for pk in requeued))
        if failed:
            self.stdout.write(self.style.ERROR(f'{len(failed)} execution(s) could not be dispatched.'))
            for execution_id, error in failed:
                self.stdout.write(f'  {execution_id}: {error}')
