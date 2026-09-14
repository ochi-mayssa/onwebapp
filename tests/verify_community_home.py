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

from users.views import login_view
from users.models import UserProfile
from community.views import home as community_home_view

def add_middleware(request):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)

def verify_community_home():
    User = get_user_model()
    factory = RequestFactory()

    print("\nTesting Community User Login Redirect...")
    username = 'community_home_test'
    password = 'password123'
    try:
        user = User.objects.get(username=username)
        user.delete()
    except User.DoesNotExist:
        pass
    
    user = User.objects.create_user(username=username, email='comm@test.com', password=password)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.service_type = 'community'
    profile.community_needs = ['website_building'] # Should NOT matter now
    profile.save()
    
    # 1. Test Login Redirect
    url = reverse('users:login_view')
    data = {'email': 'comm@test.com', 'password': password}
    request = factory.post(url, data)
    add_middleware(request)
    
    response = login_view(request)
    
    if response.status_code == 302:
        # Should redirect to community home
        if reverse('community:home') in response.url:
            print("SUCCESS: Community user redirected to Community Home on login.")
        else:
            print(f"FAILURE: Redirected to {response.url} instead of Community Home.")
    else:
        print(f"FAILURE: Login returned status {response.status_code}")

    # 2. Test Home View Access
    print("\nTesting Community Home View...")
    url = reverse('community:home')
    request = factory.get(url)
    request.user = user
    add_middleware(request)
    
    response = community_home_view(request)
    
    if response.status_code == 200:
        content = response.content.decode('utf-8')
        if 'Welcome to Community Services' in content:
            print("SUCCESS: Community Home Page content verified.")
        else:
            print("FAILURE: Community Home Page content mismatch.")
    else:
        print(f"FAILURE: Home view returned status {response.status_code}")

if __name__ == '__main__':
    verify_community_home()
