from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag(takes_context=True)
def monitoring_url(context):
    """Return the monitoring URL based on user role.
    Root/Admin → platform dashboard.
    All others → platform monitoring hub.
    """
    user = context.get('user')
    if user and (user.is_superuser or getattr(user, 'is_staff', False)):
        return reverse('projects:platform_dashboard')
    return reverse('platform_monitoring:hub')


@register.filter(name='str_split')
def str_split(value, arg):
    """Splits a string by the given delimiter."""
    return value.split(arg)
