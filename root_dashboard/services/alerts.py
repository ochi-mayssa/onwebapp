"""Centralized alert management for the Root Dashboard Operations Center.

Aggregates alerts from multiple sources:
- Application errors (ActivityLog)
- Failed payments
- ERP failures
- Security events
- Workflow failures
- High resource usage

Each alert includes severity, title, description, timestamp, related service,
status, and available actions.
"""
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from datetime import timedelta

User = get_user_model()


def _make_alert(severity, title, description, service='system', category='general',
                status='open', related_object=None, timestamp=None):
    """Build a standardized alert dict."""
    return {
        'id': None,
        'severity': severity,
        'title': title,
        'description': description,
        'service': service,
        'category': category,
        'status': status,
        'related_object': related_object,
        'timestamp': timestamp or timezone.now(),
    }


def _time_windows():
    """Return commonly used time boundaries."""
    now = timezone.now()
    return {
        'now': now,
        '1h': now - timedelta(hours=1),
        '24h': now - timedelta(hours=24),
        '7d': now - timedelta(days=7),
        '30d': now - timedelta(days=30),
    }


def get_security_alerts():
    """Detect security-related alerts."""
    alerts = []
    w = _time_windows()

    # Inactive staff accounts
    inactive_staff = User.objects.filter(is_staff=True, is_active=False).count()
    if inactive_staff > 0:
        alerts.append(_make_alert(
            severity='warning',
            title=f'{inactive_staff} inactive staff account(s)',
            description='Staff accounts are disabled but still marked as staff. Review and revoke access if needed.',
            service='auth',
            category='security',
        ))

    # Recent failed login attempts (from ActivityLog)
    try:
        from users.models import ActivityLog
        failed_logins = ActivityLog.objects.filter(
            action='login_failed',
            timestamp__gte=w['24h'],
        ).count()
        if failed_logins > 3:
            alerts.append(_make_alert(
                severity='warning',
                title=f'{failed_logins} failed login attempts (24h)',
                description='Multiple failed login attempts detected. Possible brute force attempt.',
                service='auth',
                category='security',
                timestamp=w['24h'],
            ))
    except (ImportError, Exception):
        pass

    # Superuser count check
    superuser_count = User.objects.filter(is_superuser=True).count()
    if superuser_count > 5:
        alerts.append(_make_alert(
            severity='info',
            title=f'{superuser_count} superuser accounts',
            description='Consider reviewing superuser count for security best practices.',
            service='auth',
            category='security',
        ))

    return alerts


def get_application_alerts():
    """Detect application-level alerts."""
    alerts = []
    w = _time_windows()

    # Delayed projects
    try:
        from projects.models import Project
        delayed = Project.objects.filter(current_status='DELAYED').count()
        if delayed > 0:
            alerts.append(_make_alert(
                severity='warning',
                title=f'{delayed} delayed project(s)',
                description='Projects are behind schedule and may need attention.',
                service='projects',
                category='operations',
            ))
    except (ImportError, Exception):
        pass

    # Blocked tasks
    try:
        from projects.models import PhaseTask
        blocked = PhaseTask.objects.filter(status='BLOCKED').count()
        if blocked > 0:
            alerts.append(_make_alert(
                severity='warning',
                title=f'{blocked} blocked task(s)',
                description='Tasks blocked in project workflows require resolution.',
                service='projects',
                category='operations',
            ))
    except (ImportError, Exception):
        pass

    # Unverified recent users
    try:
        from users.models import UserProfile
        unverified = UserProfile.objects.filter(
            email_verified=False,
            created_at__gte=w['7d'],
        ).count()
        if unverified > 3:
            alerts.append(_make_alert(
                severity='info',
                title=f'{unverified} users with unverified emails (7d)',
                description='Consider sending verification reminder emails.',
                service='users',
                category='engagement',
            ))
    except (ImportError, Exception):
        pass

    return alerts


