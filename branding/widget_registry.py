"""Widget registry and data providers for the unified staff dashboard."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Avg, Q, F, Sum
from django.utils import timezone

from .models import (
    BrandingRequest, BrandingMessage, BrandingNotification, BrandingFeedback,
    BrandingTimeline, TimeEntry, StaffWorkload, DailyAggregate, DesignDraft, PeerReview,
    DesignComment, DesignHandoff, CalendarEvent, StaffDashboard,
    DashboardWidget, WidgetDefinition, WIDGET_TYPES,
)
from .roles import get_user_role, ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_DESIGNER, ROLE_STAFF

User = get_user_model()


WIDGET_REGISTRY = {}


def register_widget(widget_type):
    """Decorator to register a widget data provider."""
    def decorator(func):
        WIDGET_REGISTRY[widget_type] = func
        return func
    return decorator


def get_widget_data(widget_type, request, config=None):
    """Fetch data for a widget type."""
    provider = WIDGET_REGISTRY.get(widget_type)
    if provider:
        return provider(request, config or {})
    return {'error': f'Unknown widget type: {widget_type}'}


def ensure_dashboard(user):
    """Get or create a StaffDashboard with default widgets for a user."""
    dashboard, created = StaffDashboard.objects.get_or_create(user=user)
    if created or dashboard.widgets.count() == 0:
        _seed_default_widgets(dashboard, user)
    return dashboard


def _seed_default_widgets(dashboard, user):
    """Create default widget layout for a new dashboard."""
    role = get_user_role(user)
    widgets_to_add = _default_widgets_for_role(role)
    for w in widgets_to_add:
        _ensure_widget_def(w['type'])
        wd = WidgetDefinition.objects.get(widget_type=w['type'])
        DashboardWidget.objects.get_or_create(
            dashboard=dashboard,
            col=w.get('col', 0),
            row=w.get('row', 0),
            defaults={
                'widget_def': wd,
                'title': w.get('title', ''),
                'width': w.get('width', 1),
                'height': w.get('height', 1),
                'visible_roles': w.get('visible_roles', []),
                'config': w.get('config', {}),
            }
        )


def _default_widgets_for_role(role):
    """Return default widget layout for a role."""
    common = [
        {'type': 'stats_quick', 'col': 0, 'row': 0, 'width': 2, 'height': 1, 'visible_roles': []},
        {'type': 'feed_activity', 'col': 0, 'row': 1, 'width': 2, 'height': 2, 'visible_roles': []},
        {'type': 'feed_notifications', 'col': 2, 'row': 0, 'width': 1, 'height': 1, 'visible_roles': []},
    ]

    if role in (ROLE_ADMIN, ROLE_SUPERVISOR):
        common.extend([
            {'type': 'stats_projects', 'col': 0, 'row': 0, 'width': 1, 'height': 1, 'visible_roles': [ROLE_SUPERVISOR, ROLE_ADMIN]},
            {'type': 'stats_team', 'col': 1, 'row': 0, 'width': 1, 'height': 1, 'visible_roles': [ROLE_SUPERVISOR, ROLE_ADMIN]},
            {'type': 'chart_status', 'col': 2, 'row': 1, 'width': 1, 'height': 1, 'visible_roles': [ROLE_SUPERVISOR, ROLE_ADMIN]},
            {'type': 'table_team', 'col': 0, 'row': 3, 'width': 2, 'height': 1, 'visible_roles': [ROLE_SUPERVISOR, ROLE_ADMIN]},
            {'type': 'table_recent', 'col': 2, 'row': 2, 'width': 1, 'height': 1, 'visible_roles': [ROLE_SUPERVISOR, ROLE_ADMIN]},
        ])

    if role == ROLE_DESIGNER:
        common.extend([
            {'type': 'stats_designer', 'col': 0, 'row': 0, 'width': 1, 'height': 1, 'visible_roles': [ROLE_DESIGNER]},
            {'type': 'table_timesheet', 'col': 1, 'row': 0, 'width': 1, 'height': 1, 'visible_roles': [ROLE_DESIGNER]},
            {'type': 'tools_timer', 'col': 2, 'row': 0, 'width': 1, 'height': 1, 'visible_roles': [ROLE_DESIGNER]},
            {'type': 'tools_shortcuts', 'col': 2, 'row': 1, 'width': 1, 'height': 1, 'visible_roles': [ROLE_DESIGNER]},
            {'type': 'feed_messages', 'col': 0, 'row': 2, 'width': 1, 'height': 1, 'visible_roles': [ROLE_DESIGNER]},
        ])

    if role == ROLE_STAFF:
        common.extend([
            {'type': 'table_recent', 'col': 0, 'row': 1, 'width': 2, 'height': 1, 'visible_roles': [ROLE_STAFF]},
        ])

    return common


def _ensure_widget_def(widget_type):
    """Ensure a WidgetDefinition exists for the given type."""
    if not WidgetDefinition.objects.filter(widget_type=widget_type).exists():
        labels = dict(WIDGET_TYPES)
        categories = {
            'stats_quick': 'stats', 'stats_projects': 'stats', 'stats_team': 'stats', 'stats_designer': 'stats',
            'chart_status': 'chart', 'chart_timeline': 'chart', 'chart_workload': 'chart', 'chart_performance': 'chart',
            'table_recent': 'table', 'table_team': 'table', 'table_estimated_delivery_dates': 'table', 'table_timesheet': 'table',
            'feed_activity': 'feed', 'feed_notifications': 'feed', 'feed_messages': 'feed', 'feed_calendar': 'feed',
            'tools_shortcuts': 'tools', 'tools_timer': 'tools', 'tools_figma': 'tools', 'tools_adobe': 'tools',
        }
        icons = {
            'stats_quick': 'fa-solid fa-chart-simple', 'stats_projects': 'fa-solid fa-folder-open',
            'stats_team': 'fa-solid fa-users', 'stats_designer': 'fa-solid fa-palette',
            'chart_status': 'fa-solid fa-chart-pie', 'chart_timeline': 'fa-solid fa-chart-line',
            'chart_workload': 'fa-solid fa-chart-bar', 'chart_performance': 'fa-solid fa-gauge-high',
            'table_recent': 'fa-solid fa-list', 'table_team': 'fa-solid fa-table',
            'table_estimated_delivery_dates': 'fa-solid fa-calendar-days', 'table_timesheet': 'fa-solid fa-clock',
            'feed_activity': 'fa-solid fa-stream', 'feed_notifications': 'fa-regular fa-bell',
            'feed_messages': 'fa-regular fa-comments', 'feed_calendar': 'fa-solid fa-calendar',
            'tools_shortcuts': 'fa-solid fa-bolt', 'tools_timer': 'fa-solid fa-stopwatch',
            'tools_figma': 'fa-brands fa-figma', 'tools_adobe': 'fa-solid fa-palette',
        }
        WidgetDefinition.objects.create(
            widget_type=widget_type,
            label=labels.get(widget_type, widget_type),
            icon=icons.get(widget_type, 'fa-solid fa-puzzle-piece'),
            category=categories.get(widget_type, 'stats'),
        )


def seed_all_widget_definitions():
    """Seed all widget definitions."""
    for widget_type, _ in WIDGET_TYPES:
        _ensure_widget_def(widget_type)


# ═══════════════════════════════════════════════════════════════════════════
# Widget Data Providers
# ═══════════════════════════════════════════════════════════════════════════

@register_widget('stats_quick')
def _stats_quick(request, config):
    user = request.user
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    base = BrandingRequest.objects.all()
    my_projects = base.filter(designer=user) if user.is_staff else base.filter(user=user)
    return {
        'total': base.exclude(status='ARCHIVED').count(),
        'active': base.filter(status__in=['IN_REVIEW', 'DESIGNING', 'ASSIGNED', 'WAITING_CLIENT', 'REVISION']).count(),
        'completed_week': base.filter(status='COMPLETED', completed_at__gte=week_ago).count(),
        'my_projects': my_projects.count(),
        'my_active': my_projects.filter(status__in=['IN_REVIEW', 'DESIGNING', 'ASSIGNED', 'WAITING_CLIENT', 'REVISION']).count(),
        'overdue': base.filter(estimated_delivery_date__lt=now).exclude(status__in=['COMPLETED', 'ARCHIVED']).count(),
    }


@register_widget('stats_projects')
def _stats_projects(request, config):
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    base = BrandingRequest.objects.exclude(status='ARCHIVED')
    return {
        'total': base.count(),
        'pending': base.filter(status='PENDING_REVIEW').count(),
        'in_progress': base.filter(status__in=['IN_REVIEW', 'DESIGNING', 'ASSIGNED']).count(),
        'waiting': base.filter(status='WAITING_CLIENT').count(),
        'completed': base.filter(status='COMPLETED').count(),
        'completed_week': base.filter(status='COMPLETED', completed_at__gte=week_ago).count(),
        'archived': BrandingRequest.objects.filter(status='ARCHIVED').count(),
    }


@register_widget('stats_team')
def _stats_team(request, config):
    designers = User.objects.filter(groups__name='Designers', is_active=True).distinct()
    active_designers = designers.filter(
        Q(branding_design_assignments__status__in=['DESIGNING', 'ASSIGNED'])
    ).distinct().count()
    return {
        'total_designers': designers.count(),
        'active_designers': active_designers,
        'unassigned': BrandingRequest.objects.filter(designer__isnull=True).exclude(status__in=['COMPLETED', 'ARCHIVED', 'DRAFT']).count(),
        'avg_completion_days': 5,
    }


@register_widget('stats_designer')
def _stats_designer(request, config):
    user = request.user
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    my = BrandingRequest.objects.filter(designer=user)
    return {
        'assigned': my.exclude(status__in=['COMPLETED', 'ARCHIVED']).count(),
        'designing': my.filter(status='DESIGNING').count(),
        'completed_week': my.filter(status='COMPLETED', completed_at__gte=week_ago).count(),
        'hours_this_week': TimeEntry.objects.filter(
            designer=user, date__gte=week_ago.date()
        ).aggregate(total=Sum('duration_minutes'))['total'] or 0,
    }


@register_widget('chart_status')
def _chart_status(request, config):
    statuses = ['DRAFT', 'PENDING_REVIEW', 'IN_REVIEW', 'ASSIGNED', 'DESIGNING', 'WAITING_CLIENT', 'REVISION', 'APPROVED', 'COMPLETED']
    data = BrandingRequest.objects.exclude(status='ARCHIVED').values('status').annotate(
        count=Count('id')
    ).order_by('status')
    return {
        'labels': [d['status'].replace('_', ' ').title() for d in data],
        'values': [d['count'] for d in data],
        'colors': ['#6b7280', '#f59e0b', '#3b82f6', '#8b5cf6', '#ec4899', '#f97316', '#ef4444', '#10b981', '#22c55e'],
    }


@register_widget('chart_timeline')
def _chart_timeline(request, config):
    days = 14
    now = timezone.now()
    labels = []
    created = []
    completed = []
    for i in range(days - 1, -1, -1):
        d = (now - timedelta(days=i)).date()
        labels.append(d.strftime('%b %d'))
        created.append(BrandingRequest.objects.filter(created_at__date=d).count())
        completed.append(BrandingRequest.objects.filter(completed_at__date=d, status='COMPLETED').count())
    return {'labels': labels, 'created': created, 'completed': completed}


@register_widget('chart_workload')
def _chart_workload(request, config):
    designers = User.objects.filter(groups__name='Designers', is_active=True).distinct()[:8]
    names = []
    counts = []
    for d in designers:
        names.append(d.get_full_name() or d.username)
        counts.append(BrandingRequest.objects.filter(
            designer=d
        ).exclude(status__in=['COMPLETED', 'ARCHIVED']).count())
    return {'labels': names, 'values': counts}


@register_widget('chart_performance')
def _chart_performance(request, config):
    aggs = DailyAggregate.objects.order_by('-date')[:14]
    return {
        'labels': [a.date.strftime('%b %d') for a in reversed(list(aggs))],
        'completed': [a.completed_count for a in reversed(list(aggs))],
        'created': [a.created_count for a in reversed(list(aggs))],
    }


@register_widget('table_recent')
def _table_recent(request, config):
    limit = config.get('limit', 8)
    qs = BrandingRequest.objects.select_related('designer').order_by('-created_at')[:limit]
    return {
        'requests': [
            {
                'id': r.id,
                'number': r.request_number,
                'company': r.company_name,
                'status': r.status,
                'priority': r.priority,
                'assigned': r.designer.get_full_name() if r.designer else 'Unassigned',
                'created': r.created_at.strftime('%b %d'),
            }
            for r in qs
        ]
    }


@register_widget('table_team')
def _table_team(request, config):
    designers = User.objects.filter(groups__name='Designers', is_active=True).distinct()[:10]
    return {
        'members': [
            {
                'id': d.id,
                'name': d.get_full_name() or d.username,
                'active': BrandingRequest.objects.filter(designer=d).exclude(
                    status__in=['COMPLETED', 'ARCHIVED']
                ).count(),
                'completed': BrandingRequest.objects.filter(designer=d, status='COMPLETED').count(),
            }
            for d in designers
        ]
    }


@register_widget('table_estimated_delivery_dates')
def _table_estimated_delivery_dates(request, config):
    now = timezone.now()
    qs = BrandingRequest.objects.filter(
        estimated_delivery_date__gte=now
    ).exclude(status__in=['COMPLETED', 'ARCHIVED']).order_by('estimated_delivery_date')[:8]
    return {
        'items': [
            {
                'id': r.id,
                'number': r.request_number,
                'company': r.company_name,
                'estimated_delivery_date': r.estimated_delivery_date.strftime('%b %d %Y') if r.estimated_delivery_date else 'None',
                'status': r.status,
            }
            for r in qs
        ]
    }


@register_widget('table_timesheet')
def _table_timesheet(request, config):
    now = timezone.now()
    week_start = now - timedelta(days=now.weekday())
    entries = TimeEntry.objects.filter(
        designer=request.user, date__gte=week_start.date()
    ).select_related('request').order_by('-date')[:10]
    return {
        'entries': [
            {
                'id': e.id,
                'request': str(e.request),
                'phase': e.get_phase_display() if hasattr(e, 'get_phase_display') else e.phase,
                'start': e.date.strftime('%b %d'),
                'duration': f'{e.duration_minutes}m',
            }
            for e in entries
        ]
    }


@register_widget('feed_activity')
def _feed_activity(request, config):
    limit = config.get('limit', 12)
    events = BrandingTimeline.objects.select_related('request', 'actor').order_by('-created_at')[:limit]
    return {
        'events': [
            {
                'id': e.id,
                'user': e.actor.get_full_name() if e.actor else 'System',
                'action': e.action,
                'request_number': e.request.request_number if e.request else '',
                'description': e.description[:120] if e.description else '',
                'time': e.created_at.strftime('%b %d %H:%M'),
            }
            for e in events
        ]
    }


@register_widget('feed_notifications')
def _feed_notifications(request, config):
    limit = config.get('limit', 8)
    notifs = BrandingNotification.objects.filter(
        recipient=request.user
    ).order_by('-created_at')[:limit]
    return {
        'notifications': [
            {
                'id': n.id,
                'title': n.message[:60] if n.message else '',
                'message': n.message[:100] if n.message else '',
                'is_read': n.is_read,
                'time': n.created_at.strftime('%b %d %H:%M'),
            }
            for n in notifs
        ]
    }


@register_widget('feed_messages')
def _feed_messages(request, config):
    limit = config.get('limit', 8)
    msgs = BrandingMessage.objects.filter(
        Q(request__user=request.user) | Q(sender=request.user)
    ).select_related('sender', 'request').order_by('-created_at')[:limit]
    return {
        'messages': [
            {
                'id': m.id,
                'sender': m.sender.get_full_name() if m.sender else 'System',
                'preview': m.content[:100] if m.content else '',
                'request_number': m.request.request_number if m.request else '',
                'time': m.created_at.strftime('%b %d %H:%M'),
            }
            for m in msgs
        ]
    }


@register_widget('feed_calendar')
def _feed_calendar(request, config):
    now = timezone.now()
    events = CalendarEvent.objects.filter(
        start_time__gte=now
    ).order_by('start_time')[:8]
    return {
        'events': [
            {
                'id': e.id,
                'title': e.title,
                'type': e.event_type,
                'start': e.start_time.strftime('%b %d %H:%M'),
                'location': e.location,
            }
            for e in events
        ]
    }


@register_widget('tools_shortcuts')
def _tools_shortcuts(request, config):
    from django.urls import reverse
    shortcuts = [
        {'label': 'Color Picker', 'url': reverse('branding:design_tools_color'), 'icon': 'fa-solid fa-droplet', 'color': '#818cf8'},
        {'label': 'Font Finder', 'url': reverse('branding:design_tools_fonts'), 'icon': 'fa-solid fa-font', 'color': '#f59e0b'},
        {'label': 'Asset Organizer', 'url': reverse('branding:design_tools_organizer'), 'icon': 'fa-solid fa-folder-open', 'color': '#06b6d4'},
        {'label': 'Brand Check', 'url': reverse('branding:design_tools_brand_check'), 'icon': 'fa-solid fa-clipboard-check', 'color': '#22c55e'},
        {'label': 'Figma', 'url': reverse('branding:figma_integration'), 'icon': 'fa-brands fa-figma', 'color': '#a259ff'},
        {'label': 'Adobe CC', 'url': reverse('branding:adobe_integration'), 'icon': 'fa-solid fa-palette', 'color': '#ff0000'},
    ]
    return {'shortcuts': shortcuts}


@register_widget('tools_timer')
def _tools_timer(request, config):
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    active = TimeEntry.objects.filter(designer=request.user, is_timer_running=True).first()
    week_hours = TimeEntry.objects.filter(
        designer=request.user, date__gte=week_ago.date()
    ).aggregate(
        total=Sum('duration_minutes')
    )['total'] or 0
    return {
        'is_running': active is not None,
        'active_request': str(active.request) if active and active.request else '',
        'started_at': active.timer_started_at.strftime('%H:%M') if active and active.timer_started_at else '',
        'week_hours': f'{week_hours // 60}h {week_hours % 60}m' if week_hours else '0h',
    }


@register_widget('tools_figma')
def _tools_figma(request, config):
    from .models import FigmaConnection
    conn = FigmaConnection.objects.filter(user=request.user).first()
    return {
        'connected': conn is not None,
        'workspace': conn.workspace_name if conn else '',
        'last_sync': conn.last_synced.strftime('%b %d %H:%M') if conn and conn.last_synced else 'Never',
    }


@register_widget('tools_adobe')
def _tools_adobe(request, config):
    from .models import AdobeConnection
    conn = AdobeConnection.objects.filter(user=request.user).first()
    return {
        'connected': conn is not None,
        'account': conn.adobe_email if conn else '',
        'last_sync': conn.last_synced.strftime('%b %d %H:%M') if conn and conn.last_synced else 'Never',
    }
