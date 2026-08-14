"""Decorators for the Root Dashboard."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def root_required(view_func):
    """
    Decorator that ensures the user is authenticated and is a superuser (Root).
    Redirects unauthenticated users to login.
    Raises PermissionDenied for non-superusers.
    """
    @login_required
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied(
                "You do not have permission to access the Root Command Center."
            )
        return view_func(request, *args, **kwargs)
    return _wrapped_view
