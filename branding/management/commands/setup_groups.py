"""Management command to set up branding groups and permissions."""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from branding.roles import GROUP_DESIGNERS, GROUP_SUPERVISORS, GROUP_STAFF


class Command(BaseCommand):
    help = 'Create branding groups (Designers, Supervisors, Staff) and assign permissions.'

    def handle(self, *args, **options):
        self.stdout.write('Setting up branding groups...')

        # Designers
        designers, created = Group.objects.get_or_create(name=GROUP_DESIGNERS)
        self.stdout.write(f'  [{"created" if created else "exists"}] {GROUP_DESIGNERS}')

        # Supervisors
        supervisors, created = Group.objects.get_or_create(name=GROUP_SUPERVISORS)
        self.stdout.write(f'  [{"created" if created else "exists"}] {GROUP_SUPERVISORS}')

        # Staff
        staff, created = Group.objects.get_or_create(name=GROUP_STAFF)
        self.stdout.write(f'  [{"created" if created else "exists"}] {GROUP_STAFF}')

        # Assign permissions
        branding_perms = Permission.objects.filter(
            content_type__app_label='branding'
        )

        view_perms = branding_perms.filter(codename__startswith='view_')
        change_perms = branding_perms.filter(codename__startswith='change_')

        designers.permissions.set(view_perms)
        self.stdout.write(f'  {GROUP_DESIGNERS}: {view_perms.count()} view permissions')

        supervisors.permissions.set(list(view_perms) + list(change_perms))
        self.stdout.write(f'  {GROUP_SUPERVISORS}: {view_perms.count() + change_perms.count()} view+change permissions')

        staff.permissions.set(view_perms)
        self.stdout.write(f'  {GROUP_STAFF}: {view_perms.count()} view permissions')

        self.stdout.write(self.style.SUCCESS('Done. Groups and permissions configured.'))
