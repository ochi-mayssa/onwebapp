"""Middleware for the Branding Service app.

- QueryCountMiddleware: logs SQL queries per request (DEBUG only).
- RateLimitMiddleware: enforces rate limits on API endpoints.
"""
import logging
import time

from django.conf import settings
from django.db import connection, reset_queries
from django.http import JsonResponse

from .ratelimit import check_rate_limit, _get_client_ip

logger = logging.getLogger('branding.queries')


class QueryCountMiddleware:
    """Log the total query count and duration for every request.

    Usage:
        Add 'branding.middleware.QueryCountMiddleware' to MIDDLEWARE
        (only in DEBUG). It prints to the console / Django logger.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.DEBUG:
            return self.get_response(request)

        reset_queries()
        start = time.perf_counter()

        response = self.get_response(request)

        duration = (time.perf_counter() - start) * 1000
        query_count = len(connection.queries)

        # Warn on high query counts
        level = logging.WARNING if query_count > 20 else logging.DEBUG
        logger.log(
            level,
            '[Queries] %d queries in %.1fms — %s %s',
            query_count,
            duration,
            request.method,
            request.path,
        )

        # Also attach to response for toolbar-style display
        if hasattr(response, 'content'):
            response['X-SQL-Queries'] = str(query_count)
            response['X-Query-Time'] = f'{duration:.1f}ms'

        return response


class RateLimitMiddleware:
    """Enforce rate limits on API endpoints under /api/branding/.

    - Authenticated users: 100 requests/minute.
    - Anonymous users: 20 requests/minute.
    - Staff users are exempt.
    """

    API_PREFIX = '/api/branding/'
    ANON_LIMIT = 20
    USER_LIMIT = 100
    WINDOW = 60  # 1 minute

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only apply to API endpoints
        if not request.path.startswith(self.API_PREFIX):
            return self.get_response(request)

        # Skip auth endpoints (token obtain/refresh/verify) — they have their own limits
        if '/auth/' in request.path:
            return self.get_response(request)

        # Staff are exempt
        if hasattr(request, 'user') and request.user.is_authenticated and request.user.is_staff:
            response = self.get_response(request)
            return response

        # Determine limit
        if hasattr(request, 'user') and request.user.is_authenticated:
            action = f'api_u{request.user.pk}'
            limit = self.USER_LIMIT
        else:
            ip = _get_client_ip(request)
            action = f'api_a{ip}'
            limit = self.ANON_LIMIT

        from .ratelimit import check_rate_limit as _check
        result = _check(request, action, limit, self.WINDOW)

        if not result['allowed']:
            retry_after = result['retry_after']
            response = JsonResponse(
                {
                    'error': 'Rate limit exceeded.',
                    'detail': f'Maximum {limit} requests per minute. Retry after {retry_after}s.',
                    'retry_after': retry_after,
                },
                status=429,
            )
            response['Retry-After'] = str(retry_after)
            response['X-RateLimit-Limit'] = str(limit)
            response['X-RateLimit-Remaining'] = '0'
            response['X-RateLimit-Reset'] = str(result['reset_at'])
            return response

        response = self.get_response(request)
        response['X-RateLimit-Limit'] = str(limit)
        response['X-RateLimit-Remaining'] = str(result['remaining'])
        response['X-RateLimit-Reset'] = str(result['reset_at'])
        return response
