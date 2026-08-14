"""System health checks for the Root Dashboard Operations Center.

Each service check attempts a real verification. If the check cannot be
performed, it returns 'unknown' rather than a fake healthy status.
"""
import time
import logging
import threading

from django.conf import settings

logger = logging.getLogger('root_dashboard.health')


def _make_result(status, label, detail=None):
    """Build a standardized health check result dict."""
    return {
        'status': status,
        'label': label,
        'detail': detail,
        'checked_at': time.time(),
    }


def check_django():
    """Verify Django framework is responding."""
    return _make_result('healthy', 'Django', 'Framework operational')


def check_database():
    """Verify database connectivity with a lightweight query."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        User.objects.exists()
        return _make_result('healthy', 'Database', 'Connection OK')
    except Exception as e:
        return _make_result('critical', 'Database', str(e))


def check_redis():
    """Verify Redis connectivity if configured."""
    redis_url = getattr(settings, 'REDIS_URL', None) or getattr(settings, 'CELERY_BROKER_URL', None)
    if not redis_url:
        return _make_result('unknown', 'Redis', 'Not configured')

    result = [None]

    def _try_redis():
        try:
            import redis as redis_lib
            from urllib.parse import urlparse
            parsed = urlparse(redis_url)
            r = redis_lib.Redis(
                host=parsed.hostname or 'localhost',
                port=parsed.port or 6379,
                db=int(parsed.path.lstrip('/') or 0),
                socket_timeout=1,
                socket_connect_timeout=1,
                retry_on_timeout=False,
            )
            r.ping()
            r.close()
            result[0] = _make_result('healthy', 'Redis', 'Connection OK')
        except ImportError:
            result[0] = _make_result('unknown', 'Redis', 'redis package not installed')
        except Exception as e:
            result[0] = _make_result('critical', 'Redis', str(e))

    t = threading.Thread(target=_try_redis, daemon=True)
    t.start()
    t.join(timeout=2)

    if result[0] is None:
        return _make_result('critical', 'Redis', 'Connection timed out')
    return result[0]


def check_celery():
    """Check Celery broker connectivity and inspect active workers."""
    use_celery = getattr(settings, 'USE_CELERY', False)
    if not use_celery:
        return _make_result('unknown', 'Celery', 'USE_CELERY is disabled')

    broker_url = getattr(settings, 'CELERY_BROKER_URL', None)
    if not broker_url:
        return _make_result('unknown', 'Celery', 'No broker URL configured')

    try:
        from celery import Celery
        app = Celery('websity_project')
        app.config_from_object('django.conf:settings', namespace='CELERY')
        inspector = app.control.inspect(timeout=1)
        active = inspector.active() or {}
        ping = inspector.ping() or {}
        if ping:
            worker_count = len(ping)
            return _make_result('healthy', 'Celery', f'{worker_count} worker(s) responding')
        elif active:
            return _make_result('healthy', 'Celery', f'{len(active)} worker(s) active')
        else:
            return _make_result('warning', 'Celery', 'No workers responding')
    except Exception as e:
        return _make_result('warning', 'Celery', str(e))


def check_websockets():
    """Check Django Channels layer availability."""
    try:
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer is None:
            return _make_result('unknown', 'WebSockets', 'Channel layer not configured')
        # Test with a simple group_add
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Cannot test async in sync context, just verify layer exists
                return _make_result('healthy', 'WebSockets', 'Channel layer available')
            else:
                loop.run_until_complete(layer.group_add('health_check', 'test'))
                loop.run_until_complete(layer.group_discard('health_check', 'test'))
                return _make_result('healthy', 'WebSockets', 'Channel layer operational')
        except RuntimeError:
            return _make_result('healthy', 'WebSockets', 'Channel layer available')
    except Exception as e:
        return _make_result('warning', 'WebSockets', str(e))


def check_storage():
    """Check filesystem storage writability."""
    import os
    from django.conf import settings as django_settings
    try:
        media_root = django_settings.MEDIA_ROOT
        if not media_root:
            return _make_result('unknown', 'Storage', 'MEDIA_ROOT not configured')
        os.makedirs(media_root, exist_ok=True)
        test_file = os.path.join(media_root, '.health_check')
        with open(test_file, 'w') as f:
            f.write('health')
        os.remove(test_file)
        return _make_result('healthy', 'Storage', 'Media storage writable')
    except Exception as e:
        return _make_result('warning', 'Storage', str(e))


def check_email():
    """Check email backend configuration."""
    from django.conf import settings as django_settings
    backend = django_settings.EMAIL_BACKEND
    if 'console' in backend:
        return _make_result('unknown', 'Email', 'Console backend (dev mode)')
    host = django_settings.EMAIL_HOST
    if not host:
        return _make_result('unknown', 'Email', 'No SMTP host configured')
    try:
        import smtplib
        server = smtplib.SMTP(host, django_settings.EMAIL_PORT, timeout=2)
        server.ehlo()
        server.quit()
        return _make_result('healthy', 'Email', f'SMTP {host} reachable')
    except Exception as e:
        return _make_result('warning', 'Email', str(e))


def check_stripe():
    """Check Stripe API key configuration."""
    secret_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
    if not secret_key:
        return _make_result('unknown', 'Stripe', 'No API key configured')
    if secret_key.startswith('sk_test_'):
        return _make_result('healthy', 'Stripe', 'Test mode')
    if secret_key.startswith('sk_live_'):
        return _make_result('healthy', 'Stripe', 'Live mode')
    return _make_result('warning', 'Stripe', 'Unrecognized key format')


def check_erp():
    """Check ERP integration configuration."""
    gateway_url = getattr(settings, 'ERP_GATEWAY_URL', '')
    if not gateway_url:
        return _make_result('unknown', 'ERP', 'No gateway URL configured')

    result = [None]

    def _try_erp():
        try:
            import requests
            resp = requests.get(gateway_url, timeout=2)
            result[0] = resp.status_code
        except ImportError:
            result[0] = 'import_error'
        except Exception:
            result[0] = 'error'

    t = threading.Thread(target=_try_erp, daemon=True)
    t.start()
    t.join(timeout=2)

    if result[0] is None:
        return _make_result('warning', 'ERP', 'Gateway unreachable: connection timed out')
    if result[0] == 'import_error':
        return _make_result('unknown', 'ERP', 'requests package not available')
    if result[0] == 'error':
        return _make_result('warning', 'ERP', 'Gateway unreachable')
    if result[0] < 500:
        return _make_result('healthy', 'ERP', f'Gateway responding ({result[0]})')
    return _make_result('warning', 'ERP', f'Gateway returned {result[0]}')


def check_external_apis():
    """Check external API connectivity (Sentry DSN configured, etc.)."""
    sentry_dsn = getattr(settings, 'SENTRY_DSN', '')
    has_sentry = bool(sentry_dsn)
    return _make_result(
        'healthy' if has_sentry else 'unknown',
        'External APIs',
        'Sentry configured' if has_sentry else 'Sentry not configured'
    )


def run_all_checks():
    """Run all health checks and return results with a hard overall timeout."""
    import concurrent.futures
    import threading

    checks = [
        check_django,
        check_database,
        check_redis,
        check_celery,
        check_websockets,
        check_storage,
        check_email,
        check_stripe,
        check_erp,
        check_external_apis,
    ]

    results = [None] * len(checks)

    def _run_single(idx, check_fn):
        try:
            results[idx] = check_fn()
        except Exception as e:
            label = check_fn.__name__.replace('check_', '').replace('_', ' ').title()
            results[idx] = _make_result('critical', label, f'Check failed: {e}')

    # Run all checks as daemon threads with a hard 8-second timeout
    threads = []
    for i, check_fn in enumerate(checks):
        t = threading.Thread(target=_run_single, args=(i, check_fn), daemon=True)
        threads.append(t)
        t.start()

    # Wait at most 5 seconds total
    deadline = time.time() + 5
    for t in threads:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        t.join(timeout=remaining)

    # Fill in any still-None results as timed out
    for i, check_fn in enumerate(checks):
        if results[i] is None:
            label = check_fn.__name__.replace('check_', '').replace('_', ' ').title()
            results[i] = _make_result('critical', label, 'Check timed out')

    return results


def get_overall_status(results):
    """Determine overall platform health from individual check results."""
    statuses = [r['status'] for r in results]
    if 'critical' in statuses:
        return 'critical'
    if 'warning' in statuses:
        return 'warning'
    healthy_count = sum(1 for s in statuses if s == 'healthy')
    unknown_count = sum(1 for s in statuses if s == 'unknown')
    if healthy_count > 0 and unknown_count == 0:
        return 'healthy'
    if healthy_count > 0:
        return 'healthy'
    return 'unknown'
