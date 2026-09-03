import os
import re
import logging
from urllib.parse import urlparse

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

PAGESPEED_API_URL = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed'

SCORE_THRESHOLDS = {
    'excellent': 90,
    'good': 75,
    'needs_improvement': 50,
}

THRESHOLDS = {
    'lcp': {'good': 2500, 'poor': 4000},
    'fcp': {'good': 1800, 'poor': 3000},
    'cls': {'good': 0.1, 'poor': 0.25},
    'inp': {'good': 200, 'poor': 500},
    'ttfb': {'good': 800, 'poor': 1800},
    'speed_index': {'good': 3400, 'poor': 5800},
    'total_blocking_time': {'good': 200, 'poor': 600},
}

METRIC_LABELS = {
    'lcp': 'Largest Contentful Paint',
    'fcp': 'First Contentful Paint',
    'cls': 'Cumulative Layout Shift',
    'inp': 'Interaction to Next Paint',
    'ttfb': 'Time to First Byte',
    'speed_index': 'Speed Index',
    'total_blocking_time': 'Total Blocking Time',
}

METRIC_UNITS = {
    'lcp': 's',
    'fcp': 's',
    'cls': '',
    'inp': 'ms',
    'ttfb': 's',
    'speed_index': 's',
    'total_blocking_time': 'ms',
}


def validate_url(url):
    if not url or not url.strip():
        return False, 'Please enter a website URL.'

    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        result = urlparse(url)
        if not result.scheme or not result.netloc:
            return False, 'Invalid URL format.'
        if '.' not in result.netloc:
            return False, 'Invalid URL: domain must contain a dot.'
    except Exception:
        return False, 'Invalid URL format.'

    return True, url


def normalize_url(url):
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url


def get_performance_status(score):
    if score >= SCORE_THRESHOLDS['excellent']:
        return 'excellent'
    elif score >= SCORE_THRESHOLDS['good']:
        return 'good'
    elif score >= SCORE_THRESHOLDS['needs_improvement']:
        return 'needs_improvement'
    else:
        return 'poor'


def get_performance_status_display(score):
    status = get_performance_status(score)
    return status.replace('_', ' ').title()


def get_metric_status(metric_name, value):
    if value is None:
        return 'N/A'

    t = THRESHOLDS.get(metric_name)
    if not t:
        return 'N/A'

    if value <= t['good']:
        return 'Good'
    elif value <= t['poor']:
        return 'Needs Improvement'
    else:
        return 'Poor'


def format_metric(metric_name, value):
    if value is None:
        return 'N/A'

    unit = METRIC_UNITS.get(metric_name, '')

    if metric_name == 'cls':
        return f'{value:.2f}'
    elif unit == 's':
        seconds = value / 1000
        return f'{seconds:.1f}s'
    elif unit == 'ms':
        return f'{int(value)}ms'
    else:
        return f'{value}'


def _extract_metric(audits, key):
    if not audits:
        return None
    audit = audits.get(key)
    if not audit:
        return None
    value = audit.get('numericValue')
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _calculate_score_category(score):
    if score is None:
        return 'N/A'
    return get_performance_status_display(score)


def _generate_recommendations(metrics):
    recommendations = []

    lcp = metrics.get('lcp')
    if lcp is not None:
        if lcp > 4000:
            recommendations.append(
                'Improve Largest Contentful Paint by optimizing the largest content element, '
                'reducing server response time, and leveraging browser caching.'
            )
        elif lcp > 2500:
            recommendations.append(
                'Largest Contentful Paint could be improved. Consider optimizing images '
                'and reducing server response time.'
            )

    cls = metrics.get('cls')
    if cls is not None:
        if cls > 0.25:
            recommendations.append(
                'Reduce layout shifts by defining explicit dimensions for images, videos, '
                'and dynamically injected content elements.'
            )
        elif cls > 0.1:
            recommendations.append(
                'Cumulative Layout Shift is borderline. Ensure all dynamic content has '
                'reserved space to prevent layout movement.'
            )

    tbt = metrics.get('total_blocking_time')
    if tbt is not None:
        if tbt > 600:
            recommendations.append(
                'Reduce Total Blocking Time by minimizing JavaScript execution, deferring '
                'non-critical scripts, and removing unnecessary third-party scripts.'
            )
        elif tbt > 200:
            recommendations.append(
                'Total Blocking Time could be improved. Consider code-splitting and '
                'lazy-loading non-critical JavaScript.'
            )

    fcp = metrics.get('fcp')
    if fcp is not None:
        if fcp > 3000:
            recommendations.append(
                'Improve First Contentful Paint by optimizing critical rendering path, '
                'inlining above-the-fold CSS, and reducing server response time.'
            )
        elif fcp > 1800:
            recommendations.append(
                'First Contentful Paint could be improved. Consider preloading critical resources.'
            )

    ttfb = metrics.get('ttfb')
    if ttfb is not None:
        if ttfb > 1800:
            recommendations.append(
                'Time to First Byte is high. Investigate server response time, consider '
                'using a CDN, and optimize server-side processing.'
            )
        elif ttfb > 800:
            recommendations.append(
                'Time to First Byte could be improved. Consider server optimization or CDN usage.'
            )

    speed_index = metrics.get('speed_index')
    if speed_index is not None:
        if speed_index > 5800:
            recommendations.append(
                'Speed Index is poor. Optimize above-the-fold content delivery, '
                'reduce render-blocking resources, and optimize image loading.'
            )
        elif speed_index > 3400:
            recommendations.append(
                'Speed Index could be improved. Consider optimizing critical rendering path.'
            )

    inp = metrics.get('inp')
    if inp is not None:
        if inp > 500:
            recommendations.append(
                'Interaction to Next Paint is poor. Reduce JavaScript main thread work, '
                'break up long tasks, and minimize third-party script impact.'
            )
        elif inp > 200:
            recommendations.append(
                'Interaction to Next Paint could be improved. Consider optimizing event handlers.'
            )

    if not recommendations:
        recommendations.append(
            'Performance is currently healthy. Continue monitoring to detect future regressions.'
        )

    return recommendations


