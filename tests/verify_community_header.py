import os
import django
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.urls import reverse

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()

from community.views import home as community_home_view

def verify_community_header():
    User = get_user_model()
    factory = RequestFactory()
    
    user = User.objects.create_user(username='header_test', password='password123')
    
    print("\nTesting Community Header Content...")
    url = reverse('community:home')
    request = factory.get(url)
    request.user = user
    
    response = community_home_view(request)
    
    if response.status_code == 200:
        content = response.content.decode('utf-8')
        
        # Check for Dashboard link
        if 'href="/community/dashboard/"' in content:
            print("SUCCESS: Dashboard link found in header.")
        else:
            print("FAILURE: Dashboard link NOT found in header.")
            
        # Check Brand Link
        if 'href="/community/"' in content: # Assumes community:home is /community/
             print("SUCCESS: Brand link points to Home.")
        else:
             print("FAILURE: Brand link check failed (might be /community/ or something else).")
             # Let's print the brand part
             # print(content[:1000])

    else:
        print(f"FAILURE: Home view returned status {response.status_code}")

if __name__ == '__main__':
    verify_community_header()
