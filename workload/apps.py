from django.apps import AppConfig


class WorkloadConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'workload'
    verbose_name = 'Workload Management'

    def ready(self):
        # Register cross-module integration receivers (projects, CRM).
        from . import signals  # noqa: F401
