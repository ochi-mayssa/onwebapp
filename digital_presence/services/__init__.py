"""Digital Presence services — queries existing models for real data."""
import os
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Avg, Count, Q, F


def _time_windows():
    now = timezone.now()
    return {
        'now': now,
        '7d': now - timedelta(days=7),
        '30d': now - timedelta(days=30),
        '90d': now - timedelta(days=90),
        '12m': now - timedelta(days=365),
    }


def _resolve_platform_status(provider):
    """Determine connection status from a SocialProvider instance."""
    if not provider.enabled:
        return 'not_connected'
    if provider.access_token:
        if provider.last_sync_at:
            age = timezone.now() - provider.last_sync_at
            if age > timedelta(hours=48):
                return 'sync_failed'
            return 'connected'
        return 'syncing'
    if provider.api_key:
        if provider.last_sync_at:
            return 'connected'
        return 'syncing'
    return 'not_connected'


def _check_env_credentials():
    """Check if social API env vars are set."""
    fb = bool(os.environ.get('FACEBOOK_PAGE_ACCESS_TOKEN') or os.environ.get('FACEBOOK_API_KEY'))
    ig = bool(os.environ.get('INSTAGRAM_ACCESS_TOKEN') or os.environ.get('INSTAGRAM_API_KEY'))
    li = bool(os.environ.get('LINKEDIN_API_KEY'))
    return {'facebook': fb, 'instagram': ig, 'linkedin': li}


def get_social_platforms():
    """
    Return platform status and real metrics for Facebook, Instagram, LinkedIn.
    Combines SocialProvider (connection), SocialPost (engagement), and SocialEvent (sentiment).
    """
    windows = _time_windows()
    env_creds = _check_env_credentials()

    platform_configs = [
        {
            'key': 'facebook',
            'name': 'Facebook',
            'icon': 'fa-brands fa-facebook-f',
            'color': '#1877F2',
            'provider_name': 'facebook',
        },
        {
            'key': 'instagram',
            'name': 'Instagram',
            'icon': 'fa-brands fa-instagram',
            'color': '#E4405F',
            'provider_name': 'instagram',
        },
        {
            'key': 'linkedin',
            'name': 'LinkedIn',
            'icon': 'fa-brands fa-linkedin-in',
            'color': '#0A66C2',
            'provider_name': 'linkedin',
        },
    ]

    platforms = []

    try:
        from social_proof.models import SocialProvider, SocialEvent
        from services.models import SocialPost, PlatformMetrics

        provider_map = {}
        for p in SocialProvider.objects.all():
            provider_map[p.name] = p

        for cfg in platform_configs:
            pk = cfg['key']
            provider = provider_map.get(cfg['provider_name'])
            env_ok = env_creds.get(pk, False)

            if provider:
                status = _resolve_platform_status(provider)
                last_sync = provider.last_sync_at
            elif env_ok:
                status = 'connected'
                last_sync = None
            else:
                status = 'not_connected'
                last_sync = None

            # Posts from SocialPost
            posts = SocialPost.objects.filter(platform=pk)

            total_posts = posts.count()
            total_likes = posts.aggregate(s=Sum('likes'))['s'] or 0
            total_comments = posts.aggregate(s=Sum('comments'))['s'] or 0
            total_shares = posts.aggregate(s=Sum('shares'))['s'] or 0
            total_views = posts.aggregate(s=Sum('views'))['s'] or 0
            total_engagement = posts.aggregate(s=Sum('engagement_score'))['s'] or 0

            # Growth: posts in last 30d vs prior 30d
            recent_30 = posts.filter(posted_at__gte=windows['30d']).count()
            prior_30 = posts.filter(posted_at__gte=windows['30d'] - timedelta(days=30), posted_at__lt=windows['30d']).count()
            if prior_30 > 0:
                growth_pct = round(((recent_30 - prior_30) / prior_30) * 100, 1)
            elif recent_30 > 0:
                growth_pct = 100.0
            else:
                growth_pct = None

            # Platform metrics
            try:
                pm = PlatformMetrics.objects.get(platform=pk)
                avg_engagement_rate = pm.avg_engagement_rate
            except PlatformMetrics.DoesNotExist:
                avg_engagement_rate = None

            # Events from social_proof
            if provider:
                events = SocialEvent.objects.filter(provider=provider)
                event_count = events.count()
                avg_sentiment = events.aggregate(avg=Avg('sentiment_score'))['avg']
                if avg_sentiment is not None:
                    avg_sentiment = round(float(avg_sentiment), 2)
            else:
                event_count = 0
                avg_sentiment = None

            # Engagement rate (likes+comments+shares) / total_posts * 100
            if total_posts > 0:
                eng_rate = round((total_engagement / total_posts), 1)
            else:
                eng_rate = None

            # Platform-specific metrics
            metrics = {
                'posts': total_posts,
                'total_engagement': total_engagement,
                'engagement_rate': eng_rate,
                'growth_pct': growth_pct,
                'event_count': event_count,
                'avg_sentiment': avg_sentiment,
            }

            if pk == 'facebook':
                metrics['likes'] = total_likes
                metrics['comments'] = total_comments
                metrics['shares'] = total_shares
                metrics['views'] = total_views
            elif pk == 'instagram':
                metrics['likes'] = total_likes
                metrics['comments'] = total_comments
                metrics['views'] = total_views
            elif pk == 'linkedin':
                metrics['likes'] = total_likes
                metrics['comments'] = total_comments
                metrics['shares'] = total_shares

            platforms.append({
                'key': pk,
                'name': cfg['name'],
                'icon': cfg['icon'],
                'color': cfg['color'],
                'status': status,
                'last_sync': last_sync,
                'metrics': metrics,
                'env_configured': env_ok,
                'provider_exists': provider is not None,
            })

    except (ImportError, Exception):
        for cfg in platform_configs:
            platforms.append({
                'key': cfg['key'],
                'name': cfg['name'],
                'icon': cfg['icon'],
                'color': cfg['color'],
                'status': 'unavailable',
                'last_sync': None,
                'metrics': {},
                'env_configured': False,
                'provider_exists': False,
            })

    return platforms


def get_social_posts(limit=20, platform=None, sort='engagement'):
    """Get recent social posts with engagement metrics."""
    result = {
        'available': False,
        'posts': [],
    }

    try:
        from services.models import SocialPost

        qs = SocialPost.objects.select_related('user').all()
        if platform:
            qs = qs.filter(platform=platform)

        sort_map = {
            'engagement': '-engagement_score',
            'likes': '-likes',
            'comments': '-comments',
            'shares': '-shares',
            'date': '-posted_at',
            'views': '-views',
        }
        order = sort_map.get(sort, '-engagement_score')
        posts = qs.order_by(order)[:limit]

        for p in posts:
            post_data = {
                'platform': p.platform,
                'post_url': p.post_url,
                'post_id': p.post_id,
                'caption': (p.caption or '')[:200],
                'posted_at': p.posted_at,
                'likes': p.likes,
                'comments': p.comments,
                'shares': p.shares,
                'views': p.views,
                'engagement_score': p.engagement_score,
                'classification': p.classification,
                'username': p.user.username if p.user else '',
                'profile_url': p.user.profile_url if p.user else '',
            }
            result['posts'].append(post_data)

        result['available'] = True

    except (ImportError, Exception):
        pass

    return result


