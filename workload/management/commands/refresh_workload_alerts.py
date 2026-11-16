"""Refresh workload monitoring alerts from live database records."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from workload.services import refresh_alerts

User = get_user_model()


class Command(BaseCommand):
    help = (
        'Recompute overload, under-utilisation, overdue, blocked, deadline, '
        'unassigned, team-capacity and bottleneck alerts.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant',
            help='Only process records for this workspace owner (username).',
        )

    def handle(self, *args, **options):
        tenant = None
        if options.get('tenant'):
            tenant = User.objects.filter(username=options['tenant']).first()
            if tenant is None:
                raise CommandError(
                    f'No user found with username {options["tenant"]!r}.',
                )
        result = refresh_alerts(tenant=tenant)
        self.stdout.write(
            self.style.SUCCESS(
                'Workload alerts refreshed: '
                f'{result["created"]} created, {result["updated"]} updated, '
                f'{result["resolved"]} resolved, {result["open"]} open.',
            ),
        )
        return None
