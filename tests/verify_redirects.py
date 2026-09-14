import os
import django
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.middleware import MessageMiddleware

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()

from users.views import login_view, signup

def add_middleware(request):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)

def verify_redirects():
    User = get_user_model()
    factory = RequestFactory()

    # 1. Test Admin Redirect
    print("\nTesting Admin Redirect...")
    admin_username = 'redirect_admin'
    password = 'password123'
    try:
        user = User.objects.get(username=admin_username)
        user.delete()
    except User.DoesNotExist:
        pass
    
    admin_user = User.objects.create_superuser(username=admin_username, email='admin@test.com', password=password)
    
    # Create request
    url = reverse('users:login_view')
    data = {'email': 'admin@test.com', 'password': password}
    request = factory.post(url, data)
    add_middleware(request)
    
    response = login_view(request)
    
    if response.status_code == 302:
        if '/projects/admin/' in response.url:
            print("SUCCESS: Admin redirected to Admin Dashboard.")
        else:
            print(f"FAILURE: Admin redirected to {response.url}")
    else:
        print(f"FAILURE: Admin login returned status {response.status_code}")


    # 2. Test Regular User Redirect (Skip Onboarding)
    print("\nTesting Regular User Redirect (Skip Onboarding)...")
    user_username = 'redirect_user'
    try:
        user = User.objects.get(username=user_username)
        user.delete()
    except User.DoesNotExist:
        pass
        
    # Create user without profile (simulating fresh registration/login)
    reg_user = User.objects.create_user(username=user_username, email='user@test.com', password=password)
    
    # Create request
    request = factory.post(url, data={'email': 'user@test.com', 'password': password})
    add_middleware(request)
    
    response = login_view(request)
    
    if response.status_code == 302:
        # Should NOT be onboarding
        if 'onboarding' not in response.url:
            print(f"SUCCESS: User redirected to {response.url} (Not Onboarding).")
            # Verify it's dashboard
            if '/users/dashboard/' in response.url:
                 print("SUCCESS: User redirected to User Dashboard.")
        else:
            print(f"FAILURE: User redirected to Onboarding ({response.url}).")
    else:
        print(f"FAILURE: User login returned status {response.status_code}")

if __name__ == '__main__':
    verify_redirects()
