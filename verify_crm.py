
import os
import django
from django.urls import reverse
from django.contrib.auth import get_user_model

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()

def verify_crm():
    print("Verifying CRM integration...")
    
    # 1. Check if app is installed
    from django.apps import apps
    if not apps.is_installed('crm'):
        print("ERROR: 'crm' app is not installed.")
        return
    print("✓ 'crm' app is installed.")
    
    # 2. Check URL resolution
    try:
        dashboard_url = reverse('crm:dashboard')
        print(f"✓ CRM Dashboard URL resolves to: {dashboard_url}")
    except Exception as e:
        print(f"ERROR: Could not resolve CRM dashboard URL: {e}")
        return

    # 3. Check Models
    try:
        from crm.models import Customer
        print("✓ Customer model import successful.")
    except ImportError as e:
        print(f"ERROR: Could not import Customer model: {e}")
        return

    print("CRM integration verification successful!")

if __name__ == '__main__':
    verify_crm()
