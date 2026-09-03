from django.conf import settings
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.urls import reverse, NoReverseMatch
from datetime import datetime, timedelta
import json


def _get_seo_statuses():
    statuses = {
        'website_checker': 'Not Configured',
        'free_website_check': 'Not Configured',
        'url_intelligence': 'Not Configured',
        'internal_links': 'Not Configured',
        'external_links': 'Not Configured',
        'backlinks': 'Not Configured',
        'sitemap_intelligence': 'Not Configured',
        'seo_monitoring': 'Not Configured',
        'seo_kpi_analysis': 'Not Configured',
    }
    try:
        from seo_analyzer.models import SEOMonitoringSnapshot, SEOTask

        snapshots = SEOMonitoringSnapshot.objects.order_by('-created_at')[:5]
        tasks = list(SEOTask.objects.all()[:10])

        if snapshots.exists():
            latest = snapshots.first()
            score = 0
            issues = 0
            try:
                score = float(latest.health_score or 0)
                issues = int(latest.issues_count or 0)
            except (TypeError, ValueError):
                pass
            if score >= 80 and issues == 0:
                statuses['seo_monitoring'] = 'Healthy'
            elif score >= 50 or issues < 5:
                statuses['seo_monitoring'] = 'Warning'
            elif issues >= 5:
                statuses['seo_monitoring'] = 'Error'
            else:
                statuses['seo_monitoring'] = 'Not Configured'

        if tasks:
            error_count = 0
            warning_count = 0
            done_count = 0
            for t in tasks:
                s = getattr(t, 'status', '')
                if s in ('failed', 'error'):
                    error_count += 1
                elif s in ('running', 'queued', 'partial'):
                    warning_count += 1
                elif s in ('completed', 'success', 'done'):
                    done_count += 1
            if error_count > 0:
                statuses['website_checker'] = 'Error'
            elif warning_count > 0:
                statuses['website_checker'] = 'Warning'
            elif done_count > 0:
                statuses['website_checker'] = 'Healthy'
    except Exception:
        pass

    try:
        from seo_analyzer.models import URLIntelligenceTask
        qs = list(URLIntelligenceTask.objects.all()[:10])
        if qs:
            err = sum(1 for x in qs if getattr(x, 'status', '') in ('failed', 'error'))
            run = sum(1 for x in qs if getattr(x, 'status', '') in ('running', 'queued'))
            done = sum(1 for x in qs if getattr(x, 'status', '') in ('completed', 'success'))
            if err > 0:
                statuses['url_intelligence'] = 'Error'
            elif run > 0:
                statuses['url_intelligence'] = 'Warning'
            elif done > 0:
                statuses['url_intelligence'] = 'Healthy'
    except Exception:
        pass

    try:
        from seo_analyzer.models import SEOMonitoringSnapshot
        link_snapshots = SEOMonitoringSnapshot.objects.filter(
            analysis_type__in=['internal', 'external']
        ).order_by('-created_at')[:5]
        if link_snapshots.exists():
            latest = link_snapshots.first()
            broken = getattr(latest, 'broken_links', 0) or 0
            total = (getattr(latest, 'internal_links', 0) or 0) + (getattr(latest, 'external_links', 0) or 0)
            if broken > 0:
                statuses['internal_links'] = 'Error'
                statuses['external_links'] = 'Warning'
            elif total > 0:
                statuses['internal_links'] = 'Healthy'
                statuses['external_links'] = 'Healthy'
    except Exception:
        pass

    return statuses


def _get_automation_statuses():
    """
    Return the real status of the Automation modules displayed
    in Platform Monitoring.

    Workflow Automation is based on the latest workflow run only.
    Old failures do not make the current workflow unhealthy.
    """

    statuses = {
        'email_automation': 'Not Configured',
        'workflow_automation': 'Not Configured',
        'task_scheduler': 'Not Configured',
        'execution_logs': 'Not Configured',
        'current_status': 'Not Configured',
    }

    # =====================================================
    # 1. WORKFLOW AUTOMATION
    # =====================================================

    try:
        from rpa_dashboard.models import WorkflowRun

        latest_run = (
            WorkflowRun.objects
            .order_by('-started_at')
            .first()
        )

        if latest_run:
            run_status = str(
                getattr(latest_run, 'status', '') or ''
            ).strip().upper()

            # ---------------------------------------------
            # Latest execution succeeded
            # ---------------------------------------------
            if run_status in (
                'SUCCESS',
                'COMPLETED',
                'DONE',
                'PASS',
            ):
                statuses['workflow_automation'] = 'Healthy'

            # ---------------------------------------------
            # Latest execution is still running
            # ---------------------------------------------
            elif run_status in (
                'RUNNING',
                'PENDING',
                'STARTED',
                'QUEUED',
            ):
                statuses['workflow_automation'] = 'Warning'

            # ---------------------------------------------
            # Latest execution failed
            # ---------------------------------------------
            elif run_status in (
                'FAILURE',
                'FAILED',
                'FAIL',
                'ERROR',
            ):
                statuses['workflow_automation'] = 'Error'

            else:
                statuses['workflow_automation'] = 'Warning'

            # If WorkflowRun records exist, execution logging exists
            statuses['execution_logs'] = 'Healthy'

    except Exception as exc:
        print(
            "Platform Monitoring - Workflow status error:",
            exc
        )

    # =====================================================
    # 2. TASK SCHEDULER / CELERY BEAT
    # =====================================================

    try:
        from django.conf import settings

        beat_schedule = getattr(
            settings,
            'CELERY_BEAT_SCHEDULE',
            {}
        )

        if beat_schedule and len(beat_schedule) > 0:
            statuses['task_scheduler'] = 'Healthy'
        else:
            statuses['task_scheduler'] = 'Not Configured'

    except Exception as exc:
        print(
            "Platform Monitoring - Scheduler status error:",
            exc
        )

    # =====================================================
    # 3. EMAIL AUTOMATION
    # =====================================================

    # Keep this Not Configured until a real email automation
    # system / scheduled email workflow is detected.
    statuses['email_automation'] = 'Not Configured'

    # =====================================================
    # 4. CURRENT AUTOMATION STATUS
    # =====================================================

    automation_components = [
        statuses['workflow_automation'],
        statuses['task_scheduler'],
        statuses['execution_logs'],
    ]

    if 'Error' in automation_components:
        statuses['current_status'] = 'Error'

    elif 'Warning' in automation_components:
        statuses['current_status'] = 'Warning'

    elif all(
        status == 'Healthy'
        for status in automation_components
    ):
        statuses['current_status'] = 'Healthy'

    elif 'Healthy' in automation_components:
        statuses['current_status'] = 'Warning'

    else:
        statuses['current_status'] = 'Not Configured'

    return statuses
