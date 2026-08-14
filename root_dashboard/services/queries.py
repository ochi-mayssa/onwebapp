"""Services for querying platform data for the Root Dashboard.

All queries use existing OnWebApp models. No fake data is generated.
Metrics return real values from the database or safe unavailable states.
"""
from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum, Avg, F
from django.db.models.functions import TruncMonth, TruncWeek, TruncDay
from django.utils import timezone

from datetime import timedelta

User = get_user_model()


# ---------------------------------------------------------------------------
# Time Window Helpers
# ---------------------------------------------------------------------------

def _time_windows():
    """Return commonly used time window boundaries."""
    now = timezone.now()
    return {
        'now': now,
        'today': now.replace(hour=0, minute=0, second=0, microsecond=0),
        'yesterday': (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
        '7d': now - timedelta(days=7),
        '30d': now - timedelta(days=30),
        '90d': now - timedelta(days=90),
        '12m': now - timedelta(days=365),
    }


# ---------------------------------------------------------------------------
# 1. User Metrics
# ---------------------------------------------------------------------------

def get_user_metrics():
    """
    Return real user statistics from the Django User model.
    """
    w = _time_windows()

    total = User.objects.count()
    active = User.objects.filter(is_active=True).count()
    staff = User.objects.filter(is_staff=True).count()
    superusers = User.objects.filter(is_superuser=True).count()
    new_today = User.objects.filter(date_joined__gte=w['today']).count()
    new_7d = User.objects.filter(date_joined__gte=w['7d']).count()
    new_30d = User.objects.filter(date_joined__gte=w['30d']).count()
    suspended = User.objects.filter(is_active=False).count()

    return {
        'total': total,
        'active': active,
        'staff': staff,
        'superusers': superusers,
        'new_today': new_today,
        'new_7d': new_7d,
        'new_30d': new_30d,
        'suspended': suspended,
    }


# ---------------------------------------------------------------------------
# 2. Customer Metrics (CRM)
# ---------------------------------------------------------------------------

def get_customer_metrics():
    """
    Return real customer statistics from the CRM Customer model.
    Falls back gracefully if CRM is not available.
    """
    try:
        from crm.models import Customer
    except ImportError:
        return _unavailable('CRM module not available')

    w = _time_windows()

    total = Customer.objects.count()

    lifecycle_counts = dict(
        Customer.objects.values_list('lifecycle_stage')
        .annotate(count=Count('id'))
        .values_list('lifecycle_stage', 'count')
    )

    active = sum(
        lifecycle_counts.get(stage, 0)
        for stage in ('ACTIVE_CLIENT', 'RETAINED_CLIENT')
    )
    at_risk = lifecycle_counts.get('CHURNED', 0)
    leads = lifecycle_counts.get('LEAD', 0) + lifecycle_counts.get('QUALIFIED_LEAD', 0)

    new_30d = Customer.objects.filter(created_at__gte=w['30d']).count()
    new_7d = Customer.objects.filter(created_at__gte=w['7d']).count()

    # Health scores
    health_stats = Customer.objects.aggregate(
        avg_health=Avg('current_health_score'),
    )

    return {
        'total': total,
        'active': active,
        'at_risk': at_risk,
        'leads': leads,
        'new_30d': new_30d,
        'new_7d': new_7d,
        'avg_health_score': round(health_stats['avg_health'] or 0, 1),
    }


# ---------------------------------------------------------------------------
# 3. Project Metrics
# ---------------------------------------------------------------------------

def get_project_metrics():
    """
    Return real project statistics from the projects.Project model.
    """
    try:
        from projects.models import Project
    except ImportError:
        return _unavailable('Projects module not available')

    w = _time_windows()

    total = Project.objects.count()

    status_counts = dict(
        Project.objects.values_list('current_status')
        .annotate(count=Count('id'))
        .values_list('current_status', 'count')
    )

    active_statuses = ('PLANNING', 'DESIGN', 'DEVELOPMENT', 'DELIVERY')
    active = sum(status_counts.get(s, 0) for s in active_statuses)
    completed = status_counts.get('COMPLETED', 0)
    on_hold = status_counts.get('ON_HOLD', 0)
    cancelled = status_counts.get('CANCELLED', 0)
    delayed = status_counts.get('DELAYED', 0)

    # Phase breakdown
    try:
        from projects.models import ProjectPhase
        phase_counts = dict(
            ProjectPhase.objects.values_list('status')
            .annotate(count=Count('id'))
            .values_list('status', 'count')
        )
        in_progress_phases = phase_counts.get('IN_PROGRESS', 0)
        blocked_phases = phase_counts.get('DELAYED', 0)
    except (ImportError, Exception):
        in_progress_phases = 0
        blocked_phases = 0

    new_30d = Project.objects.filter(created_at__gte=w['30d']).count()
    new_7d = Project.objects.filter(created_at__gte=w['7d']).count()

    # Average progress
    avg_progress = Project.objects.aggregate(avg=Avg('progress_percentage'))['avg'] or 0

    return {
        'total': total,
        'active': active,
        'completed': completed,
        'on_hold': on_hold,
        'cancelled': cancelled,
        'delayed': delayed,
        'in_progress_phases': in_progress_phases,
        'blocked_phases': blocked_phases,
        'new_30d': new_30d,
        'new_7d': new_7d,
        'avg_progress': round(avg_progress, 1),
    }


# ---------------------------------------------------------------------------
# 4. Subscription Metrics
# ---------------------------------------------------------------------------

def get_subscription_metrics():
    """
    Return real subscription statistics from the UserSubscription model.
    """
    try:
        from users.models import UserSubscription
    except ImportError:
        return _unavailable('Subscriptions module not available')

    now = timezone.now()

    total = UserSubscription.objects.count()
    active = UserSubscription.objects.filter(
        is_active=True,
        end_date__gte=now,
    ).count()

    # Expired (end_date passed)
    expired = UserSubscription.objects.filter(
        is_active=True,
        end_date__lt=now,
    ).count()

    # Never activated / trial
    trial = UserSubscription.objects.filter(
        is_active=True,
        start_date__isnull=True,
    ).count()

    # Cancelled (inactive with a plan)
    cancelled = UserSubscription.objects.filter(
        is_active=False,
        plan__isnull=False,
    ).count()

    # Free tier (no plan)
    free = UserSubscription.objects.filter(plan__isnull=True).count()

    return {
        'total': total,
        'active': active,
        'expired': expired,
        'trial': trial,
        'cancelled': cancelled,
        'free': free,
    }


# ---------------------------------------------------------------------------
# 5. Revenue & Payment Metrics
# ---------------------------------------------------------------------------

def get_revenue_metrics():
    """
    Return real revenue statistics from Payment and Invoice models.
    """
    w = _time_windows()

    # --- Stripe/Payment records ---
    payment_total_cents = 0
    payment_count = 0
    payment_failed = 0
    try:
        from payments.models import Payment
        agg = Payment.objects.aggregate(
            total=Sum('amount'),
            count=Count('id'),
        )
        payment_total_cents = agg['total'] or 0
        payment_count = agg['count'] or 0
        payment_failed = Payment.objects.exclude(status__in=('succeeded', 'completed')).count()
    except (ImportError, Exception):
        pass

    # --- Project Invoices ---
    invoice_total = 0
    invoice_paid = 0
    invoice_outstanding = 0
    try:
        from projects.models import Invoice
        inv_agg = Invoice.objects.aggregate(
            total=Sum('amount'),
        )
        invoice_total = float(inv_agg['total'] or 0)
        invoice_paid = float(
            Invoice.objects.filter(status='PAID').aggregate(t=Sum('amount'))['t'] or 0
        )
        invoice_outstanding = invoice_total - invoice_paid
    except (ImportError, Exception):
        pass

    # --- Subscription revenue (from PaymentPlan prices) ---
    subscription_mrr = 0
    try:
        from users.models import UserSubscription
        from payments.models import PaymentPlan
        active_subs = UserSubscription.objects.filter(
            is_active=True,
            plan__isnull=False,
        ).select_related('plan')
        for sub in active_subs:
            if sub.plan and sub.plan.price:
                duration = sub.plan.duration_days or 30
                monthly = float(sub.plan.price) * (30.0 / duration)
                subscription_mrr += monthly
    except (ImportError, Exception):
        pass

    return {
        'total_revenue_cents': payment_total_cents,
        'total_revenue_display': f"${payment_total_cents / 100:,.2f}" if payment_total_cents else '$0.00',
        'payment_count': payment_count,
        'payment_failed': payment_failed,
        'invoice_total': invoice_total,
        'invoice_paid': invoice_paid,
        'invoice_outstanding': round(invoice_outstanding, 2),
        'subscription_mrr': round(subscription_mrr, 2),
        'subscription_mrr_display': f"${subscription_mrr:,.2f}",
        'data_available': payment_count > 0 or invoice_total > 0,
    }


# ---------------------------------------------------------------------------
# 6. Service Overview
# ---------------------------------------------------------------------------

def get_service_overview():
    """
    Return compact status for major OnWebApp modules.
    """
    services = []

    # Branding
    try:
        from branding.models import BrandingRequest
        br_total = BrandingRequest.objects.count()
        br_active = BrandingRequest.objects.exclude(
            status__in=('COMPLETED', 'ARCHIVED', 'CANCELLED')
        ).count()
        services.append({
            'name': 'Branding',
            'icon': 'fas fa-palette',
            'color': '#8b5cf6',
            'status': 'active',
            'stats': {'total': br_total, 'active': br_active},
        })
    except (ImportError, Exception):
        services.append({
            'name': 'Branding',
            'icon': 'fas fa-palette',
            'color': '#8b5cf6',
            'status': 'unavailable',
            'stats': {},
        })

    # ERP
    try:
        from users.models import UserERP
        erp_total = UserERP.objects.count()
        erp_active = UserERP.objects.filter(status='active').count()
        services.append({
            'name': 'ERP',
            'icon': 'fas fa-industry',
            'color': '#f97316',
            'status': 'active',
            'stats': {'total': erp_total, 'active': erp_active},
        })
    except (ImportError, Exception):
        services.append({
            'name': 'ERP',
            'icon': 'fas fa-industry',
            'color': '#f97316',
            'status': 'unavailable',
            'stats': {},
        })

    # CRM
    try:
        from crm.models import Customer
        crm_total = Customer.objects.count()
        crm_active = Customer.objects.filter(
            lifecycle_stage__in=('ACTIVE_CLIENT', 'RETAINED_CLIENT')
        ).count()
        services.append({
            'name': 'CRM',
            'icon': 'fas fa-users',
            'color': '#0ea5e9',
            'status': 'active',
            'stats': {'total': crm_total, 'active': crm_active},
        })
    except (ImportError, Exception):
        services.append({
            'name': 'CRM',
            'icon': 'fas fa-users',
            'color': '#0ea5e9',
            'status': 'unavailable',
            'stats': {},
        })

    # SEO Analyzer
    try:
        from seo_analyzer.models import SEOAnalysis
        seo_total = SEOAnalysis.objects.count()
        services.append({
            'name': 'SEO Analyzer',
            'icon': 'fas fa-search',
            'color': '#10b981',
            'status': 'active',
            'stats': {'total': seo_total},
        })
    except (ImportError, Exception):
        services.append({
            'name': 'SEO Analyzer',
            'icon': 'fas fa-search',
            'color': '#10b981',
            'status': 'unavailable',
            'stats': {},
        })

    # Projects
    try:
        from projects.models import Project
        proj_total = Project.objects.count()
        proj_active = Project.objects.exclude(
            current_status__in=('COMPLETED', 'CANCELLED')
        ).count()
        services.append({
            'name': 'Projects',
            'icon': 'fas fa-project-diagram',
            'color': '#6366f1',
            'status': 'active',
            'stats': {'total': proj_total, 'active': proj_active},
        })
    except (ImportError, Exception):
        services.append({
            'name': 'Projects',
            'icon': 'fas fa-project-diagram',
            'color': '#6366f1',
            'status': 'unavailable',
            'stats': {},
        })

    # Community
    try:
        from community.models import CommunityPost
        comm_total = CommunityPost.objects.count()
        services.append({
            'name': 'Community',
            'icon': 'fas fa-comments',
            'color': '#ec4899',
            'status': 'active',
            'stats': {'total': comm_total},
        })
    except (ImportError, Exception):
        services.append({
            'name': 'Community',
            'icon': 'fas fa-comments',
            'color': '#ec4899',
            'status': 'unavailable',
            'stats': {},
        })

    # Social Proof
    try:
        from social_proof.models import SocialEvent
        sp_total = SocialEvent.objects.count()
        services.append({
            'name': 'Social Proof',
            'icon': 'fas fa-bullhorn',
            'color': '#14b8a6',
            'status': 'active',
            'stats': {'total': sp_total},
        })
    except (ImportError, Exception):
        services.append({
            'name': 'Social Proof',
            'icon': 'fas fa-bullhorn',
            'color': '#14b8a6',
            'status': 'unavailable',
            'stats': {},
        })

    # Chatbot
    try:
        from chatbot.models import ChatSession
        chat_total = ChatSession.objects.count()
        services.append({
            'name': 'Chatbot',
            'icon': 'fas fa-robot',
            'color': '#a855f7',
            'status': 'active',
            'stats': {'total': chat_total},
        })
    except (ImportError, Exception):
        services.append({
            'name': 'Chatbot',
            'icon': 'fas fa-robot',
            'color': '#a855f7',
            'status': 'unavailable',
            'stats': {},
        })

    return services


# ---------------------------------------------------------------------------
# 7. Chart Data (Trends)
# ---------------------------------------------------------------------------

def get_user_growth_chart(days=90):
    """User growth over the last N days, bucketed by week."""
    w = _time_windows()
    start = w['now'] - timedelta(days=days)

    data = (
        User.objects
        .filter(date_joined__gte=start)
        .annotate(period=TruncWeek('date_joined'))
        .values('period')
        .annotate(count=Count('id'))
        .order_by('period')
    )

    labels = []
    values = []
    for row in data:
        labels.append(row['period'].strftime('%b %d'))
        values.append(row['count'])

    return {'labels': labels, 'values': values, 'title': 'User Growth'}


def get_project_activity_chart(days=90):
    """Project creation over the last N days, bucketed by week."""
    try:
        from projects.models import Project
    except ImportError:
        return {'labels': [], 'values': [], 'title': 'Project Activity', 'unavailable': True}

    w = _time_windows()
    start = w['now'] - timedelta(days=days)

    data = (
        Project.objects
        .filter(created_at__gte=start)
        .annotate(period=TruncWeek('created_at'))
        .values('period')
        .annotate(count=Count('id'))
        .order_by('period')
    )

    labels = []
    values = []
    for row in data:
        labels.append(row['period'].strftime('%b %d'))
        values.append(row['count'])

    return {'labels': labels, 'values': values, 'title': 'Project Activity'}


def get_revenue_chart(days=90):
    """Revenue over the last N days from Invoice model, bucketed by month."""
    try:
        from projects.models import Invoice
    except ImportError:
        return {'labels': [], 'values': [], 'title': 'Revenue', 'unavailable': True}

    w = _time_windows()
    start = w['now'] - timedelta(days=days)

    data = (
        Invoice.objects
        .filter(issued_date__gte=start.date() if hasattr(start, 'date') else start)
        .annotate(period=TruncMonth('issued_date'))
        .values('period')
        .annotate(total=Sum('amount'))
        .order_by('period')
    )

    labels = []
    values = []
    for row in data:
        labels.append(row['period'].strftime('%b %Y'))
        values.append(float(row['total'] or 0))

    return {'labels': labels, 'values': values, 'title': 'Revenue'}


def get_subscription_chart(days=90):
    """Subscription creation over the last N days, bucketed by week."""
    try:
        from users.models import UserSubscription
    except ImportError:
        return {'labels': [], 'values': [], 'title': 'Subscriptions', 'unavailable': True}

    w = _time_windows()
    start = w['now'] - timedelta(days=days)

    data = (
        UserSubscription.objects
        .filter(created_at__gte=start)
        .annotate(period=TruncWeek('created_at'))
        .values('period')
        .annotate(count=Count('id'))
        .order_by('period')
    )

    labels = []
    values = []
    for row in data:
        labels.append(row['period'].strftime('%b %d'))
        values.append(row['count'])

    return {'labels': labels, 'values': values, 'title': 'Subscriptions'}


# ---------------------------------------------------------------------------
# 8. Alerts & Issues
# ---------------------------------------------------------------------------

def get_alerts():
    """Return real platform alerts/issues that require attention."""
    alerts = []
    w = _time_windows()

    # Inactive staff accounts
    inactive_staff = User.objects.filter(
        is_staff=True, is_active=False
    ).count()
    if inactive_staff > 0:
        alerts.append({
            'severity': 'warning',
            'title': f'{inactive_staff} inactive staff account(s)',
            'detail': 'Staff accounts are disabled but still marked as staff.',
            'category': 'security',
        })

    # Users without email verification (recent)
    try:
        from users.models import UserProfile
        unverified = UserProfile.objects.filter(
            email_verified=False,
            created_at__gte=w['30d'],
        ).count()
        if unverified > 0:
            alerts.append({
                'severity': 'info',
                'title': f'{unverified} users with unverified emails (30d)',
                'detail': 'Consider sending verification reminder emails.',
                'category': 'engagement',
            })
    except (ImportError, Exception):
        pass

    # Delayed projects
    try:
        from projects.models import Project
        delayed = Project.objects.filter(current_status='DELAYED').count()
        if delayed > 0:
            alerts.append({
                'severity': 'warning',
                'title': f'{delayed} delayed project(s)',
                'detail': 'Projects behind schedule may need attention.',
                'category': 'performance',
            })
    except (ImportError, Exception):
        pass

    # Blocked tasks
    try:
        from projects.models import PhaseTask
        blocked = PhaseTask.objects.filter(status='BLOCKED').count()
        if blocked > 0:
            alerts.append({
                'severity': 'warning',
                'title': f'{blocked} blocked task(s)',
                'detail': 'Tasks blocked in project workflows.',
                'category': 'performance',
            })
    except (ImportError, Exception):
        pass

    # Failed payments
    try:
        from payments.models import Payment
        failed_payments = Payment.objects.exclude(
            status__in=('succeeded', 'completed')
        ).count()
        if failed_payments > 0:
            alerts.append({
                'severity': 'error',
                'title': f'{failed_payments} failed payment(s)',
                'detail': 'Payment failures require follow-up.',
                'category': 'billing',
            })
    except (ImportError, Exception):
        pass

    # Churned customers
    try:
        from crm.models import Customer
        churned = Customer.objects.filter(lifecycle_stage='CHURNED').count()
        if churned > 0:
            alerts.append({
                'severity': 'warning',
                'title': f'{churned} churned customer(s)',
                'detail': 'Customers who have left the platform.',
                'category': 'engagement',
            })
    except (ImportError, Exception):
        pass

    # No alerts = all clear
    if not alerts:
        alerts.append({
            'severity': 'success',
            'title': 'All systems operational',
            'detail': 'No issues detected. Platform is running smoothly.',
            'category': 'system',
        })

    return alerts


# ---------------------------------------------------------------------------
# 9. Recent Activity
# ---------------------------------------------------------------------------

def get_recent_activity(limit=12):
    """Return recent platform activity from ActivityLog."""
    activity_items = []

    try:
        from users.models import ActivityLog
        logs = (
            ActivityLog.objects
            .select_related('user')
            .order_by('-timestamp')[:limit]
        )
        for log in logs:
            activity_items.append({
                'user': log.user.email if log.user else 'System',
                'action': log.action,
                'timestamp': log.timestamp,
                'ip_address': log.ip_address,
            })
        return activity_items
    except (ImportError, Exception):
        pass

    # Fallback: recent user registrations
    recent_users = User.objects.order_by('-date_joined')[:limit]
    for u in recent_users:
        activity_items.append({
            'user': u.email,
            'action': 'account_created',
            'timestamp': u.date_joined,
            'ip_address': None,
        })

    return activity_items


# ---------------------------------------------------------------------------
# 10. Platform Health
# ---------------------------------------------------------------------------

def get_platform_health():
    """Return platform health indicators."""
    health = {
        'database': {'status': 'ok', 'label': 'Database'},
        'auth_system': {'status': 'ok', 'label': 'Authentication'},
        'user_model': {'status': 'ok', 'label': 'User Model'},
    }

    # Database check
    try:
        User.objects.exists()
        health['database']['status'] = 'ok'
    except Exception as e:
        health['database']['status'] = 'error'
        health['database']['detail'] = str(e)

    # Auth system check
    try:
        from django.contrib.auth.models import Group, Permission
        Group.objects.exists()
        Permission.objects.exists()
        health['auth_system']['status'] = 'ok'
    except Exception as e:
        health['auth_system']['status'] = 'error'
        health['auth_system']['detail'] = str(e)

    # User model check
    try:
        User.objects.count()
        health['user_model']['status'] = 'ok'
    except Exception as e:
        health['user_model']['status'] = 'error'
        health['user_model']['detail'] = str(e)

    return health


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unavailable(reason):
    """Return a standard unavailable-state dict."""
    return {
        'unavailable': True,
        'reason': reason,
        'total': 0,
        'active': 0,
    }
