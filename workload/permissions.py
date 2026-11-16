"""Role detection and object-level scoping for workload records.

The platform's existing RBAC convention (``branding.roles``) is based on Django
staff/superuser flags plus named groups.  Workload follows the same convention:

* Administrator - superuser or ``Workload Administrators`` group.
* Manager       - staff user or ``Workload Managers`` group.
* Employee      - ``operations.EmployeeProfile`` or ``Workload Employees`` group.
* Client        - any other authenticated user.

Managers operate the platform, so they may view all workload records.  Every
non-manager is scoped to their own assignments or to explicitly client-visible
records belonging to their tenant.
"""
from functools import wraps

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Q

User = get_user_model()

GROUP_ADMINISTRATORS = 'Workload Administrators'
GROUP_MANAGERS = 'Workload Managers'
GROUP_EMPLOYEES = 'Workload Employees'

ROLE_ADMIN = 'admin'
ROLE_MANAGER = 'manager'
ROLE_EMPLOYEE = 'employee'
ROLE_CLIENT = 'client'


def _in_group(user, name):
    try:
        return user.groups.filter(name=name).exists()
    except Exception:  # pragma: no cover - defensive during migrations
        return False


def _has_employee_profile(user):
    try:
        from operations.models import EmployeeProfile

        return EmployeeProfile.objects.filter(user=user, is_active_employee=True).exists()
    except Exception:  # pragma: no cover - operations app may be unavailable
        return False


def get_role(user):
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser or _in_group(user, GROUP_ADMINISTRATORS):
        return ROLE_ADMIN
    if user.is_staff or _in_group(user, GROUP_MANAGERS):
        return ROLE_MANAGER
    if _in_group(user, GROUP_EMPLOYEES) or _has_employee_profile(user):
        return ROLE_EMPLOYEE
    return ROLE_CLIENT


def is_admin(user):
    return bool(user and user.is_authenticated and (
        user.is_superuser or _in_group(user, GROUP_ADMINISTRATORS)
    ))


def is_global_manager(user):
    """Return True for platform operators whose scope is the whole install.

    Only Django staff/superusers (and the explicitly trusted workload
    administrator group) operate globally.  A user who is merely a member of
    the ``Workload Managers`` group is a workspace manager and stays inside
    their own tenant.
    """
    if not user or not user.is_authenticated:
        return False
    return bool(
        user.is_superuser
        or user.is_staff
        or _in_group(user, GROUP_ADMINISTRATORS)
    )


def is_manager(user):
    role = get_role(user)
    return role in (ROLE_ADMIN, ROLE_MANAGER)


def is_employee(user):
    return get_role(user) in (ROLE_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE)


def is_client(user):
    return get_role(user) == ROLE_CLIENT


def can_manage_resources(user):
    return is_manager(user)


def can_configure_policies(user):
    return is_admin(user)


def _tenant_manager_work_items(user):
    """Q object for work a workspace manager is allowed to manage."""
    return (
        Q(tenant=user)
        | Q(team__tenant=user)
        | Q(team__lead=user)
        | Q(assignee=user)
        | Q(created_by=user)
        | Q(assignments__resource__user=user)
    )


def scope_work_items(queryset, user):
    """Apply tenant/assignment scoping.

    Global staff operators see everything.  Workspace managers only see work
    that belongs to their tenant, their teams, or themselves.  Non-managers
    keep the narrower employee/client rules.
    """
    if not user or not user.is_authenticated:
        return queryset.none()
    role = get_role(user)
    if role in (ROLE_ADMIN, ROLE_MANAGER):
        if is_global_manager(user):
            return queryset
        return queryset.filter(_tenant_manager_work_items(user)).distinct()
    if role == ROLE_EMPLOYEE:
        return queryset.filter(
            Q(assignee=user)
            | Q(team__members=user)
            | Q(created_by=user)
            | Q(tenant=user)
            | Q(assignments__resource__user=user)
        ).distinct()
    # Client: only explicitly exposed records that belong to this tenant/client.
    return queryset.filter(
        Q(tenant=user, is_client_visible=True)
        | Q(client__user=user, is_client_visible=True)
    ).distinct()


