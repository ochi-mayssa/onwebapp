
import os
import django
from django.conf import settings
from django.urls import reverse
from django.contrib import admin

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()

print("Admin registered models:")
for model, model_admin in admin.site._registry.items():
    print(f"{model._meta.app_label}.{model._meta.model_name}")

print("\nTrying to reverse 'admin:projects_invoice_add':")
try:
    url = reverse('admin:projects_invoice_add')
    print(f"Success: {url}")
except Exception as e:
    print(f"Error: {e}")

print("\nTrying to reverse 'admin:projects_project_add':")
try:
    url = reverse('admin:projects_project_add')
    print(f"Success: {url}")
except Exception as e:
    print(f"Error: {e}")