def get_social_chart_data(metric='engagement', platform=None, period='30d'):
    """Get time-series data for Chart.js visualization."""
    windows = _time_windows()
    period_days = {'7d': 7, '30d': 30, '90d': 90, '12m': 365}.get(period, 30)
    start = windows['now'] - timedelta(days=period_days)

    result = {
        'labels': [],
        'datasets': [],
    }

    try:
        from services.models import SocialPost
        from django.db.models.functions import TruncDate

        qs = SocialPost.objects.filter(posted_at__gte=start)
        if platform and platform != 'all':
            qs = qs.filter(platform=platform)

        platforms_to_chart = ['facebook', 'instagram', 'linkedin'] if not platform or platform == 'all' else [platform]
        colors = {'facebook': '#1877F2', 'instagram': '#E4405F', 'linkedin': '#0A66C2'}

        # Build date labels
        if period_days <= 30:
            delta = timedelta(days=1)
            fmt = '%b %d'
        elif period_days <= 90:
            delta = timedelta(days=7)
            fmt = '%b %d'
        else:
            delta = timedelta(days=30)
            fmt = '%b %Y'

        labels = []
        current = start
        while current <= windows['now']:
            labels.append(current.strftime(fmt))
            current += delta
        result['labels'] = labels

        metric_field_map = {
            'followers': 'likes',
            'reach': 'views',
            'impressions': 'views',
            'engagement': 'engagement_score',
            'engagement_rate': 'engagement_score',
            'likes': 'likes',
            'comments': 'comments',
            'shares': 'shares',
        }
        field = metric_field_map.get(metric, 'engagement_score')

        for pk in platforms_to_chart:
            platform_posts = qs.filter(platform=pk)
            data_points = []
            current = start
            while current <= windows['now']:
                next_point = current + delta
                count = platform_posts.filter(
                    posted_at__gte=current, posted_at__lt=next_point
                ).aggregate(s=Sum(field))['s'] or 0
                data_points.append(count)
                current = next_point

            result['datasets'].append({
                'label': pk.capitalize(),
                'data': data_points,
                'borderColor': colors.get(pk, '#52525b'),
                'backgroundColor': colors.get(pk, '#52525b') + '33',
            })

    except (ImportError, Exception):
        pass

    return result


def get_social_alerts():
    """Generate alerts from real data patterns."""
    alerts = []

    try:
        from social_proof.models import SocialProvider, SocialEvent
        from services.models import SocialPost, PlatformMetrics
        from django.db.models import Sum

        # 1. Check for expired/failed connections
        for provider in SocialProvider.objects.filter(enabled=True):
            if provider.last_sync_at:
                age = timezone.now() - provider.last_sync_at
                if age > timedelta(hours=48):
                    alerts.append({
                        'severity': 'critical',
                        'title': f'{provider.get_name_display()} sync failed',
                        'message': f'Last successful sync was {provider.last_sync_at.strftime("%b %d, %H:%M")}. Connection may need re-authentication.',
                        'category': 'connection',
                        'platform': provider.name,
                    })
                elif age > timedelta(hours=24):
                    alerts.append({
                        'severity': 'warning',
                        'title': f'{provider.get_name_display()} sync delayed',
                        'message': f'Last sync was {provider.last_sync_at.strftime("%b %d, %H:%M")}.',
                        'category': 'connection',
                        'platform': provider.name,
                    })

        # 2. Check env vars for unconfigured platforms
        env_creds = _check_env_credentials()
        for pk, configured in env_creds.items():
            if not configured:
                provider_names = {'facebook': 'Facebook', 'instagram': 'Instagram', 'linkedin': 'LinkedIn'}
                exists = SocialProvider.objects.filter(name=pk).exists()
                if not exists:
                    alerts.append({
                        'severity': 'info',
                        'title': f'{provider_names[pk]} not configured',
                        'message': f'Set environment variables to enable {provider_names[pk]} integration.',
                        'category': 'connection',
                        'platform': pk,
                    })

        # 3. Engagement drop detection (7d vs prior 7d)
        now = timezone.now()
        for pk in ['facebook', 'instagram', 'linkedin']:
            posts = SocialPost.objects.filter(platform=pk)
            recent = posts.filter(posted_at__gte=now - timedelta(days=7)).aggregate(s=Sum('engagement_score'))['s'] or 0
            prior = posts.filter(
                posted_at__gte=now - timedelta(days=14), posted_at__lt=now - timedelta(days=7)
            ).aggregate(s=Sum('engagement_score'))['s'] or 0

            if prior > 0 and recent < prior * 0.5:
                alerts.append({
                    'severity': 'warning',
                    'title': f'{pk.capitalize()} engagement dropped',
                    'message': f'Engagement fell {round((1 - recent/prior) * 100)}% compared to previous week.',
                    'category': 'engagement',
                    'platform': pk,
                })

            # Viral post detection
            viral = posts.filter(classification='viral', posted_at__gte=now - timedelta(days=7))
            for v in viral[:2]:
                alerts.append({
                    'severity': 'info',
                    'title': f'Viral post on {pk.capitalize()}',
                    'message': f'Post by {v.user.username if v.user else "unknown"} got {v.engagement_score} engagements.',
                    'category': 'success',
                    'platform': pk,
                })

        # 4. Negative sentiment spike
        events_24h = SocialEvent.objects.filter(created_at__gte=now - timedelta(hours=24))
        neg_count = events_24h.filter(sentiment_score__lt=-0.3).count()
        total_24h = events_24h.count()
        if total_24h > 0 and neg_count / total_24h > 0.3:
            alerts.append({
                'severity': 'warning',
                'title': 'Negative sentiment spike',
                'message': f'{neg_count} of {total_24h} events in last 24h have negative sentiment.',
                'category': 'sentiment',
                'platform': 'all',
            })

    except (ImportError, Exception):
        pass

    return alerts


