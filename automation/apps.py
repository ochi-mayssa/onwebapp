from django.apps import AppConfig


class AutomationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'automation'

    def ready(self):
        # Ensure accidental secret strings in automation logs are redacted even
        # when no explicit handler is configured (production propagates to root).
        import logging

        from .security.redaction import SecretRedactingFilter

        logger = logging.getLogger('automation')
        if not any(isinstance(item, SecretRedactingFilter) for item in logger.filters):
            logger.addFilter(SecretRedactingFilter())
