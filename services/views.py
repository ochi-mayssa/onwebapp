from django.shortcuts import render, redirect, Http404
from django.contrib.auth.decorators import login_required
from .forms import CompanyForm, UrlInputForm, MachineForm, KeywordForm, SocialTrackingForm
import os
from . import processors
from platform_app.models import Link
from .analytics_engine import AnalyticsEngine
from .models import SocialPost, SocialUser, Hashtag, PlatformMetrics
from .service_content import SERVICE_CONTENT
from .decorators import require_plan_limit
import jwt
import datetime
from django.conf import settings

def services_index(request):
    return render(request, 'services/index.html')

@login_required
@require_plan_limit('industrial_automation')
def industrial_automation(request):
    form = MachineForm(request.POST or None)
    result = None
    
    # Provide default data for a professional look on initial load
    if request.method == 'POST' and form.is_valid():
        identifier = form.cleaned_data.get('identifier')
        result = processors.process_industrial_automation(identifier, user=request.user)
    else:
        # Initial simulation for Machine #1
        result = processors.process_industrial_automation("CNC-Milling-01", user=request.user)
        
    return render(request, 'services/industrial_automation.html', {
        'form': form, 
        'result': result,
        'service': SERVICE_CONTENT['industrial-automation']
    })

def smart_factory(request):
    context = {'service': SERVICE_CONTENT['smart-factory-systems']}
    return render(request, 'services/service_detail.html', context)

@login_required
@require_plan_limit('market_analysis')
def market_analysis_tools(request):
    # Simulated market data
    result = {
        'market_size': '$12.4B',
        'growth_rate': '15.2%',
        'market_share': '12.4%',
        'market_rank': 3,
        'top_players': ['Acme Dynamics', 'Global Intelligence', 'OnWebApp'],
        'trends': [
            {'title': 'AI Adoption', 'impact': 'High'},
            {'title': 'Edge Computing', 'impact': 'Medium'},
            {'title': 'Sustainable Tech', 'impact': 'Low'}
        ]
    }
    return render(request, 'services/market_analysis_tools.html', {
        'result': result,
        'service': SERVICE_CONTENT['market-analysis-tools']
    })

def iot_integration(request):
    context = {'service': SERVICE_CONTENT['iot-integration']}
    return render(request, 'services/service_detail.html', context)

def predictive_maintenance(request):
    form = MachineForm(request.POST or None)
    prediction = None
    if request.method == 'POST' and form.is_valid():
        identifier = form.cleaned_data.get('identifier')
        prediction = processors.process_predictive_maintenance(identifier)
    return render(request, 'services/predictive_maintenance.html', {
        'form': form, 
        'prediction': prediction,
        'service': SERVICE_CONTENT['predictive-maintenance']
    })

@login_required
@require_plan_limit('competitor_tracking')
def competitor_tracking(request):
    form = UrlInputForm(request.POST or None)
    result = None
    if request.method == 'POST' and form.is_valid():
        url = form.cleaned_data.get('url')
        result = processors.process_seo_analysis(url)
    else:
        # Initial simulation
        result = processors.process_seo_analysis("https://competitor.com")
        result['competitor_name'] = "Global Tech Corp"
        result['market_share'] = "24%"
        result['rank'] = 2
        
    return render(request, 'services/competitor_tracking.html', {
        'form': form, 
        'result': result,
        'service': SERVICE_CONTENT['competitor-tracking']
    })

@login_required
@require_plan_limit('seo_analytics')
def seo_analytics(request):
    return render(request, 'services/seo_analytics.html')

def social_intelligence(request):
    context = {'service': SERVICE_CONTENT['social-intelligence']}
    return render(request, 'services/service_detail.html', context)

@login_required
@require_plan_limit('social_tracking')
def social_media_tracking(request):
    form = SocialTrackingForm(request.POST or None)
    result = None
    if request.method == 'POST' and form.is_valid():
        handle = form.cleaned_data.get('handle')
        platforms = form.cleaned_data.get('platforms') or None
        days = form.cleaned_data.get('days') or 30
        result = processors.process_social_tracking(handle, platforms=platforms, days=days, user=request.user)
        
    return render(request, 'services/social_media_tracking.html', {
        'form': form, 
        'result': result,
        'service': SERVICE_CONTENT['social-media-tracking']
    })

import jwt
import datetime
from django.conf import settings

from . import erp_utils

@login_required
@require_plan_limit('erp_integration')
def erp_integration(request):
    """Primary ERP service view using ERPNext white-label backend with local simulation fallback."""
    erp_site = getattr(request.user, 'erp_site', None)
    erp_token = erp_utils.get_erp_token(request.user)
    
    # Use processor to get simulated data as well
    erp_data = processors.process_erp_data(request.user.username)
    
    return render(request, 'services/erpnext_dashboard.html', {
        'erp_site': erp_site,
        'erp_token': erp_token,
        'erp_data': erp_data,
        'service': SERVICE_CONTENT['erp-integration']
    })


@login_required
def erpnext_dashboard(request):
    """Alias for the ERPNext dashboard."""
    return redirect('services:erp_integration')