def get_social_media_health():
    """
    Real social media health from social_proof and services apps.
    Returns provider status, event counts, sentiment.
    """
    result = {
        'available': False,
        'providers_connected': 0,
        'providers_total': 0,
        'total_events': 0,
        'positive_events': 0,
        'negative_events': 0,
        'avg_sentiment': None,
        'recent_events': [],
        'providers': [],
    }

    try:
        from social_proof.models import SocialProvider, SocialEvent
        providers = SocialProvider.objects.all()
        result['providers_total'] = providers.count()
        result['providers_connected'] = providers.filter(enabled=True).count()
        result['available'] = True

        for p in providers:
            event_count = SocialEvent.objects.filter(provider=p).count()
            result['providers'].append({
                'name': p.get_name_display(),
                'enabled': p.enabled,
                'events': event_count,
                'last_sync': p.last_sync_at,
            })

        events = SocialEvent.objects.all()
        result['total_events'] = events.count()
        result['positive_events'] = events.filter(sentiment_score__gt=0.3).count()
        result['negative_events'] = events.filter(sentiment_score__lt=-0.3).count()

        from django.db.models import Avg
        avg = events.aggregate(avg=Avg('sentiment_score'))['avg']
        if avg is not None:
            result['avg_sentiment'] = round(float(avg), 2)

        recent = events.order_by('-created_at')[:5]
        for e in recent:
            result['recent_events'].append({
                'author': getattr(e, 'author_name', 'Unknown'),
                'text': getattr(e, 'text', '')[:100],
                'sentiment': getattr(e, 'sentiment_score', 0),
                'provider': str(e.provider),
                'created_at': e.created_at,
            })

    except (ImportError, Exception):
        pass

    return result


def get_seo_health():
    """Real SEO health from seo_analyzer app."""
    result = {
        'available': False,
        'total_tasks': 0,
        'completed_tasks': 0,
        'latest_health_score': None,
        'latest_visibility_score': None,
        'latest_technical_score': None,
        'latest_content_score': None,
        'issues_count': 0,
        'snapshots_count': 0,
        'recent_tasks': [],
    }

    try:
        from seo_analyzer.models import SEOTask, SEOResult, SEOMonitoringSnapshot, SEOIssue
        tasks = SEOTask.objects.all()
        result['total_tasks'] = tasks.count()
        result['completed_tasks'] = tasks.filter(status='completed').count()
        result['available'] = True

        latest_result = SEOResult.objects.order_by('-created_at').first()
        if latest_result:
            result['latest_health_score'] = getattr(latest_result, 'health_score', None)
            result['latest_visibility_score'] = getattr(latest_result, 'visibility_score', None)
            result['latest_technical_score'] = getattr(latest_result, 'technical_score', None)
            result['latest_content_score'] = getattr(latest_result, 'content_score', None)

        result['issues_count'] = SEOIssue.objects.count()
        result['snapshots_count'] = SEOMonitoringSnapshot.objects.count()

        recent = tasks.order_by('-created_at')[:5]
        for t in recent:
            result['recent_tasks'].append({
                'url': getattr(t, 'url', ''),
                'status': getattr(t, 'status', ''),
                'created_at': t.created_at,
            })

    except (ImportError, Exception):
        pass

    return result


def get_keyword_visibility():
    """Real keyword data from seo_analyzer URL intelligence."""
    result = {
        'available': False,
        'total_analyses': 0,
        'avg_keyword_score': None,
        'keywords_found': 0,
        'recent_analyses': [],
    }

    try:
        from seo_analyzer.models import URLIntelligenceResult, URLIntelligenceTask
        tasks = URLIntelligenceTask.objects.all()
        result['total_analyses'] = tasks.count()
        result['available'] = True

        from django.db.models import Avg
        avg = URLIntelligenceResult.objects.aggregate(
            avg=Avg('keyword_relevance_score')
        )['avg']
        if avg is not None:
            result['avg_keyword_score'] = round(float(avg), 1)

        matched = URLIntelligenceResult.objects.filter(keyword_match_status='yes').count()
        partial = URLIntelligenceResult.objects.filter(keyword_match_status='partial').count()
        result['keywords_found'] = matched + partial

        recent = tasks.order_by('-created_at')[:5]
        for t in recent:
            result['recent_analyses'].append({
                'url': getattr(t, 'url', ''),
                'keyword': getattr(t, 'target_keyword', ''),
                'created_at': t.created_at,
            })

    except (ImportError, Exception):
        pass

    return result


def get_content_performance():
    """Real content performance from seo_analyzer monitoring snapshots."""
    result = {
        'available': False,
        'total_snapshots': 0,
        'latest_content_score': None,
        'pages_audited': 0,
        'missing_h1': 0,
        'missing_meta': 0,
        'missing_alt': 0,
        'total_words': 0,
    }

    try:
        from seo_analyzer.models import SEOMonitoringSnapshot, SEOPageAudit
        result['total_snapshots'] = SEOMonitoringSnapshot.objects.count()
        result['available'] = True

        latest = SEOMonitoringSnapshot.objects.order_by('-created_at').first()
        if latest:
            result['latest_content_score'] = getattr(latest, 'content_score', None)

        pages = SEOPageAudit.objects.all()
        result['pages_audited'] = pages.count()
        result['missing_h1'] = pages.filter(h1_count=0).count()
        result['missing_meta'] = pages.filter(meta_description='').count()
        result['missing_alt'] = pages.filter(images_missing_alt__gt=0).count()

        from django.db.models import Sum
        total_words = pages.aggregate(total=Sum('word_count'))['total']
        result['total_words'] = total_words or 0

    except (ImportError, Exception):
        pass

    return result


def get_connection_status():
    """Check connectivity status of external services."""
    status = {
        'social_proof': False,
        'seo_analyzer': False,
        'services': False,
    }

    try:
        from social_proof.models import SocialProvider
        status['social_proof'] = SocialProvider.objects.filter(enabled=True).exists()
    except (ImportError, Exception):
        pass

    try:
        from seo_analyzer.models import SEOTask
        status['seo_analyzer'] = True
    except (ImportError, Exception):
        pass

    try:
        from services.models import SocialPost
        status['services'] = True
    except (ImportError, Exception):
        pass

    return status


# ---------------------------------------------------------------------------
# SEO Command Center services
# ---------------------------------------------------------------------------

