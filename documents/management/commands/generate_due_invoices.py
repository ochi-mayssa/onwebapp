"""Generate invoices for recurring billing profiles that are due.

Useful on hosts without Celery Beat:

    python manage.py generate_due_invoices
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from documents.services import run_due_billing_profiles


class Command(BaseCommand):
    help = 'Generate draft invoices for due recurring billing profiles.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            help='Run as if today were this date (YYYY-MM-DD). Defaults to today.',
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        raw_date = options.get('date')
        if raw_date:
            from datetime import date
            today = date.fromisoformat(raw_date)

        summary = run_due_billing_profiles(today=today)
        self.stdout.write(self.style.SUCCESS(
            f"Created {summary['created']}, skipped {summary['skipped']}, "
            f"failed {summary['failed']} for {today.isoformat()}."
        ))
        for reference in summary['documents']:
            self.stdout.write(f'  - {reference}')
