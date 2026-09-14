from django.db import models
from django.utils import timezone


class DatabaseInitialization(models.Model):
    """Tracks whether the database has been initialized.

    This model serves as the single source of truth for whether
    the OnWebApp database has completed its one-time initialization.
    It persists across container rebuilds because it lives in PostgreSQL.
    """

    INIT_IDENTIFIER = 'onwebapp_main'

    identifier = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text='Unique identifier for this initialization process.',
    )
    is_initialized = models.BooleanField(
        default=False,
        help_text='Whether the initialization completed successfully.',
    )
    initialized_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of successful initialization.',
    )
    completed_steps = models.JSONField(
        default=list,
        blank=True,
        help_text='List of initialization steps that completed successfully.',
    )
    error_message = models.TextField(
        blank=True,
        default='',
        help_text='Error message if initialization failed.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Database Initialization'
        verbose_name_plural = 'Database Initialization'
        ordering = ['-created_at']

    def __str__(self):
        status = 'Initialized' if self.is_initialized else 'Pending'
        return f'DB Initialization ({status})'

    @classmethod
    def is_db_initialized(cls):
        """Check if the database has been initialized."""
        return cls.objects.filter(
            identifier=cls.INIT_IDENTIFIER,
            is_initialized=True,
        ).exists()

    @classmethod
    def mark_initialized(cls, steps=None):
        """Mark the database as successfully initialized."""
        obj, _ = cls.objects.update_or_create(
            identifier=cls.INIT_IDENTIFIER,
            defaults={
                'is_initialized': True,
                'initialized_at': timezone.now(),
                'completed_steps': steps or [],
                'error_message': '',
            },
        )
        return obj

    @classmethod
    def mark_failed(cls, error_message):
        """Mark initialization as failed."""
        obj, _ = cls.objects.update_or_create(
            identifier=cls.INIT_IDENTIFIER,
            defaults={
                'is_initialized': False,
                'error_message': error_message,
            },
        )
        return obj