def get_seo_command_center():
    """
    Full SEO command center data from seo_analyzer models.
    Combines SEOResult, SEOMonitoringSnapshot, SEOPageAudit, SEOIssue.
    """
    result = {
        'available': False,
        'health_score': None,
        'technical_score': None,
        'on_page_score': None,
        'performance_score': None,
        'discovery_score': None,
        'ai_opportunity_score': None,
        'pages_crawled': 0,
        'total_issues': 0,
        'critical_issues': 0,
        'high_issues': 0,
        'medium_issues': 0,
        'low_issues': 0,
        'broken_links': 0,
        'missing_titles': 0,
        'missing_descriptions': 0,
        'missing_alt_text': 0,
        'noindex_pages': 0,
        'https_pages': 0,
        'total_pages': 0,
        'indexed_pages': 0,
        'internal_links': 0,
        'external_links': 0,
        'sitemap_entries': 0,
        'recent_tasks': [],
        'latest_domain': None,
    }

    try:
        from seo_analyzer.models import (
            SEOTask, SEOResult, SEOPageAudit, SEOIssue,
            SEOMonitoringSnapshot,
        )

        # Latest completed task with result
        latest_task = (
            SEOTask.objects
            .filter(status='completed')
            .select_related('result')
            .order_by('-created_at')
            .first()
        )

        if latest_task and hasattr(latest_task, 'result'):
            r = latest_task.result
            result['available'] = True
            result['health_score'] = float(r.health_score) if r.health_score else None
            result['technical_score'] = float(r.technical_score) if r.technical_score else None
            result['on_page_score'] = float(r.on_page_score) if r.on_page_score else None
            result['performance_score'] = float(r.performance_score) if r.performance_score else None
            result['discovery_score'] = float(r.discovery_score) if r.discovery_score else None
            result['ai_opportunity_score'] = float(r.ai_opportunity_score) if r.ai_opportunity_score else None
            result['pages_crawled'] = r.pages_crawled
            result['total_issues'] = r.total_issues
            result['critical_issues'] = r.critical_issues
            result['high_issues'] = r.high_issues
            result['medium_issues'] = r.medium_issues
            result['low_issues'] = r.low_issues
            result['broken_links'] = r.broken_internal_links_count
            result['internal_links'] = r.internal_links_count
            result['sitemap_entries'] = r.sitemap_entries_found
            result['latest_domain'] = latest_task.domain

            # Page audit aggregates
            pages = SEOPageAudit.objects.filter(task=latest_task)
            result['missing_titles'] = pages.filter(title_tag='').count() + pages.filter(title_tag__isnull=True).count()
            result['missing_descriptions'] = pages.filter(meta_description='').count() + pages.filter(meta_description__isnull=True).count()
            result['missing_alt_text'] = pages.filter(images_missing_alt__gt=0).count()
            result['noindex_pages'] = pages.filter(is_noindex=True).count()
            result['https_pages'] = pages.filter(has_canonical=True).count()
            result['total_pages'] = pages.count()
            result['external_links'] = SEOIssue.objects.filter(
                task=latest_task, category='discovery'
            ).count()
        else:
            # Fallback: try SEOMonitoringSnapshot
            snapshot = SEOMonitoringSnapshot.objects.order_by('-created_at').first()
            if snapshot:
                result['available'] = True
                result['health_score'] = float(snapshot.health_score) if snapshot.health_score else None
                result['technical_score'] = float(snapshot.technical_score) if snapshot.technical_score else None
                result['performance_score'] = float(snapshot.performance_score) if snapshot.performance_score else None
                result['broken_links'] = snapshot.broken_links or 0
                result['indexed_pages'] = snapshot.indexed_pages or 0
                result['latest_domain'] = snapshot.domain

        # Recent tasks
        for t in SEOTask.objects.select_related('result').order_by('-created_at')[:8]:
            task_data = {
                'url': t.url,
                'domain': t.domain,
                'status': t.status,
                'created_at': t.created_at,
                'pages_crawled': 0,
                'issues': 0,
                'health_score': None,
            }
            if hasattr(t, 'result'):
                task_data['pages_crawled'] = t.result.pages_crawled
                task_data['issues'] = t.result.total_issues
                task_data['health_score'] = float(t.result.health_score) if t.result.health_score else None
            result['recent_tasks'].append(task_data)

    except (ImportError, Exception):
        pass

    return result


def get_seo_health_breakdown():
    """
    Detailed SEO health score breakdown from the latest SEOResult.
    Returns individual category scores for the radar/breakdown chart.
    """
    result = {
        'available': False,
        'categories': [],
    }

    try:
        from seo_analyzer.models import SEOTask

        latest_task = (
            SEOTask.objects
            .filter(status='completed')
            .select_related('result')
            .order_by('-created_at')
            .first()
        )

        if latest_task and hasattr(latest_task, 'result'):
            r = latest_task.result
            result['available'] = True

            score_map = [
                ('Technical SEO', float(r.technical_score) if r.technical_score else None),
                ('On-Page SEO', float(r.on_page_score) if r.on_page_score else None),
                ('Performance', float(r.performance_score) if r.performance_score else None),
                ('Discovery', float(r.discovery_score) if r.discovery_score else None),
                ('AI Opportunity', float(r.ai_opportunity_score) if r.ai_opportunity_score else None),
            ]

            for name, score in score_map:
                if score is not None:
                    result['categories'].append({
                        'name': name,
                        'score': score,
                        'status': 'good' if score >= 70 else 'needs_work' if score >= 40 else 'poor',
                    })
                else:
                    result['categories'].append({
                        'name': name,
                        'score': None,
                        'status': 'unavailable',
                    })

    except (ImportError, Exception):
        pass

    return result


def get_seo_issues_by_severity():
    """
    Prioritized SEO issues from SEOIssue and URLIntelligenceIssue.
    Categorized into critical, warning, and opportunities.
    """
    result = {
        'available': False,
        'critical': [],
        'warning': [],
        'opportunities': [],
    }

    try:
        from seo_analyzer.models import SEOIssue, URLIntelligenceIssue

        # Critical: broken pages, 404s, indexing problems
        critical_issues = SEOIssue.objects.select_related('page_audit').filter(severity='critical')[:10]
        for issue in critical_issues:
            page_url = ''
            if issue.page_audit:
                page_url = issue.page_audit.url or issue.page_audit.final_url or ''
            result['critical'].append({
                'name': issue.name,
                'severity': issue.severity,
                'category': issue.category,
                'description': issue.description,
                'url': page_url,
                'recommendation': issue.recommended_fix or '',
                'status': issue.status,
            })

        # Also check URLIntelligenceIssue for critical
        ui_critical = URLIntelligenceIssue.objects.filter(severity='critical')[:5]
        for issue in ui_critical:
            task_url = issue.task.url if issue.task else ''
            result['critical'].append({
                'name': issue.name,
                'severity': issue.severity,
                'category': issue.category,
                'description': issue.description,
                'url': task_url,
                'recommendation': issue.recommended_fix or '',
                'status': issue.status,
            })

        # Warning: missing titles, descriptions, alt text, performance
        warning_issues = SEOIssue.objects.select_related('page_audit').filter(severity__in=['high', 'medium'])[:15]
        for issue in warning_issues:
            page_url = ''
            if issue.page_audit:
                page_url = issue.page_audit.url or issue.page_audit.final_url or ''
            result['warning'].append({
                'name': issue.name,
                'severity': issue.severity,
                'category': issue.category,
                'description': issue.description,
                'url': page_url,
                'recommendation': issue.recommended_fix or '',
                'status': issue.status,
            })

        # URL Intelligence warnings
        ui_warning = URLIntelligenceIssue.objects.filter(severity__in=['high', 'medium'])[:5]
        for issue in ui_warning:
            task_url = issue.task.url if issue.task else ''
            result['warning'].append({
                'name': issue.name,
                'severity': issue.severity,
                'category': issue.category,
                'description': issue.description,
                'url': task_url,
                'recommendation': issue.recommended_fix or '',
                'status': issue.status,
            })

        # Opportunities: low severity + informational
        low_issues = SEOIssue.objects.select_related('page_audit').filter(severity='low')[:10]
        for issue in low_issues:
            page_url = ''
            if issue.page_audit:
                page_url = issue.page_audit.url or issue.page_audit.final_url or ''
            result['opportunities'].append({
                'name': issue.name,
                'severity': issue.severity,
                'category': issue.category,
                'description': issue.description,
                'url': page_url,
                'recommendation': issue.recommended_fix or '',
                'status': issue.status,
            })

        ui_info = URLIntelligenceIssue.objects.filter(severity='informational')[:5]
        for issue in ui_info:
            task_url = issue.task.url if issue.task else ''
            result['opportunities'].append({
                'name': issue.name,
                'severity': issue.severity,
                'category': issue.category,
                'description': issue.description,
                'url': task_url,
                'recommendation': issue.recommended_fix or '',
                'status': issue.status,
            })

        result['available'] = True

    except (ImportError, Exception):
        pass

    return result


