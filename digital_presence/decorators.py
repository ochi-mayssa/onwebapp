"""Decorators for Digital Presence views."""
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def designer_or_superuser_required(view_func):
    """
    Decorator: user must be a designer or superuser.
    Uses the existing branding roles system.
    """
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        from branding.roles import is_designer
        if not is_designer(request.user):
            raise PermissionDenied('Designers only.')
        return view_func(request, *args, **kwargs)
    return _wrapped