@login_required
@require_plan_limit('crm_integration')
def crm_integration(request):
    """Primary CRM service view using ERPNext white-label backend with local simulation fallback."""
    erp_site = getattr(request.user, 'erp_site', None)
    erp_token = erp_utils.get_erp_token(request.user)
    
    # Use processor to get simulated CRM data
    crm_data = processors.process_crm_data(request.user.username)
    
    return render(request, 'services/crm_integration.html', {
        'erp_site': erp_site,
        'erp_token': erp_token,
        'crm_data': crm_data,
        'service': SERVICE_CONTENT['crm-integration']
    })


from django.http import HttpResponse
from django.template.loader import render_to_string
try:
    from weasyprint import HTML
except (ImportError, OSError):
    HTML = None

@login_required
def export_invoice_pdf(request):
    """Exports an ERPNext invoice object to PDF using WeasyPrint."""
    if request.method != 'POST':
        return redirect('services:erp_integration')
    
    import json
    try:
        invoice_data = json.loads(request.POST.get('invoice_json'))
    except (ValueError, TypeError):
        return HttpResponse("Invalid Invoice Data", status=400)

    if not HTML:
        return HttpResponse("PDF Engine (WeasyPrint) not available on this server.", status=500)

    # Render template to HTML string
    html_string = render_to_string('emails/invoice_pdf_template.html', {
        'invoice': invoice_data,
        'user': request.user,
        'date': datetime.datetime.now()
    })

    # Generate PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Invoice_{invoice_data.get("name")}.pdf"'
    
    HTML(string=html_string).write_pdf(response)
    return response

@login_required
def social_tracking(request):
    form = SocialTrackingForm(request.POST or None)
    result = None
    if request.method == 'POST' and form.is_valid():
        handle = form.cleaned_data.get('handle')
        platforms = form.cleaned_data.get('platforms')
        days = form.cleaned_data.get('days') or 30
        result = processors.process_social_tracking(handle, platforms=platforms, days=days)
    return render(request, 'services/social_tracking.html', {
        'form': form, 
        'result': result,
        'service': SERVICE_CONTENT['social-brand-tracking']
    })

def service_detail(request, page):
    # Redirect specific tools to their dedicated views
    if page in ('link-analyzer', 'link_analyzer'):
        return redirect('services:link_analyzer')
    if page in ('social-media-tracking', 'social_media_tracking'):
        return redirect('services:social_media_tracking')
    if page in ('keyword-research', 'keyword_research'):
        return redirect('services:keyword_research')
    if page in ('engagement-analytics', 'engagement_analytics'):
        return redirect('services:engagement_analytics')
    if page in ('industrial-automation', 'industrial_automation'):
        return redirect('services:industrial_automation')
    if page in ('predictive-maintenance', 'predictive_maintenance'):
        return redirect('services:predictive_maintenance')
    if page in ('smart-factory-systems', 'smart_factory_systems'):
        return redirect('services:smart_factory')
    if page in ('iot-integration', 'iot_integration'):
        return redirect('services:iot_integration')
    if page in ('market-analysis-tools', 'market_analysis_tools'):
        return redirect('services:market_analysis_tools')
    if page in ('competitor-tracking', 'competitor_tracking'):
        return redirect('services:competitor_tracking')
    if page in ('seo-performance-dashboard', 'seo_performance_dashboard'):
        return redirect('services:seo_performance_dashboard')
    if page in ('keyword-checker', 'keyword_checker'):
        return redirect('services:keyword_checker')
    if page in ('social-brand-tracking', 'social_brand_tracking'):
        return redirect('services:social_tracking')
    if page in ('erp-integration', 'erp_integration'):
        return redirect('services:erp_integration')
    if page in ('crm-integration', 'crm_integration'):
        return redirect('services:crm_integration')
    if page in ('platform-monitoring', 'platform_monitoring'):
        return redirect('platform_monitoring:hub')

    # Check if we have structured content for this page
    if page in SERVICE_CONTENT:
        context = {'service': SERVICE_CONTENT[page]}
        return render(request, 'services/service_detail.html', context)

    page_clean = page.replace('-', '_')
    return render(request, f'services/{page_clean}.html')

@login_required
@require_plan_limit('seo_analytics')
def seo_performance_dashboard(request):
    form = UrlInputForm(request.POST or None)
    result = None
    if request.method == 'POST' and form.is_valid():
        url = form.cleaned_data.get('url')
        result = processors.process_seo_analysis(url)
    else:
        # Initial simulation
        result = processors.process_seo_analysis("https://onwebapp.com")
        
    return render(request, 'services/seo_performance_dashboard.html', {
        'form': form, 
        'result': result,
        'service': SERVICE_CONTENT['seo-performance-dashboard']
    })

@login_required
@require_plan_limit('platform_monitoring')
def platform_monitoring(request):
    return redirect('platform_monitoring:hub')

def platform_links(request):
    links = Link.objects.all()
    return render(request, 'services/platform_links.html', {'links': links})