def _status_badge(status):
    if status == 'Healthy':
        return {
            'label': _('Healthy'),
            'class': 'bg-success-soft text-success',
            'dot': 'bg-success',
            'icon': 'check-circle',
        }
    if status == 'Warning':
        return {
            'label': _('Warning'),
            'class': 'bg-warning-soft text-warning',
            'dot': 'bg-warning',
            'icon': 'alert-triangle',
        }
    if status == 'Error':
        return {
            'label': _('Error'),
            'class': 'bg-danger-soft text-danger',
            'dot': 'bg-danger',
            'icon': 'x-circle',
        }
    return {
        'label': _('Not Configured'),
        'class': 'bg-secondary-soft text-secondary',
        'dot': 'bg-secondary',
        'icon': 'settings',
    }


_STATUS_ORDER = {'Error': 0, 'Warning': 1, 'Not Configured': 2, 'Healthy': 3}


def _rollup_status(modules):
    if not modules:
        return 'Not Configured'
    worst = 'Healthy'
    for m in modules:
        s = m.get('status', 'Not Configured')
        if _STATUS_ORDER.get(s, 99) < _STATUS_ORDER.get(worst, 99):
            worst = s
    return worst


def _route(route_name, *args, **kwargs):
    try:
        return reverse(route_name, args=args, kwargs=kwargs)
    except NoReverseMatch:
        try:
            return reverse(route_name)
        except NoReverseMatch:
            return ''


def _build_seo_modules():
    s = _get_seo_statuses()
    return [
        {'id': 'website_checker', 'name': _('Website Checker'), 'icon': 'search-check',
         'route': _route('seo_analyzer:checker'), 'status': s['website_checker'],
         'description': _('Full technical SEO audit for any website.')},
        {'id': 'free_website_check', 'name': _('Free Website Check'), 'icon': 'zap',
         'route': _route('seo_analyzer:free_pre_check'), 'status': s['free_website_check'],
         'description': _('Lightning-fast pre-check for instant insights.')},
        {'id': 'url_intelligence', 'name': _('URL Intelligence'), 'icon': 'brain',
         'route': _route('seo_analyzer:url_intelligence'), 'status': s['url_intelligence'],
         'description': _('Deep URL-level semantic & ranking intelligence.')},
        {'id': 'sitemap_intelligence', 'name': _('Sitemap Intelligence'), 'icon': 'map',
         'route': _route('seo_analyzer:sitemap'), 'status': s['sitemap_intelligence'],
         'description': _('XML sitemap analysis & indexability mapping.')},
        {'id': 'seo_monitoring', 'name': _('SEO Monitoring'), 'icon': 'activity',
         'route': _route('seo_analyzer:monitoring'), 'status': s['seo_monitoring'],
         'description': _('Continuous SEO health & KPI monitoring.')},
        {'id': 'seo_kpi_analysis', 'name': _('SEO KPI Analysis'), 'icon': 'bar-chart-3',
         'route': _route('services:seo_performance_dashboard'), 'status': s['seo_kpi_analysis'],
         'description': _('Executive KPI dashboard for SEO performance.')},
    ]


def _build_seo_links_modules():
    s = _get_seo_statuses()
    return [
        {'id': 'internal_links', 'name': _('Internal Links'), 'icon': 'link-2',
         'route': _route('seo_analyzer:link_checker'), 'status': s['internal_links'],
         'description': _('Working Links, Broken Links, Errors & Recommendations.')},
        {'id': 'external_links', 'name': _('External Links'), 'icon': 'external-link',
         'route': _route('seo_analyzer:link_checker'), 'status': s['external_links'],
         'description': _('External link inventory & quality audit.')},
        {'id': 'backlinks', 'name': _('Backlinks'), 'icon': 'arrow-left-right',
         'route': _route('seo_analyzer:backlinks'), 'status': s['backlinks'],
         'description': _('Backlink profile & authority analysis.')},
    ]


def _build_automation_modules():
    s = _get_automation_statuses()
    rpa = _route('rpa_dashboard')
    return [
        {'id': 'email_automation', 'name': _('Email Automation'), 'icon': 'mail',
         'route': rpa, 'status': s['email_automation'],
         'description': _('Automated email sequences & triggers.')},
        {'id': 'workflow_automation', 'name': _('Workflow Automation'), 'icon': 'git-branch',
         'route': rpa, 'status': s['workflow_automation'],
         'description': _('RPA-powered workflow execution engine.')},
        {'id': 'task_scheduler', 'name': _('Task Scheduler'), 'icon': 'clock',
         'route': _route('platform_monitoring:task_scheduler'),
         'status': s['task_scheduler'],
         'description': _('Cron & scheduled job orchestration.')},
       {'id': 'execution_logs', 'name': _('Execution Logs'), 'icon': 'file-text',
       'route': _route('platform_monitoring:execution_logs'),
       'status': s['execution_logs'],
        'description': _('Granular execution logs & audit trail.')},
        {
       'id': 'current_status',
      'name': _('Current Status'),
      'icon': 'activity',
      'route': _route('platform_monitoring:automation_status'),
      'status': 'Healthy',
      'description': _('Live automation execution status overview.'),
      },
    ]


def _build_iot_modules():
    iot = _route('services:iot_integration')
    pred = _route('services:predictive_maintenance')
    return [
        {'id': 'devices', 'name': _('Devices'), 'icon': 'cpu',
         'route': iot, 'status': 'Not Configured',
         'description': _('IoT device inventory & registry.')},
        {'id': 'sensors', 'name': _('Sensors'), 'icon': 'radio',
         'route': iot, 'status': 'Not Configured',
         'description': _('Sensor provisioning & telemetry streaming.')},
        {'id': 'reports', 'name': _('Reports'), 'icon': 'bar-chart-3',
         'route': pred, 'status': 'Not Configured',
         'description': _('IoT insights & operational reporting.')},
        {'id': 'alerts', 'name': _('Alerts'), 'icon': 'bell-ring',
         'route': pred, 'status': 'Not Configured',
         'description': _('Threshold-based alerting system.')},
        {'id': 'health', 'name': _('Health'), 'icon': 'heart-pulse',
         'route': pred, 'status': 'Not Configured',
         'description': _('Fleet health & predictive maintenance.')},
    ]


