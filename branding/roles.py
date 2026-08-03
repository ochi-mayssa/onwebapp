"""Role detection and permission utilities for the Branding Service."""
from functools import wraps

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.urls import reverse

User = get_user_model()

# Group names
GROUP_DESIGNERS = 'Designers'
GROUP_SUPERVISORS = 'Supervisors'
GROUP_STAFF = 'Staff'

ROLE_CLIENT = 'client'
ROLE_DESIGNER = 'designer'
ROLE_SUPERVISOR = 'supervisor'
ROLE_STAFF = 'staff'
ROLE_ADMIN = 'admin'


def get_user_role(user):
    """Determine the user's role in the branding system."""
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return ROLE_ADMIN
    if user.groups.filter(name=GROUP_SUPERVISORS).exists():
        return ROLE_SUPERVISOR
    if user.groups.filter(name=GROUP_DESIGNERS).exists():
        return ROLE_DESIGNER
    if user.is_staff:
        return ROLE_STAFF
    return ROLE_CLIENT


def is_admin(user):
    """Check if user is a superuser."""
    return user.is_authenticated and user.is_superuser


def is_supervisor(user):
    """Check if user is in the Supervisors group."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=GROUP_SUPERVISORS).exists()


def is_designer(user):
    """Check if user is in the Designers group."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=GROUP_DESIGNERS).exists()


def is_staff_user(user):
    """Check if user is staff (any staff role)."""
    return user.is_authenticated and user.is_staff


def is_client(user):
    """Check if user is a regular client (not staff)."""
    return user.is_authenticated and not user.is_staff


def get_role_dashboard_url(user):
    """Get the appropriate dashboard URL for the user's role."""
    role = get_user_role(user)
    if role in (ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_STAFF):
        return reverse('branding:unified_dashboard')
    if role == ROLE_DESIGNER:
        return reverse('branding:designer_dashboard')
    return reverse('branding:my_requests')


def get_role_nav_items(user):
    """Return navigation items based on user role."""
    role = get_user_role(user)
    nav = []

    # Brand / Home — always first
    nav.append({
        'url': reverse('branding:landing'),
        'label': 'Branding Service',
        'icon': 'fa-solid fa-palette',
        'class': 'branding-nav-brand',
    })

    if role in (ROLE_ADMIN, ROLE_SUPERVISOR):
        # Supervisor / Admin nav
        nav.extend([
            {
                'url': reverse('branding:unified_dashboard'),
                'label': 'Dashboard',
                'icon': 'fa-solid fa-gauge-high',
            },
            {
                'url': reverse('branding:supervisor_dashboard'),
                'label': 'Supervisor',
                'icon': 'fa-solid fa-users-gear',
            },
            {
                'url': reverse('branding:dashboard'),
                'label': 'Requests',
                'icon': 'fa-solid fa-list-check',
            },
            {
                'url': reverse('branding:kanban'),
                'label': 'Board',
                'icon': 'fa-solid fa-table-columns',
            },
            {
                'url': reverse('branding:supervisor_team'),
                'label': 'Team',
                'icon': 'fa-solid fa-users',
            },
            {
                'url': reverse('branding:analytics_overview'),
                'label': 'Analytics',
                'icon': 'fa-solid fa-chart-line',
            },
            {
                'url': reverse('branding:feedback_list'),
                'label': 'Feedback',
                'icon': 'fa-solid fa-star',
            },
        ])

    elif role == ROLE_DESIGNER:
        # Designer nav
        nav.extend([
            {
                'url': reverse('branding:designer_dashboard'),
                'label': 'My Work',
                'icon': 'fa-solid fa-palette',
            },
            {
                'url': reverse('branding:workflow_dashboard'),
                'label': 'Workflow',
                'icon': 'fa-solid fa-diagram-project',
            },
            {
                'url': reverse('branding:kanban'),
                'label': 'Board',
                'icon': 'fa-solid fa-table-columns',
            },
            {
                'url': reverse('branding:designer_time_tracking'),
                'label': 'Timer',
                'icon': 'fa-solid fa-stopwatch',
            },
            {
                'url': reverse('branding:designer_resources'),
                'label': 'Resources',
                'icon': 'fa-solid fa-book',
            },
            {
                'url': reverse('branding:design_tools_color'),
                'label': 'Tools',
                'icon': 'fa-solid fa-screwdriver-wrench',
            },
            {
                'url': reverse('branding:knowledge_base'),
                'label': 'KB',
                'icon': 'fa-solid fa-lightbulb',
            },
        ])

    elif role == ROLE_STAFF:
        # Regular staff nav
        nav.extend([
            {
                'url': reverse('branding:unified_dashboard'),
                'label': 'Dashboard',
                'icon': 'fa-solid fa-gauge-high',
            },
            {
                'url': reverse('branding:dashboard'),
                'label': 'Requests',
                'icon': 'fa-solid fa-list-check',
            },
            {
                'url': reverse('branding:kanban'),
                'label': 'Board',
                'icon': 'fa-solid fa-table-columns',
            },
            {
                'url': reverse('branding:feedback_list'),
                'label': 'Feedback',
                'icon': 'fa-solid fa-star',
            },
        ])

    elif role == ROLE_CLIENT:
        # Client nav
        nav.extend([
            {
                'url': reverse('branding:my_requests'),
                'label': 'Dashboard',
                'icon': 'fa-solid fa-gauge-high',
            },
            {
                'url': reverse('branding:wizard'),
                'label': 'New Request',
                'icon': 'fa-solid fa-plus',
            },
            {
                'url': reverse('branding:client_profile'),
                'label': 'Profile',
                'icon': 'fa-solid fa-sliders',
            },
        ])

    return nav