def get_seo_chart_data(metric='health_score', period='30d'):
    """
    Time-series SEO data for Chart.js from SEOMonitoringSnapshot and SEOHistoricalReport.
    """
    windows = _time_windows()
    period_days = {'7d': 7, '30d': 30, '90d': 90, '12m': 365}.get(period, 30)
    start = windows['now'] - timedelta(days=period_days)

    result = {
        'labels': [],
        'datasets': [],
    }

    try:
        from seo_analyzer.models import SEOMonitoringSnapshot, SEOHistoricalReport

        metric_fields = {
            'health_score': 'health_score',
            'technical_score': 'technical_score',
            'performance_score': 'performance_score',
            'content_score': 'content_score',
            'visibility_score': 'visibility_score',
        }
        field = metric_fields.get(metric, 'health_score')

        # Build date labels
        if period_days <= 7:
            delta = timedelta(days=1)
            fmt = '%b %d'
        elif period_days <= 90:
            delta = timedelta(days=7)
            fmt = '%b %d'
        else:
            delta = timedelta(days=30)
            fmt = '%b %Y'

        labels = []
        current = start
        while current <= windows['now']:
            labels.append(current.strftime(fmt))
            current += delta
        result['labels'] = labels

        # Try SEOMonitoringSnapshot first
        snapshots = SEOMonitoringSnapshot.objects.filter(
            created_at__gte=start, analysis_type='website'
        ).order_by('created_at')

        if snapshots.exists():
            data_points = []
            current = start
            while current <= windows['now']:
                next_point = current + delta
                snap = snapshots.filter(
                    created_at__gte=current, created_at__lt=next_point
                ).order_by('-created_at').first()
                val = float(getattr(snap, field, 0)) if snap and getattr(snap, field, None) is not None else None
                data_points.append(val)
                current = next_point

            result['datasets'].append({
                'label': metric.replace('_', ' ').title(),
                'data': data_points,
                'borderColor': '#818cf8',
                'backgroundColor': '#818cf833',
            })
        else:
            # Fallback to SEOHistoricalReport
            reports = SEOHistoricalReport.objects.filter(
                created_at__gte=start
            ).order_by('created_at')

            if reports.exists():
                data_points = []
                current = start
                while current <= windows['now']:
                    next_point = current + delta
                    rep = reports.filter(
                        created_at__gte=current, created_at__lt=next_point
                    ).order_by('-created_at').first()
                    val = float(getattr(rep, field, 0)) if rep and getattr(rep, field, None) is not None else None
                    data_points.append(val)
                    current = next_point

                result['datasets'].append({
                    'label': metric.replace('_', ' ').title(),
                    'data': data_points,
                    'borderColor': '#818cf8',
                    'backgroundColor': '#818cf833',
                })

    except (ImportError, Exception):
        pass

    return result


# ---------------------------------------------------------------------------
# Keywords services
# ---------------------------------------------------------------------------

def get_keyword_monitoring():
    """
    Keyword monitoring data from URLIntelligenceTask and URLIntelligenceResult.
    Returns keyword list with position, relevance, match status.
    """
    result = {
        'available': False,
        'total_keywords': 0,
        'matched_count': 0,
        'partial_count': 0,
        'avg_relevance': None,
        'keywords': [],
    }

    try:
        from seo_analyzer.models import URLIntelligenceTask, URLIntelligenceResult

        tasks = URLIntelligenceTask.objects.exclude(
            target_keyword=''
        ).select_related('result').order_by('-created_at')

        total = tasks.count()
        if total == 0:
            result['available'] = True
            return result

        result['available'] = True
        result['total_keywords'] = total

        seen_keywords = {}
        for task in tasks:
            kw = task.target_keyword.strip()
            if not kw or kw in seen_keywords:
                continue

            kw_data = {
                'keyword': kw,
                'url': task.url,
                'domain': task.domain,
                'status': task.status,
                'created_at': task.created_at,
                'relevance_score': None,
                'match_status': task.target_keyword and 'not_provided',
                'health_score': None,
                'technical_score': None,
                'seo_friendliness': None,
                'issues': 0,
            }

            if hasattr(task, 'result') and task.result:
                r = task.result
                kw_data['relevance_score'] = float(r.keyword_relevance_score) if r.keyword_relevance_score else None
                kw_data['match_status'] = r.keyword_match_status
                kw_data['health_score'] = float(r.health_score) if r.health_score else None
                kw_data['technical_score'] = float(r.technical_score) if r.technical_score else None
                kw_data['seo_friendliness'] = float(r.seo_friendliness_score) if r.seo_friendliness_score else None
                kw_data['issues'] = r.total_issues

                if r.keyword_match_status == 'yes':
                    result['matched_count'] += 1
                elif r.keyword_match_status == 'partial':
                    result['partial_count'] += 1

            seen_keywords[kw] = True
            result['keywords'].append(kw_data)

        # Average relevance
        relevance_scores = [k['relevance_score'] for k in result['keywords'] if k['relevance_score'] is not None]
        if relevance_scores:
            result['avg_relevance'] = round(sum(relevance_scores) / len(relevance_scores), 1)

    except (ImportError, Exception):
        pass

    return result


