"""Context processors shared by the Branding Studio templates."""

from .models import BrandingMessage, BrandingNotification
from .roles import get_user_role, get_role_nav_items, get_role_dropdown_items


def branding_context(request):
    """Expose unread notification and message counts, user role, and navigation to branding templates."""
    unread = 0
    unread_messages = 0
    user_role = None
    role_nav = []
    role_dropdown = []
    if request.user.is_authenticated:
        unread = BrandingNotification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
        unread_messages = BrandingMessage.get_unread_count(request.user)
        user_role = get_user_role(request.user)
        try:
            role_nav = get_role_nav_items(request.user)
        except Exception:
            role_nav = []
        try:
            role_dropdown = get_role_dropdown_items(request.user)
        except Exception:
            role_dropdown = []
    return {
        'unread_notifications': unread,
        'unread_messages': unread_messages,
        'user_role': user_role,
        'role_nav': role_nav,
        'role_dropdown': role_dropdown,
    }
