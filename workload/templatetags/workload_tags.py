"""Small template helpers used by the workload workspace."""
from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def query_replace(context, **kwargs):
    """Return the current query string with the given keys replaced.

    ``None`` or an empty value removes the key.  Used for pagination links that
    keep the active filters intact.
    """
    request = context.get('request')
    if request is None:
        return ''
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value in (None, ''):
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()


@register.filter
def clamp_percent(value, maximum=100):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    return min(max(number, 0), maximum)


@register.filter
def get_item(mapping, key):
    if hasattr(mapping, 'get'):
        return mapping.get(key)
    return None
