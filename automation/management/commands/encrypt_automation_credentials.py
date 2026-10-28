from django.core.management.base import BaseCommand

from automation.models import IntegrationConnection
from automation.security.crypto import ENVELOPE_MARKER


class Command(BaseCommand):
    help = 'Encrypt any legacy plaintext integration credentials in place.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report rows that would be encrypted without writing changes.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        connections = IntegrationConnection.objects.all().only('id', 'credentials')
        pending = []
        for connection in connections:
            credentials = connection.credentials or {}
            if credentials and ENVELOPE_MARKER not in credentials:
                pending.append(connection.pk)
                if not dry_run:
                    connection.set_credentials(credentials)
                    connection.save(update_fields=['credentials', 'updated_at'])

        if dry_run:
            self.stdout.write(f'{len(pending)} connection(s) would be encrypted.')
        else:
            self.stdout.write(self.style.SUCCESS(f'Encrypted {len(pending)} connection(s).'))
        if pending:
            self.stdout.write('Connection ids: ' + ', '.join(str(pk) for pk in pending))
