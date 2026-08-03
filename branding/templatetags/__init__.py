from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Return mapping[key], or None when key is missing."""
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def status_label(choices, value):
    """Map a status code to its human label."""
    for code, label in choices:
        if code == value:
            return label
    return value


@register.filter
def join_display(mapping, items):
    """Join a list of codes into their human labels from a choices mapping."""
    if not items:
        return '—'
    labels = [dict(mapping).get(item, item) for item in items]
    return ', '.join(labels)
