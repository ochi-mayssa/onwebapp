"""Digital Presence views — workspace for monitoring OnWebApp's online presence."""
from django.shortcuts import render
from django.http import JsonResponse

from .decorators import designer_or_superuser_required
from .services import (
    get_social_media_health,
    get_seo_health,
    get_keyword_visibility,
    get_content_performance,
    get_connection_status,
    get_social_platforms,
    get_social_posts,
    get_social_chart_data,
    get_social_alerts,
    get_seo_command_center,
    get_seo_health_breakdown,
    get_seo_issues_by_severity,
    get_seo_chart_data,
    get_keyword_monitoring,
    get_keyword_opportunities,
    get_keyword_chart_data,
    get_content_opportunities,
    get_unified_alerts,
    get_sync_status,
    get_overview_data,
)


@designer_or_superuser_required
def overview(request):
    """Digital Presence Overview — cross-section dashboard."""
    period = request.GET.get('period', '30d')

    overview_data = get_overview_data()
    social = get_social_media_health()
    seo = get_seo_health()
    keywords = get_keyword_visibility()
    content = get_content_performance()
    connections = get_connection_status()
    alerts = get_unified_alerts()
    sync_status = get_sync_status()

    context = {
        'page_title': 'Digital Presence',
        'page_subtitle': 'Monitor social media, SEO, keywords and content performance.',
        'overview': overview_data,
        'social': social,
        'seo': seo,
        'keywords': keywords,
        'content': content,
        'connections': connections,
        'alerts': alerts,
        'sync_status': sync_status,
        'period': period,
    }
    return render(request, 'digital_presence/overview.html', context)


@designer_or_superuser_required
def social_media(request):
    """Social Media monitoring page."""
    platforms = get_social_platforms()
    posts_data = get_social_posts(limit=20, sort='engagement')
    top_posts = get_social_posts(limit=10, sort='likes')
    alerts = get_social_alerts()
    sync_status = get_sync_status()

    total_posts = sum(p['metrics'].get('posts', 0) for p in platforms)
    total_engagement = sum(p['metrics'].get('total_engagement', 0) for p in platforms)
    connected_count = sum(1 for p in platforms if p['status'] == 'connected')

    context = {
        'page_title': 'Social Media',
        'page_subtitle': 'Monitor OnWebApp social media presence and engagement.',
        'platforms': platforms,
        'posts': posts_data.get('posts', []),
        'top_posts': top_posts.get('posts', []),
        'alerts': alerts,
        'total_posts': total_posts,
        'total_engagement': total_engagement,
        'connected_count': connected_count,
        'platform_count': len(platforms),
        'sync_status': sync_status,
    }
    return render(request, 'digital_presence/social_media.html', context)


@designer_or_superuser_required
def social_chart_data(request):
    """JSON API for Chart.js performance data."""
    metric = request.GET.get('metric', 'engagement')
    platform = request.GET.get('platform', 'all')
    period = request.GET.get('period', '30d')
    data = get_social_chart_data(metric=metric, platform=platform, period=period)
    return JsonResponse(data)


@designer_or_superuser_required
def seo(request):
    """SEO Command Center."""
    seo_data = get_seo_command_center()
    health_breakdown = get_seo_health_breakdown()
    issues = get_seo_issues_by_severity()
    sync_status = get_sync_status()

    context = {
        'page_title': 'SEO Command Center',
        'page_subtitle': 'Monitor search engine optimization health and performance.',
        'seo': seo_data,
        'health_breakdown': health_breakdown,
        'issues': issues,
        'sync_status': sync_status,
    }
    return render(request, 'digital_presence/seo.html', context)


@designer_or_superuser_required
def seo_chart_data(request):
    """JSON API for SEO trend chart data."""
    metric = request.GET.get('metric', 'health_score')
    period = request.GET.get('period', '30d')
    data = get_seo_chart_data(metric=metric, period=period)
    return JsonResponse(data)


@designer_or_superuser_required
def keywords(request):
    """Keywords monitoring dashboard."""
    kw_data = get_keyword_monitoring()
    opportunities = get_keyword_opportunities()
    sync_status = get_sync_status()

    context = {
        'page_title': 'Keywords',
        'page_subtitle': 'Track keyword rankings, visibility, and opportunities.',
        'keywords': kw_data,
        'opportunities': opportunities,
        'sync_status': sync_status,
    }
    return render(request, 'digital_presence/keywords.html', context)


@designer_or_superuser_required
def keyword_chart_data(request):
    """JSON API for keyword trend chart data."""
    keyword = request.GET.get('keyword', None)
    period = request.GET.get('period', '30d')
    data = get_keyword_chart_data(keyword=keyword, period=period)
    return JsonResponse(data)


@designer_or_superuser_required
def content(request):
    """Content Performance — pages, opportunities, SEO health."""
    content_data = get_content_performance()
    opportunities = get_content_opportunities()
    sync_status = get_sync_status()

    context = {
        'page_title': 'Content Performance',
        'page_subtitle': 'Analyze content performance and identify opportunities.',
        'content': content_data,
        'opportunities': opportunities,
        'sync_status': sync_status,
    }
    return render(request, 'digital_presence/content.html', context)


@designer_or_superuser_required
def reports(request):
    """Reports — aggregated Digital Presence reports."""
    social = get_social_media_health()
    seo_data = get_seo_health()
    seo_command = get_seo_command_center()
    keywords = get_keyword_visibility()
    keyword_mon = get_keyword_monitoring()
    content = get_content_performance()
    platforms = get_social_platforms()
    sync_status = get_sync_status()

    context = {
        'page_title': 'Reports',
        'page_subtitle': 'Digital Presence performance reports.',
        'social': social,
        'seo': seo_data,
        'seo_command': seo_command,
        'keywords': keywords,
        'keyword_mon': keyword_mon,
        'content': content,
        'platforms': platforms,
        'sync_status': sync_status,
    }
    return render(request, 'digital_presence/reports.html', context)


@designer_or_superuser_required
def api_overview(request):
    """JSON API for overview data."""
    social = get_social_media_health()
    seo = get_seo_health()
    keywords = get_keyword_visibility()
    content = get_content_performance()
    connections = get_connection_status()
    alerts = get_unified_alerts()
    sync_status = get_sync_status()

    return JsonResponse({
        'social': social,
        'seo': seo,
        'keywords': keywords,
        'content': content,
        'connections': connections,
        'alerts': alerts,
        'sync_status': sync_status,
    })
