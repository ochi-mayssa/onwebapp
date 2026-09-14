
import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()
settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

from django.test import RequestFactory
from django.contrib.auth.models import User
from crm.views import crm_dashboard
from crm.models import Customer
from projects.models import Invoice

def verify_crm_dashboard():
    print("Verifying CRM Dashboard logic...")
    factory = RequestFactory()
    request = factory.get('/crm/dashboard/')
    
    # Create or get a superuser for testing
    user, created = User.objects.get_or_create(username='test_admin_verifier', defaults={'email': 'admin@example.com', 'is_staff': True, 'is_superuser': True})
    if created:
        user.set_password('password')
        user.save()
        print("Created temporary admin user.")
    
    request.user = user
    
    try:
        response = crm_dashboard(request)
        print(f"View execution status code: {response.status_code}")
        if response.status_code == 200:
            print("SUCCESS: CRM Dashboard view executed successfully.")
            # We can't easily inspect context from the response object returned by render() directly 
            # without using the test client, but a 200 OK means the template rendered without error.
        else:
            print("FAILURE: View returned non-200 status.")
            
    except Exception as e:
        print(f"CRITICAL ERROR during view execution: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    verify_crm_dashboard()
