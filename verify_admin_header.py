import os
import django
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.urls import reverse

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()

from projects.views import admin_dashboard as admin_dashboard_view
from users.views import dashboard as user_dashboard_view
from django.shortcuts import render

def verify_admin_header():
    User = get_user_model()
    # Create admin user
    username = 'admin_header_test'
    password = 'password123'
    email = 'admin_header@example.com'
    
    try:
        user = User.objects.get(username=username)
        user.delete()
    except User.DoesNotExist:
        pass
        
    user = User.objects.create_superuser(username=username, password=password, email=email)
    print(f"Admin user created: {user.username}")

    factory = RequestFactory()

    # 1. Test Admin Dashboard
    print("\nTesting Admin Dashboard...")
    url = reverse('projects:admin_dashboard')
    request = factory.get(url)
    request.user = user
    
    # We need to simulate the view rendering with the template
    # Since admin_dashboard_view returns a render(), we can inspect the content if we could capture it.
    # However, view functions return an HttpResponse object which has .content (byte string).
    
    response = admin_dashboard_view(request)
    
    if response.status_code == 200:
        content = response.content.decode('utf-8')
        
        # Check for Dashboard link
        # The link is: <a class="..." href="/users/dashboard/">Dashboard</a>
        # We search for href="/users/dashboard/"
        if 'href="/users/dashboard/"' in content:
            print("FAILURE: Dashboard link FOUND in Admin Dashboard header.")
            # Print context around the match
            idx = content.find('href="/users/dashboard/"')
            print(content[max(0, idx-50):min(len(content), idx+50)])
        else:
            print("SUCCESS: Dashboard link NOT found in Admin Dashboard header.")

        # Check for Services link (e.g. Industrial Automation)
        if 'Industrial Automation' in content:
             # Wait, "Industrial Automation" might be in the body content if the dashboard shows it?
             # But admin dashboard shouldn't show services content unless it's in the menu.
             # The menu item is "Industrial Automation".
             # But wait, checking for specific text is risky.
             # Let's check for the dropdown toggle "Services" or "Automation & IoT"
             if 'Automation & IoT' in content:
                 print("FAILURE: Services menu 'Automation & IoT' FOUND in Admin Dashboard header.")
             else:
                 print("SUCCESS: Services menu 'Automation & IoT' NOT found in Admin Dashboard header.")
        else:
             print("SUCCESS: 'Industrial Automation' text not found (likely menu hidden).")

        # Check for Admin dropdown
        if 'id="adminDropdown"' in content:
            print("SUCCESS: Admin dropdown FOUND in Admin Dashboard header.")
        else:
            print("FAILURE: Admin dropdown NOT found in Admin Dashboard header.")

    else:
        print(f"FAILURE: Admin Dashboard returned status {response.status_code}")

    # 2. Test User Dashboard (Home context)
    # We can't easily test 'home' view because it's in home app, but we can test user dashboard
    # The user dashboard extends 'users/base_users.html' usually, or 'base.html'?
    # Let's check users/dashboard view.
    
    print("\nTesting User Dashboard (to ensure link IS present there)...")
    # Actually, user dashboard might not show "Dashboard" link because it IS the dashboard.
    # But let's check if the header renders correctly.
    # But wait, users/dashboard.html might extend base.html?
    
    # Let's try accessing a non-admin page, e.g. home page if we can.
    # Or just use the request.path context check.
    
    # Let's simulate a request to home page rendering base.html directly (or a view that uses it).
    from home.views import index
    url = reverse('home:home')
    request = factory.get(url)
    request.user = user
    response = index(request)
    
    if response.status_code == 200:
        content = response.content.decode('utf-8')
        if 'href="/users/dashboard/"' in content:
            print("SUCCESS: Dashboard link FOUND on Home Page.")
        else:
            print("FAILURE: Dashboard link NOT found on Home Page.")
    else:
        print(f"FAILURE: Home Page returned status {response.status_code}")

if __name__ == '__main__':
    verify_admin_header()
