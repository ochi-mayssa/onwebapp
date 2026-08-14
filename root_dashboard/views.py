"""Views for the Root Dashboard — Command Center and Operations Center."""
from django.shortcuts import render
from django.http import JsonResponse
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from .decorators import root_required
from .services.queries import (
    get_user_metrics,
    get_customer_metrics,
    get_project_metrics,
    get_subscription_metrics,
    get_revenue_metrics,
    get_service_overview,
    get_alerts as get_executive_alerts,
    get_recent_activity,
    get_platform_health,
    get_user_growth_chart,
    get_project_activity_chart,
    get_revenue_chart,
    get_subscription_chart,
)
from .services.system_health import run_all_checks, get_overall_status
from .services.infrastructure import get_all_infrastructure_metrics
from .services.alerts import get_all_alerts, get_alert_summary
from .services.search import global_search

# Cache timeout for metrics (seconds)
METRICS_CACHE_TTL = 120
HEALTH_CACHE_TTL = 60


# ---------------------------------------------------------------------------
# Command Center (Executive Dashboard)
# ---------------------------------------------------------------------------

@root_required
def command_center(request):
    """
    Main Root Dashboard — Executive Command Center.
    Only accessible to superusers.
    Uses caching for performance on repeated loads.
    """
    time_filter = request.GET.get('period', '90d')
    days_map = {'7d': 7, '30d': 30, '90d': 90, '365d': 365}
    chart_days = days_map.get(time_filter, 90)

    # Cache key includes time filter so charts update per-period
    cache_key_metrics = f'root_metrics_{time_filter}'
    cache_key_charts = f'root_charts_{chart_days}'

    user_metrics = cache.get(f'{cache_key_metrics}_users')
    if user_metrics is None:
        user_metrics = get_user_metrics()
        cache.set(f'{cache_key_metrics}_users', user_metrics, METRICS_CACHE_TTL)

    customer_metrics = cache.get(f'{cache_key_metrics}_customers')
    if customer_metrics is None:
        customer_metrics = get_customer_metrics()
        cache.set(f'{cache_key_metrics}_customers', customer_metrics, METRICS_CACHE_TTL)

    project_metrics = cache.get(f'{cache_key_metrics}_projects')
    if project_metrics is None:
        project_metrics = get_project_metrics()
        cache.set(f'{cache_key_metrics}_projects', project_metrics, METRICS_CACHE_TTL)

    subscription_metrics = cache.get(f'{cache_key_metrics}_subscriptions')
    if subscription_metrics is None:
        subscription_metrics = get_subscription_metrics()
        cache.set(f'{cache_key_metrics}_subscriptions', subscription_metrics, METRICS_CACHE_TTL)

    revenue_metrics = cache.get(f'{cache_key_metrics}_revenue')
    if revenue_metrics is None:
        revenue_metrics = get_revenue_metrics()
        cache.set(f'{cache_key_metrics}_revenue', revenue_metrics, METRICS_CACHE_TTL)

    service_overview = cache.get('root_service_overview')
    if service_overview is None:
        service_overview = get_service_overview()
        cache.set('root_service_overview', service_overview, METRICS_CACHE_TTL)

    alerts = cache.get('root_executive_alerts')
    if alerts is None:
        alerts = get_executive_alerts()
        cache.set('root_executive_alerts', alerts, METRICS_CACHE_TTL)

    platform_health = cache.get('root_platform_health')
    if platform_health is None:
        platform_health = get_platform_health()
        cache.set('root_platform_health', platform_health, HEALTH_CACHE_TTL)

    recent_activity = cache.get('root_recent_activity')
    if recent_activity is None:
        recent_activity = get_recent_activity(limit=12)
        cache.set('root_recent_activity', recent_activity, HEALTH_CACHE_TTL)

    charts = cache.get(cache_key_charts)
    if charts is None:
        charts = {
            'user_growth': get_user_growth_chart(chart_days),
            'project_activity': get_project_activity_chart(chart_days),
            'revenue': get_revenue_chart(chart_days),
            'subscriptions': get_subscription_chart(chart_days),
        }
        cache.set(cache_key_charts, charts, METRICS_CACHE_TTL)

    context = {
        'user_metrics': user_metrics,
        'customer_metrics': customer_metrics,
        'project_metrics': project_metrics,
        'subscription_metrics': subscription_metrics,
        'revenue_metrics': revenue_metrics,
        'service_overview': service_overview,
        'alerts': alerts,
        'recent_activity': recent_activity,
        'platform_health': platform_health,
        'charts': charts,
        'time_filter': time_filter,
        'page_title': 'Root Command Center',
        'page_subtitle': 'Executive overview of the OnWebApp platform.',
    }
    return render(request, 'root_dashboard/command_center.html', context)


