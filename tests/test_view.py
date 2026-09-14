import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()

# Override ALLOWED_HOSTS
settings.ALLOWED_HOSTS = ['testserver', '127.0.0.1', 'localhost', '*']

from django.test import Client
from django.contrib.auth import get_user_model
import traceback

User = get_user_model()
admin_user = User.objects.filter(is_staff=True).first()

c = Client(raise_request_exception=True)
c.force_login(admin_user)

try:
    print("Making request...")
    response = c.get('/projects/admin/')
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("Context 'projects' count:", response.context['projects'].count())
        content = response.content.decode('utf-8')
        if "Application web for MO" in content:
            print("Project title found in response content.")
        else:
            print("Project title NOT found in response content.")
            print("Content snippet:", content[:500])
except Exception:
    traceback.print_exc()
