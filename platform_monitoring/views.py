from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext_lazy as _
from django.urls import reverse, NoReverseMatch
from datetime import datetime


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

        snapshots = SEOMonitoringSnapshot.objects.order_by('-recorded_at')[:5]
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
        from seo_analyzer.models import LinkCheckTask
        qs = list(LinkCheckTask.objects.all()[:10])
        if qs:
            broken = 0
            total = 0
            for t in qs:
                total += 1
                try:
                    broken += int(getattr(t, 'broken_links_count', 0) or 0)
                except (TypeError, ValueError):
                    pass
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
    statuses = {
        'email_automation': 'Not Configured',
        'workflow_automation': 'Not Configured',
        'task_scheduler': 'Not Configured',
        'execution_logs': 'Not Configured',
        'current_status': 'Not Configured',
    }
    try:
        from rpa_dashboard.models import WorkflowRun
        runs = list(WorkflowRun.objects.all()[:20])
        if runs:
            failed = sum(1 for r in runs if getattr(r, 'status', '') in ('failed', 'error'))
            running = sum(1 for r in runs if getattr(r, 'status', '') in ('running', 'pending'))
            success = sum(1 for r in runs if getattr(r, 'status', '') in ('success', 'completed'))
            if failed > 0:
                statuses['workflow_automation'] = 'Error'
                statuses['execution_logs'] = 'Error'
                statuses['current_status'] = 'Error'
            elif running > 0:
                statuses['workflow_automation'] = 'Warning'
                statuses['execution_logs'] = 'Warning'
                statuses['current_status'] = 'Warning'
            elif success > 0:
                statuses['workflow_automation'] = 'Healthy'
                statuses['execution_logs'] = 'Healthy'
                statuses['current_status'] = 'Healthy'
    except Exception:
        pass
    return statuses


def _get_integration_statuses():
    statuses = {
        'erp': 'Not Configured',
        'crm': 'Not Configured',
        'stripe': 'Not Configured',
        'google': 'Not Configured',
        'meta': 'Not Configured',
        'api_status': 'Healthy',
    }
    try:
        from crm.models import Customer
        if Customer.objects.exists():
            statuses['crm'] = 'Healthy'
    except Exception:
        pass
    try:
        from payments.models import Invoice
        if Invoice.objects.all()[:5].exists():
            statuses['stripe'] = 'Healthy'
    except Exception:
        pass
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
         'route': rpa, 'status': s['task_scheduler'],
         'description': _('Cron & scheduled job orchestration.')},
        {'id': 'execution_logs', 'name': _('Execution Logs'), 'icon': 'file-text',
         'route': rpa, 'status': s['execution_logs'],
         'description': _('Granular execution logs & audit trail.')},
        {'id': 'current_status', 'name': _('Current Status'), 'icon': 'activity',
         'route': rpa, 'status': s['current_status'],
         'description': _('Live automation execution status overview.')},
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
