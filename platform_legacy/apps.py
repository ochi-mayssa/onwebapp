from django.apps import AppConfig


class PlatformLegacyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'platform_legacy'
    verbose_name = 'Industrial Platform (legacy)'

    def ready(self):
        # Initialization for the legacy package (if needed)
        pass
