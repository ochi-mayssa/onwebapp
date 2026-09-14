"""
One-time database initialization for OnWebApp.

Safe to run on every deployment. Checks the database for an existing
initialization marker and skips if already completed.

Usage:
    python manage.py initialize_onwebapp

Coolify deployment:
    python manage.py migrate
    python manage.py initialize_onwebapp
"""

import sys
import traceback

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from root_dashboard.models import DatabaseInitialization


# Each step: (name, module_path, command_name)
# We import lazily to avoid circular imports and to only load what we need.
INITIALIZATION_STEPS = [
    {
        'name': 'community_wizard_data',
        'description': 'Community wizard data (services, addons, packages)',
        'command': 'seed_community',
    },
    {
        'name': 'blog_content',
        'description': 'Blog articles and posts',
        'command': 'seed_blog',
    },
    {
        'name': 'forum_structure',
        'description': 'Forum categories, tags, badges',
        'command': 'seed_forum',
    },
    {
        'name': 'branding_questionnaires',
        'description': 'Branding questionnaire templates',
        'command': 'seed_questionnaires',
    },
    {
        'name': 'branding_collections',
        'description': 'Brand collection library',
        'command': 'seed_brand_collections',
    },
    {
        'name': 'seo_monitoring',
        'description': 'SEO monitoring snapshots',
        'command': 'seed_seo_monitoring',
    },
    {
        'name': 'branding_groups',
        'description': 'Branding groups and permissions',
        'command': 'setup_groups',
    },
    {
        'name': 'payment_plans',
        'description': 'Payment plans (Free, Basic, Premium)',
        'command': 'seed_test_data',
    },
]


class Command(BaseCommand):
    help = 'One-time OnWebApp database initialization. Safe to run on every deployment.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-initialization even if already completed.',
        )
        parser.add_argument(
            '--skip-migrate',
            action='store_true',
            help='Skip running migrations before initialization.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually initializing.',
        )

    def handle(self, *args, **options):
        force = options['force']
        skip_migrate = options['skip_migrate']
        dry_run = options['dry_run']

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('OnWebApp Database Initialization'))
        self.stdout.write('=' * 56)

        # ── Step 1: Check if already initialized ──────────────────────
        if not force and DatabaseInitialization.is_db_initialized():
            self.stdout.write(
                self.style.SUCCESS(
                    '\n  OnWebApp database is already initialized. Skipping.\n'
                )
            )
            return

        if force:
            self.stdout.write(
                self.style.WARNING('  --force flag detected. Re-initializing.\n')
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('  --dry-run flag detected. No changes will be made.\n')
            )

        # ── Step 2: Run migrations ────────────────────────────────────
        if not skip_migrate and not dry_run:
            self.stdout.write(self.style.MIGRATE_LABEL('\n  Running migrations...'))
            try:
                call_command('migrate', '--noinput', verbosity=0)
                self.stdout.write(self.style.SUCCESS('  Migrations complete.'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Migration failed: {e}'))
                self._handle_failure(str(e))
                return
        elif skip_migrate:
            self.stdout.write(self.style.WARNING('  Skipping migrations (--skip-migrate).'))

        # ── Step 3: Run initialization steps ──────────────────────────
        self.stdout.write(self.style.MIGRATE_LABEL('\n  Initializing data...'))
        completed_steps = []
        total = len(INITIALIZATION_STEPS)

        for i, step in enumerate(INITIALIZATION_STEPS, 1):
            name = step['name']
            desc = step['description']
            cmd = step['command']

            self.stdout.write(f'\n  [{i}/{total}] {desc}...')

            if dry_run:
                self.stdout.write(self.style.WARNING(f'       Would run: manage.py {cmd}'))
                completed_steps.append(name)
                continue

            try:
                call_command(cmd, verbosity=0)
                completed_steps.append(name)
                self.stdout.write(self.style.SUCCESS(f'       Done.'))
            except Exception as e:
                error_detail = traceback.format_exc()
                self.stdout.write(self.style.ERROR(f'       Failed: {e}'))
                self.stdout.write(self.style.ERROR(f'       Detail: {error_detail}'))
                self._handle_failure(
                    f'Step "{name}" failed: {e}\n\n{error_detail}',
                    completed_steps,
                )
                return

        # ── Step 4: Mark as initialized ───────────────────────────────
        if not dry_run:
            try:
                with transaction.atomic():
                    DatabaseInitialization.mark_initialized(steps=completed_steps)
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'\n  Failed to mark database as initialized: {e}'
                ))
                self._handle_failure(str(e), completed_steps)
                return

        # ── Done ──────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 56))
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'  Dry run complete. {len(completed_steps)} steps would be executed.\n'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    '  Database initialization completed successfully.\n'
                )
            )
            self.stdout.write(f'  Timestamp: {timezone.now().isoformat()}')
            self.stdout.write(f'  Steps completed: {len(completed_steps)}/{total}')
            self.stdout.write('')

    def _handle_failure(self, error_message, completed_steps=None):
        """Record failure and exit with error code."""
        try:
            DatabaseInitialization.mark_failed(error_message)
        except Exception:
            # If we can't even write to the DB, just log it
            self.stdout.write(self.style.ERROR(
                '  WARNING: Could not record failure to database.'
            ))

        self.stdout.write('')
        self.stdout.write(self.style.ERROR(
            '  Initialization FAILED. Database is NOT marked as initialized.'
        ))
        self.stdout.write(self.style.ERROR(
            '  Fix the error and re-run: python manage.py initialize_onwebapp'
        ))
        self.stdout.write('')
        sys.exit(1)