def scope_resources(queryset, user):
    """Managers see their tenant's resources; employees see their own."""
    if not user or not user.is_authenticated:
        return queryset.none()
    if is_global_manager(user):
        return queryset
    if is_manager(user):
        return queryset.filter(
            Q(tenant=user)
            | Q(team__tenant=user)
            | Q(team__lead=user)
            | Q(user=user)
        ).distinct()
    return queryset.filter(Q(user=user) | Q(team__members=user)).distinct()


def assignable_resources(user):
    """Active resources a caller may assign work to.

    Shared system/process resources belong to the platform and can serve any
    workspace; every other resource must pass the tenant/team scope rules.
    """
    from .models import WorkloadResource

    queryset = WorkloadResource.objects.filter(is_active=True)
    if not user or not user.is_authenticated:
        return queryset.none()
    if is_global_manager(user):
        return queryset
    scoped = scope_resources(queryset, user)
    return queryset.filter(
        Q(pk__in=scoped.values('pk'))
        | Q(tenant__isnull=True, kind=WorkloadResource.KIND_SYSTEM),
    ).distinct()


def scope_alerts(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if is_global_manager(user):
        return queryset
    if is_manager(user):
        return queryset.filter(
            Q(tenant=user)
            | Q(recipient=user)
            | Q(resource__user=user)
            | Q(resource__tenant=user)
            | Q(team__tenant=user)
            | Q(team__lead=user)
            | Q(work_item__tenant=user)
            | Q(work_item__team__tenant=user)
            | Q(work_item__team__lead=user)
            | Q(work_item__assignee=user)
        ).distinct()
    return queryset.filter(Q(recipient=user) | Q(work_item__assignee=user)).distinct()


def scope_teams(queryset, user):
    """Restrict teams to the caller's tenant for non-staff managers."""
    if not user or not user.is_authenticated:
        return queryset.none()
    if is_global_manager(user):
        return queryset
    if is_manager(user):
        return queryset.filter(
            Q(tenant=user) | Q(lead=user) | Q(members=user),
        ).distinct()
    return queryset.filter(members=user).distinct()


def scope_policies(queryset, user):
    """Tenant managers can read the global default and their own policies."""
    if not user or not user.is_authenticated:
        return queryset.none()
    if is_global_manager(user):
        return queryset
    if is_manager(user):
        return queryset.filter(Q(tenant__isnull=True) | Q(tenant=user))
    return queryset.none()


def assignable_users(user):
    """Active users a caller may select as an assignee or team member."""
    if not user or not user.is_authenticated:
        return User.objects.none()
    queryset = User.objects.filter(is_active=True)
    if is_global_manager(user):
        return queryset.order_by('first_name', 'last_name', 'username')
    if is_manager(user):
        return queryset.filter(
            Q(pk=user.pk)
            | Q(workload_teams__tenant=user)
            | Q(workload_teams__lead=user)
            | Q(workload_resource__tenant=user)
        ).distinct().order_by('first_name', 'last_name', 'username')
    return queryset.filter(pk=user.pk)


def can_view_work_item(user, item):
    if not user or not user.is_authenticated:
        return False
    if is_global_manager(user):
        return True
    return scope_work_items(type(item).objects.filter(pk=item.pk), user).exists()


def can_edit_work_item(user, item):
    if is_global_manager(user):
        return True
    if not user or not user.is_authenticated:
        return False
    if is_manager(user):
        return scope_work_items(type(item).objects.filter(pk=item.pk), user).exists()
    return item.created_by_id == user.id or item.assignee_id == user.id


def can_change_status(user, item):
    return can_edit_work_item(user, item)


def can_assign_work(user):
    return is_manager(user)


def _forbid(message='You do not have permission to perform this action.'):
    raise PermissionDenied(message)


def login_required_workload(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        return view_func(request, *args, **kwargs)

    return _wrapped


def manager_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        if not is_manager(request.user):
            _forbid('Manager access is required for workload administration.')
        return view_func(request, *args, **kwargs)

    return _wrapped


def admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        if not is_admin(request.user):
            _forbid('Administrator access is required to configure workload policies.')
        return view_func(request, *args, **kwargs)

    return _wrapped
