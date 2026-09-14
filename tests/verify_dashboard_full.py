import os
import django
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.urls import reverse

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()

from projects.models import Project, ProjectPhase
from projects.views import dashboard as project_dashboard_view
from projects.views import project_detail as project_detail_view
from projects.views import approve_phase as approve_phase_view
from projects.views import admin_dashboard as admin_dashboard_view
from projects.views import admin_project_detail as admin_project_detail_view

def verify_full_flow():
    User = get_user_model()
    # Create test user
    username = 'testuser_dashboard_flow'
    password = 'password123'
    email = 'testuser@example.com'
    
    try:
        user = User.objects.get(username=username)
        user.delete() # Clean up previous run
    except User.DoesNotExist:
        pass
        
    user = User.objects.create_user(username=username, password=password, email=email)
    print(f"User created: {user.username}")

    # Create a project for the user
    project = Project.objects.create(
        client=user,
        title="Test Project Alpha",
        description="A test project for dashboard verification",
        current_status="PLANNING",
        progress_percentage=10
    )
    print(f"Project created: {project.title} (ID: {project.id})")

    p1 = ProjectPhase.objects.create(
        project=project,
        phase_type='DESIGN',
        status='IN_PROGRESS',
        approval_status='AWAITING_CLIENT',
        ready_for_review=True
    )
    p2 = ProjectPhase.objects.create(
        project=project,
        phase_type='DEVELOPMENT',
        status='NOT_STARTED'
    )

    # Create a factory
    factory = RequestFactory()

    # 1. Test Project Dashboard View
    print("\nTesting Project Dashboard View...")
    url = reverse('projects:dashboard')
    request = factory.get(url)
    request.user = user
    
    response = project_dashboard_view(request)
    
    if response.status_code == 200:
        content = response.content.decode('utf-8')
        if project.title in content:
            print("SUCCESS: Project title found in dashboard.")
        else:
            print("FAILURE: Project title NOT found in dashboard.")
            # print(content[:500]) # Debug
    else:
        print(f"FAILURE: Dashboard returned status {response.status_code}")

    # 2. Test Project Detail View
    print("\nTesting Project Detail View...")
    url = reverse('projects:project_detail', args=[project.id])
    request = factory.get(url)
    request.user = user
    
    response = project_detail_view(request, project_id=project.id)
    
    if response.status_code == 200:
        content = response.content.decode('utf-8')
        
        # Save content to file for inspection
        with open('debug_response.html', 'w', encoding='utf-8') as f:
            f.write(content)
        print("Debug: Saved response content to debug_response.html")

        if project.title in content and project.description in content:
            print("SUCCESS: Project title and description found in detail view.")
        else:
            print("FAILURE: Content mismatch in detail view.")
            print(f"Title present: {project.title in content}")
            print(f"Description present: {project.description in content}")

        if 'Approve' in content:
            print("SUCCESS: Approval button visible to client for current phase.")
        else:
            print("FAILURE: Approval button not visible.")

        if 'Locked until previous step is approved' in content:
            print("SUCCESS: Next step is locked pending approval.")
        else:
            print("FAILURE: Lock indication missing for next step.")
    else:
        print(f"FAILURE: Project Detail returned status {response.status_code}")

    # Simulate client approval
    print("\nApproving current phase as client...")
    url = reverse('projects:approve_phase', args=[project.id, p1.id])
    request = factory.post(url)
    request.user = user
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.contrib.messages.storage.fallback import FallbackStorage
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    request._messages = FallbackStorage(request)
    approve_phase_view(request, project_id=project.id, phase_id=p1.id)

    # Re-render detail
    request = factory.get(reverse('projects:project_detail', args=[project.id]))
    request.user = user
    response = project_detail_view(request, project_id=project.id)
    content = response.content.decode('utf-8')
    if 'Approved' in content and 'Locked until previous step is approved' not in content:
        print("SUCCESS: Phase approved and next step unlocked.")
    else:
        print("FAILURE: Approval flow did not update UI as expected.")

    # Admin dashboard verification
    print("\nTesting Admin Dashboard...")
    admin_username = 'admin_test_for_dashboard'
    try:
        admin_user = User.objects.get(username=admin_username)
        admin_user.delete()
    except User.DoesNotExist:
        pass
    admin_user = User.objects.create_user(username=admin_username, password='password123', email='admin@example.com')
    admin_user.is_staff = True
    admin_user.save()

    # Admin dashboard
    url = reverse('projects:admin_dashboard')
    request = factory.get(url)
    request.user = admin_user
    response = admin_dashboard_view(request)
    print(f"Admin dashboard status: {response.status_code}")
    content = response.content.decode('utf-8')
    if project.title in content:
        print("SUCCESS: Project listed on admin dashboard.")
    else:
        print("FAILURE: Project not listed on admin dashboard.")

    # Admin project detail
    url = reverse('projects:admin_project_detail', args=[project.id])
    request = factory.get(url)
    request.user = admin_user
    response = admin_project_detail_view(request, project_id=project.id)
    print(f"Admin project detail status: {response.status_code}")
    content = response.content.decode('utf-8')
    with open('debug_admin_detail.html', 'w', encoding='utf-8') as f:
        f.write(content)
    if 'Admin Control Panel' in content:
        print("SUCCESS: Admin project detail loads content.")
    else:
        print("FAILURE: Admin project detail missing expected content.")

    # Clean up
    project.delete()
    user.delete()
    admin_user.delete()
    print("\nTest data cleaned up.")

if __name__ == "__main__":
    try:
        verify_full_flow()
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