@root_required
def health_check(request):
    """Detailed platform health check — JSON endpoint."""
    health = get_platform_health()
    all_ok = all(s['status'] == 'ok' for s in health.values())

    return JsonResponse({
        'status': 'healthy' if all_ok else 'degraded',
        'checks': health,
    })


# ---------------------------------------------------------------------------
# Operations Center (System Health, Infrastructure, Alerts)
# ---------------------------------------------------------------------------

@root_required
def operations_center(request):
    """
    Operations Center — System Health, Infrastructure, Alerts, Activity.
    Only accessible to superusers.
    Uses caching to avoid slow network checks on every load.
    """
    # Cache health + infrastructure for 60s (they involve network I/O)
    health_checks = cache.get('root_ops_health')
    if health_checks is None:
        health_checks = run_all_checks()
        cache.set('root_ops_health', health_checks, HEALTH_CACHE_TTL)

    overall_health = get_overall_status(health_checks)

    infrastructure = cache.get('root_ops_infra')
    if infrastructure is None:
        infrastructure = get_all_infrastructure_metrics()
        cache.set('root_ops_infra', infrastructure, HEALTH_CACHE_TTL)

    alerts = cache.get('root_ops_alerts')
    if alerts is None:
        alerts = get_all_alerts()
        cache.set('root_ops_alerts', alerts, METRICS_CACHE_TTL)

    alert_summary = get_alert_summary(alerts)

    activity = cache.get('root_ops_activity')
    if activity is None:
        activity = get_recent_activity(limit=15)
        cache.set('root_ops_activity', activity, HEALTH_CACHE_TTL)

    platform_health = cache.get('root_platform_health')
    if platform_health is None:
        platform_health = get_platform_health()
        cache.set('root_platform_health', platform_health, HEALTH_CACHE_TTL)

    context = {
        'health_checks': health_checks,
        'overall_health': overall_health,
        'infrastructure': infrastructure,
        'alerts': alerts,
        'alert_summary': alert_summary,
        'recent_activity': activity,
        'platform_health': platform_health,
        'page_title': 'Operations Center',
        'page_subtitle': 'System health, infrastructure, and alerts.',
    }
    return render(request, 'root_dashboard/operations_center.html', context)


@root_required
def health_api(request):
    """JSON health check endpoint for external monitoring."""
    health_checks = run_all_checks()
    overall = get_overall_status(health_checks)
    return JsonResponse({
        'status': overall,
        'checks': {
            c['label'].lower().replace(' ', '_'): {
                'status': c['status'],
                'detail': c['detail'],
            }
            for c in health_checks
        },
    })


@root_required
def infrastructure_api(request):
    """JSON infrastructure metrics endpoint."""
    metrics = get_all_infrastructure_metrics()
    return JsonResponse({
        'cpu': metrics['cpu']['value'],
        'memory': metrics['memory']['value'],
        'disk': metrics['disk']['value'],
        'celery_workers': metrics['celery'].get('workers'),
        'celery_active': metrics['celery'].get('active_tasks'),
    })


# ---------------------------------------------------------------------------
# Global Search API
# ---------------------------------------------------------------------------

@root_required
def search_api(request):
    """
    Global search endpoint — searches across Users, Customers, Projects,
    Branding, ERP, Payments. Returns JSON results.
    Only accessible to superusers.
    """
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': {}, 'total': 0, 'query': query})

    results = global_search(query)
    return JsonResponse(results)
