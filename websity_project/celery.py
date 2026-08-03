import os
from celery import Celery


# Set default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')

app = Celery('websity_project')

# Read config from Django settings, using `CELERY_` namespace for Celery keys.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from installed apps.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