def get_keyword_opportunities():
    """
    Identify keyword opportunities from URL Intelligence data.
    Looks for high impressions + low CTR, declining rankings, etc.
    """
    result = {
        'available': False,
        'opportunities': [],
    }

    try:
        from seo_analyzer.models import URLIntelligenceResult, URLIntelligenceTask

        results = URLIntelligenceResult.objects.select_related('task').filter(
            task__target_keyword__isnull=False
        ).exclude(task__target_keyword='')

        if not results.exists():
            result['available'] = True
            return result

        result['available'] = True

        for r in results:
            keyword = r.task.target_keyword if r.task else ''
            if not keyword:
                continue

            # High impressions + low CTR opportunity
            if r.keyword_match_status == 'partial' and r.keyword_relevance_score and r.keyword_relevance_score < 70:
                result['opportunities'].append({
                    'keyword': keyword,
                    'url': r.task.url if r.task else '',
                    'type': 'keyword_mismatch',
                    'title': f'Keyword partially matches for "{keyword}"',
                    'description': f'Keyword relevance is {float(r.keyword_relevance_score):.0f}%. Content may need optimization for this keyword.',
                    'why_it_matters': 'Partial keyword match means your page is ranking but not fully optimized for the target keyword.',
                    'suggested_action': 'Review page content, title tag, and headings to better include the target keyword naturally.',
                    'relevance_score': float(r.keyword_relevance_score),
                })

            # Low SEO friendliness
            if r.seo_friendliness_score and r.seo_friendliness_score < 50:
                result['opportunities'].append({
                    'keyword': keyword,
                    'url': r.task.url if r.task else '',
                    'type': 'low_friendliness',
                    'title': f'Low SEO friendliness for "{keyword}"',
                    'description': f'URL SEO friendliness score is {float(r.seo_friendliness_score):.0f}%. Significant improvements possible.',
                    'why_it_matters': 'Low SEO friendliness means the page has structural or technical issues hurting search performance.',
                    'suggested_action': 'Fix technical issues, improve URL structure, and ensure proper canonical and indexability settings.',
                    'relevance_score': float(r.keyword_relevance_score) if r.keyword_relevance_score else 0,
                })

            # Issues found
            if r.total_issues > 0:
                result['opportunities'].append({
                    'keyword': keyword,
                    'url': r.task.url if r.task else '',
                    'type': 'issues_found',
                    'title': f'{r.total_issues} issues found for "{keyword}"',
                    'description': f'Page has {r.total_issues} SEO issues ({r.critical_issues} critical, {r.high_issues} high) that may affect rankings.',
                    'why_it_matters': 'SEO issues directly impact search engine crawling, indexing, and ranking of your content.',
                    'suggested_action': 'Review and fix critical and high-severity issues first for maximum impact.',
                    'relevance_score': float(r.keyword_relevance_score) if r.keyword_relevance_score else 0,
                })

            # No keyword match
            if r.keyword_match_status == 'no':
                result['opportunities'].append({
                    'keyword': keyword,
                    'url': r.task.url if r.task else '',
                    'type': 'no_match',
                    'title': f'No keyword match for "{keyword}"',
                    'description': f'Target keyword not found in page content. Page may not be ranking for this term.',
                    'why_it_matters': 'Without the keyword present in content, search engines cannot associate the page with that search query.',
                    'suggested_action': 'Add the target keyword to the page title, headings, and body content in a natural way.',
                    'relevance_score': 0,
                })

    except (ImportError, Exception):
        pass

    return result


def get_keyword_chart_data(keyword=None, period='30d'):
    """
    Keyword trend data for Chart.js.
    Uses SEOHistoricalReport scores as a proxy for keyword performance over time.
    """
    windows = _time_windows()
    period_days = {'7d': 7, '30d': 30, '90d': 90}.get(period, 30)
    start = windows['now'] - timedelta(days=period_days)

    result = {
        'labels': [],
        'datasets': [],
    }

    try:
        from seo_analyzer.models import SEOMonitoringSnapshot, SEOHistoricalReport

        # Build date labels
        if period_days <= 7:
            delta = timedelta(days=1)
            fmt = '%b %d'
        else:
            delta = timedelta(days=7)
            fmt = '%b %d'

        labels = []
        current = start
        while current <= windows['now']:
            labels.append(current.strftime(fmt))
            current += delta
        result['labels'] = labels

        # Use health_score as proxy for keyword performance trend
        snapshots = SEOMonitoringSnapshot.objects.filter(
            created_at__gte=start, analysis_type='website'
        ).order_by('created_at')

        if snapshots.exists():
            data_points = []
            current = start
            while current <= windows['now']:
                next_point = current + delta
                snap = snapshots.filter(
                    created_at__gte=current, created_at__lt=next_point
                ).order_by('-created_at').first()
                val = float(snap.health_score) if snap and snap.health_score is not None else None
                data_points.append(val)
                current = next_point

            result['datasets'].append({
                'label': 'SEO Health Score',
                'data': data_points,
                'borderColor': '#818cf8',
                'backgroundColor': '#818cf833',
            })

            # Add keyword relevance trend if available
            kw_data = []
            current = start
            while current <= windows['now']:
                next_point = current + delta
                snap = snapshots.filter(
                    created_at__gte=current, created_at__lt=next_point
                ).order_by('-created_at').first()
                val = float(snap.content_score) if snap and snap.content_score is not None else None
                kw_data.append(val)
                current = next_point

            result['datasets'].append({
                'label': 'Content Score',
                'data': kw_data,
                'borderColor': '#22c55e',
                'backgroundColor': '#22c55e33',
            })
        else:
            # Fallback to SEOHistoricalReport
            reports = SEOHistoricalReport.objects.filter(
                created_at__gte=start
            ).order_by('created_at')

            if reports.exists():
                data_points = []
                current = start
                while current <= windows['now']:
                    next_point = current + delta
                    rep = reports.filter(
                        created_at__gte=current, created_at__lt=next_point
                    ).order_by('-created_at').first()
                    val = float(rep.health_score) if rep and rep.health_score is not None else None
                    data_points.append(val)
                    current = next_point

                result['datasets'].append({
                    'label': 'Health Score',
                    'data': data_points,
                    'borderColor': '#818cf8',
                    'backgroundColor': '#818cf833',
                })

    except (ImportError, Exception):
        pass

    return result


# ---------------------------------------------------------------------------
# Content Opportunities & Overview services
# ---------------------------------------------------------------------------

