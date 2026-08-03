"""Project package init.

Importing the Celery app here can break management commands when Celery
is not installed or misconfigured. Wrap import in a try/except so Django
commands (migrations, shell, etc.) can run without requiring Celery.
"""

try:
	from .celery import app as celery_app
except Exception:
	celery_app = None

__all__ = ('celery_app',)
