"""Custom template tags for Root Dashboard."""
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def severity_badge(severity):
    """Render a colored badge for alert severity."""
    mapping = {
        'success': '<span class="badge bg-success"><i class="fas fa-check-circle me-1"></i>OK</span>',
        'info': '<span class="badge bg-info"><i class="fas fa-info-circle me-1"></i>Info</span>',
        'warning': '<span class="badge bg-warning text-dark"><i class="fas fa-exclamation-triangle me-1"></i>Warning</span>',
        'error': '<span class="badge bg-danger"><i class="fas fa-times-circle me-1"></i>Error</span>',
        'critical': '<span class="badge bg-danger"><i class="fas fa-exclamation-circle me-1"></i>Critical</span>',
    }
    return mark_safe(mapping.get(severity, f'<span class="badge bg-secondary">{severity}</span>'))


@register.filter
def status_dot(status):
    """Render a colored status dot."""
    color_map = {
        'ok': '#10b981',
        'healthy': '#10b981',
        'active': '#10b981',
        'warning': '#f59e0b',
        'error': '#ef4444',
        'critical': '#ef4444',
        'inactive': '#94a3b8',
    }
    color = color_map.get(status, '#94a3b8')
    return mark_safe(
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;'
        f'background-color:{color};margin-right:6px;"></span>'
    )


@register.filter
def category_icon(category):
    """Return an icon class for an alert category."""
    icon_map = {
        'security': 'fas fa-shield-alt',
        'engagement': 'fas fa-users',
        'system': 'fas fa-cog',
        'performance': 'fas fa-tachometer-alt',
        'billing': 'fas fa-credit-card',
        'operations': 'fas fa-cogs',
        'general': 'fas fa-info-circle',
    }
    return icon_map.get(category, 'fas fa-info-circle')


@register.filter
def intcomma(value):
    """Format a number with commas: 1234567 -> 1,234,567."""
    try:
        value = int(value)
        return f'{value:,}'
    except (ValueError, TypeError):
        return value


@register.filter
def currency(value):
    """Format a number as currency: 1234.56 -> $1,234.56."""
    try:
        value = float(value)
        return f'${value:,.2f}'
    except (ValueError, TypeError):
        return value


@register.filter
def severity_color(severity):
    """Return a CSS color for a given severity level."""
    color_map = {
        'success': '#10b981',
        'info': '#3b82f6',
        'warning': '#f59e0b',
        'error': '#ef4444',
        'critical': '#ef4444',
    }
    return color_map.get(severity, '#94a3b8')
