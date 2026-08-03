"""Custom permissions for the Branding API."""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsStaffUser(BasePermission):
    """Allow access only to staff users."""

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_staff


class IsClientUser(BasePermission):
    """Allow access only to authenticated non-staff users (clients)."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and not request.user.is_staff
        )


class IsOwnerOrStaff(BasePermission):
    """Object-level: allow the request owner or any staff member."""

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        # BrandingRequest has a `user` FK
        if hasattr(obj, 'user'):
            return obj.user_id == request.user.id
        # BrandingFeedback has a `request` FK → check request.user
        if hasattr(obj, 'request') and hasattr(obj.request, 'user'):
            return obj.request.user_id == request.user.id
        # BrandingNotification has a `recipient` FK
        if hasattr(obj, 'recipient'):
            return obj.recipient_id == request.user.id
        # BrandingMessage has a `sender` FK
        if hasattr(obj, 'sender'):
            return obj.sender_id == request.user.id
        return False


class IsRequestOwnerOrStaff(BasePermission):
    """For nested resources: check the parent BrandingRequest ownership."""

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        # obj should be a BrandingRequest or have a `request` FK
        req = getattr(obj, 'request', obj)
        if hasattr(req, 'user'):
            return req.user_id == request.user.id
        return False
