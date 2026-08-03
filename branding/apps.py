from django.apps import AppConfig


class BrandingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'branding'
    verbose_name = 'Branding Service'

    def ready(self):
        import branding.signals  # noqa: F401
