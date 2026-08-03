"""Rate limiting utilities using Django's cache backend.

Provides a sliding-window rate limiter backed by LocMem or Redis.
All functions are stateless and thread-safe.
"""
import time

from django.core.cache import cache


def _get_client_ip(request):
    """Extract the client IP, respecting X-Forwarded-For."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def _user_key(user_id, action):
    """Cache key for authenticated users."""
    return f'rl:{action}:u{user_id}'


def _anon_key(ip, action):
    """Cache key for anonymous users."""
    return f'rl:{action}:a{ip}'


def _get_usage(key, window):
    """Return the number of requests in the current window.

    Uses a simple fixed-window approach: store a list of timestamps.
    """
    now = time.time()
    data = cache.get(key)
    if data is None:
        data = []

    # Prune timestamps outside the window
    cutoff = now - window
    data = [ts for ts in data if ts > cutoff]

    return data


def _record_request(key, window):
    """Record a new request and return the updated count."""
    now = time.time()
    data = cache.get(key)
    if data is None:
        data = []

    cutoff = now - window
    data = [ts for ts in data if ts > cutoff]
    data.append(now)

    # Store with TTL equal to the window so expired keys are auto-cleaned
    cache.set(key, data, timeout=int(window) + 10)

    return len(data)


def check_rate_limit(request, action, limit, window):
    """Check if the request is within the rate limit.

    Args:
        request: Django HttpRequest
        action: string identifier for the rate limit bucket
        max_requests: maximum requests allowed in the window
        window: time window in seconds

    Returns:
        dict with keys: allowed, remaining, retry_after, reset_at
    """
    if hasattr(request, 'user') and request.user.is_authenticated:
        if request.user.is_staff:
            return {
                'allowed': True,
                'remaining': limit,
                'retry_after': 0,
                'reset_at': 0,
            }
        key = _user_key(request.user.pk, action)
    else:
        ip = _get_client_ip(request)
        key = _anon_key(ip, action)

    usage = _get_usage(key, window)
    count = len(usage)
    remaining = max(0, limit - count)

    if count >= limit:
        # Calculate when the oldest request in the window expires
        oldest = usage[0] if usage else time.time()
        retry_after = max(1, int(oldest + window - time.time()) + 1)
        reset_at = int(oldest + window)
        return {
            'allowed': False,
            'remaining': 0,
            'retry_after': retry_after,
            'reset_at': reset_at,
        }

    # Record this request
    new_count = _record_request(key, window)
    remaining = max(0, limit - new_count)

    return {
        'allowed': True,
        'remaining': remaining,
        'retry_after': 0,
        'reset_at': int(time.time() + window),
    }


# ---------------------------------------------------------------------------
# Predefined rate limit profiles
# ---------------------------------------------------------------------------

RATE_LIMITS = {
    'wizard_submit': {
        'action': 'wizard_submit',
        'limit': 5,
        'window': 3600,       # 1 hour
        'description': 'Wizard submission: 5 per hour per user',
    },
    'file_upload': {
        'action': 'file_upload',
        'limit': 20,
        'window': 3600,       # 1 hour
        'description': 'File uploads: 20 per hour per user',
    },
    'api_user': {
        'action': 'api_user',
        'limit': 100,
        'window': 60,         # 1 minute
        'description': 'API: 100 per minute per user',
    },
    'api_anon': {
        'action': 'api_anon',
        'limit': 20,
        'window': 60,         # 1 minute
        'description': 'API unauthenticated: 20 per minute',
    },
    'login': {
        'action': 'login',
        'limit': 10,
        'window': 900,        # 15 minutes
        'description': 'Login attempts: 10 per 15 minutes',
    },
}


def check_rate_limit_by_name(request, profile_name):
    """Check rate limit using a named profile from RATE_LIMITS."""
    profile = RATE_LIMITS.get(profile_name)
    if not profile:
        return {'allowed': True, 'remaining': 0, 'retry_after': 0, 'reset_at': 0}
    return check_rate_limit(request, profile['action'], profile['limit'], profile['window'])
