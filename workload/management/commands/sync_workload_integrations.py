"""Synchronise project tasks and CRM service requests into workload."""
from __future__ import annotations

from django.core.management.base import BaseCommand

from workload.services import sync_from_integrations


class Command(BaseCommand):
    help = (
        'Mirror existing project tasks and CRM service requests into workload '
        'items. Unique one-to-one links make repeated runs safe.'
    )

    def handle(self, *args, **options):
        result = sync_from_integrations()
        projects = result['projects']
        crm = result['crm']
        self.stdout.write(
            self.style.SUCCESS(
                'Workload integration sync complete: '
                f'{projects["synced"]} project task(s) ({projects["errors"]} errors), '
                f'{crm["synced"]} CRM request(s) ({crm["errors"]} errors).',
            ),
        )
        return None
