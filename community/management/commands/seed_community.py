from django.core.management.base import BaseCommand
from community.views import _ensure_services_exist, _ensure_addons_exist, _ensure_plans_exist


class Command(BaseCommand):
    help = 'Seed the database with community wizard data (services, addons, packages)'

    def handle(self, *args, **options):
        self.stdout.write('Seeding services...')
        _ensure_services_exist()
        self.stdout.write(self.style.SUCCESS('  Services OK'))

        self.stdout.write('Seeding addons...')
        _ensure_addons_exist()
        self.stdout.write(self.style.SUCCESS('  Addons OK'))

        self.stdout.write('Seeding packages...')
        _ensure_plans_exist()
        self.stdout.write(self.style.SUCCESS('  Packages OK'))

        self.stdout.write(self.style.SUCCESS('All wizard seed data is ready.'))