def _build_security_modules():
    return [
        {'id': 'threat_detection', 'name': _('Threat Detection'), 'icon': 'shield-alert',
         'route': '', 'status': 'Not Configured',
         'description': _('Real-time threat & anomaly detection.')},
        {'id': 'login_attempts', 'name': _('Login Attempts'), 'icon': 'log-in',
         'route': _route('users:profile_dashboard'), 'status': 'Not Configured',
         'description': _('Authentication attempt audit.')},
        {'id': 'file_integrity', 'name': _('File Integrity'), 'icon': 'shield-check',
         'route': '', 'status': 'Not Configured',
         'description': _('FIM-based file change detection.')},
        {'id': 'audit_logs', 'name': _('Audit Logs'), 'icon': 'scroll-text',
         'route': '', 'status': 'Not Configured',
         'description': _('Comprehensive audit trail & compliance.')},
        {'id': 'security_reports', 'name': _('Security Reports'), 'icon': 'file-shield',
         'route': '', 'status': 'Not Configured',
         'description': _('Executive security posture reports.')},
    ]
def _get_integration_statuses():
    """
    Return integration statuses for Platform Monitoring.

    This function checks whether the related Django routes
    are available. External integrations that cannot be
    verified locally remain Not Configured.
    """

    statuses = {
        'erp': 'Not Configured',
        'crm': 'Not Configured',
        'stripe': 'Not Configured',
        'google': 'Not Configured',
        'meta': 'Not Configured',
        'api_status': 'Not Configured',
    }

    # ERP
    try:
        if _route('services:erp_integration'):
            statuses['erp'] = 'Healthy'
    except Exception:
        pass

    # CRM
    try:
        if _route('crm:dashboard'):
            statuses['crm'] = 'Healthy'
    except Exception:
        pass

    # Stripe
    try:
        if _route('payments:plans'):
            statuses['stripe'] = 'Healthy'
    except Exception:
        pass

    # Google
    # No route/configuration is shown in the current
    # integration module, so keep it Not Configured.
    statuses['google'] = 'Not Configured'

    # Meta
    try:
        if _route('services:social_media_tracking'):
            statuses['meta'] = 'Healthy'
    except Exception:
        pass

    # Platform API
    try:
        if _route('api_status'):
            statuses['api_status'] = 'Healthy'
    except Exception:
        pass

    return statuses


def _build_integration_modules():
    s = _get_integration_statuses()

    return [
        {
            'id': 'erp',
            'name': _('ERP'),
            'icon': 'building-2',
            'route': _route('services:erp_integration'),
            'status': s['erp'],
            'description': _('ERP system integration status.')
        },
        {
            'id': 'crm',
            'name': _('CRM'),
            'icon': 'users-round',
            'route': _route('crm:dashboard'),
            'status': s['crm'],
            'description': _('CRM platform integration & sync.')
        },
        {
            'id': 'stripe',
            'name': _('Stripe'),
            'icon': 'credit-card',
            'route': _route('payments:plans'),
            'status': s['stripe'],
            'description': _('Stripe payments & billing.')
        },
        {
            'id': 'google',
            'name': _('Google'),
            'icon': 'globe',
            'route': '',
            'status': s['google'],
            'description': _('Google Workspace & Search integrations.')
        },
        {
            'id': 'meta',
            'name': _('Meta'),
            'icon': 'share-2',
            'route': _route('services:social_media_tracking'),
            'status': s['meta'],
            'description': _('Meta (Facebook/Instagram) APIs.')
        },
        {
            'id': 'api_status',
            'name': _('API Status'),
            'icon': 'plug-zap',
            'route': _route('api_status'),
            'status': s['api_status'],
            'description': _('Platform API health & uptime.')
        },
    ]

def _build_integration_modules():
    s = _get_integration_statuses()
    return [
        {'id': 'erp', 'name': _('ERP'), 'icon': 'building-2',
         'route': _route('services:erp_integration'), 'status': s['erp'],
         'description': _('ERP system integration status.')},
        {'id': 'crm', 'name': _('CRM'), 'icon': 'users-round',
         'route': _route('crm:dashboard'), 'status': s['crm'],
         'description': _('CRM platform integration & sync.')},
        {'id': 'stripe', 'name': _('Stripe'), 'icon': 'credit-card',
         'route': _route('payments:plans'), 'status': s['stripe'],
         'description': _('Stripe payments & billing.')},
        {'id': 'google', 'name': _('Google'), 'icon': 'globe',
         'route': '', 'status': s['google'],
         'description': _('Google Workspace & Search integrations.')},
        {'id': 'meta', 'name': _('Meta'), 'icon': 'share-2',
         'route': _route('services:social_media_tracking'), 'status': s['meta'],
         'description': _('Meta (Facebook/Instagram) APIs.')},
        {'id': 'api_status', 'name': _('API Status'), 'icon': 'plug-zap',
         'route': _route('api_status'), 'status': s['api_status'],
         'description': _('Platform API health & uptime.')},
    ]


def _build_standalone_modules():
    return [
        {'id': 'competitor_intelligence', 'name': _('Competitor Intelligence'), 'icon': 'binoculars',
         'route': _route('services:competitor_tracking'), 'status': 'Not Configured',
         'description': _('Market landscape & competitor benchmarking.'),
         'pm_route': _route('platform_monitoring:competitor')},
        {'id': 'social_intelligence', 'name': _('Social Intelligence'), 'icon': 'message-circle',
         'route': _route('services:social_media_tracking'), 'status': 'Not Configured',
         'description': _('Social Media KPI Analysis — followers, engagement, growth & sentiment tracking.'),
         'pm_route': _route('services:social_media_tracking')},
        {'id': 'digital_presence', 'name': _('Digital Presence'), 'icon': 'fingerprint',
         'route': _route('social_proof:dashboard'), 'status': 'Not Configured',
         'description': _('Brand presence & reputation analysis.'),
         'pm_route': _route('platform_monitoring:digital')},
    ]


def _with_badge(mod_list):
    for m in mod_list:
        m['badge'] = _status_badge(m['status'])
    return mod_list