def get_role_dropdown_items(user):
    """Return dropdown menu items based on user role."""
    role = get_user_role(user)
    items = []

    if role in (ROLE_ADMIN, ROLE_SUPERVISOR):
        items.extend([
            {'url': reverse('branding:my_requests'), 'label': 'My Requests', 'icon': 'fa-solid fa-folder-open'},
            {'url': reverse('branding:client_profile'), 'label': 'Branding Profile', 'icon': 'fa-solid fa-sliders'},
            {'url': reverse('branding:notifications'), 'label': 'Notifications', 'icon': 'fa-regular fa-bell'},
            {'url': reverse('users:profile_dashboard'), 'label': 'Profile', 'icon': 'fa-solid fa-user'},
            {'section': 'Staff'},
            {'url': reverse('branding:unified_dashboard'), 'label': 'Dashboard', 'icon': 'fa-solid fa-gauge-high'},
            {'url': reverse('branding:kanban'), 'label': 'Board', 'icon': 'fa-solid fa-table-columns'},
            {'url': reverse('branding:supervisor_team'), 'label': 'Team', 'icon': 'fa-solid fa-users'},
            {'url': reverse('branding:designer_dashboard'), 'label': 'My Work', 'icon': 'fa-solid fa-palette'},
            {'section': 'Designer'},
            {'url': reverse('branding:designer_time_tracking'), 'label': 'Time Tracking', 'icon': 'fa-solid fa-stopwatch'},
            {'url': reverse('branding:designer_resources'), 'label': 'Resources', 'icon': 'fa-solid fa-book'},
            {'url': reverse('branding:designer_templates'), 'label': 'Templates', 'icon': 'fa-solid fa-file-lines'},
            {'url': reverse('branding:collection_template_list'), 'label': 'Collection Templates', 'icon': 'fa-solid fa-layer-group'},
            {'section': 'Collaboration'},
            {'url': reverse('branding:knowledge_base'), 'label': 'Knowledge Base', 'icon': 'fa-solid fa-lightbulb'},
            {'url': reverse('branding:showcase'), 'label': 'Showcase', 'icon': 'fa-solid fa-trophy'},
            {'section': 'Integrations'},
            {'url': reverse('branding:figma_integration'), 'label': 'Figma', 'icon': 'fa-brands fa-figma', 'style': 'color:#a259ff'},
            {'url': reverse('branding:adobe_integration'), 'label': 'Adobe CC', 'icon': 'fa-solid fa-palette', 'style': 'color:#ff0000'},
            {'url': reverse('branding:design_tools_color'), 'label': 'Color Picker', 'icon': 'fa-solid fa-droplet', 'style': 'color:#818cf8'},
            {'url': reverse('branding:design_tools_fonts'), 'label': 'Font Finder', 'icon': 'fa-solid fa-font', 'style': 'color:#f59e0b'},
            {'url': reverse('branding:design_tools_organizer'), 'label': 'Asset Organizer', 'icon': 'fa-solid fa-folder-open', 'style': 'color:#06b6d4'},
            {'url': reverse('branding:design_tools_brand_check'), 'label': 'Brand Check', 'icon': 'fa-solid fa-clipboard-check', 'style': 'color:#22c55e'},
            {'url': reverse('branding:slack_integration'), 'label': 'Slack', 'icon': 'fa-brands fa-slack', 'style': 'color:#e01e5a'},
            {'url': reverse('branding:calendar_integration'), 'label': 'Calendar', 'icon': 'fa-solid fa-calendar-days', 'style': 'color:#3b82f6'},
        ])

    elif role == ROLE_DESIGNER:
        items.extend([
            {'url': reverse('branding:my_requests'), 'label': 'My Requests', 'icon': 'fa-solid fa-folder-open'},
            {'url': reverse('branding:client_profile'), 'label': 'Branding Profile', 'icon': 'fa-solid fa-sliders'},
            {'url': reverse('branding:notifications'), 'label': 'Notifications', 'icon': 'fa-regular fa-bell'},
            {'url': reverse('users:profile_dashboard'), 'label': 'Profile', 'icon': 'fa-solid fa-user'},
            {'section': 'Designer'},
            {'url': reverse('branding:unified_dashboard'), 'label': 'Dashboard', 'icon': 'fa-solid fa-gauge-high'},
            {'url': reverse('branding:kanban'), 'label': 'Board', 'icon': 'fa-solid fa-table-columns'},
            {'url': reverse('branding:designer_dashboard'), 'label': 'My Work', 'icon': 'fa-solid fa-palette'},
            {'url': reverse('branding:workflow_dashboard'), 'label': 'Workflow', 'icon': 'fa-solid fa-diagram-project'},
            {'url': reverse('branding:designer_time_tracking'), 'label': 'Time Tracking', 'icon': 'fa-solid fa-stopwatch'},
            {'url': reverse('branding:designer_resources'), 'label': 'Resources', 'icon': 'fa-solid fa-book'},
            {'url': reverse('branding:designer_templates'), 'label': 'Templates', 'icon': 'fa-solid fa-file-lines'},
            {'section': 'Tools'},
            {'url': reverse('branding:design_tools_color'), 'label': 'Color Picker', 'icon': 'fa-solid fa-droplet', 'style': 'color:#818cf8'},
            {'url': reverse('branding:design_tools_fonts'), 'label': 'Font Finder', 'icon': 'fa-solid fa-font', 'style': 'color:#f59e0b'},
            {'url': reverse('branding:design_tools_organizer'), 'label': 'Asset Organizer', 'icon': 'fa-solid fa-folder-open', 'style': 'color:#06b6d4'},
            {'url': reverse('branding:design_tools_brand_check'), 'label': 'Brand Check', 'icon': 'fa-solid fa-clipboard-check', 'style': 'color:#22c55e'},
            {'section': 'Collaboration'},
            {'url': reverse('branding:knowledge_base'), 'label': 'Knowledge Base', 'icon': 'fa-solid fa-lightbulb'},
            {'url': reverse('branding:showcase'), 'label': 'Showcase', 'icon': 'fa-solid fa-trophy'},
            {'section': 'Integrations'},
            {'url': reverse('branding:figma_integration'), 'label': 'Figma', 'icon': 'fa-brands fa-figma', 'style': 'color:#a259ff'},
            {'url': reverse('branding:adobe_integration'), 'label': 'Adobe CC', 'icon': 'fa-solid fa-palette', 'style': 'color:#ff0000'},
            {'url': reverse('branding:slack_integration'), 'label': 'Slack', 'icon': 'fa-brands fa-slack', 'style': 'color:#e01e5a'},
            {'url': reverse('branding:calendar_integration'), 'label': 'Calendar', 'icon': 'fa-solid fa-calendar-days', 'style': 'color:#3b82f6'},
        ])

    elif role == ROLE_STAFF:
        items.extend([
            {'url': reverse('branding:my_requests'), 'label': 'My Requests', 'icon': 'fa-solid fa-folder-open'},
            {'url': reverse('branding:client_profile'), 'label': 'Branding Profile', 'icon': 'fa-solid fa-sliders'},
            {'url': reverse('branding:notifications'), 'label': 'Notifications', 'icon': 'fa-regular fa-bell'},
            {'url': reverse('users:profile_dashboard'), 'label': 'Profile', 'icon': 'fa-solid fa-user'},
            {'section': 'Staff'},
            {'url': reverse('branding:unified_dashboard'), 'label': 'Dashboard', 'icon': 'fa-solid fa-gauge-high'},
            {'url': reverse('branding:kanban'), 'label': 'Board', 'icon': 'fa-solid fa-table-columns'},
            {'url': reverse('branding:feedback_list'), 'label': 'Feedback', 'icon': 'fa-solid fa-star'},
        ])

    elif role == ROLE_CLIENT:
        items.extend([
            {'url': reverse('branding:my_requests'), 'label': 'Dashboard', 'icon': 'fa-solid fa-gauge-high'},
            {'url': reverse('branding:wizard'), 'label': 'New Request', 'icon': 'fa-solid fa-plus'},
            {'url': reverse('branding:client_profile'), 'label': 'Branding Profile', 'icon': 'fa-solid fa-sliders'},
            {'url': reverse('branding:notifications'), 'label': 'Notifications', 'icon': 'fa-regular fa-bell'},
            {'url': reverse('users:profile_dashboard'), 'label': 'Profile', 'icon': 'fa-solid fa-user'},
        ])

    return items


# ── Decorators ────────────────────────────────────────────────────────────

def designer_required(view_func):
    """Decorator: user must be a designer or superuser."""
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not is_designer(request.user):
            raise PermissionDenied('Designers only.')
        return view_func(request, *args, **kwargs)
    return _wrapped


def supervisor_required(view_func):
    """Decorator: user must be a supervisor or superuser."""
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not is_supervisor(request.user):
            raise PermissionDenied('Supervisors only.')
        return view_func(request, *args, **kwargs)
    return _wrapped


def staff_required(view_func):
    """Decorator: user must be any staff member."""
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied('Staff only.')
        return view_func(request, *args, **kwargs)
    return _wrapped
