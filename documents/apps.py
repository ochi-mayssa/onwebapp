from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'documents'
    verbose_name = 'Documents & E-Signature'

    def ready(self):
        from . import signals  # noqa: F401  (register automation receivers)