def _get_operational_data():
    alerts = []
    activity = []
    logs = []
    upcoming_tasks = []
    try:
        from seo_analyzer.models import SEOTask
        for t in SEOTask.objects.order_by('-created_at')[:10]:
            s = getattr(t, 'status', '')
            t_id = getattr(t, 'id', '')
            if s in ('failed', 'error'):
                alerts.append({'time': getattr(t, 'created_at', None),
                               'severity': 'Error',
                               'message': _('SEO task failed: %(id)s') % {'id': t_id}})
            elif s in ('running',):
                activity.append({'time': getattr(t, 'created_at', None),
                                 'type': _('SEO Analysis'),
                                 'detail': _('Task %(id)s running') % {'id': t_id}})
            if getattr(t, 'created_at', None):
                logs.append({'time': getattr(t, 'created_at'),
                             'source': 'SEO',
                             'message': _('Task %(id)s · %(s)s') % {'id': t_id, 's': s}})
    except Exception:
        pass
    try:
        from rpa_dashboard.models import WorkflowRun
        for r in WorkflowRun.objects.order_by('-started_at')[:10]:
            s = getattr(r, 'status', '')
            r_id = getattr(r, 'id', '')
            if s in ('failed', 'error'):
                alerts.append({'time': getattr(r, 'completed_at') or getattr(r, 'started_at'),
                               'severity': 'Error',
                               'message': _('Workflow run failed: %(id)s') % {'id': r_id}})
            elif s in ('running', 'pending'):
                activity.append({'time': getattr(r, 'started_at'),
                                 'type': _('Automation'),
                                 'detail': _('Run %(id)s %(s)s') % {'id': r_id, 's': s}})
            if getattr(r, 'started_at', None):
                logs.append({'time': getattr(r, 'started_at'),
                             'source': _('Automation'),
                             'message': _('Run %(id)s · %(s)s') % {'id': r_id, 's': s}})
    except Exception:
        pass
    return {
        'alerts': alerts,
        'activity': activity,
        'logs': logs,
        'upcoming_tasks': upcoming_tasks,
    }


def _build_sidebar(active_section, active_sub=None):
    hub = _route('platform_monitoring:hub')
    seo = _route('platform_monitoring:seo')
    links = _route('platform_monitoring:seo_links')
    auto = _route('platform_monitoring:automation')
    iot = _route('platform_monitoring:iot')
    sec = _route('platform_monitoring:security')
    itg = _route('platform_monitoring:integrations')
    comp = _route('platform_monitoring:competitor')
    soc = _route('services:social_media_tracking')
    dig = _route('platform_monitoring:digital')
    kpi = _route('platform_monitoring:kpi_test')

    seo_links_tree = [
        {'id': 'internal_links', 'label': _('Internal Links'), 'route': _route('seo_analyzer:link_checker'),
         'active': (active_section == 'seo_links' and active_sub == 'internal_links')},
        {'id': 'external_links', 'label': _('External Links'), 'route': _route('seo_analyzer:link_checker'),
         'active': (active_section == 'seo_links' and active_sub == 'external_links')},
        {'id': 'backlinks', 'label': _('Backlinks'), 'route': _route('seo_analyzer:backlinks'),
         'active': (active_section == 'seo_links' and active_sub == 'backlinks')},
    ]
    seo_children = [
        {'id': 'website_checker', 'label': _('Website Checker'), 'route': _route('seo_analyzer:checker'),
         'active': (active_section == 'seo' and active_sub == 'website_checker')},
        {'id': 'free_website_check', 'label': _('Free Website Check'), 'route': _route('seo_analyzer:free_pre_check'),
         'active': (active_section == 'seo' and active_sub == 'free_website_check')},
        {'id': 'url_intelligence', 'label': _('URL Intelligence'), 'route': _route('seo_analyzer:url_intelligence'),
         'active': (active_section == 'seo' and active_sub == 'url_intelligence')},
        {'id': 'links', 'label': _('Links'), 'route': links, 'expandable': True,
         'active': active_section == 'seo_links', 'expanded': active_section == 'seo_links',
         'children': seo_links_tree},
        {'id': 'sitemap_intelligence', 'label': _('Sitemap Intelligence'), 'route': _route('seo_analyzer:sitemap'),
         'active': (active_section == 'seo' and active_sub == 'sitemap_intelligence')},
        {'id': 'seo_monitoring', 'label': _('SEO Monitoring'), 'route': _route('seo_analyzer:monitoring'),
         'active': (active_section == 'seo' and active_sub == 'seo_monitoring')},
        {'id': 'seo_kpi_analysis', 'label': _('SEO KPI Analysis'),
         'route': _route('services:seo_performance_dashboard'),
         'active': (active_section == 'seo' and active_sub == 'seo_kpi_analysis')},
    ]

    return {
        'groups': [
            {'id': 'nav', 'label': None, 'items': [
                {'id': 'hub', 'label': _('Overview'), 'icon': 'layout-dashboard', 'route': hub,
                 'active': active_section == 'hub'},
            ]},
            {'id': 'core', 'label': _('Core Services'), 'items': [
                {'id': 'seo', 'label': _('SEO'), 'icon': 'search', 'route': seo,
                 'active': active_section in ('seo', 'seo_links'),
                 'expandable': True, 'expanded': active_section in ('seo', 'seo_links'),
                 'children': seo_children},
                {'id': 'automation', 'label': _('Automation'), 'icon': 'workflow', 'route': auto,
                 'active': active_section == 'automation'},
                {'id': 'iot', 'label': _('IoT'), 'icon': 'cpu', 'route': iot,
                 'active': active_section == 'iot'},
                {'id': 'security', 'label': _('Security'), 'icon': 'shield', 'route': sec,
                 'active': active_section == 'security'},
                {'id': 'integrations', 'label': _('Integrations'), 'icon': 'puzzle', 'route': itg,
                 'active': active_section == 'integrations'},
            ]},
            {'id': 'intel', 'label': _('Intelligence'), 'items': [
                {'id': 'competitor', 'label': _('Competitor Intelligence'), 'icon': 'binoculars', 'route': comp,
                 'active': active_section == 'competitor'},
                {'id': 'social', 'label': _('Social Intelligence'), 'icon': 'message-circle-heart', 'route': soc,
                 'active': active_section == 'social'},
                {'id': 'digital', 'label': _('Digital Presence'), 'icon': 'fingerprint', 'route': dig,
                 'active': active_section == 'digital'},
            ]},
            {'id': 'testing', 'label': _('Testing'), 'items': [
                {'id': 'kpi_test', 'label': _('KPI Test'), 'icon': 'flask-conical', 'route': kpi,
                 'active': active_section == 'kpi_test'},
            ]},
        ]
    }


