import logging
from datetime import datetime, timedelta

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

GA4_DATA_API_URL = 'https://analyticsdata.googleapis.com/v1beta'
GA4_SCOPES = ['https://www.googleapis.com/auth/analytics.readonly']

DATE_RANGE_OPTIONS = {
    '7d': {'days': 7, 'label': 'Last 7 Days'},
    '30d': {'days': 30, 'label': 'Last 30 Days'},
    '90d': {'days': 90, 'label': 'Last 90 Days'},
}


def get_oauth_client_id():
    return getattr(settings, 'GA4_CLIENT_ID', '')


def get_oauth_client_secret():
    return getattr(settings, 'GA4_CLIENT_SECRET', '')


def get_oauth_redirect_uri():
    return getattr(settings, 'GA4_REDIRECT_URI', '')


def get_oauth_authorize_url():
    client_id = get_oauth_client_id()
    redirect_uri = get_oauth_redirect_uri()
    scopes = ' '.join(GA4_SCOPES)

    return (
        f'https://accounts.google.com/o/oauth2/v2/auth'
        f'?client_id={client_id}'
        f'&redirect_uri={redirect_uri}'
        f'&response_type=code'
        f'&scope={scopes}'
        f'&access_type=offline'
        f'&prompt=consent'
    )


def exchange_code_for_tokens(code):
    client_id = get_oauth_client_id()
    client_secret = get_oauth_client_secret()
    redirect_uri = get_oauth_redirect_uri()

    token_url = 'https://oauth2.googleapis.com/token'
    payload = {
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
    }

    try:
        resp = requests.post(token_url, data=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.exception('GA4 OAuth token exchange failed')
        return {'error': str(e)}


def refresh_access_token(refresh_token):
    client_id = get_oauth_client_id()
    client_secret = get_oauth_client_secret()

    token_url = 'https://oauth2.googleapis.com/token'
    payload = {
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'refresh_token',
    }

    try:
        resp = requests.post(token_url, data=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.exception('GA4 token refresh failed')
        return None


def get_valid_credentials(property_obj):
    access_token = property_obj.access_token
    expires_at = property_obj.token_expires_at

    if expires_at and timezone.now() >= expires_at:
        refreshed = refresh_access_token(property_obj.refresh_token)
        if not refreshed or 'error' in refreshed:
            return None
        access_token = refreshed.get('access_token', access_token)
        expires_in = refreshed.get('expires_in', 3600)
        property_obj.access_token = access_token
        property_obj.token_expires_at = timezone.now() + timedelta(seconds=expires_in)
        property_obj.save(update_fields=['access_token', 'token_expires_at'])

    return access_token


def list_ga4_properties(access_token):
    url = 'https://analyticsadmin.googleapis.com/v1beta/accountSummaries'
    headers = {'Authorization': f'Bearer {access_token}'}

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        properties = []
        for account in data.get('accountSummaries', []):
            account_name = account.get('displayName', '')
            for prop in account.get('propertySummaries', []):
                raw_id = prop.get('property', '')
                clean_id = raw_id.replace('properties/', '')
                properties.append({
                    'property_id': clean_id,
                    'display_name': prop.get('displayName', ''),
                    'account_name': account_name,
                    'display_name_full': f"{prop.get('displayName', '')} ({account_name})",
                })

        return properties
    except requests.RequestException as e:
        logger.exception('GA4 properties list failed')
        return []


def run_ga4_report(access_token, property_id, date_range='30d'):
    url = f'{GA4_DATA_API_URL}/properties/{property_id}:runReport'
    headers = {'Authorization': f'Bearer {access_token}'}

    days = DATE_RANGE_OPTIONS.get(date_range, DATE_RANGE_OPTIONS['30d'])['days']
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    body = {
        'dateRanges': [{'startDate': start_date, 'endDate': end_date}],
        'metrics': [
            {'name': 'totalUsers'},
            {'name': 'sessions'},
            {'name': 'screenPageViews'},
            {'name': 'averageSessionDuration'},
            {'name': 'engagementRate'},
            {'name': 'bounceRate'},
        ],
        'dimensions': [{'name': 'date'}],
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.exception('GA4 report failed for property %s', property_id)
        return {'error': str(e)}


def run_ga4_traffic_sources_report(access_token, property_id, date_range='30d'):
    url = f'{GA4_DATA_API_URL}/properties/{property_id}:runReport'
    headers = {'Authorization': f'Bearer {access_token}'}

    days = DATE_RANGE_OPTIONS.get(date_range, DATE_RANGE_OPTIONS['30d'])['days']
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    body = {
        'dateRanges': [{'startDate': start_date, 'endDate': end_date}],
        'metrics': [
            {'name': 'sessions'},
            {'name': 'totalUsers'},
        ],
        'dimensions': [{'name': 'sessionSource'}],
        'limit': 10,
        'orderBys': [{'metric': {'metricName': 'sessions'}, 'desc': True}],
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.exception('GA4 traffic sources report failed for property %s', property_id)
        return {'error': str(e)}


def run_ga4_previous_period_report(access_token, property_id, date_range='30d'):
    url = f'{GA4_DATA_API_URL}/properties/{property_id}:runReport'
    headers = {'Authorization': f'Bearer {access_token}'}

    days = DATE_RANGE_OPTIONS.get(date_range, DATE_RANGE_OPTIONS['30d'])['days']
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    prev_end = (datetime.now() - timedelta(days=days) - timedelta(days=1)).strftime('%Y-%m-%d')
    prev_start = (datetime.now() - timedelta(days=days * 2) - timedelta(days=1)).strftime('%Y-%m-%d')

    body = {
        'dateRanges': [
            {'startDate': start_date, 'endDate': end_date},
            {'startDate': prev_start, 'endDate': prev_end},
        ],
        'metrics': [
            {'name': 'totalUsers'},
            {'name': 'sessions'},
            {'name': 'screenPageViews'},
            {'name': 'averageSessionDuration'},
            {'name': 'engagementRate'},
            {'name': 'bounceRate'},
        ],
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.exception('GA4 previous period report failed')
        return {'error': str(e)}


def calculate_kpis(report_data):
    if not report_data or 'error' in report_data:
        return None

    rows = report_data.get('rows', [])
    if not rows:
        return None

    totals = {
        'total_users': 0,
        'sessions': 0,
        'screen_page_views': 0,
        'total_session_duration': 0,
        'weighted_engagement': 0,
        'weighted_bounce': 0,
    }

    for row in rows:
        vals = row.get('metricValues', [])
        if len(vals) >= 6:
            totals['total_users'] += _safe_int(vals[0].get('value', '0'))
            totals['sessions'] += _safe_int(vals[1].get('value', '0'))
            totals['screen_page_views'] += _safe_int(vals[2].get('value', '0'))
            duration = _safe_float(vals[3].get('value', '0'))
            sessions = _safe_int(vals[1].get('value', '0'))
            totals['total_session_duration'] += duration * sessions
            totals['weighted_engagement'] += _safe_float(vals[4].get('value', '0')) * sessions
            totals['weighted_bounce'] += _safe_float(vals[5].get('value', '0')) * sessions

    sessions = totals['sessions'] or 1

    avg_session_duration = totals['total_session_duration'] / sessions
    engagement_rate = totals['weighted_engagement'] / sessions
    bounce_rate = totals['weighted_bounce'] / sessions
    sessions_per_user = totals['sessions'] / max(totals['total_users'], 1)

    return {
        'total_users': totals['total_users'],
        'sessions': totals['sessions'],
        'screen_page_views': totals['screen_page_views'],
        'avg_session_duration': round(avg_session_duration, 1),
        'engagement_rate': round(engagement_rate * 100, 1),
        'bounce_rate': round(bounce_rate * 100, 1),
        'sessions_per_user': round(sessions_per_user, 2),
    }


def calculate_trend(report_data):
    if not report_data or 'error' in report_data or 'rows' not in report_data:
        return None

    rows = report_data.get('rows', [])
    row_count = len(rows)

    if row_count < 2:
        return None

    mid = row_count // 2
    current_rows = rows[:mid]
    previous_rows = rows[mid:]

    def sum_metrics(rows_chunk):
        totals = [0.0] * 6
        for row in rows_chunk:
            vals = row.get('metricValues', [])
            for i in range(min(6, len(vals))):
                totals[i] += _safe_float(vals[i].get('value', '0'))
        return totals

    current = sum_metrics(current_rows)
    previous = sum_metrics(previous_rows)

    trends = []
    metric_names = ['total_users', 'sessions', 'screen_page_views', 'avg_session_duration', 'engagement_rate', 'bounce_rate']

    for i, name in enumerate(metric_names):
        curr_val = current[i]
        prev_val = previous[i]
        if prev_val == 0:
            pct_change = 0
        else:
            pct_change = ((curr_val - prev_val) / prev_val) * 100
        trends.append({
            'metric': name,
            'current': round(curr_val, 1),
            'previous': round(prev_val, 1),
            'change_pct': round(pct_change, 1),
            'direction': 'up' if pct_change > 0 else ('down' if pct_change < 0 else 'stable'),
        })

    return trends


def calculate_traffic_sources(report_data):
    if not report_data or 'error' in report_data:
        return []

    rows = report_data.get('rows', [])
    sources = []

    for row in rows:
        dimensions = row.get('dimensionValues', [])
        metrics = row.get('metricValues', [])

        source_name = dimensions[0].get('value', 'Unknown') if dimensions else 'Unknown'
        sessions = _safe_int(metrics[0].get('value', '0')) if len(metrics) > 0 else 0
        users = _safe_int(metrics[1].get('value', '0')) if len(metrics) > 1 else 0

        sources.append({
            'source': source_name,
            'sessions': sessions,
            'users': users,
        })

    total_sessions = sum(s['sessions'] for s in sources) or 1
    for s in sources:
        s['percentage'] = round((s['sessions'] / total_sessions) * 100, 1)

    return sorted(sources, key=lambda x: x['sessions'], reverse=True)


def _safe_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
