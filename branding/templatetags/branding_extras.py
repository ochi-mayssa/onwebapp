from django import template
from django.utils.safestring import mark_safe
import json

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Return mapping[key], or None when key is missing."""
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def status_label(value, choices=None):
    """Map a status code to its human label. If no choices, use STATUS_CHOICES."""
    if choices is None:
        from branding.models import STATUS_CHOICES
        choices = STATUS_CHOICES
    for code, label in choices:
        if code == value:
            return label
    return value


@register.filter
def join_display(mapping, items):
    """Join a list of codes into their human labels from a mapping of code -> label."""
    if not items:
        return '—'
    labels = [mapping.get(item, item) for item in items]
    return ', '.join(labels)


@register.filter
def duration_display(seconds):
    """Render a duration (seconds) as a compact human string."""
    if seconds is None:
        return '—'
    seconds = float(seconds)
    if seconds < 60:
        return f'{int(seconds)}s'
    if seconds < 3600:
        return f'{int(seconds // 60)}m'
    if seconds < 86400:
        return f'{seconds / 3600:.1f}h'
    return f'{seconds / 86400:.1f}d'


@register.filter
def star_range(rating):
    """Return range(1, 6) for a given rating (for iterating in templates)."""
    try:
        return range(1, int(rating) + 1)
    except (TypeError, ValueError):
        return range(0)


@register.filter
def star_empty_range(rating):
    """Return range for empty stars (5 - rating)."""
    try:
        return range(0, 5 - int(rating))
    except (TypeError, ValueError):
        return range(5)


@register.simple_tag
def star_html(rating):
    """Render a 5-star HTML string with filled and empty stars."""
    rating = int(rating) if rating else 0
    filled = '<i class="fa-solid fa-star text-warning"></i> ' * min(rating, 5)
    empty = '<i class="fa-regular fa-star text-warning"></i> ' * (5 - min(rating, 5))
    return mark_safe(filled + empty)  # noqa: S308


@register.simple_tag
def star_html_readonly(rating):
    """Render a 5-star HTML string (read-only, for display)."""
    rating = int(rating) if rating else 0
    stars = []
    for i in range(1, 6):
        if i <= rating:
            stars.append('<i class="fa-solid fa-star text-warning"></i>')
        else:
            stars.append('<i class="fa-regular fa-star text-muted"></i>')
    return mark_safe(' '.join(stars))  # noqa: S308


@register.filter
def multiply(value, arg):
    """Multiply value by arg."""
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def to_json(value):
    """Serialize value to JSON for use in data attributes."""
    return mark_safe(json.dumps(value))  # noqa: S308


@register.filter
def format_minutes(value):
    """Format a timedelta or total minutes as 'Xh Ym'."""
    if value is None:
        return '0h 0m'
    if hasattr(value, 'total_seconds'):
        total = int(value.total_seconds())
    else:
        try:
            total = int(value)
        except (ValueError, TypeError):
            return '0h 0m'
    hours = total // 3600
    minutes = (total % 3600) // 60
    if hours and minutes:
        return f'{hours}h {minutes}m'
    if hours:
        return f'{hours}h'
    return f'{minutes}m'


@register.simple_tag
def question_type_icon(question_type):
    icons = {
        'multiple_choice': 'fa-solid fa-list',
        'preference_scale': 'fa-solid fa-sliders',
        'yes_no': 'fa-solid fa-toggle-on',
        'short_text': 'fa-solid fa-font',
        'long_text': 'fa-solid fa-align-left',
        'color_picker': 'fa-solid fa-droplet',
        'font_selection': 'fa-solid fa-text-height',
        'image_upload': 'fa-solid fa-image',
        'rank_order': 'fa-solid fa-arrows-up-down',
        'rating': 'fa-solid fa-star',
    }
    return icons.get(question_type, 'fa-solid fa-circle-question')


@register.simple_tag
def question_type_label(question_type):
    labels = {
        'multiple_choice': 'Multiple Choice',
        'preference_scale': 'Scale',
        'yes_no': 'Yes/No',
        'short_text': 'Short Text',
        'long_text': 'Long Text',
        'color_picker': 'Color',
        'font_selection': 'Font',
        'image_upload': 'Image',
        'rank_order': 'Rank',
        'rating': 'Rating',
    }
    return labels.get(question_type, question_type)


@register.simple_tag
def phase_icon(phase):
    icons = {
        'discovery': 'fa-solid fa-magnifying-glass',
        'concept_direction': 'fa-solid fa-compass',
        'color_typography': 'fa-solid fa-palette',
        'layout_structure': 'fa-solid fa-table-cells-large',
        'final_polish': 'fa-solid fa-wand-magic-sparkles',
    }
    return icons.get(phase, 'fa-solid fa-circle-question')


@register.filter
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def percentage(value, total):
    try:
        total = float(total)
        if total == 0:
            return 0
        return round(float(value) / total * 100)
    except (ValueError, TypeError):
        return 0


@register.filter
def absolute(value):
    """Return the absolute value."""
    try:
        return abs(value)
    except (TypeError, ValueError):
        return 0


@register.filter
def filter_by_concept(decisions, concept):
    """Filter a list of decisions by concept."""
    return [d for d in decisions if d.concept_id == concept.pk]