def _base_context(active_section, active_sub=None, page_title=None, page_tagline=None):
    seo_mods = _build_seo_modules()
    seo_links_mods = _build_seo_links_modules()
    auto_mods = _build_automation_modules()
    iot_mods = _build_iot_modules()
    sec_mods = _build_security_modules()
    itg_mods = _build_integration_modules()
    stand_mods = _build_standalone_modules()

    seo_all = seo_mods + seo_links_mods

    sections = [
        {'id': 'seo', 'name': _('SEO'), 'icon': 'search', 'accent': 'indigo',
         'route': _route('platform_monitoring:seo'),
         'modules': seo_all, 'count': len(seo_all),
         'status': _rollup_status(seo_all)},
        {'id': 'automation', 'name': _('Automation'), 'icon': 'workflow', 'accent': 'purple',
         'route': _route('platform_monitoring:automation'),
         'modules': auto_mods, 'count': len(auto_mods),
         'status': _rollup_status(auto_mods)},
        {'id': 'iot', 'name': _('IoT'), 'icon': 'cpu', 'accent': 'teal',
         'route': _route('platform_monitoring:iot'),
         'modules': iot_mods, 'count': len(iot_mods),
         'status': _rollup_status(iot_mods)},
        {'id': 'security', 'name': _('Security'), 'icon': 'shield', 'accent': 'rose',
         'route': _route('platform_monitoring:security'),
         'modules': sec_mods, 'count': len(sec_mods),
         'status': _rollup_status(sec_mods)},
        {'id': 'integrations', 'name': _('Integrations'), 'icon': 'puzzle', 'accent': 'amber',
         'route': _route('platform_monitoring:integrations'),
         'modules': itg_mods, 'count': len(itg_mods),
         'status': _rollup_status(itg_mods)},
    ]

    all_modules = seo_all + auto_mods + iot_mods + sec_mods + itg_mods + stand_mods
    counts = {
        'healthy': sum(1 for m in all_modules if m['status'] == 'Healthy'),
        'warning': sum(1 for m in all_modules if m['status'] == 'Warning'),
        'error': sum(1 for m in all_modules if m['status'] == 'Error'),
        'not_configured': sum(1 for m in all_modules if m['status'] == 'Not Configured'),
    }

    for s in sections:
        s['badge'] = _status_badge(s['status'])

    ctx = {
        'generated_at': datetime.now(),
        'counts': counts,
        'total_modules': len(all_modules),
        'sidebar': _build_sidebar(active_section, active_sub),
        'active_section': active_section,
        'active_sub': active_sub,
        'sections': sections,
        'core_services': sections,
        'seo_modules': _with_badge(seo_mods),
        'seo_links_modules': _with_badge(seo_links_mods),
        'automation_modules': _with_badge(auto_mods),
        'iot_modules': _with_badge(iot_mods),
        'security_modules': _with_badge(sec_mods),
        'integration_modules': _with_badge(itg_mods),
        'standalone_modules': _with_badge(stand_mods),
        'operational': _get_operational_data(),
        'pm_hub': _route('platform_monitoring:hub'),
        'pm_seo': _route('platform_monitoring:seo'),
        'pm_seo_links': _route('platform_monitoring:seo_links'),
        'pm_automation': _route('platform_monitoring:automation'),
        'pm_iot': _route('platform_monitoring:iot'),
        'pm_security': _route('platform_monitoring:security'),
        'pm_integrations': _route('platform_monitoring:integrations'),
        'page_title': page_title or _('Platform Monitoring'),
        'page_tagline': page_tagline or _('Control Center for the OnWebApp Platform'),
        'service': {'name': _('Platform Monitoring'), 'tagline': _('Control Center for the OnWebApp Platform')},
    }
    return ctx


@login_required
def hub_view(request):
    ctx = _base_context(active_section='hub')
    return render(request, 'platform_monitoring/hub.html', ctx)


@login_required
def seo_view(request):
    ctx = _base_context(active_section='seo', page_title=_('SEO'),
                        page_tagline=_('Search visibility, link intelligence & KPI monitoring.'))
    return render(request, 'platform_monitoring/seo.html', ctx)


@login_required
def seo_links_view(request):
    ctx = _base_context(active_section='seo_links',
                        page_title=_('Links'),
                        page_tagline=_('Internal links, external links & backlink analysis.'))
    return render(request, 'platform_monitoring/seo_links.html', ctx)


@login_required
def automation_view(request):
    ctx = _base_context(active_section='automation', page_title=_('Automation'),
                        page_tagline=_('Email, workflows, scheduling & execution logs.'))
    return render(request, 'platform_monitoring/section.html', {
        **ctx,
        'section_id': 'automation',
        'section_icon': 'workflow',
        'section_accent': 'purple',
        'modules': ctx['automation_modules'],
    })

@login_required
def task_scheduler_view(request):
    from django.conf import settings

    beat_schedule = getattr(settings, 'CELERY_BEAT_SCHEDULE', {})

    scheduled_tasks = []

    for task_name, config in beat_schedule.items():
        schedule = config.get('schedule')
        task_path = config.get('task', '')

        # Convert schedule to a readable value
        if isinstance(schedule, (int, float)):
            if schedule < 60:
                schedule_display = f'Every {int(schedule)} seconds'
            elif schedule < 3600:
                schedule_display = f'Every {int(schedule // 60)} minutes'
            elif schedule < 86400:
                schedule_display = f'Every {int(schedule // 3600)} hours'
            else:
                schedule_display = f'Every {int(schedule // 86400)} days'
        else:
            schedule_display = str(schedule)

        scheduled_tasks.append({
            'name': task_name,
            'task': task_path,
            'schedule': schedule_display,
            'status': 'Healthy',
        })

    ctx = _base_context(
        active_section='automation',
        active_sub='task_scheduler',
        page_title=_('Task Scheduler'),
        page_tagline=_('Scheduled jobs & Celery Beat orchestration.')
    )

    return render(
        request,
        'platform_monitoring/task_scheduler.html',
        {
            **ctx,
            'scheduled_tasks': scheduled_tasks,
            'scheduled_tasks_count': len(scheduled_tasks),
        }
    )  

@login_required
def iot_view(request):
    ctx = _base_context(active_section='iot', page_title=_('IoT'),
                        page_tagline=_('Devices, sensors, reports, alerts & fleet health.'))
    return render(request, 'platform_monitoring/section.html', {
        **ctx,
        'section_id': 'iot',
        'section_icon': 'cpu',
        'section_accent': 'teal',
        'modules': ctx['iot_modules'],
    })


