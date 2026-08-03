from django import template

register = template.Library()

@register.filter
def get_attr(obj, attr):
    """Get an attribute from an object or a key from a dictionary."""
    if isinstance(obj, dict):
        return obj.get(attr)
    return getattr(obj, attr, None)