def run_performance_test(url, api_key=None):
    if api_key is None:
        api_key = getattr(settings, 'PAGESPEED_API_KEY', '') or os.environ.get('PAGESPEED_API_KEY', '')

    valid, result = validate_url(url)
    if not valid:
        return {'success': False, 'error': result}

    url = normalize_url(result)

    results = {'success': True, 'url': url, 'mobile': None, 'desktop': None}

    for strategy in ('mobile', 'desktop'):
        try:
            params = {
                'url': url,
                'strategy': strategy,
                'category': 'performance',
            }
            if api_key:
                params['key'] = api_key

            response = requests.get(
                PAGESPEED_API_URL,
                params=params,
                timeout=60,
            )

            if response.status_code == 429:
                return {'success': False, 'error': 'API rate limit exceeded. Please try again later.'}

            if response.status_code != 200:
                return {'success': False, 'error': f'PageSpeed API returned status {response.status_code}.'}

            data = response.json()

            if 'error' in data:
                error_msg = data['error'].get('message', 'Unknown API error')
                return {'success': False, 'error': f'PageSpeed API error: {error_msg}'}

            lighthouse = data.get('lighthouseResult', {})
            if not lighthouse:
                return {'success': False, 'error': 'Invalid API response: no Lighthouse result.'}

            categories = lighthouse.get('categories', {})
            perf_category = categories.get('performance', {})
            score_raw = perf_category.get('score')
            if score_raw is None:
                return {'success': False, 'error': 'Performance score not available.'}

            performance_score = round(score_raw * 100)

            audits = lighthouse.get('audits', {})

            metrics = {
                'lcp': _extract_metric(audits, 'largest-contentful-paint'),
                'fcp': _extract_metric(audits, 'first-contentful-paint'),
                'inp': _extract_metric(audits, 'interactive'),
                'cls': _extract_metric(audits, 'cumulative-layout-shift'),
                'ttfb': _extract_metric(audits, 'server-response-time'),
                'speed_index': _extract_metric(audits, 'speed-index'),
                'total_blocking_time': _extract_metric(audits, 'total-blocking-time'),
            }

            status = get_performance_status(performance_score)
            recommendations = _generate_recommendations(metrics)

            device_result = {
                'performance_score': performance_score,
                'status': status,
                'fcp': metrics['fcp'],
                'lcp': metrics['lcp'],
                'inp': metrics['inp'],
                'cls': metrics['cls'],
                'ttfb': metrics['ttfb'],
                'speed_index': metrics['speed_index'],
                'total_blocking_time': metrics['total_blocking_time'],
                'recommendations': recommendations,
            }

            results[strategy] = device_result

        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'PageSpeed API request timed out. Please try again.'}
        except requests.exceptions.ConnectionError:
            return {'success': False, 'error': 'Unable to connect to PageSpeed API. Check your internet connection.'}
        except Exception as e:
            logger.exception('PageSpeed test error for %s (%s)', url, strategy)
            return {'success': False, 'error': f'Unexpected error: {str(e)}'}

    if results['mobile'] and results['desktop']:
        mobile_score = results['mobile']['performance_score']
        desktop_score = results['desktop']['performance_score']
        overall = round((mobile_score + desktop_score) / 2, 1)
        overall_status = get_performance_status(overall)
        results['overall'] = {
            'performance_score': overall,
            'status': overall_status,
        }
        combined_recommendations = list(dict.fromkeys(
            results['mobile']['recommendations'] + results['desktop']['recommendations']
        ))
        results['mobile']['recommendations'] = combined_recommendations
        results['desktop']['recommendations'] = combined_recommendations
    elif results['mobile']:
        results['overall'] = {
            'performance_score': results['mobile']['performance_score'],
            'status': results['mobile']['status'],
        }
    elif results['desktop']:
        results['overall'] = {
            'performance_score': results['desktop']['performance_score'],
            'status': results['desktop']['status'],
        }

    return results