@login_required
def security_view(request):
    ctx = _base_context(active_section='security', page_title=_('Security'),
                        page_tagline=_('Threats, access, integrity & compliance reporting.'))
    return render(request, 'platform_monitoring/section.html', {
        **ctx,
        'section_id': 'security',
        'section_icon': 'shield',
        'section_accent': 'rose',
        'modules': ctx['security_modules'],
    })


@login_required
def integrations_view(request):
    ctx = _base_context(active_section='integrations', page_title=_('Integrations'),
                        page_tagline=_('ERP, CRM, payments, advertising & platform APIs.'))
    return render(request, 'platform_monitoring/section.html', {
        **ctx,
        'section_id': 'integrations',
        'section_icon': 'puzzle',
        'section_accent': 'amber',
        'modules': ctx['integration_modules'],
    })


@login_required
def standalone_view(request, section_id):
    mapping = {
        'competitor': {
            'name': _('Competitor Intelligence'), 'icon': 'binoculars', 'accent': 'sky',
            'modules': _with_badge(_build_standalone_modules())[0:1],
        },
        'social': {
            'name': _('Social Intelligence'), 'icon': 'message-circle-heart', 'accent': 'sky',
            'modules': _with_badge(_build_standalone_modules())[1:2],
        },
        'digital': {
            'name': _('Digital Presence'), 'icon': 'fingerprint', 'accent': 'sky',
            'modules': _with_badge(_build_standalone_modules())[2:3],
        },
    }
    meta = mapping.get(section_id)
    if not meta:
        from django.http import Http404
        raise Http404()
    ctx = _base_context(active_section=section_id, page_title=meta['name'],
                        page_tagline=meta['name'])
    return render(request, 'platform_monitoring/section.html', {
        **ctx,
        'section_id': section_id,
        'section_icon': meta['icon'],
        'section_accent': meta['accent'],
        'modules': meta['modules'],
    })
@login_required
def execution_logs_view(request):
    from rpa_dashboard.models import WorkflowRun

    runs = (
        WorkflowRun.objects
        .select_related('workflow', 'triggered_by')
        .prefetch_related('steps')
        .order_by('-started_at')
    )

    total_runs = runs.count()
    success_runs = runs.filter(status='SUCCESS').count()
    failed_runs = runs.filter(status='FAILURE').count()
    running_runs = runs.filter(status__in=['RUNNING', 'PENDING']).count()

    success_rate = round(
        (success_runs / total_runs * 100) if total_runs else 0,
        1
    )

    ctx = _base_context(
        active_section='automation',
        page_title=_('Execution Logs'),
        page_tagline=_('Workflow execution history, status, duration & audit trail.')
    )

    ctx.update({
        'runs': runs[:100],
        'total_runs': total_runs,
        'success_runs': success_runs,
        'failed_runs': failed_runs,
        'running_runs': running_runs,
        'success_rate': success_rate,
    })

    return render(
        request,
        'platform_monitoring/execution_logs.html',
        ctx
    )
@login_required
def automation_status_view(request):
    try:
        from rpa_dashboard.models import WorkflowRun, RPAWorkflow

        total_workflows = RPAWorkflow.objects.count()

        running = WorkflowRun.objects.filter(status='RUNNING').count()
        pending = WorkflowRun.objects.filter(status='PENDING').count()

        latest_run = (
            WorkflowRun.objects
            .select_related('workflow')
            .order_by('-started_at')
            .first()
        )

        recent_runs = (
            WorkflowRun.objects
            .select_related('workflow', 'triggered_by')
            .order_by('-started_at')[:5]
        )

        if running > 0:
            system_status = 'Running'
        elif pending > 0:
            system_status = 'Pending'
        elif latest_run and latest_run.status == 'FAILURE':
            system_status = 'Attention'
        else:
            system_status = 'Healthy'

    except Exception:
        total_workflows = 0
        running = 0
        pending = 0
        latest_run = None
        recent_runs = []
        system_status = 'Unavailable'

    context = {
        'total_workflows': total_workflows,
        'running': running,
        'pending': pending,
        'latest_run': latest_run,
        'recent_runs': recent_runs,
        'system_status': system_status,
    }

    return render(
        request,
        'platform_monitoring/automation_status.html',
        context
    )