def get_content_opportunities():
    """
    Identify content opportunities from real SEO data.
    Combines SEOPageAudit, SEOIssue, URLIntelligenceResult, SocialPost.
    """
    result = {
        'available': False,
        'opportunities': [],
    }

    try:
        from seo_analyzer.models import SEOPageAudit, SEOIssue, URLIntelligenceResult, URLIntelligenceTask
        from services.models import SocialPost

        pages = SEOPageAudit.objects.select_related('task').all()
        if not pages.exists():
            result['available'] = True
            return result

        result['available'] = True

        missing_title = pages.filter(title_tag='')[:5]
        for p in missing_title:
            result['opportunities'].append({
                'page': p.url or p.final_url or '',
                'type': 'missing_seo',
                'reason': 'Missing title tag',
                'data': 'Page has no title tag defined.',
                'suggested_action': 'Add a descriptive title tag (50-60 characters) that includes the target keyword.',
                'priority': 'high',
            })

        missing_meta = pages.filter(meta_description='')[:5]
        for p in missing_meta:
            result['opportunities'].append({
                'page': p.url or p.final_url or '',
                'type': 'missing_seo',
                'reason': 'Missing meta description',
                'data': 'Page has no meta description.',
                'suggested_action': 'Add a compelling meta description (150-160 characters) that summarizes the page content.',
                'priority': 'high',
            })

        missing_h1 = pages.filter(h1_count=0)[:5]
        for p in missing_h1:
            result['opportunities'].append({
                'page': p.url or p.final_url or '',
                'type': 'missing_seo',
                'reason': 'Missing H1 heading',
                'data': 'Page has no H1 heading tag.',
                'suggested_action': 'Add exactly one H1 heading that clearly describes the page content.',
                'priority': 'medium',
            })

        missing_alt = pages.filter(images_missing_alt__gt=0)[:5]
        for p in missing_alt:
            result['opportunities'].append({
                'page': p.url or p.final_url or '',
                'type': 'missing_seo',
                'reason': f'{p.images_missing_alt} images missing alt text',
                'data': f'{p.images_count} images total, {p.images_missing_alt} without alt text.',
                'suggested_action': 'Add descriptive alt text to all images for accessibility and SEO.',
                'priority': 'medium',
            })

        broken = pages.filter(broken_internal_links_count__gt=0)[:5]
        for p in broken:
            result['opportunities'].append({
                'page': p.url or p.final_url or '',
                'type': 'broken_links',
                'reason': f'{p.broken_internal_links_count} broken internal links',
                'data': 'Page contains links that return 404 or other error responses.',
                'suggested_action': 'Fix or remove broken links to improve user experience and crawlability.',
                'priority': 'high',
            })

        high_issue_results = URLIntelligenceResult.objects.select_related('task').filter(
            total_issues__gt=0
        ).order_by('-total_issues')[:5]
        for r in high_issue_results:
            result['opportunities'].append({
                'page': r.task.url if r.task else r.original_url,
                'type': 'seo_issues',
                'reason': f'{r.total_issues} SEO issues ({r.critical_issues} critical)',
                'data': f'Health score: {float(r.health_score):.0f}%.' if r.health_score else 'Health score unavailable.',
                'suggested_action': 'Review and fix critical issues first for maximum impact.',
                'priority': 'critical' if r.critical_issues > 0 else 'high',
            })

        viral_posts = SocialPost.objects.select_related('user').filter(
            classification='viral'
        ).order_by('-engagement_score')[:3]
        for post in viral_posts:
            result['opportunities'].append({
                'page': post.post_url,
                'type': 'social_success',
                'reason': f'Viral post on {post.platform}',
                'data': f'{post.engagement_score} engagements ({post.likes} likes, {post.comments} comments, {post.shares} shares).',
                'suggested_action': 'Consider creating similar content or boosting this post for wider reach.',
                'priority': 'info',
            })

        thin_content = pages.filter(word_count__lt=300, word_count__gt=0)[:5]
        for p in thin_content:
            result['opportunities'].append({
                'page': p.url or p.final_url or '',
                'type': 'thin_content',
                'reason': f'Thin content ({p.word_count} words)',
                'data': 'Page has fewer than 300 words, which may be insufficient for search ranking.',
                'suggested_action': 'Expand the content with valuable, relevant information to improve ranking potential.',
                'priority': 'medium',
            })

    except (ImportError, Exception):
        pass

    return result


def get_unified_alerts():
    """
    Unified alerts combining Social Media, SEO, Keywords, Content.
    Single source of truth for 'Requires Attention' section.
    """
    alerts = []

    try:
        from social_proof.models import SocialProvider, SocialEvent
        from services.models import SocialPost
        from seo_analyzer.models import SEOIssue, SEOPageAudit, URLIntelligenceResult, URLIntelligenceTask
        from django.db.models import Sum

        now = timezone.now()

        for provider in SocialProvider.objects.filter(enabled=True):
            if provider.last_sync_at:
                age = now - provider.last_sync_at
                if age > timedelta(hours=48):
                    alerts.append({
                        'section': 'social',
                        'severity': 'critical',
                        'title': f'{provider.get_name_display()} sync failed',
                        'message': f'Last sync {provider.last_sync_at.strftime("%b %d, %H:%M")}.',
                    })
                elif age > timedelta(hours=24):
                    alerts.append({
                        'section': 'social',
                        'severity': 'warning',
                        'title': f'{provider.get_name_display()} sync delayed',
                        'message': f'Last sync {provider.last_sync_at.strftime("%b %d, %H:%M")}.',
                    })

        for pk in ['facebook', 'instagram', 'linkedin']:
            posts = SocialPost.objects.filter(platform=pk)
            recent = posts.filter(posted_at__gte=now - timedelta(days=7)).aggregate(s=Sum('engagement_score'))['s'] or 0
            prior = posts.filter(
                posted_at__gte=now - timedelta(days=14), posted_at__lt=now - timedelta(days=7)
            ).aggregate(s=Sum('engagement_score'))['s'] or 0
            if prior > 0 and recent < prior * 0.5:
                alerts.append({
                    'section': 'social',
                    'severity': 'warning',
                    'title': f'{pk.capitalize()} engagement dropped',
                    'message': f'Engagement fell {round((1 - recent/prior) * 100)}% this week.',
                })

        critical_issues = SEOIssue.objects.filter(severity='critical', status='open').count()
        if critical_issues > 0:
            alerts.append({
                'section': 'seo',
                'severity': 'critical',
                'title': f'{critical_issues} critical SEO issues',
                'message': 'Open critical issues require immediate attention.',
            })

        high_issues = SEOIssue.objects.filter(severity='high', status='open').count()
        if high_issues > 0:
            alerts.append({
                'section': 'seo',
                'severity': 'warning',
                'title': f'{high_issues} high-priority SEO issues',
                'message': 'High-severity issues may impact search rankings.',
            })

        pages_with_broken = SEOPageAudit.objects.filter(broken_internal_links_count__gt=0).count()
        if pages_with_broken > 0:
            alerts.append({
                'section': 'seo',
                'severity': 'warning',
                'title': f'{pages_with_broken} pages with broken links',
                'message': 'Broken internal links hurt crawlability and user experience.',
            })

        no_match = URLIntelligenceResult.objects.filter(keyword_match_status='no').count()
        if no_match > 0:
            alerts.append({
                'section': 'keywords',
                'severity': 'warning',
                'title': f'{no_match} keywords with no match',
                'message': 'Target keywords not found in page content.',
            })

        declining = URLIntelligenceResult.objects.filter(
            keyword_match_status='partial', keyword_relevance_score__lt=40
        ).count()
        if declining > 0:
            alerts.append({
                'section': 'keywords',
                'severity': 'info',
                'title': f'{declining} keywords with low relevance',
                'message': 'Keywords with relevance below 40% may need content optimization.',
            })

        missing_titles = SEOPageAudit.objects.filter(title_tag='').count()
        if missing_titles > 0:
            alerts.append({
                'section': 'content',
                'severity': 'warning',
                'title': f'{missing_titles} pages missing title tags',
                'message': 'Title tags are essential for SEO and click-through rates.',
            })

        missing_meta = SEOPageAudit.objects.filter(meta_description='').count()
        if missing_meta > 0:
            alerts.append({
                'section': 'content',
                'severity': 'info',
                'title': f'{missing_meta} pages missing meta descriptions',
                'message': 'Meta descriptions improve CTR from search results.',
            })

    except (ImportError, Exception):
        pass

    return alerts