@login_required
@require_plan_limit('link_analyzer')
def link_analyzer(request):
    form = UrlInputForm(request.POST or None)
    result = None
    if request.method == 'POST' and form.is_valid():
        url = form.cleaned_data['url']
        analysis = processors.process_seo_analysis(url)
        summary = analysis.get('executive_summary') or {}
        broken_links = analysis.get('broken_links') or []
        result = {
            'url': url,
            'total_links': summary.get('links_discovered', 0),
            'internal_links': summary.get('internal_links_discovered', 0),
            'external_links': summary.get('external_links_discovered', 0),
            'links_checked': summary.get('links_checked', 0),
            'broken_links': broken_links,
            'broken_links_count': summary.get('broken_links', len(broken_links)),
            'error': analysis.get('error'),
            'error_message': analysis.get('error_message'),
            'blocked': analysis.get('blocked'),
            'analysis_source': analysis.get('analysis_source'),
            'chart': analysis.get('chart'),
        }
        crawler_api = os.environ.get('LINK_CRAWLER_API')
        if crawler_api and hasattr(processors, 'requests'):
            try:
                resp = processors.requests.get(crawler_api, params={'url': url}, timeout=10)
                if resp.ok:
                    api_broken = resp.json().get('broken_links', []) or []
                    if api_broken:
                        result['broken_links'] = api_broken
                        result['broken_links_count'] = len(api_broken)
                    result['source'] = 'api'
            except Exception:
                pass
    return render(request, 'services/link_analyzer.html', {
        'form': form, 
        'result': result,
        'service': SERVICE_CONTENT['link-analyzer']
    })

@login_required
@require_plan_limit('keyword_research')
def keyword_research(request):
    form = KeywordForm(request.POST or None)
    result = None
    if request.method == 'POST' and form.is_valid():
        query = form.cleaned_data.get('query')
        kw = processors.process_keyword_research(query)
        result = {
            'query': query,
            'suggested_keywords': kw.get('suggested_keywords', []),
            'chart': kw.get('chart'),
            'source': kw.get('source', 'simulated')
        }
    return render(request, 'services/keyword_research.html', {
        'form': form, 
        'result': result,
        'service': SERVICE_CONTENT['keyword-research']
    })

def keyword_checker(request):
    kw_form = KeywordForm(request.POST or None)
    url_form = UrlInputForm(request.POST or None)
    result = None
    if request.method == 'POST' and kw_form.is_valid() and url_form.is_valid():
        query = kw_form.cleaned_data.get('query')
        url = url_form.cleaned_data.get('url')
        kw = processors.process_keyword_research(query)
        seo = processors.process_seo_analysis(url)
        seo_score = seo.get('seo_score', 0)
        traffic = seo.get('estimated_monthly_traffic', 0)
        feasible = seo_score >= 70 or traffic > 500
        result = {
            'query': query,
            'url': url,
            'feasible': feasible,
            'kw': kw,
            'seo': seo
        }
    return render(request, 'services/keyword_checker.html', {
        'kw_form': kw_form, 
        'url_form': url_form, 
        'result': result,
        'service': SERVICE_CONTENT['keyword-checker']
    })

def engagement_analytics(request):
    form = CompanyForm(request.POST or None)
    result = None
    if request.method == 'POST' and form.is_valid():
        company = form.cleaned_data.get('company')
        data = processors.process_social_analytics(company)
        result = {
            'handle': data.get('handle', company),
            'followers': data.get('total_followers', 0),
            'engagement_rate': data.get('average_engagement_rate', 0),
            'top_platforms': list(data.get('platforms', {}).keys()),
            'chart': data.get('chart'),
            'summary': data.get('summary'),
            'source': data.get('source', 'simulated')
        }
    return render(request, 'services/engagement_analytics.html', {
        'form': form, 
        'result': result,
        'service': SERVICE_CONTENT['engagement-analytics']
    })

# --- New Social Media Analytics Views ---

def social_dashboard_view(request):
    """
    Main dashboard for Social Media Analytics.
    """
    engine = AnalyticsEngine()
    stats = engine.get_dashboard_stats()
    
    # Check if we have any data; if not, suggest running a crawl
    if stats['total_posts'] == 0:
        message = "No data found. Please run a crawl to populate the dashboard."
    else:
        message = None
        
    return render(request, 'social_media/dashboard.html', {'stats': stats, 'message': message})

def run_social_crawl(request):
    """
    View to trigger a crawl manually.
    """
    form = SocialTrackingForm(request.POST or None)
    result = None
    error = None
    
    if request.method == 'POST' and form.is_valid():
        handle = form.cleaned_data['handle']
        platforms = form.cleaned_data['platforms']
        
        engine = AnalyticsEngine()
        results = {}
        
        for platform in platforms:
            # if platform == 'facebook': continue # Not implemented yet -> Removed skip logic
            try:
                res = engine.run_analysis(platform, handle)
                results[platform] = res
            except ValueError as e:
                # Capture blocking error for missing keys
                if not error: error = ""
                error += f"{str(e)} "
            except Exception as e:
                if not error: error = ""
                error += f"Error crawling {platform}: {str(e)} "
        
        if not error:
            result = results
            
    return render(request, 'social_media/reports.html', {'form': form, 'result': result, 'error': error})