def get_payment_alerts():
    """Detect payment-related alerts."""
    alerts = []

    # Failed payments
    try:
        from payments.models import Payment
        failed = Payment.objects.exclude(
            status__in=('succeeded', 'completed')
        ).count()
        if failed > 0:
            alerts.append(_make_alert(
                severity='error',
                title=f'{failed} failed payment(s)',
                description='Payment failures require follow-up with affected customers.',
                service='payments',
                category='billing',
            ))
    except (ImportError, Exception):
        pass

    # Overdue invoices
    try:
        from projects.models import Invoice
        from django.utils import timezone as tz
        overdue = Invoice.objects.filter(
            status='ISSUED',
            due_date__lt=tz.now().date(),
        ).count()
        if overdue > 0:
            alerts.append(_make_alert(
                severity='warning',
                title=f'{overdue} overdue invoice(s)',
                description='Invoices past due date require follow-up.',
                service='invoices',
                category='billing',
            ))
    except (ImportError, Exception):
        pass

    return alerts


def get_workflow_alerts():
    """Detect workflow/automation alerts."""
    alerts = []

    try:
        from rpa_dashboard.models import WorkflowRun
        failed_runs = WorkflowRun.objects.filter(
            status__in=('FAILURE', 'FAILED', 'ERROR'),
        ).count()
        if failed_runs > 0:
            alerts.append(_make_alert(
                severity='error',
                title=f'{failed_runs} failed workflow run(s)',
                description='Automation workflows have failed and may need investigation.',
                service='automation',
                category='operations',
            ))
    except (ImportError, Exception):
        pass

    try:
        from seo_analyzer.models import SEOTask
        failed_seo = SEOTask.objects.filter(
            status__in=('failed', 'error'),
        ).count()
        if failed_seo > 0:
            alerts.append(_make_alert(
                severity='warning',
                title=f'{failed_seo} failed SEO task(s)',
                description='SEO analysis tasks have failed.',
                service='seo',
                category='operations',
            ))
    except (ImportError, Exception):
        pass

    return alerts


def get_crm_alerts():
    """Detect CRM-related alerts."""
    alerts = []

    try:
        from crm.models import Customer
        churned = Customer.objects.filter(lifecycle_stage='CHURNED').count()
        if churned > 0:
            alerts.append(_make_alert(
                severity='warning',
                title=f'{churned} churned customer(s)',
                description='Customers have left the platform. Review retention strategies.',
                service='crm',
                category='engagement',
            ))
    except (ImportError, Exception):
        pass

    # Low health score customers
    try:
        from crm.models import Customer
        low_health = Customer.objects.filter(
            current_health_score__lt=40,
        ).count()
        if low_health > 0:
            alerts.append(_make_alert(
                severity='warning',
                title=f'{low_health} customer(s) with low health score',
                description='Customers with health score below 40 may be at risk of churning.',
                service='crm',
                category='engagement',
            ))
    except (ImportError, Exception):
        pass

    return alerts


def get_all_alerts():
    """Aggregate all alerts from all sources."""
    all_alerts = []
    all_alerts.extend(get_security_alerts())
    all_alerts.extend(get_application_alerts())
    all_alerts.extend(get_payment_alerts())
    all_alerts.extend(get_workflow_alerts())
    all_alerts.extend(get_crm_alerts())

    # Sort by severity: error > warning > info
    severity_order = {'error': 0, 'warning': 1, 'info': 2}
    all_alerts.sort(key=lambda a: severity_order.get(a['severity'], 3))

    return all_alerts


def get_alert_summary(alerts):
    """Return a summary count of alerts by severity."""
    return {
        'total': len(alerts),
        'error': sum(1 for a in alerts if a['severity'] == 'error'),
        'warning': sum(1 for a in alerts if a['severity'] == 'warning'),
        'info': sum(1 for a in alerts if a['severity'] == 'info'),
    }
