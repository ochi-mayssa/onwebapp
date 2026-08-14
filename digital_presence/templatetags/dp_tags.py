from django import template
from django.contrib.humanize.templatetags.humanize import intcomma as _humanize_intcomma

register = template.Library()


@register.filter(name='intcomma')
def intcomma(value):
    return _humanize_intcomma(value)


def _get_severity(item):
    """Get severity from dict or object."""
    if isinstance(item, dict):
        return item.get('severity', '')
    return getattr(item, 'severity', '')


@register.simple_tag
def critical_count(alerts):
    """Count critical alerts."""
    if not alerts:
        return 0
    return sum(1 for a in alerts if _get_severity(a) == 'critical')


@register.simple_tag
def warning_count(alerts):
    """Count warning alerts."""
    if not alerts:
        return 0
    return sum(1 for a in alerts if _get_severity(a) == 'warning')
