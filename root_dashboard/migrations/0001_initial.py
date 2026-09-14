from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='DatabaseInitialization',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'identifier',
                    models.CharField(
                        db_index=True,
                        help_text='Unique identifier for this initialization process.',
                        max_length=100,
                        unique=True,
                    ),
                ),
                (
                    'is_initialized',
                    models.BooleanField(
                        default=False,
                        help_text='Whether the initialization completed successfully.',
                    ),
                ),
                (
                    'initialized_at',
                    models.DateTimeField(
                        blank=True,
                        help_text='Timestamp of successful initialization.',
                        null=True,
                    ),
                ),
                (
                    'completed_steps',
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text='List of initialization steps that completed successfully.',
                    ),
                ),
                (
                    'error_message',
                    models.TextField(
                        blank=True,
                        default='',
                        help_text='Error message if initialization failed.',
                    ),
                ),
                (
                    'created_at',
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    'updated_at',
                    models.DateTimeField(auto_now=True),
                ),
            ],
            options={
                'verbose_name': 'Database Initialization',
                'verbose_name_plural': 'Database Initialization',
                'ordering': ['-created_at'],
            },
        ),
    ]
