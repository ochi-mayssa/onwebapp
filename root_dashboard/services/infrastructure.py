"""Infrastructure metrics for the Root Dashboard Operations Center.

Uses psutil for real CPU, memory, and disk metrics.
Falls back to 'unavailable' if psutil is not installed.
"""
import time


def _unavailable_metric(name):
    """Return an unavailable metric dict."""
    return {
        'name': name,
        'value': None,
        'unit': '',
        'status': 'unavailable',
        'detail': 'Monitoring unavailable',
    }


def get_cpu_metrics():
    """Return real CPU usage metrics."""
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()
        freq_current = round(cpu_freq.current, 0) if cpu_freq else None

        if cpu_percent > 90:
            status = 'critical'
        elif cpu_percent > 75:
            status = 'warning'
        else:
            status = 'healthy'

        return {
            'name': 'CPU Usage',
            'value': cpu_percent,
            'unit': '%',
            'status': status,
            'detail': f'{cpu_count} cores' + (f' @ {freq_current} MHz' if freq_current else ''),
        }
    except ImportError:
        return _unavailable_metric('CPU Usage')
    except Exception as e:
        return _unavailable_metric('CPU Usage')


def get_memory_metrics():
    """Return real memory usage metrics."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        used_gb = round(mem.used / (1024 ** 3), 2)
        total_gb = round(mem.total / (1024 ** 3), 2)
        percent = mem.percent

        if percent > 90:
            status = 'critical'
        elif percent > 75:
            status = 'warning'
        else:
            status = 'healthy'

        return {
            'name': 'Memory Usage',
            'value': percent,
            'unit': '%',
            'status': status,
            'detail': f'{used_gb} / {total_gb} GB',
        }
    except ImportError:
        return _unavailable_metric('Memory Usage')
    except Exception as e:
        return _unavailable_metric('Memory Usage')


def get_disk_metrics():
    """Return real disk usage metrics."""
    try:
        import psutil
        disk = psutil.disk_usage('/')
        used_gb = round(disk.used / (1024 ** 3), 2)
        total_gb = round(disk.total / (1024 ** 3), 2)
        percent = disk.percent

        if percent > 90:
            status = 'critical'
        elif percent > 80:
            status = 'warning'
        else:
            status = 'healthy'

        return {
            'name': 'Disk Usage',
            'value': percent,
            'unit': '%',
            'status': status,
            'detail': f'{used_gb} / {total_gb} GB',
        }
    except ImportError:
        return _unavailable_metric('Disk Usage')
    except Exception as e:
        return _unavailable_metric('Disk Usage')


def get_request_metrics():
    """Return request count and error rate from Django cache if available."""
    try:
        from django.core.cache import cache
        total = cache.get('root_dashboard_request_count', 0)
        errors = cache.get('root_dashboard_error_count', 0)
        error_rate = round((errors / total * 100), 2) if total > 0 else 0

        return {
            'total_requests': total,
            'error_count': errors,
            'error_rate': error_rate,
            'status': 'healthy' if error_rate < 5 else 'warning',
        }
    except Exception:
        return {
            'total_requests': None,
            'error_count': None,
            'error_rate': None,
            'status': 'unavailable',
        }


def get_celery_metrics():
    """Return Celery queue and worker metrics."""
    from django.conf import settings
    use_celery = getattr(settings, 'USE_CELERY', False)
    if not use_celery:
        return {
            'workers': None,
            'active_tasks': None,
            'status': 'unavailable',
            'detail': 'USE_CELERY is disabled',
        }

    try:
        from celery import Celery
        app = Celery('websity_project')
        app.config_from_object('django.conf:settings', namespace='CELERY')
        inspector = app.control.inspect(timeout=1)
        active = inspector.active() or {}
        ping = inspector.ping() or {}

        worker_count = len(ping)
        total_active = sum(len(tasks) for tasks in active.values())

        return {
            'workers': worker_count,
            'active_tasks': total_active,
            'status': 'healthy' if worker_count > 0 else 'warning',
            'detail': f'{worker_count} workers, {total_active} active tasks',
        }
    except Exception as e:
        return {
            'workers': None,
            'active_tasks': None,
            'status': 'unavailable',
            'detail': str(e),
        }


def get_websocket_metrics():
    """Return WebSocket connection metrics."""
    try:
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer is None:
            return {
                'connections': None,
                'status': 'unavailable',
                'detail': 'Channel layer not configured',
            }
        # InMemoryChannelLayer doesn't expose connection count
        # RedisChannelLayer may expose it via .capacity or channel stats
        return {
            'connections': None,
            'status': 'healthy',
            'detail': 'Channel layer available',
        }
    except Exception as e:
        return {
            'connections': None,
            'status': 'unavailable',
            'detail': str(e),
        }


def get_all_infrastructure_metrics():
    """Collect all infrastructure metrics."""
    return {
        'cpu': get_cpu_metrics(),
        'memory': get_memory_metrics(),
        'disk': get_disk_metrics(),
        'requests': get_request_metrics(),
        'celery': get_celery_metrics(),
        'websockets': get_websocket_metrics(),
    }