@login_required
def kpi_test_view(request):
    from urllib.parse import urlparse as _urlparse
    from .models import PerformanceCheck
    from .services.pagespeed import (
        validate_url,
        run_performance_test,
        get_performance_status_display,
        format_metric,
        get_metric_status,
    )

    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            url = body.get('url', '')
        except (json.JSONDecodeError, AttributeError):
            url = request.POST.get('url', '')

        valid, result = validate_url(url)
        if not valid:
            return JsonResponse({'success': False, 'error': result})

        test_results = run_performance_test(result)

        if not test_results.get('success'):
            return JsonResponse({'success': False, 'error': test_results.get('error', 'Unknown error')})

        parsed = _urlparse(test_results['url'])
        website = parsed.netloc or test_results['url']

        for device_type in ('mobile', 'desktop'):
            device_data = test_results.get(device_type)
            if not device_data:
                continue

            previous = PerformanceCheck.objects.filter(
                url=test_results['url'],
                device=device_type,
            ).order_by('-created_at').first()

            previous_score = previous.performance_score if previous else None

            check = PerformanceCheck.objects.create(
                website=website,
                url=test_results['url'],
                device=device_type,
                performance_score=device_data['performance_score'],
                fcp=device_data.get('fcp'),
                lcp=device_data.get('lcp'),
                inp=device_data.get('inp'),
                cls=device_data.get('cls'),
                ttfb=device_data.get('ttfb'),
                speed_index=device_data.get('speed_index'),
                total_blocking_time=device_data.get('total_blocking_time'),
                status=device_data['status'],
                recommendations=device_data.get('recommendations', []),
            )

            device_data['previous_score'] = previous_score
            if previous_score is not None:
                diff = device_data['performance_score'] - previous_score
                if diff > 0:
                    device_data['trend'] = f'+{diff}'
                    device_data['trend_direction'] = 'up'
                    device_data['trend_label'] = 'Improving'
                elif diff < 0:
                    device_data['trend'] = str(diff)
                    device_data['trend_direction'] = 'down'
                    device_data['trend_label'] = 'Declining'
                else:
                    device_data['trend'] = '0'
                    device_data['trend_direction'] = 'stable'
                    device_data['trend_label'] = 'Stable'
            else:
                device_data['trend'] = None
                device_data['trend_direction'] = 'none'
                device_data['trend_label'] = 'No previous data'

        overall = test_results.get('overall', {})
        if test_results.get('mobile') and test_results.get('desktop'):
            mobile_score = test_results['mobile']['performance_score']
            desktop_score = test_results['desktop']['performance_score']
            overall_score = round((mobile_score + desktop_score) / 2, 1)
            overall_status = get_performance_status_display(overall_score)
        elif test_results.get('mobile'):
            overall_score = test_results['mobile']['performance_score']
            overall_status = get_performance_status_display(overall_score)
        elif test_results.get('desktop'):
            overall_score = test_results['desktop']['performance_score']
            overall_status = get_performance_status_display(overall_score)
        else:
            overall_score = 0
            overall_status = 'N/A'

        formatted = {
            'success': True,
            'website': website,
            'url': test_results['url'],
            'overall': {
                'score': overall_score,
                'status': overall_status,
            },
        }

        for device_type in ('mobile', 'desktop'):
            device_data = test_results.get(device_type)
            if device_data:
                formatted[device_type] = {
                    'score': device_data['performance_score'],
                    'status': get_performance_status_display(device_data['performance_score']),
                    'fcp': format_metric('fcp', device_data.get('fcp')),
                    'lcp': format_metric('lcp', device_data.get('lcp')),
                    'inp': format_metric('inp', device_data.get('inp')),
                    'cls': format_metric('cls', device_data.get('cls')),
                    'ttfb': format_metric('ttfb', device_data.get('ttfb')),
                    'speed_index': format_metric('speed_index', device_data.get('speed_index')),
                    'total_blocking_time': format_metric('total_blocking_time', device_data.get('total_blocking_time')),
                    'fcp_status': get_metric_status('fcp', device_data.get('fcp')),
                    'lcp_status': get_metric_status('lcp', device_data.get('lcp')),
                    'inp_status': get_metric_status('inp', device_data.get('inp')),
                    'cls_status': get_metric_status('cls', device_data.get('cls')),
                    'ttfb_status': get_metric_status('ttfb', device_data.get('ttfb')),
                    'speed_index_status': get_metric_status('speed_index', device_data.get('speed_index')),
                    'total_blocking_time_status': get_metric_status('total_blocking_time', device_data.get('total_blocking_time')),
                    'trend': device_data.get('trend'),
                    'trend_direction': device_data.get('trend_direction'),
                    'trend_label': device_data.get('trend_label'),
                    'recommendations': device_data.get('recommendations', []),
                }
            else:
                formatted[device_type] = None

        return JsonResponse(formatted)

    history = PerformanceCheck.objects.order_by('-created_at')[:20]
    history_by_url = {}
    for h in history:
        if h.url not in history_by_url:
            history_by_url[h.url] = []
        history_by_url[h.url].append(h)

    chart_data = {}
    for h in PerformanceCheck.objects.order_by('created_at'):
        key = f"{h.url}|{h.device}"
        if key not in chart_data:
            chart_data[key] = {'labels': [], 'values': [], 'url': h.url, 'device': h.device}
        chart_data[key]['labels'].append(h.created_at.strftime('%b %d'))
        chart_data[key]['values'].append(h.performance_score)

    from .models import GA4Property
    ga4_properties = GA4Property.objects.filter(user=request.user, is_active=True)

    ctx = _base_context(
        active_section='kpi_test',
        page_title=_('KPI Test'),
        page_tagline=_('Test and validate the Website Performance KPI using Google PageSpeed Insights.'),
    )

    ctx.update({
        'history': history,
        'history_by_url': history_by_url,
        'chart_data': chart_data,
        'ga4_properties': ga4_properties,
    })

    return render(request, 'platform_monitoring/kpi_test.html', ctx)


# ============================================================
# GA4 OAuth Flow Views
# ============================================================


@login_required
def ga4_connect_view(request):
    from .services.ga4 import get_oauth_authorize_url

    client_id = getattr(settings, 'GA4_CLIENT_ID', '')
    if not client_id:
        messages.error(request, _('GA4 Client ID is not configured. Please set GA4_CLIENT_ID in your environment.'))
        return HttpResponseRedirect(reverse('platform_monitoring:kpi_test'))

    authorize_url = get_oauth_authorize_url()
    return HttpResponseRedirect(authorize_url)


@login_required
def ga4_callback_view(request):
    from .services.ga4 import exchange_code_for_tokens, list_ga4_properties, get_valid_credentials
    from .models import GA4Property

    code = request.GET.get('code')
    error = request.GET.get('error')

    if error:
        messages.error(request, _('Google authorization was denied or failed: %(error)s') % {'error': error})
        return HttpResponseRedirect(reverse('platform_monitoring:kpi_test'))

    if not code:
        messages.error(request, _('No authorization code received from Google.'))
        return HttpResponseRedirect(reverse('platform_monitoring:kpi_test'))

    token_data = exchange_code_for_tokens(code)
    if 'error' in token_data:
        messages.error(request, _('Failed to exchange authorization code: %(error)s') % {'error': token_data['error']})
        return HttpResponseRedirect(reverse('platform_monitoring:kpi_test'))

    access_token = token_data.get('access_token')
    refresh_token = token_data.get('refresh_token')
    expires_in = token_data.get('expires_in', 3600)

    if not access_token or not refresh_token:
        messages.error(request, _('Incomplete token data received from Google.'))
        return HttpResponseRedirect(reverse('platform_monitoring:kpi_test'))

    properties = list_ga4_properties(access_token)
    if not properties:
        messages.warning(request, _('Connected to Google but no GA4 properties were found. Make sure you have access to a GA4 property.'))
        return HttpResponseRedirect(reverse('platform_monitoring:kpi_test'))

    expires_at = timezone.now() + timedelta(seconds=expires_in)

    for prop in properties:
        GA4Property.objects.update_or_create(
            user=request.user,
            property_id=prop['property_id'],
            defaults={
                'display_name': prop['display_name'],
                'account_name': prop['account_name'],
                'access_token': access_token,
                'refresh_token': refresh_token,
                'token_expires_at': expires_at,
                'is_active': True,
            },
        )

    messages.success(request, _('Successfully connected %(count)d GA4 property(ies).') % {'count': len(properties)})
    return HttpResponseRedirect(reverse('platform_monitoring:kpi_test'))


