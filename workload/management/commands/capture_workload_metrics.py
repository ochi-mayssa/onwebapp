"""Capture a daily workload metric snapshot for trend analytics."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from workload.services import capture_metrics

User = get_user_model()


class Command(BaseCommand):
    help = (
        'Store organisation, team and resource workload metrics for today. '
        'Running it twice on the same day replaces the earlier snapshot.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant',
            help='Only capture metrics for this workspace owner (username).',
        )

    def handle(self, *args, **options):
        tenant = None
        if options.get('tenant'):
            tenant = User.objects.filter(username=options['tenant']).first()
            if tenant is None:
                raise CommandError(
                    f'No user found with username {options["tenant"]!r}.',
                )
        created = capture_metrics(tenant=tenant)
        self.stdout.write(
            self.style.SUCCESS(
                f'Captured {created} workload metric row(s) for today.',
            ),
        )
        return None
