"""Decorator for applying rate limits to Django views."""
from functools import wraps

from django.http import JsonResponse

from .ratelimit import check_rate_limit, check_rate_limit_by_name


def rate_limit(profile_or_limit=None, window=None, action=None):
    """Apply a rate limit to a Django view.

    Usage:
        @rate_limit('wizard_submit')
        def my_view(request):
            ...

        @rate_limit(limit=10, window=60, action='custom_action')
        def my_view(request):
            ...

    When a named profile is given (string), it looks up RATE_LIMITS.
    When limit/window/action are given directly, they are used as-is.
    Staff users are exempt.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            # Staff users are exempt
            if hasattr(request, 'user') and request.user.is_authenticated and request.user.is_staff:
                response = view_func(request, *args, **kwargs)
                return response

            # Determine rate limit parameters
            if isinstance(profile_or_limit, str):
                result = check_rate_limit_by_name(request, profile_or_limit)
            elif profile_or_limit is not None and window is not None:
                act = action or view_func.__name__
                result = check_rate_limit(request, act, profile_or_limit, window)
            else:
                # No rate limit configured — pass through
                return view_func(request, *args, **kwargs)

            # Set rate limit headers on the response
            def _add_headers(response):
                response['X-RateLimit-Limit'] = str(
                    (RATE_LIMITS.get(profile_or_limit, {}) or {}).get('limit', profile_or_limit or 0)
                )
                response['X-RateLimit-Remaining'] = str(result['remaining'])
                response['X-RateLimit-Reset'] = str(result['reset_at'])
                return response

            if not result['allowed']:
                retry_after = result['retry_after']
                response = JsonResponse(
                    {
                        'error': 'Rate limit exceeded. Please try again later.',
                        'detail': f'You have exceeded the rate limit. Retry after {retry_after} seconds.',
                        'retry_after': retry_after,
                    },
                    status=429,
                )
                response['Retry-After'] = str(retry_after)
                response['X-RateLimit-Remaining'] = '0'
                response['X-RateLimit-Reset'] = str(result['reset_at'])
                return response

            response = view_func(request, *args, **kwargs)
            _add_headers(response)
            return response

        return _wrapped
    return decorator


# Re-import for use in decorator header logic
from .ratelimit import RATE_LIMITS  # noqa: E402