def get_sync_status():
    """
    Data freshness for each section.
    Returns last sync time for Social, SEO, Keywords.
    """
    result = {
        'social': {'status': 'unavailable', 'last_sync': None, 'platforms': []},
        'seo': {'status': 'unavailable', 'last_sync': None},
        'keywords': {'status': 'unavailable', 'last_sync': None},
    }

    try:
        from social_proof.models import SocialProvider
        providers = SocialProvider.objects.all()
        if providers.exists():
            result['social']['status'] = 'available'
            latest_sync = None
            for p in providers:
                platform_data = {
                    'name': p.get_name_display(),
                    'last_sync': p.last_sync_at,
                    'status': 'connected' if p.enabled else 'not_connected',
                }
                if p.last_sync_at:
                    age = timezone.now() - p.last_sync_at
                    if age > timedelta(hours=48):
                        platform_data['status'] = 'sync_failed'
                    if latest_sync is None or p.last_sync_at > latest_sync:
                        latest_sync = p.last_sync_at
                result['social']['platforms'].append(platform_data)
            result['social']['last_sync'] = latest_sync
    except (ImportError, Exception):
        pass

    try:
        from seo_analyzer.models import SEOTask
        latest_task = SEOTask.objects.filter(status='completed').order_by('-completed_at').first()
        if latest_task:
            result['seo']['status'] = 'available'
            result['seo']['last_sync'] = latest_task.completed_at or latest_task.created_at
    except (ImportError, Exception):
        pass

    try:
        from seo_analyzer.models import URLIntelligenceTask
        latest_task = URLIntelligenceTask.objects.filter(status='completed').order_by('-completed_at').first()
        if latest_task:
            result['keywords']['status'] = 'available'
            result['keywords']['last_sync'] = latest_task.completed_at or latest_task.created_at
    except (ImportError, Exception):
        pass

    return result


def get_overview_data():
    """
    Cross-section overview data combining Social, SEO, Keywords, Content.
    Used by the improved Overview page.
    """
    result = {
        'social': {},
        'seo': {},
        'keywords': {},
        'content': {},
    }

    try:
        from social_proof.models import SocialProvider, SocialEvent
        from services.models import SocialPost
        from django.db.models import Sum

        platforms = SocialProvider.objects.all()
        result['social'] = {
            'available': True,
            'facebook_status': 'not_connected',
            'instagram_status': 'not_connected',
            'linkedin_status': 'not_connected',
            'total_engagement': 0,
            'best_post': None,
        }

        for p in platforms:
            status = 'connected' if p.enabled else 'not_connected'
            if p.last_sync_at and (timezone.now() - p.last_sync_at) > timedelta(hours=48):
                status = 'sync_failed'
            if p.name == 'facebook':
                result['social']['facebook_status'] = status
            elif p.name == 'instagram':
                result['social']['instagram_status'] = status
            elif p.name == 'linkedin':
                result['social']['linkedin_status'] = status

        total_eng = SocialPost.objects.aggregate(s=Sum('engagement_score'))['s'] or 0
        result['social']['total_engagement'] = total_eng

        best = SocialPost.objects.select_related('user').order_by('-engagement_score').first()
        if best:
            result['social']['best_post'] = {
                'platform': best.platform,
                'caption': (best.caption or '')[:100],
                'engagement': best.engagement_score,
                'url': best.post_url,
            }

    except (ImportError, Exception):
        result['social'] = {'available': False}

    try:
        from seo_analyzer.models import SEOTask
        latest = SEOTask.objects.filter(status='completed').select_related('result').order_by('-created_at').first()
        if latest and hasattr(latest, 'result'):
            r = latest.result
            result['seo'] = {
                'available': True,
                'health_score': float(r.health_score) if r.health_score else None,
                'technical_score': float(r.technical_score) if r.technical_score else None,
                'pages_crawled': r.pages_crawled,
                'total_issues': r.total_issues,
                'critical_issues': r.critical_issues,
            }
        else:
            result['seo'] = {'available': False}
    except (ImportError, Exception):
        result['seo'] = {'available': False}

    try:
        from seo_analyzer.models import URLIntelligenceResult, URLIntelligenceTask
        total_kw = URLIntelligenceTask.objects.exclude(target_keyword='').count()
        matched = URLIntelligenceResult.objects.filter(keyword_match_status='yes').count()
        partial = URLIntelligenceResult.objects.filter(keyword_match_status='partial').count()
        improving = URLIntelligenceResult.objects.filter(
            keyword_match_status='yes', keyword_relevance_score__gte=70
        ).count()
        declining = URLIntelligenceResult.objects.filter(
            keyword_match_status='partial', keyword_relevance_score__lt=40
        ).count()
        result['keywords'] = {
            'available': total_kw > 0,
            'total': total_kw,
            'matched': matched,
            'partial': partial,
            'improving': improving,
            'declining': declining,
        }
    except (ImportError, Exception):
        result['keywords'] = {'available': False}

    try:
        from seo_analyzer.models import SEOPageAudit
        pages = SEOPageAudit.objects.all()
        total = pages.count()
        missing_title = pages.filter(title_tag='').count()
        missing_meta = pages.filter(meta_description='').count()
        missing_alt = pages.filter(images_missing_alt__gt=0).count()
        result['content'] = {
            'available': total > 0,
            'total_pages': total,
            'missing_title': missing_title,
            'missing_meta': missing_meta,
            'missing_alt': missing_alt,
            'needs_attention': missing_title + missing_meta + missing_alt,
        }
    except (ImportError, Exception):
        result['content'] = {'available': False}

    return result