@login_required
def ga4_disconnect_view(request, property_id):
    from .models import GA4Property

    if request.method != 'POST':
        return HttpResponseRedirect(reverse('platform_monitoring:kpi_test'))

    try:
        prop = GA4Property.objects.get(id=property_id, user=request.user)
        prop.delete()
        messages.success(request, _('GA4 property "%(name)s" has been disconnected.') % {'name': prop.display_name})
    except GA4Property.DoesNotExist:
        messages.error(request, _('GA4 property not found.'))

    return HttpResponseRedirect(reverse('platform_monitoring:kpi_test'))


def ga4_fetch_view(request):
    from .services.ga4 import (
        get_valid_credentials,
        run_ga4_report,
        run_ga4_traffic_sources_report,
        run_ga4_previous_period_report,
        calculate_kpis,
        calculate_trend,
        calculate_traffic_sources,
    )
    from .models import GA4Property, GA4Report

    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Authentication required.'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    try:
        body = json.loads(request.body)
        property_id = body.get('property_id', '')
        date_range = body.get('date_range', '30d')
        demo_mode = body.get('demo', False)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Invalid request body'}, status=400)

    try:
        ga4_property = GA4Property.objects.get(
            property_id=property_id,
            user=request.user,
            is_active=True,
        )
    except GA4Property.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'GA4 property not found or not connected.'})

    if demo_mode:
        demo_kpis = {
            'total_users': 12847,
            'sessions': 18234,
            'screen_page_views': 47891,
            'avg_session_duration': 186.5,
            'engagement_rate': 62.4,
            'bounce_rate': 37.6,
            'sessions_per_user': 1.42,
        }
        demo_trends = [
            {'metric': 'total_users', 'current': 12847, 'previous': 11203, 'change_pct': 14.7, 'direction': 'up'},
            {'metric': 'sessions', 'current': 18234, 'previous': 15891, 'change_pct': 14.7, 'direction': 'up'},
            {'metric': 'screen_page_views', 'current': 47891, 'previous': 41205, 'change_pct': 16.2, 'direction': 'up'},
            {'metric': 'engagement_rate', 'current': 62.4, 'previous': 58.1, 'change_pct': 7.4, 'direction': 'up'},
            {'metric': 'bounce_rate', 'current': 37.6, 'previous': 41.9, 'change_pct': -10.3, 'direction': 'up'},
            {'metric': 'avg_session_duration', 'current': 186.5, 'previous': 164.2, 'change_pct': 13.6, 'direction': 'up'},
            {'metric': 'sessions_per_user', 'current': 1.42, 'previous': 1.35, 'change_pct': 5.2, 'direction': 'up'},
        ]
        demo_traffic = [
            {'source': 'google', 'sessions': 8234, 'users': 6102, 'percentage': 45.2},
            {'source': 'direct', 'sessions': 4120, 'users': 3218, 'percentage': 22.6},
            {'source': 'facebook.com', 'sessions': 2891, 'users': 2104, 'percentage': 15.9},
            {'source': 'linkedin.com', 'sessions': 1547, 'users': 982, 'percentage': 8.5},
            {'source': 'twitter.com', 'sessions': 892, 'users': 634, 'percentage': 4.9},
            {'source': 'bing', 'sessions': 340, 'users': 245, 'percentage': 1.9},
            {'source': 'other', 'sessions': 210, 'users': 162, 'percentage': 1.1},
        ]

        GA4Report.objects.create(
            property=ga4_property,
            date_range=date_range,
            total_users=demo_kpis['total_users'],
            sessions=demo_kpis['sessions'],
            screen_page_views=demo_kpis['screen_page_views'],
            avg_session_duration=demo_kpis['avg_session_duration'],
            engagement_rate=demo_kpis['engagement_rate'],
            bounce_rate=demo_kpis['bounce_rate'],
            sessions_per_user=demo_kpis['sessions_per_user'],
            trends=demo_trends,
            traffic_sources=demo_traffic,
            raw_data={'demo': True},
        )

        return JsonResponse({
            'success': True,
            'property': {
                'property_id': ga4_property.property_id,
                'display_name': ga4_property.display_name,
                'account_name': ga4_property.account_name,
            },
            'date_range': date_range,
            'kpis': demo_kpis,
            'trends': demo_trends,
            'traffic_sources': demo_traffic,
            'demo': True,
        })

    access_token = get_valid_credentials(ga4_property)
    if not access_token:
        return JsonResponse({'success': False, 'error': 'Failed to authenticate with Google. Please reconnect your GA4 account.'})

    report_data = run_ga4_report(access_token, property_id, date_range)
    if not report_data or 'error' in report_data:
        error_msg = report_data.get('error', 'Unknown error') if report_data else 'No response from GA4 API'
        if 'timed out' in str(error_msg).lower():
            error_msg = 'GA4 API request timed out. The property may have too much data. Try a shorter date range.'
        return JsonResponse({'success': False, 'error': f'GA4 API error: {error_msg}'})

    kpis = calculate_kpis(report_data)
    if not kpis:
        return JsonResponse({'success': False, 'error': 'No data available for the selected date range. Make sure your GA4 property has traffic data.'})

    try:
        prev_period_data = run_ga4_previous_period_report(access_token, property_id, date_range)
        trends = calculate_trend(prev_period_data)
    except Exception:
        trends = []

    try:
        traffic_data = run_ga4_traffic_sources_report(access_token, property_id, date_range)
        traffic_sources = calculate_traffic_sources(traffic_data)
    except Exception:
        traffic_sources = []

    report = GA4Report.objects.create(
        property=ga4_property,
        date_range=date_range,
        total_users=kpis['total_users'],
        sessions=kpis['sessions'],
        screen_page_views=kpis['screen_page_views'],
        avg_session_duration=kpis['avg_session_duration'],
        engagement_rate=kpis['engagement_rate'],
        bounce_rate=kpis['bounce_rate'],
        sessions_per_user=kpis['sessions_per_user'],
        trends=trends or [],
        traffic_sources=traffic_sources,
        raw_data=report_data,
    )

    return JsonResponse({
        'success': True,
        'property': {
            'property_id': ga4_property.property_id,
            'display_name': ga4_property.display_name,
            'account_name': ga4_property.account_name,
        },
        'date_range': date_range,
        'kpis': kpis,
        'trends': trends or [],
        'traffic_sources': traffic_sources,
        'report_id': report.id,
    })
