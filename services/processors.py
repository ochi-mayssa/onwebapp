"""
Domain-specific processors for service pages.
Each processor contains the business logic for a particular service.
Processors return structured result dicts suitable for rendering and charting.
"""

import datetime
import math
import os
import json
import random
from collections import Counter
import re
from urllib.parse import urlparse, parse_qs
from . import erp_utils
from django.utils import timezone

from .models import SocialPost, SocialTrackingSnapshot, SocialUser

try:
    import requests
    _HAS_REQUESTS = True
except Exception:
    requests = None
    _HAS_REQUESTS = False

try:
    from bs4 import BeautifulSoup
    _HAS_BS4_GLOBAL = True
except Exception:
    BeautifulSoup = None
    _HAS_BS4_GLOBAL = False


def process_industrial_automation(identifier: str, user=None) -> dict:
    """Enhanced processor for industrial automation diagnostics.
    
    Provides: health score, specific failure modes, maintenance window, detailed metrics.
    """
    seed = sum(ord(c) for c in identifier)

    # If an external industrial diagnostics API is configured, use it.
    industrial_api = os.environ.get('INDUSTRIAL_API_URL')
    industrial_api_key = os.environ.get('INDUSTRIAL_API_KEY')
    if industrial_api and _HAS_REQUESTS:
        try:
            payload = {'identifier': identifier}
            headers = {'Content-Type': 'application/json'}
            if industrial_api_key:
                headers['Authorization'] = f'Bearer {industrial_api_key}'
            resp = requests.post(industrial_api, json=payload, headers=headers, timeout=10)
            if resp.ok:
                data = resp.json()
                data['source'] = 'api'
                return data
        except Exception:
            # Fall back to deterministic local result on any API failure
            pass
    health_score = max(40, 100 - ((seed % 60)))
    
    # Simulate specific fault codes based on identifier hash
    fault_code_base = seed % 5
    fault_codes = [
        'VIBRATION_ANOMALY',
        'THERMAL_SPIKE',
        'PRESSURE_DEVIATION',
        'BEARING_WEAR',
        'LUBRICATION_LOSS'
    ]
    
    issues = []
    if health_score < 70:
        # Deterministic faults based on health
        num_issues = min(3, max(1, 10 - int(health_score / 10)))
        for i in range(num_issues):
            issues.append({
                'code': fault_codes[(fault_code_base + i) % len(fault_codes)],
                'description': f'Detected anomaly in subsystem {chr(65 + i)}',
                'severity': 'high' if health_score < 50 else 'medium',
                'impact': 'Potential downtime if not addressed'
            })
    
    # Estimate maintenance window
    days_until_maintenance = max(1, int((health_score / 100.0) * 180))
    next_maintenance = datetime.date.today() + datetime.timedelta(days=days_until_maintenance)
    
    # Generate chart data: health trend over past 4 quarters
    labels = ['Q1', 'Q2', 'Q3', 'Q4']
    values = [
        max(30, health_score - 5),
        max(30, health_score - 2),
        health_score,
        health_score + (2 if seed % 2 == 0 else -2)
    ]
    
    result = {
        'source': 'simulated',
        'identifier': identifier,
        'health_score': round(health_score, 1),
        'status': 'critical' if health_score < 50 else ('warning' if health_score < 75 else 'healthy'),
        'issues': issues,
        'next_maintenance': next_maintenance.isoformat(),
        'estimated_remaining_life_days': days_until_maintenance,
        'maintenance_cost_estimate': f'${1500 + (seed % 3000)}',
        'summary': f'Machine {identifier} shows {"critical degradation" if health_score < 50 else "normal wear patterns"}.',
        'chart': {
            'labels': labels,
            'values': values,
            'title': 'Equipment Health Trend'
        }
    }

    if user:
        # Enhancement 2: Push IoT data to ERP
        erp_utils.push_iot_data_to_erp(user, identifier, {
            'health_score': result['health_score'],
            'status': result['status'],
            'last_check': result['next_maintenance']
        })

    return result


def process_erp_data(company_name: str) -> dict:
    """Enhanced processor for ERP data integration with role-based KPIs and trends.
    
    Provides: inventory levels, order summaries, financial health, and resource allocation.
    """
    seed = sum(ord(c) for c in company_name)
    random.seed(seed)
    
    erp_api_url = os.environ.get('ERP_API_URL')
    erp_api_key = os.environ.get('ERP_API_KEY')
    
    if erp_api_url and _HAS_REQUESTS:
        try:
            headers = {'Content-Type': 'application/json'}
            if erp_api_key:
                headers['Authorization'] = f'Bearer {erp_api_key}'
            resp = requests.get(f"{erp_api_url}/dashboard?company={company_name}", headers=headers, timeout=10)
            if resp.ok:
                data = resp.json()
                data['source'] = 'api'
                return data
        except Exception:
            pass

    # Role-Based Data Simulation
    
    # 1. Finance Role KPIs
    revenue_growth = random.randint(5, 20)
    gross_profit_margin = random.randint(25, 45)
    days_sales_outstanding = random.randint(30, 60)
    budget_usage = random.randint(60, 95)
    
    # 2. Supply Chain / Operations KPIs
    inventory_health = random.randint(50, 95)
    inventory_turnover = round(random.uniform(4.0, 8.0), 1)
    pending_orders = random.randint(10, 60)
    machine_uptime = random.randint(85, 99)
    
    # 3. Manufacturing KPIs
    production_volume = random.randint(1000, 5000)
    material_yield = random.randint(90, 98)
    cycle_time = round(random.uniform(10.5, 25.0), 1)
    
    # Trends for Line Charts (Last 6 Months)
    months = ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar']
    revenue_trend = [random.randint(40000, 60000) for _ in range(6)]
    expense_trend = [random.randint(30000, 45000) for _ in range(6)]
    
    # Department Allocation for Radar/Bar Chart
    departments = ['Sales', 'HR', 'Production', 'Logistics', 'Finance']
    allocation = [random.randint(10, 40) for _ in range(5)]
    total = sum(allocation)
    allocation_pct = [round((x / total) * 100, 1) for x in allocation]
    
    # Risk Alerts
    alerts = []
    if inventory_health < 60:
        alerts.append({'type': 'danger', 'msg': 'Low inventory risk in Zone B', 'action': 'Reorder initiated'})
    if budget_usage > 90:
        alerts.append({'type': 'warning', 'msg': 'Department budget exceeding 90%', 'action': 'Review required'})
    if machine_uptime < 90:
        alerts.append({'type': 'danger', 'msg': 'Maintenance delay on Line 4', 'action': 'Schedule reset'})
    if not alerts:
        alerts.append({'type': 'success', 'msg': 'All systems within optimal parameters', 'action': 'None'})

    return {
        'source': 'simulated',
        'company': company_name,
        'last_sync': datetime.datetime.now().isoformat(),
        'summary': f"ERP systems for {company_name} are operational. Financial health is { 'strong' if revenue_growth > 12 else 'stable'}.",
        
        # Role: Finance
        'finance': {
            'revenue_growth': f"{revenue_growth}%",
            'gross_margin': f"{gross_profit_margin}%",
            'dso': days_sales_outstanding,
            'budget_usage': f"{budget_usage}%",
            'trends': {
                'labels': months,
                'revenue': revenue_trend,
                'expenses': expense_trend
            }
        },
        
        # Role: Operations / Supply Chain
        'operations': {
            'inventory_health': inventory_health,
            'inventory_turnover': inventory_turnover,
            'pending_orders': pending_orders,
            'machine_uptime': f"{machine_uptime}%",
            'allocation': {
                'labels': departments,
                'values': allocation_pct
            }
        },
        
        # Role: Manufacturing
        'manufacturing': {
            'production_volume': production_volume,
            'material_yield': f"{material_yield}%",
            'cycle_time': f"{cycle_time}h",
            'efficiency_score': random.randint(70, 95)
        },
        
        # System-wide Alerts
        'alerts': alerts
    }


def execute_erp_command(company_name: str, command: str, parameters: dict = None) -> dict:
    """Simulates a control command being sent to an ERP/Factory system."""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    
    commands = {
        'start_production': {
            'status': 'success',
            'message': f"[{timestamp}] Production line Alpha-1 initiated for {company_name}.",
            'icon': 'fas fa-play text-success'
        },
        'stop_production': {
            'status': 'warning',
            'message': f"[{timestamp}] Safe shutdown sequence initiated for {company_name} facilities.",
            'icon': 'fas fa-stop text-danger'
        },
        'emergency_reset': {
            'status': 'danger',
            'message': f"[{timestamp}] EMERGENCY RESET executed. All systems returning to baseline for {company_name}.",
            'icon': 'fas fa-exclamation-triangle text-warning'
        },
        'adjust_temp': {
            'status': 'info',
            'message': f"[{timestamp}] Climate control adjusted to {parameters.get('value', '22')}°C in storage zone B.",
            'icon': 'fas fa-thermometer-half text-info'
        }
    }
    
    return commands.get(command, {
        'status': 'error',
        'message': f"Unknown command: {command}",
        'icon': 'fas fa-times text-muted'
    })


def process_crm_data(company_name: str) -> dict:
    """Enhanced processor for CRM data integration with role-based KPIs and trends.
    
    Provides: lead conversion rates, sales pipeline, customer sentiment, and lifecycle stages.
    """
    seed = sum(ord(c) for c in company_name)
    random.seed(seed + 1) # Different seed from ERP
    
    crm_api_url = os.environ.get('CRM_API_URL')
    crm_api_key = os.environ.get('CRM_API_KEY')
    
    if crm_api_url and _HAS_REQUESTS:
        try:
            headers = {'Content-Type': 'application/json'}
            if crm_api_key:
                headers['Authorization'] = f'Bearer {crm_api_key}'
            resp = requests.get(f"{crm_api_url}/analytics?company={company_name}", headers=headers, timeout=10)
            if resp.ok:
                data = resp.json()
                data['source'] = 'api'
                return data
        except Exception:
            pass

    # Role-Based CRM Data Simulation
    
    # 1. Sales Role KPIs
    active_leads = random.randint(100, 500)
    conversion_rate = random.randint(8, 22)
    pipeline_value = random.randint(200000, 800000)
    lead_velocity = random.randint(10, 30) # % growth month over month
    
    # 2. Marketing Role KPIs
    customer_acquisition_cost = random.randint(50, 150)
    marketing_roi = round(random.uniform(2.5, 5.5), 1)
    lead_sources = ['Organic', 'Paid Search', 'Social', 'Referral', 'Email']
    source_distribution = [random.randint(10, 40) for _ in range(5)]
    total_src = sum(source_distribution)
    source_pct = [round((x / total_src) * 100, 1) for x in source_distribution]
    
    # 3. Customer Support / Retention KPIs
    satisfaction_score = random.randint(70, 98)
    retention_rate = random.randint(85, 99)
    churn_risk_score = random.randint(5, 25)
    
    # Trends for Lead Growth (Last 6 Months)
    months = ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar']
    new_leads_trend = [random.randint(20, 50) for _ in range(6)]
    closed_deals_trend = [random.randint(5, 15) for _ in range(6)]
    
    # Sales Funnel Breakdown
    stages = ['Prospecting', 'Qualification', 'Proposal', 'Negotiation', 'Closed Won']
    counts = [random.randint(50, 100), random.randint(30, 60), random.randint(20, 40), random.randint(10, 20), random.randint(5, 15)]
    
    # Risk Alerts for CRM
    alerts = []
    if churn_risk_score > 20:
        alerts.append({'type': 'danger', 'msg': 'High churn risk detected in Enterprise segment', 'action': 'Retention campaign'})
    if marketing_roi < 3.0:
        alerts.append({'type': 'warning', 'msg': 'Marketing ROI below target (3.0x)', 'action': 'Optimize ad spend'})
    if lead_velocity < 15:
        alerts.append({'type': 'info', 'msg': 'Lead velocity slowing down', 'action': 'Review top-of-funnel'})
    if not alerts:
        alerts.append({'type': 'success', 'msg': 'Sales funnel healthy and accelerating', 'action': 'None'})

    return {
        'source': 'simulated',
        'company': company_name,
        'last_update': datetime.datetime.now().isoformat(),
        'sentiment': 'positive' if satisfaction_score > 85 else 'neutral',
        'summary': f"CRM insights for {company_name} indicate a { 'strong' if conversion_rate > 15 else 'steady'} sales pipeline.",
        
        # Role: Sales
        'sales': {
            'active_leads': active_leads,
            'conversion_rate': f"{conversion_rate}%",
            'pipeline_value': f"${pipeline_value:,}",
            'lead_velocity': f"+{lead_velocity}%",
            'funnel': {
                'labels': stages,
                'values': counts
            }
        },
        
        # Role: Marketing
        'marketing': {
            'cac': f"${customer_acquisition_cost}",
            'roi': f"{marketing_roi}x",
            'sources': {
                'labels': lead_sources,
                'values': source_pct
            },
            'trends': {
                'labels': months,
                'leads': new_leads_trend,
                'deals': closed_deals_trend
            }
        },
        
        # Role: Customer Success
        'support': {
            'satisfaction_score': f"{satisfaction_score}/100",
            'retention_rate': f"{retention_rate}%",
            'churn_risk': f"{churn_risk_score}%",
            'health_index': random.randint(75, 95)
        },
        
        # CRM Alerts
        'alerts': alerts
    }


def execute_crm_command(company_name: str, command: str, parameters: dict = None) -> dict:
    """Simulates a lead management action being sent to a CRM system."""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    
    commands = {
        'assign_sales': {
            'status': 'success',
            'message': f"[{timestamp}] Top 5 leads for {company_name} assigned to Senior Sales Team.",
            'icon': 'fas fa-user-check text-success'
        },
        'auto_respond': {
            'status': 'info',
            'message': f"[{timestamp}] Automated welcome sequence sent to {parameters.get('count', '12')} new prospects.",
            'icon': 'fas fa-paper-plane text-info'
        },
        'escalate_lead': {
            'status': 'warning',
            'message': f"[{timestamp}] Lead ID {parameters.get('id', 'L-99')} escalated to Regional Director for {company_name}.",
            'icon': 'fas fa-arrow-up text-warning'
        },
        'bulk_export': {
            'status': 'primary',
            'message': f"[{timestamp}] Full customer database encrypted and exported for backup.",
            'icon': 'fas fa-file-export text-primary'
        }
    }
    
    return commands.get(command, {
        'status': 'error',
        'message': f"Unknown CRM action: {command}",
        'icon': 'fas fa-times text-muted'
    })


def process_predictive_maintenance(identifier: str) -> dict:
    """Enhanced processor for predictive maintenance.
    
    Provides: failure probability, recommended maintenance window, ML confidence, risk metrics.
    """
    seed = sum(ord(c) for c in identifier)

    # Optional external predictive maintenance API
    pm_api = os.environ.get('PREDICTIVE_MAINTENANCE_API')
    pm_api_key = os.environ.get('PREDICTIVE_MAINTENANCE_KEY')
    if pm_api and _HAS_REQUESTS:
        try:
            payload = {'identifier': identifier}
            headers = {'Content-Type': 'application/json'}
            if pm_api_key:
                headers['Authorization'] = f'Bearer {pm_api_key}'
            resp = requests.post(pm_api, json=payload, headers=headers, timeout=10)
            if resp.ok:
                data = resp.json()
                data['source'] = 'api'
                return data
        except Exception:
            pass
    # Simulate ML model confidence (0-100)
    base_probability = (seed % 100) * 0.8
    failure_probability = min(99, max(5, base_probability))
    
    # Calculate recommended maintenance days
    if failure_probability > 80:
        maintenance_days = 3
        risk_level = 'critical'
    elif failure_probability > 60:
        maintenance_days = 7
        risk_level = 'high'
    elif failure_probability > 40:
        maintenance_days = 14
        risk_level = 'medium'
    else:
        maintenance_days = 30
        risk_level = 'low'
    
    # Simulate confidence metrics
    model_confidence = 75 + (seed % 20)
    training_samples = 5000 + (seed % 10000)
    
    # Failure probability trend (getting worse over time)
    labels = ['Week -3', 'Week -2', 'Week -1', 'This Week']
    trend_values = [
        max(0, failure_probability - 15),
        max(0, failure_probability - 8),
        max(0, failure_probability - 3),
        failure_probability
    ]
    
    return {
        'source': 'simulated',
        'identifier': identifier,
        'failure_probability': round(failure_probability, 1),
        'failure_probability_percent': f'{round(failure_probability)}%',
        'risk_level': risk_level,
        'recommended_maintenance_in_days': maintenance_days,
        'next_service_date': (datetime.date.today() + datetime.timedelta(days=maintenance_days)).isoformat(),
        'model_confidence': f'{model_confidence}%',
        'training_samples': training_samples,
        'top_failure_modes': [
            {'mode': 'Bearing wear', 'probability': f'{round(failure_probability * 0.4)}%'},
            {'mode': 'Seal degradation', 'probability': f'{round(failure_probability * 0.3)}%'},
            {'mode': 'Lubrication depletion', 'probability': f'{round(failure_probability * 0.2)}%'},
        ],
        'estimated_downtime_hours': max(2, int(failure_probability / 20)),
        'summary': f'ML model predicts {round(failure_probability)}% failure probability within 30 days.',
        'chart': {
            'labels': labels,
            'values': trend_values,
            'title': 'Failure Probability Trend'
        }
    }


def process_market_analysis(company: str) -> dict:
    """Enhanced processor for market analysis tools.
    
    Provides: market size, revenue growth, competitive position, market trends.
    """
    seed = sum(ord(c) for c in company)

    # Optional market data API (e.g., Crunchbase / financial data provider)
    market_api = os.environ.get('MARKET_DATA_API')
    market_api_key = os.environ.get('MARKET_DATA_KEY')
    if market_api and _HAS_REQUESTS:
        try:
            payload = {'company': company}
            headers = {'Content-Type': 'application/json'}
            if market_api_key:
                headers['Authorization'] = f'Bearer {market_api_key}'
            resp = requests.get(market_api, params=payload, headers=headers, timeout=10)
            if resp.ok:
                data = resp.json()
                data['source'] = 'api'
                return data
        except Exception:
            pass
    
    # Simulate company financials
    base_revenue = 5_000_000
    revenue = base_revenue + (seed % 20_000_000)
    growth_percent = ((seed % 25) - 10) * 1.5  # Range: -15% to +27.5%
    market_share = (seed % 20) + 2  # 2-22%
    market_size = revenue / (market_share / 100) if market_share > 0 else 100_000_000
    
    # Competitive metrics
    rank_in_market = (seed % 50) + 1  # Rank 1-50
    competitor_count = 50 + (seed % 200)
    
    # Quarterly revenue trend
    labels = ['Q1', 'Q2', 'Q3', 'Q4']
    quarterly_revenue = []
    for i in range(4):
        q_rev = revenue * (1 + ((i - 1.5) * 0.02 + (seed % 10) / 100.0))
        quarterly_revenue.append(int(q_rev))
    
    return {
        'source': 'simulated',
        'company': company,
        'annual_revenue': f'${revenue:,}',
        'annual_revenue_numeric': revenue,
        'growth_percent': f'{round(growth_percent, 1)}%',
        'market_share': f'{round(market_share, 1)}%',
        'market_size': f'${int(market_size):,}',
        'market_rank': rank_in_market,
        'total_competitors': competitor_count,
        'year_over_year_growth': f'{round(growth_percent, 2)}%',
        'trend': 'positive' if growth_percent > 0 else 'negative',
        'key_metrics': {
            'employee_count': 100 + (seed % 1000),
            'founded_year': 2010 + (seed % 15),
            'headquarters': f'Region {chr(65 + (seed % 5))}',
        },
        'summary': f'{company} is ranked #{rank_in_market} in a market of {competitor_count} competitors with {round(market_share, 1)}% share.',
        'chart': {
            'labels': labels,
            'values': quarterly_revenue,
            'title': 'Quarterly Revenue Trend'
        }
    }


import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from seo_analyzer.services.utils import (
        build_http_session,
        classify_request_exception,
        clean_text,
        extract_domain,
        is_internal_url,
        normalize_url,
        DEFAULT_REQUEST_TIMEOUT,
    )
    _HAS_SEO_UTILS = True
except Exception:
    _HAS_SEO_UTILS = False

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except Exception:
    _HAS_BS4 = False

try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    _HAS_CONCURRENT = True
except Exception:
    _HAS_CONCURRENT = False

SEO_DASHBOARD_LINK_CHECK_LIMIT = 50
SEO_DASHBOARD_LINK_CHECK_TIMEOUT = 5
SEO_DASHBOARD_LINK_CHECK_WORKERS = 10

_SEO_KPI_WEIGHTS = {
    "technical_health": {
        "https": 15,
        "http_200": 15,
        "indexability": 15,
        "canonical": 15,
        "robots_ok": 10,
        "title_exists": 10,
        "meta_desc_exists": 10,
        "h1_single": 10,
        "broken_link_ratio": 10,
        "_total": 110,
    },
    "on_page_seo": {
        "title_quality": 25,
        "meta_desc_quality": 20,
        "h1_structure": 20,
        "heading_structure": 10,
        "canonical_present": 10,
        "image_alt_coverage": 15,
        "_total": 100,
    },
}


def _fetch_page(session, url: str) -> dict:
    """Phase 2: Real page fetch with safe error handling."""
    result = {
        "original_url": url,
        "final_url": None,
        "http_status": None,
        "redirected": False,
        "redirect_count": 0,
        "response_time": None,
        "https": False,
        "content_type": None,
        "page_size": None,
        "html_content": None,
        "headers": {},
        "success": False,
        "error_type": None,
        "error_message": None,
        "blocked": False,
    }

    try:
        import time
        started = time.perf_counter()
        response = session.get(
            url,
            timeout=DEFAULT_REQUEST_TIMEOUT,
            allow_redirects=True,
            stream=True,
        )
        elapsed = time.perf_counter() - started

        result["final_url"] = normalize_url(response.url) if _HAS_SEO_UTILS else response.url
        result["http_status"] = response.status_code
        result["redirected"] = len(response.history) > 0
        result["redirect_count"] = len(response.history)
        result["response_time"] = round(elapsed, 4)
        result["https"] = response.url.startswith("https://")
        result["content_type"] = response.headers.get("Content-Type", "")
        result["page_size"] = len(response.content)
        result["headers"] = dict(response.headers)

        if response.status_code == 403:
            result["blocked"] = True
            result["error_message"] = "Analysis Limited — Website blocked automated access (403 Forbidden)."

        if "text/html" in result["content_type"].lower() or not result["content_type"]:
            result["html_content"] = response.content
            result["success"] = True
        else:
            result["success"] = False
            result["error_type"] = "Unsupported Content Type"
            result["error_message"] = f"Unsupported content type: {result['content_type']}"

    except Exception as exc:
        error_type, error_msg = classify_request_exception(exc) if _HAS_SEO_UTILS else (
            "Connection Error", str(exc)
        )
        result["error_type"] = error_type
        result["error_message"] = error_msg
        if error_type in ("SSL Error", "DNS Resolution Error", "Connection Refused", "Timeout"):
            pass
        if "429" in str(exc):
            result["blocked"] = True

    return result


def _analyze_on_page_seo(html_content: bytes, base_url: str, base_domain: str) -> dict:
    """Phase 3: Real on-page SEO analysis from fetched HTML."""
    result = {
        "title": None,
        "title_exists": False,
        "title_length": None,
        "meta_description": None,
        "meta_desc_exists": False,
        "meta_desc_length": None,
        "h1_count": 0,
        "h1_texts": [],
        "h2_count": 0,
        "h3_count": 0,
        "multiple_h1": False,
        "canonical_exists": False,
        "canonical_url": None,
        "canonical_self": None,
        "robots_meta": None,
        "noindex": False,
        "nofollow": False,
        "html_lang": None,
        "images_total": 0,
        "images_with_alt": 0,
        "images_empty_alt": 0,
        "images_missing_alt": 0,
        "images_alt_attribute_percentage": None,
        "images_alt_percentage": None,
        "links_total": 0,
        "links_internal": 0,
        "links_external": 0,
        "internal_links_discovered": [],
        "external_links_discovered": [],
        "word_count": None,
    }

    if not html_content or not _HAS_BS4:
        return result

    try:
        from urllib.parse import urljoin
        soup = BeautifulSoup(html_content, "html.parser")
    except Exception:
        return result

    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        result["html_lang"] = html_tag["lang"]

    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        result["title"] = clean_text(title_tag.get_text()) if _HAS_SEO_UTILS else title_tag.get_text(strip=True)
        result["title_exists"] = True
        result["title_length"] = len(result["title"])

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        result["meta_description"] = clean_text(meta_desc["content"]) if _HAS_SEO_UTILS else meta_desc["content"].strip()
        result["meta_desc_exists"] = True
        result["meta_desc_length"] = len(result["meta_description"])

    h1_tags = soup.find_all("h1")
    result["h1_count"] = len(h1_tags)
    result["multiple_h1"] = result["h1_count"] > 1
    for h1 in h1_tags:
        text = h1.get_text(strip=True)
        if text:
            cleaned = clean_text(text) if _HAS_SEO_UTILS else text
            if cleaned:
                result["h1_texts"].append(cleaned)

    result["h2_count"] = len(soup.find_all("h2"))
    result["h3_count"] = len(soup.find_all("h3"))

    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    if canonical_tag and canonical_tag.get("href"):
        result["canonical_exists"] = True
        raw_href = canonical_tag["href"]
        result["canonical_url"] = normalize_url(urljoin(base_url, raw_href)) if _HAS_SEO_UTILS else urljoin(base_url, raw_href)
        if base_url and result["canonical_url"]:
            result["canonical_self"] = normalize_url(base_url) == result["canonical_url"] if _HAS_SEO_UTILS else base_url.rstrip("/") == result["canonical_url"].rstrip("/")

    robots_tag = soup.find("meta", attrs={"name": "robots"})
    if robots_tag and robots_tag.get("content"):
        result["robots_meta"] = robots_tag["content"].strip()
        content_lower = result["robots_meta"].lower()
        result["noindex"] = "noindex" in content_lower
        result["nofollow"] = "nofollow" in content_lower

    images = soup.find_all("img")
    result["images_total"] = len(images)
    with_alt = 0
    empty_alt = 0
    missing_alt = 0
    for img in images:
        if not img.has_attr("alt"):
            missing_alt += 1
        else:
            alt_val = img.get("alt") or ""
            if alt_val.strip() == "":
                empty_alt += 1
            else:
                with_alt += 1
    result["images_with_alt"] = with_alt
    result["images_empty_alt"] = empty_alt
    result["images_missing_alt"] = missing_alt
    if result["images_total"] > 0:
        has_alt_attr = result["images_total"] - missing_alt
        result["images_alt_attribute_percentage"] = round((has_alt_attr / result["images_total"]) * 100, 1)
        result["images_alt_percentage"] = result["images_alt_attribute_percentage"]

    internal_set = set()
    external_set = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        try:
            absolute_url = normalize_url(urljoin(base_url, href)) if _HAS_SEO_UTILS else urljoin(base_url, href)
        except Exception:
            continue
        result["links_total"] += 1
        if _HAS_SEO_UTILS and is_internal_url(absolute_url, base_domain):
            result["links_internal"] += 1
            internal_set.add(absolute_url)
        else:
            try:
                from urllib.parse import urlparse
                target_domain = urlparse(absolute_url).netloc.lower()
                if target_domain == base_domain.lower():
                    result["links_internal"] += 1
                    internal_set.add(absolute_url)
                else:
                    result["links_external"] += 1
                    external_set.add(absolute_url)
            except Exception:
                result["links_external"] += 1
                external_set.add(absolute_url)

    result["internal_links_discovered"] = sorted(internal_set)
    result["external_links_discovered"] = sorted(external_set)

    try:
        visible_text = soup.get_text(separator=" ")
        words = [w for w in visible_text.split() if w.strip()]
        result["word_count"] = len(words)
    except Exception:
        pass

    return result


def _check_internal_links(session, internal_links: list, source_page_url: str) -> dict:
    """Phase 5: Real link checking for internal links only."""
    result = {
        "links_discovered": len(internal_links),
        "links_checked": 0,
        "links_checked_list": [],
        "broken_links": [],
        "sample_limited": False,
    }

    if not internal_links or not _HAS_CONCURRENT:
        return result

    links_to_check = internal_links[:SEO_DASHBOARD_LINK_CHECK_LIMIT]
    result["sample_limited"] = len(internal_links) > SEO_DASHBOARD_LINK_CHECK_LIMIT

    def _check_one(link_url: str):
        try:
            resp = session.head(
                link_url,
                timeout=SEO_DASHBOARD_LINK_CHECK_TIMEOUT,
                allow_redirects=True,
            )
            if resp.status_code in (403, 405, 429, 500, 501, 502, 503):
                resp = session.get(
                    link_url,
                    timeout=SEO_DASHBOARD_LINK_CHECK_TIMEOUT,
                    allow_redirects=True,
                    stream=True,
                )
            return link_url, resp.status_code, None
        except Exception as exc:
            err_type, _ = classify_request_exception(exc) if _HAS_SEO_UTILS else ("Error", str(exc))
            return link_url, None, err_type

    workers = min(SEO_DASHBOARD_LINK_CHECK_WORKERS, len(links_to_check))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_check_one, url): url for url in links_to_check}
        for future in as_completed(futures):
            link_url, status_code, error_type = future.result()
            result["links_checked"] += 1
            result["links_checked_list"].append({
                "url": link_url,
                "status_code": status_code,
                "error_type": error_type,
            })

            is_broken = False
            severity = None
            recommendation = None

            if error_type is not None:
                is_broken = True
                severity = "Warning"
                recommendation = f"Connection issue ({error_type}). Verify URL is reachable and retry."
            elif status_code is not None and isinstance(status_code, int):
                if status_code == 404:
                    is_broken = True
                    severity = "High"
                    recommendation = "Replace with a valid destination or set up a proper 301 redirect."
                elif status_code == 410:
                    is_broken = True
                    severity = "High"
                    recommendation = "Resource is permanently gone. Remove the link or redirect to relevant content."
                elif 500 <= status_code < 600:
                    is_broken = True
                    severity = "Critical"
                    recommendation = f"Server error ({status_code}). Investigate server logs and fix the underlying application issue."
                elif status_code in (403, 401):
                    is_broken = True
                    severity = "Medium"
                    recommendation = f"Access restricted ({status_code}). Ensure the resource is publicly accessible if it should be indexed."
                elif 400 <= status_code < 500 and status_code not in (403, 401):
                    is_broken = True
                    severity = "Medium"
                    recommendation = f"HTTP client error ({status_code}). Review and fix the link target."

            if is_broken:
                result["broken_links"].append({
                    "url": link_url,
                    "status_code": status_code if status_code is not None else (error_type or "Unreachable"),
                    "found_on": source_page_url,
                    "severity": severity,
                    "recommendation": recommendation,
                    "error_type": error_type,
                })

    return result


def _calculate_kpis(fetch_result: dict, on_page: dict, link_check: dict) -> dict:
    """Phase 6: Deterministic KPI calculations with documented weights.

    Technical Health Weight Breakdown (_SEO_KPI_WEIGHTS["technical_health"]):
    - https: 15 pts — HTTPS on final URL
    - http_200: 15 pts — HTTP 200 status
    - indexability: 15 pts — not noindex
    - canonical: 15 pts — canonical exists and self-references
    - robots_ok: 10 pts — no conflicting robots
    - title_exists: 10 pts — title present
    - meta_desc_exists: 10 pts — meta description present
    - h1_single: 10 pts — exactly one H1
    - broken_link_ratio: 10 pts — 0 broken links (pro-rated)
    Max: 110 (capped to 100)

    On-Page SEO Weight Breakdown (_SEO_KPI_WEIGHTS["on_page_seo"]):
    - title_quality: 25 pts — exists (10) + length 30-60 (15)
    - meta_desc_quality: 20 pts — exists (8) + length 50-320 (12)
    - h1_structure: 20 pts — exactly one H1 (15) + text present (5)
    - heading_structure: 10 pts — has H2 headings
    - canonical_present: 10 pts — canonical tag present
    - image_alt_coverage: 15 pts — percentage scaled
    Max: 100
    """
    w_tech = _SEO_KPI_WEIGHTS["technical_health"]
    tech_score = 0.0
    tech_components = {}

    tech_components["https"] = w_tech["https"] if fetch_result.get("https") else 0
    tech_score += tech_components["https"]

    tech_components["http_200"] = w_tech["http_200"] if fetch_result.get("http_status") == 200 else 0
    tech_score += tech_components["http_200"]

    tech_components["indexability"] = w_tech["indexability"] if not on_page.get("noindex") else 0
    tech_score += tech_components["indexability"]

    canonical_ok = on_page.get("canonical_exists") and on_page.get("canonical_self") is True
    tech_components["canonical"] = w_tech["canonical"] if canonical_ok else 0
    tech_score += tech_components["canonical"]

    robots_conflict = on_page.get("noindex") or on_page.get("nofollow")
    tech_components["robots_ok"] = 0 if robots_conflict else w_tech["robots_ok"]
    tech_score += tech_components["robots_ok"]

    tech_components["title_exists"] = w_tech["title_exists"] if on_page.get("title_exists") else 0
    tech_score += tech_components["title_exists"]

    tech_components["meta_desc_exists"] = w_tech["meta_desc_exists"] if on_page.get("meta_desc_exists") else 0
    tech_score += tech_components["meta_desc_exists"]

    tech_components["h1_single"] = w_tech["h1_single"] if on_page.get("h1_count") == 1 else 0
    tech_score += tech_components["h1_single"]

    checked = link_check.get("links_checked", 0)
    broken = len(link_check.get("broken_links", []))
    if checked > 0:
        ratio = 1.0 - (broken / max(1, checked))
        tech_components["broken_link_ratio"] = round(w_tech["broken_link_ratio"] * ratio, 1)
    else:
        tech_components["broken_link_ratio"] = w_tech["broken_link_ratio"]
    tech_score += tech_components["broken_link_ratio"]

    tech_score_capped = min(100.0, tech_score)
    tech_status = (
        "Excellent" if tech_score_capped >= 90
        else "Good" if tech_score_capped >= 75
        else "Fair" if tech_score_capped >= 50
        else "Poor"
    )

    w_onp = _SEO_KPI_WEIGHTS["on_page_seo"]
    onp_score = 0.0
    onp_components = {}

    title_sub = 0.0
    if on_page.get("title_exists"):
        title_sub += 10
        t_len = on_page.get("title_length") or 0
        if 30 <= t_len <= 60:
            title_sub += 15
        elif 20 <= t_len <= 70:
            title_sub += 8
    onp_components["title_quality"] = round(title_sub, 1)
    onp_score += title_sub

    md_sub = 0.0
    if on_page.get("meta_desc_exists"):
        md_sub += 8
        md_len = on_page.get("meta_desc_length") or 0
        if 50 <= md_len <= 320:
            md_sub += 12
        elif 30 <= md_len <= 350:
            md_sub += 6
    onp_components["meta_desc_quality"] = round(md_sub, 1)
    onp_score += md_sub

    h1_sub = 0.0
    if on_page.get("h1_count") == 1:
        h1_sub += 15
        if on_page.get("h1_texts"):
            h1_sub += 5
    onp_components["h1_structure"] = round(h1_sub, 1)
    onp_score += h1_sub

    hs_sub = w_onp["heading_structure"] if on_page.get("h2_count", 0) > 0 else 0
    onp_components["heading_structure"] = hs_sub
    onp_score += hs_sub

    cp_sub = w_onp["canonical_present"] if on_page.get("canonical_exists") else 0
    onp_components["canonical_present"] = cp_sub
    onp_score += cp_sub

    alt_pct = on_page.get("images_alt_percentage")
    if on_page.get("images_total", 0) == 0:
        ia_sub = w_onp["image_alt_coverage"]
    elif alt_pct is not None:
        ia_sub = round(w_onp["image_alt_coverage"] * (alt_pct / 100.0), 1)
    else:
        ia_sub = 0
    onp_components["image_alt_coverage"] = ia_sub
    onp_score += ia_sub

    onp_score_capped = min(100.0, onp_score)
    onp_status = (
        "Excellent" if onp_score_capped >= 90
        else "Good" if onp_score_capped >= 75
        else "Fair" if onp_score_capped >= 50
        else "Poor"
    )

    if link_check.get("links_checked", 0) > 0:
        lh_valid = link_check["links_checked"] - len(link_check.get("broken_links", []))
        lh_score = round((lh_valid / link_check["links_checked"]) * 100, 1)
        lh_status = (
            "Excellent" if lh_score >= 95
            else "Good" if lh_score >= 85
            else "Fair" if lh_score >= 70
            else "Poor"
        )
    else:
        lh_score = None
        lh_status = None

    indexable = (
        fetch_result.get("http_status") == 200
        and not on_page.get("noindex")
    )
    overall_components = [
        v for v in [tech_score_capped, onp_score_capped]
    ]
    if lh_score is not None:
        overall_components.append(lh_score)
    overall = round(sum(overall_components) / len(overall_components), 1) if overall_components else None
    overall_status = (
        "Excellent" if overall and overall >= 90
        else "Good" if overall and overall >= 75
        else "Fair" if overall and overall >= 50
        else "Poor" if overall
        else None
    )

    return {
        "overall_seo_health": {
            "score": overall,
            "status": overall_status,
        },
        "technical_health": {
            "score": round(tech_score_capped, 1),
            "status": tech_status,
            "components": tech_components,
            "weights": w_tech,
        },
        "on_page_seo": {
            "score": round(onp_score_capped, 1),
            "status": onp_status,
            "components": onp_components,
            "weights": w_onp,
        },
        "link_health": {
            "score": lh_score,
            "status": lh_status,
            "available": lh_score is not None,
        },
        "indexability": {
            "indexable": indexable,
            "status": "Indexable" if indexable else "Not Indexable",
        },
        "crawl_efficiency": {
            "score": None,
            "status": "Not Available",
            "reason": "Requires multi-page crawl data",
            "available": False,
        },
        "index_coverage": {
            "score": None,
            "status": "Not Available",
            "reason": "Requires Google Search Console data",
            "available": False,
        },
        "visibility_index": {
            "score": None,
            "status": "Not Available",
            "reason": "Requires search performance data",
            "available": False,
        },
        "ai_opportunity": {
            "score": None,
            "status": "Not Available",
            "reason": "Content Opportunity Score requires real content depth analysis",
            "available": False,
        },
    }


def _generate_issues(fetch_result: dict, on_page: dict, link_check: dict) -> list:
    """Phase 9: Dynamic issue generation from detected conditions."""
    issues = []

    def _add(severity, issue_title, evidence, why_it_matters, recommended_action):
        issues.append({
            "severity": severity,
            "issue": issue_title,
            "evidence": evidence,
            "why_it_matters": why_it_matters,
            "recommended_action": recommended_action,
        })

    if not fetch_result.get("https"):
        _add(
            "Critical",
            "HTTPS Missing",
            f"Final URL '{fetch_result.get('final_url') or fetch_result.get('original_url')}' was served over HTTP.",
            "HTTPS is a confirmed ranking factor. Browsers show security warnings on HTTP pages. Users lose trust and conversions drop.",
            "Install a valid SSL certificate and configure a permanent 301 redirect from all HTTP URLs to HTTPS.",
        )

    http_status = fetch_result.get("http_status")
    if http_status is not None and http_status != 200:
        if 500 <= http_status < 600:
            _add(
                "Critical",
                f"Server Error HTTP {http_status}",
                f"Page returned HTTP {http_status} instead of 200 OK.",
                "Search engines cannot index pages returning 5xx errors. Users see an error page. Severe organic traffic loss.",
                "Investigate server/application logs, fix the underlying error, and verify the page returns 200 OK.",
            )
        elif http_status == 404:
            _add(
                "Critical",
                "Page Returns 404 Not Found",
                f"URL returned HTTP 404.",
                "404 pages are not indexed. If this URL should exist, all backlink and internal link equity is wasted.",
                "Restore the page, or create a 301 redirect to the most relevant existing page.",
            )
        elif http_status == 403:
            _add(
                "High",
                "Page Returns 403 Forbidden",
                "Server returned 403 Forbidden. Automated access may be blocked.",
                "If legitimate users/bots see 403, the page cannot be indexed or accessed.",
                "Check server access rules, WAF rules, and authentication requirements. Public pages should return 200.",
            )
        elif http_status == 429:
            _add(
                "High",
                "Rate Limited (HTTP 429)",
                "Server returned 429 Too Many Requests.",
                "Aggressive rate-limiting can hinder search engine crawling and indexation.",
                "Whitelist legitimate search engine crawler IPs and adjust rate-limit thresholds for benign crawlers.",
            )
        else:
            _add(
                "Medium",
                f"Unexpected HTTP Status: {http_status}",
                f"Page returned HTTP {http_status}.",
                "Non-200 status codes may prevent proper indexation or cause poor UX.",
                "Review server configuration and ensure the page returns 200 OK for public content.",
            )

    if fetch_result.get("blocked"):
        _add(
            "Medium",
            "Automated Access Blocked",
            fetch_result.get("error_message") or "Website appears to block automated crawlers.",
            "Limited analysis reduces the reliability of detected issues. Real users may not be affected.",
            "No action required for the live site. For better audit coverage, consider whitelisting the audit tool.",
        )

    if on_page.get("noindex"):
        _add(
            "Critical",
            "Noindex Detected",
            f"Robots meta: '{on_page.get('robots_meta') or 'noindex present'}'.",
            "Pages with noindex are explicitly removed from search engine indexes. Zero organic traffic for this page.",
            "Remove 'noindex' from the robots meta tag and X-Robots-Tag header unless the page should intentionally be hidden.",
        )

    if on_page.get("nofollow"):
        _add(
            "Medium",
            "Nofollow Detected",
            f"Robots meta contains nofollow: '{on_page.get('robots_meta')}'.",
            "Nofollow prevents search engines from following internal links on this page, wasting internal equity flow.",
            "Remove 'nofollow' from robots meta unless you intentionally want to prevent link flow (rare for main pages).",
        )

    if not on_page.get("title_exists"):
        _add(
            "High",
            "Missing Title Tag",
            "No <title> tag found in the document <head>.",
            "Title tags are the #1 on-page SEO factor. Missing titles get auto-generated by search engines and rarely rank well.",
            "Add a unique, descriptive <title> tag (30–60 characters) that includes the primary target keyword.",
        )
    else:
        t_len = on_page.get("title_length") or 0
        if t_len > 60:
            _add(
                "Medium",
                "Title Tag Too Long",
                f"Title is {t_len} characters (recommended: 30–60).",
                "Search engines truncate titles longer than ~60 chars in SERPs, reducing CTR and message clarity.",
                "Shorten the title to 30–60 characters, keeping the most important keywords at the beginning.",
            )
        elif t_len < 30:
            _add(
                "Low",
                "Title Tag Very Short",
                f"Title is only {t_len} characters.",
                "Very short titles don't leverage the full SERP real estate available for keywords and CTR messaging.",
                "Expand the title with more descriptive keywords and a value proposition, up to ~60 characters.",
            )

    if not on_page.get("meta_desc_exists"):
        _add(
            "Medium",
            "Missing Meta Description",
            "No meta description tag found.",
            "Meta descriptions influence click-through rate in SERPs. Search engines will auto-generate snippets.",
            "Write a compelling meta description (50–320 chars) with a clear CTA and target keywords.",
        )
    else:
        md_len = on_page.get("meta_desc_length") or 0
        if md_len > 320:
            _add(
                "Low",
                "Meta Description Too Long",
                f"Meta description is {md_len} chars (recommended: 50–320).",
                "Long descriptions are truncated in SERPs.",
                "Condense to under 320 characters while preserving the CTA and key message.",
            )
        elif md_len < 50:
            _add(
                "Low",
                "Meta Description Very Short",
                f"Meta description is only {md_len} chars.",
                "Short descriptions rarely compel clicks. Underutilized SERP space.",
                "Expand with persuasive copy and a clear call to action.",
            )

    if on_page.get("h1_count") == 0:
        _add(
            "High",
            "Missing H1 Tag",
            "No H1 heading found on the page.",
            "H1 signals the primary page topic to search engines and users. Pages without H1s often underperform.",
            "Add exactly one descriptive H1 near the top of the content that includes the primary keyword.",
        )
    elif on_page.get("multiple_h1"):
        _add(
            "Medium",
            "Multiple H1 Tags",
            f"Found {on_page['h1_count']} H1 tags on the page.",
            "Multiple H1s confuse search engines about the primary topic. Modern HTML5 is more forgiving but best practice is one H1.",
            "Convert extra H1s to H2/H3 headings, keeping a single semantic H1 for the main topic.",
        )

    if not on_page.get("canonical_exists"):
        _add(
            "High",
            "Missing Canonical Tag",
            "No <link rel=canonical> tag found.",
            "Without a canonical, duplicate URLs (query strings, www/non-www) can split ranking signals.",
            "Add a self-referencing canonical tag on every page pointing to the preferred URL version.",
        )
    elif on_page.get("canonical_self") is False:
        _add(
            "Critical",
            "Canonical Points to Different URL",
            f"Canonical URL '{on_page.get('canonical_url')}' does not match the current page.",
            "If the canonical points elsewhere, THIS page is effectively de-indexed in favor of the canonical target.",
            "Unless this is intentional, update the canonical URL to reference the page's own final URL.",
        )

    img_total = on_page.get("images_total") or 0
    img_missing = on_page.get("images_missing_alt") or 0
    img_empty = on_page.get("images_empty_alt") or 0
    img_with = on_page.get("images_with_alt") or 0

    if img_total > 0 and img_missing > 0:
        attr_pct = on_page.get("images_alt_attribute_percentage") or 0
        _add(
            "Medium",
            f"Images Missing ALT Attribute",
            f"{img_missing} of {img_total} images have no ALT attribute at all. {img_with} have descriptive ALT, {img_empty} have empty alt=\"\".",
            "ALT attributes are required for WCAG accessibility compliance. Images completely missing the ALT attribute are the highest-priority image SEO gap.",
            "Add ALT attributes to images that currently have no alt attribute. Use descriptive text for content images and empty alt=\"\" for purely decorative images.",
        )

    if img_total > 0 and img_empty > 0:
        _add(
            "Info",
            f"Review Empty ALT Text",
            f"{img_empty} of {img_total} images use empty alt=\"\" (valid for decorative images).",
            "Empty alt=\"\" is the correct markup for purely decorative images. Informative images should have descriptive ALT text, not empty ALT.",
            "Review images with empty ALT text and confirm they are decorative. Informative images should use descriptive ALT text.",
        )

    broken_count = len(link_check.get("broken_links", []))
    if broken_count > 0:
        crit = sum(1 for b in link_check["broken_links"] if b.get("severity") == "Critical")
        high = sum(1 for b in link_check["broken_links"] if b.get("severity") == "High")
        _add(
            "Critical" if crit > 0 else "High",
            f"Broken Internal Links Found: {broken_count}",
            f"Detected {broken_count} broken internal links ({crit} Critical, {high} High) in the checked sample.",
            "Broken links waste crawl budget, frustrate users, and weaken internal link equity distribution. 5xx errors signal low quality.",
            "Fix each broken link: redirect 404s to relevant pages, restore deleted content, or remove invalid links.",
        )

    return issues


def _generate_recommendations(issues: list) -> list:
    """Phase 10: Recommendations generated from detected issues only."""
    if not issues:
        return [{
            "priority": "Info",
            "recommendation": "No critical SEO recommendations detected for the analyzed page.",
            "estimated_time": "—",
            "business_impact": "—",
            "ranking_potential": "—",
        }]

    severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}
    sorted_issues = sorted(issues, key=lambda i: severity_order.get(i["severity"], 99))

    time_map = {
        "Critical": "2-4 hours",
        "High": "1-2 hours",
        "Medium": "30-60 minutes",
        "Low": "15-30 minutes",
    }
    impact_map = {
        "Critical": "Very High",
        "High": "High",
        "Medium": "Medium",
        "Low": "Low",
    }

    recs = []
    seen_titles = set()
    for issue in sorted_issues:
        title = issue["issue"]
        if title in seen_titles:
            continue
        seen_titles.add(title)
        sev = issue["severity"]
        recs.append({
            "priority": sev,
            "recommendation": issue["recommended_action"],
            "issue_title": title,
            "estimated_time": time_map.get(sev, "—"),
            "business_impact": impact_map.get(sev, "—"),
            "ranking_potential": impact_map.get(sev, "—"),
        })

    return recs


def process_seo_analysis(url: str) -> dict:
    """REAL production-grade SEO analysis.

    NO simulated data. NO fake scores. NO hardcoded recommendations.
    KPIs are deterministic and fully documented.
    """
    from django.utils import timezone

    analyzed_at = timezone.now()

    original_url = normalize_url(url) if _HAS_SEO_UTILS else url
    base_domain = extract_domain(original_url) if _HAS_SEO_UTILS else ""
    session = build_http_session() if _HAS_SEO_UTILS else (requests.Session() if _HAS_REQUESTS else None)
    if session is None:
        return {
            "source": "error",
            "url": original_url,
            "analysis_source": "Unavailable",
            "analyzed_at": analyzed_at.isoformat(),
            "error": "Missing required dependencies (requests library).",
            "kpis": None,
            "issues": [],
            "recommendations": [],
            "prioritized_recommendations": [],
        }

    fetch_result = _fetch_page(session, original_url)

    if not fetch_result["success"] and not fetch_result.get("blocked"):
        error_summary = fetch_result.get("error_message") or "Page could not be analyzed."
        kpis = _calculate_kpis(fetch_result, {}, {"links_checked": 0, "broken_links": []})
        issues = _generate_issues(fetch_result, {}, {"links_checked": 0, "broken_links": []})
        recs = _generate_recommendations(issues)
        return {
            "source": "live_analysis",
            "analysis_source": "Live Page Analysis (Limited)",
            "url": original_url,
            "final_url": fetch_result.get("final_url") or original_url,
            "analyzed_at": analyzed_at.isoformat(),
            "http_status": fetch_result.get("http_status"),
            "https": fetch_result.get("https"),
            "response_time": fetch_result.get("response_time"),
            "content_type": fetch_result.get("content_type"),
            "page_size": fetch_result.get("page_size"),
            "error_type": fetch_result.get("error_type"),
            "error_message": fetch_result.get("error_message"),
            "blocked": fetch_result.get("blocked"),
            "fetch": fetch_result,
            "on_page": None,
            "link_check": {
                "links_discovered": 0,
                "links_checked": 0,
                "broken_links": [],
                "sample_limited": False,
            },
            "kpis": kpis,
            "issues": issues,
            "recommendations": recs,
            "prioritized_recommendations": recs,
            "executive_summary": {
                "overall_score": kpis["overall_seo_health"]["score"],
                "overall_status": kpis["overall_seo_health"]["status"],
                "critical_issues": sum(1 for i in issues if i["severity"] == "Critical"),
                "high_issues": sum(1 for i in issues if i["severity"] == "High"),
                "medium_issues": sum(1 for i in issues if i["severity"] == "Medium"),
                "low_issues": sum(1 for i in issues if i["severity"] == "Low"),
                "passed_checks": _count_passed_checks(fetch_result, {}, kpis),
                "links_discovered": 0,
                "links_checked": 0,
                "broken_links": 0,
            },
            "chart": None,
            "historical_note": "No historical data available yet. Run additional audits over time to build a performance trend.",
        }

    on_page = _analyze_on_page_seo(
        fetch_result.get("html_content"),
        fetch_result.get("final_url") or original_url,
        base_domain,
    )

    internal_links = on_page.get("internal_links_discovered", [])
    source_page = fetch_result.get("final_url") or original_url
    link_check = _check_internal_links(session, internal_links, source_page)

    kpis = _calculate_kpis(fetch_result, on_page, link_check)
    issues = _generate_issues(fetch_result, on_page, link_check)
    recs = _generate_recommendations(issues)

    critical_issues = sum(1 for i in issues if i["severity"] == "Critical")
    high_issues = sum(1 for i in issues if i["severity"] == "High")
    medium_issues = sum(1 for i in issues if i["severity"] == "Medium")
    low_issues = sum(1 for i in issues if i["severity"] == "Low")
    broken_links_count = len(link_check.get("broken_links", []))

    overall_score = kpis["overall_seo_health"]["score"]
    overall_status = kpis["overall_seo_health"]["status"]
    seo_grade = (
        "A" if overall_score and overall_score >= 90
        else "B" if overall_score and overall_score >= 80
        else "C" if overall_score and overall_score >= 70
        else "D" if overall_score
        else None
    )

    return {
        "source": "live_analysis",
        "analysis_source": "Live Page Analysis",
        "url": original_url,
        "final_url": fetch_result.get("final_url") or original_url,
        "analyzed_at": analyzed_at.isoformat(),
        "http_status": fetch_result.get("http_status"),
        "https": fetch_result.get("https"),
        "redirected": fetch_result.get("redirected"),
        "redirect_count": fetch_result.get("redirect_count"),
        "response_time": fetch_result.get("response_time"),
        "content_type": fetch_result.get("content_type"),
        "page_size": fetch_result.get("page_size"),
        "error_type": fetch_result.get("error_type"),
        "error_message": fetch_result.get("error_message"),
        "blocked": fetch_result.get("blocked"),
        "seo_score": overall_score,
        "seo_grade": seo_grade,
        "health_score": kpis["technical_health"]["score"],
        "visibility_score": None,
        "crawl_efficiency_score": None,
        "index_coverage_score": None,
        "ai_opportunity_score": None,
        "fetch": fetch_result,
        "on_page": on_page,
        "link_check": link_check,
        "kpis": kpis,
        "issues": issues,
        "recommendations": recs,
        "prioritized_recommendations": recs,
        "broken_links": link_check.get("broken_links", []),
        "broken_links_count": broken_links_count,
        "executive_summary": {
            "overall_score": overall_score,
            "overall_status": overall_status,
            "critical_issues": critical_issues,
            "high_issues": high_issues,
            "medium_issues": medium_issues,
            "low_issues": low_issues,
            "total_issues": len(issues),
            "passed_checks": _count_passed_checks(fetch_result, on_page, kpis),
            "links_discovered": on_page.get("links_internal", 0) + on_page.get("links_external", 0),
            "internal_links_discovered": on_page.get("links_internal", 0),
            "external_links_discovered": on_page.get("links_external", 0),
            "links_checked": link_check.get("links_checked", 0),
            "broken_links": broken_links_count,
        },
        "chart": None,
        "historical_note": "No historical data available yet. Run additional audits over time to build a performance trend.",
    }


def _count_passed_checks(fetch_result: dict, on_page: dict, kpis: dict) -> int:
    """Count checks that passed for the executive summary."""
    passed = 0
    if fetch_result.get("https"):
        passed += 1
    if fetch_result.get("http_status") == 200:
        passed += 1
    if on_page and not on_page.get("noindex"):
        passed += 1
    if on_page and on_page.get("title_exists"):
        passed += 1
    if on_page and on_page.get("meta_desc_exists"):
        passed += 1
    if on_page and on_page.get("h1_count") == 1:
        passed += 1
    if on_page and on_page.get("canonical_exists"):
        passed += 1
    if on_page and not on_page.get("multiple_h1"):
        passed += 1
    if on_page and on_page.get("images_total", 0) > 0 and on_page.get("images_missing_alt", 0) == 0:
        passed += 1
    if on_page and on_page.get("images_total", 0) == 0:
        passed += 1
    if kpis.get("link_health", {}).get("available") and len(kpis.get("link_health", {}).get("broken_links", [])) == 0:
        passed += 1
    return passed


def process_old_seo_analysis_DEPRECATED(url: str) -> dict:
    """DO NOT USE — Old simulated version kept for regression reference only."""
    return process_seo_analysis(url)


def process_social_analytics(handle: str) -> dict:
    """Enhanced processor for social media analytics.
    
    Provides: follower count, engagement metrics, platform breakdown, growth trends.
    """
    seed = sum(ord(c) for c in handle)

    # Optional social analytics API hook (Twitter/Meta/Third-party)
    social_api = os.environ.get('SOCIAL_API_URL')
    social_api_key = os.environ.get('SOCIAL_API_KEY')
    if social_api and _HAS_REQUESTS:
        try:
            params = {'handle': handle}
            headers = {}
            if social_api_key:
                headers['Authorization'] = f'Bearer {social_api_key}'
            resp = requests.get(social_api, params=params, headers=headers, timeout=10)
            if resp.ok:
                data = resp.json()
                data['source'] = 'api'
                return data
        except Exception:
            pass
    
    # Follower metrics
    base_followers = 5000
    followers = base_followers + (seed % 500000)
    
    # Engagement rates per platform
    platforms = {
        'Twitter': {'followers': int(followers * 0.4), 'engagement_rate': (seed % 5) + 0.5},
        'Instagram': {'followers': int(followers * 0.35), 'engagement_rate': (seed % 8) + 1.0},
        'YouTube': {'followers': int(followers * 0.15), 'engagement_rate': (seed % 6) + 0.8},
        'TikTok': {'followers': int(followers * 0.1), 'engagement_rate': (seed % 12) + 2.0},
    }
    
    total_engagement = sum(p['engagement_rate'] for p in platforms.values()) / len(platforms)
    
    # Content performance
    top_posts = [
        {'platform': 'Twitter', 'likes': 5000 + seed % 20000, 'shares': 100 + seed % 5000},
        {'platform': 'Instagram', 'likes': 15000 + seed % 50000, 'shares': 500 + seed % 10000},
        {'platform': 'TikTok', 'likes': 100000 + seed % 500000, 'shares': 10000 + seed % 100000},
    ]
    
    # Follower growth trend
    labels = ['Week 1', 'Week 2', 'Week 3', 'Week 4']
    growth_trend = [
        followers * (1 - 0.03 + (seed % 5) / 100.0),
        followers * (1 - 0.02 + (seed % 5) / 100.0),
        followers * (1 - 0.01 + (seed % 5) / 100.0),
        followers
    ]
    
    return {
        'source': 'simulated',
        'handle': handle,
        'total_followers': int(followers),
        'total_followers_formatted': f'{int(followers):,}',
        'average_engagement_rate': round(total_engagement, 2),
        'engagement_rate_percent': f'{round(total_engagement, 2)}%',
        'platforms': platforms,
        'top_posts': top_posts,
        'monthly_growth': f'{round((seed % 30) / 10, 1)}%',
        'posts_this_month': 5 + (seed % 30),
        'audience_demographics': {
            'age_18_24': f'{seed % 40}%',
            'age_25_34': f'{20 + (seed % 40)}%',
            'age_35_plus': f'{20 + (seed % 40)}%',
        },
        'summary': f'{handle} has {int(followers):,} followers across platforms with {round(total_engagement, 2)}% average engagement.',
        'chart': {
            'labels': labels,
            'values': [int(x) for x in growth_trend],
            'title': 'Followers Growth Over 4 Weeks'
        }
    }


SUPPORTED_SOCIAL_TRACKING_PLATFORMS = {
    'twitter': 'X / Twitter',
    'instagram': 'Instagram',
    'tiktok': 'TikTok',
    'facebook': 'Facebook',
    'linkedin': 'LinkedIn',
    'youtube': 'YouTube',
}
SUPPORTED_SOCIAL_TRACKING_DOMAINS = {
    'twitter.com': 'twitter',
    'x.com': 'twitter',
    'instagram.com': 'instagram',
    'tiktok.com': 'tiktok',
    'facebook.com': 'facebook',
    'fb.com': 'facebook',
    'linkedin.com': 'linkedin',
    'youtube.com': 'youtube',
    'youtu.be': 'youtube',
    'www.twitter.com': 'twitter',
    'www.x.com': 'twitter',
    'www.instagram.com': 'instagram',
    'www.tiktok.com': 'tiktok',
    'www.facebook.com': 'facebook',
    'www.fb.com': 'facebook',
    'www.linkedin.com': 'linkedin',
    'www.youtube.com': 'youtube',
    'm.youtube.com': 'youtube',
}
_SOCIAL_SPECIAL_PATH_PREFIXES = {
    'linkedin': {'company', 'in', 'school', 'organization', 'groups'},
    'instagram': set(),
    'tiktok': set(),
    'facebook': {'groups', 'pages', 'profile.php'},
    'youtube': {'channel', 'c', 'user'},
    'twitter': set(),
}
POSITIVE_SENTIMENT_WORDS = {'good', 'great', 'love', 'excellent', 'happy', 'like', 'positive', 'awesome'}
NEGATIVE_SENTIMENT_WORDS = {'bad', 'terrible', 'hate', 'angry', 'negative', 'poor', 'sad', 'wrong'}


def _format_followers(value):
    return f'{int(value):,}' if value is not None else 'Not Available'


def _format_engagement_rate(value):
    return f'{value:.2f}%' if value is not None else 'Not Available'


def _empty_growth_chart():
    return {
        'available': False,
        'labels': [],
        'values': [],
        'title': 'Audience Growth Trajectory',
        'message': 'Historical data is not available yet. Growth tracking will begin after the first saved snapshot.',
    }


CRAWL_STATUS_SUCCESS = 'success'
CRAWL_STATUS_PARTIAL = 'partial'
CRAWL_STATUS_PLATFORM_RESTRICTED = 'platform_restricted'
CRAWL_STATUS_AUTH_REQUIRED = 'auth_required'
CRAWL_STATUS_RATE_LIMITED = 'rate_limited'
CRAWL_STATUS_PROFILE_NOT_FOUND = 'profile_not_found'
CRAWL_STATUS_PRIVATE_ACCOUNT = 'private_account'
CRAWL_STATUS_REQUEST_FAILED = 'request_failed'

CRAWL_STATUS_LABELS = {
    CRAWL_STATUS_SUCCESS: 'Success',
    CRAWL_STATUS_PARTIAL: 'Partial Data',
    CRAWL_STATUS_PLATFORM_RESTRICTED: 'Platform Restricted',
    CRAWL_STATUS_AUTH_REQUIRED: 'Authentication Required',
    CRAWL_STATUS_RATE_LIMITED: 'Rate Limited',
    CRAWL_STATUS_PROFILE_NOT_FOUND: 'Profile Not Found',
    CRAWL_STATUS_PRIVATE_ACCOUNT: 'Private Account',
    CRAWL_STATUS_REQUEST_FAILED: 'Request Failed',
}

ANALYSIS_SOURCE_PUBLIC_CRAWL = 'Public Profile Analysis'
ANALYSIS_SOURCE_API = 'Official API'
ANALYSIS_SOURCE_DB = 'Stored Snapshot'
ANALYSIS_SOURCE_UNAVAILABLE = 'Unavailable'

PROFILE_PLATFORM_URL_MAP = {
    'instagram': 'https://www.instagram.com/{handle}/',
    'facebook': 'https://www.facebook.com/{handle}',
    'tiktok': 'https://www.tiktok.com/@{handle}',
    'youtube': 'https://www.youtube.com/@{handle}',
    'twitter': 'https://x.com/{handle}',
    'linkedin': 'https://www.linkedin.com/company/{handle}/',
}

_PROFILE_COMPLETENESS_FIELDS_CRAWLABLE = (
    'display_name',
    'bio',
    'profile_image',
    'website',
)


def _build_profile_url(platform, normalized_handle):
    tmpl = PROFILE_PLATFORM_URL_MAP.get(platform)
    if tmpl and normalized_handle:
        return tmpl.format(handle=normalized_handle)
    return None


def _new_normalized_profile(platform, handle, raw_input):
    return {
        'platform': platform or None,
        'profile_url': _build_profile_url(platform, handle),
        'handle': handle or None,
        'display_name': None,
        'bio': None,
        'profile_image': None,
        'website': None,
        'verified': None,
        'followers': None,
        'following': None,
        'posts_count': None,
        'recent_posts': [],
        'likes': None,
        'comments': None,
        'shares': None,
        'views': None,
        'analysis_source': ANALYSIS_SOURCE_UNAVAILABLE,
        'crawl_status': CRAWL_STATUS_REQUEST_FAILED,
        'crawl_message': '',
        'analyzed_at': None,
        'raw_input': raw_input,
    }


def _crawl_public_profile(platform, normalized_handle, raw_profile_url=None, timeout=10):
    """Crawl a public social profile and extract honest, parseable public data only.

    Never fabricates. Uses meta-tags, title, JSON-LD when present.
    Sets crawl_status honestly per-platform.
    """
    profile = _new_normalized_profile(platform, normalized_handle, raw_profile_url or normalized_handle)
    profile['analyzed_at'] = timezone.now()

    profile_url = raw_profile_url or _build_profile_url(platform, normalized_handle)
    if not profile_url:
        profile['crawl_status'] = CRAWL_STATUS_REQUEST_FAILED
        profile['crawl_message'] = 'Unable to resolve profile URL.'
        return profile
    profile['profile_url'] = profile_url

    if not (_HAS_REQUESTS):
        profile['crawl_status'] = CRAWL_STATUS_REQUEST_FAILED
        profile['crawl_message'] = 'HTTP client (requests) is not available in this environment.'
        profile['analysis_source'] = ANALYSIS_SOURCE_UNAVAILABLE
        return profile

    user_agent = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0 Safari/537.36'
    )
    headers = {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    try:
        resp = requests.get(profile_url, headers=headers, timeout=timeout, allow_redirects=True)
    except Exception as exc:
        profile['crawl_status'] = CRAWL_STATUS_REQUEST_FAILED
        profile['crawl_message'] = f'HTTP request failed: {getattr(exc, "__class__", type(exc)).__name__}'
        profile['analysis_source'] = ANALYSIS_SOURCE_UNAVAILABLE
        return profile

    http_status = resp.status_code
    final_url = resp.url

    if http_status == 404 or '/404' in final_url or 'not-found' in final_url.lower():
        profile['crawl_status'] = CRAWL_STATUS_PROFILE_NOT_FOUND
        profile['crawl_message'] = 'Profile URL returned 404 Not Found.'
        profile['analysis_source'] = ANALYSIS_SOURCE_PUBLIC_CRAWL
        return profile

    if http_status in (429,):
        profile['crawl_status'] = CRAWL_STATUS_RATE_LIMITED
        profile['crawl_message'] = 'Rate-limited by the platform (HTTP 429).'
        profile['analysis_source'] = ANALYSIS_SOURCE_PUBLIC_CRAWL
        return profile

    if http_status in (401, 403):
        profile['crawl_status'] = CRAWL_STATUS_AUTH_REQUIRED
        profile['crawl_message'] = 'Authentication required by the platform (HTTP {}).'.format(http_status)
        profile['analysis_source'] = ANALYSIS_SOURCE_PUBLIC_CRAWL
        return profile

    if http_status >= 400:
        profile['crawl_status'] = CRAWL_STATUS_PLATFORM_RESTRICTED
        profile['crawl_message'] = 'Platform returned HTTP {} without public profile data.'.format(http_status)
        profile['analysis_source'] = ANALYSIS_SOURCE_PUBLIC_CRAWL
        return profile

    html = resp.text or ''
    soup = None
    if _HAS_BS4_GLOBAL and html:
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception:
            soup = None

    def _meta(prop_name, attr='property'):
        if not soup:
            return None
        try:
            tag = soup.find('meta', attrs={attr: prop_name})
            return (tag.get('content') or '').strip() if tag else None
        except Exception:
            return None

    og_title = _meta('og:title') or _meta('twitter:title', attr='name') or None
    og_desc = _meta('og:description') or _meta('twitter:description', attr='name') or None
    og_image = _meta('og:image') or _meta('twitter:image', attr='name') or None
    og_url = _meta('og:url') or None
    og_site = (_meta('og:site_name') or '').lower()

    title_text = None
    if soup:
        try:
            title_tag = soup.find('title')
            if title_tag and title_tag.string:
                title_text = (title_tag.string or '').strip()
        except Exception:
            pass

    extracted_any = False

    if og_title:
        title_part = og_title.split('•')[0].split('|')[0].split('(')[0].strip()
        if title_part and len(title_part) >= 1:
            profile['display_name'] = title_part
            extracted_any = True

    if og_desc:
        profile['bio'] = og_desc.strip() or None
        extracted_any = True

    if og_image:
        profile['profile_image'] = og_image.strip() or None
        extracted_any = True

    if og_url:
        profile['profile_url'] = og_url.strip() or profile['profile_url']

    if title_text and not profile['display_name']:
        t = title_text.split('•')[0].split('|')[0].split('(')[0].strip()
        if t:
            profile['display_name'] = t
            extracted_any = True

    if normalized_handle and not profile['display_name']:
        profile['display_name'] = normalized_handle

    blocked_keywords = ('login', 'sign in', 'join linkedin', 'sign up', 'log in', 'access denied')
    blocked = any(k in (title_text or '').lower() for k in blocked_keywords)

    def _meta_num(regex_pattern, text_pool):
        if not text_pool:
            return None
        m = re.search(regex_pattern, text_pool)
        if not m:
            return None
        raw = m.group(1).replace(',', '').replace(' ', '')
        try:
            return int(float(raw))
        except Exception:
            mult = 1.0
            suffix = m.group(1).lower()
            if suffix.endswith('k'):
                mult = 1_000
            elif suffix.endswith('m'):
                mult = 1_000_000
            elif suffix.endswith('b'):
                mult = 1_000_000_000
            num_part = re.sub(r'[^0-9.]', '', m.group(1))
            try:
                return int(float(num_part) * mult)
            except Exception:
                return None
        return None

    # Per-platform honest statuses. All major platforms block unauthenticated crawlers for
    # counts/interactions; we do NOT fabricate. Set realistic restricted status.
    restricted_platforms_blocking_counts = {
        'instagram', 'linkedin', 'facebook', 'tiktok', 'youtube', 'twitter',
    }

    profile['analysis_source'] = ANALYSIS_SOURCE_PUBLIC_CRAWL

    if blocked and platform in restricted_platforms_blocking_counts:
        profile['crawl_status'] = CRAWL_STATUS_PLATFORM_RESTRICTED
        if extracted_any:
            profile['crawl_status'] = CRAWL_STATUS_PARTIAL
        profile['crawl_message'] = (
            'Some public metrics could not be retrieved without an official provider. '
            'Basic profile metadata extracted from public HTML where available.'
        )
        return profile

    if http_status in (200, 301, 302) and extracted_any and platform in restricted_platforms_blocking_counts:
        # Even a 200 w/ some meta tags rarely has follower counts for these platforms.
        profile['crawl_status'] = CRAWL_STATUS_PARTIAL
        profile['crawl_message'] = (
            'Profile detected. Follower counts and interaction data require an official provider; '
            'public profile metadata is displayed where parseable.'
        )
        return profile

    if extracted_any:
        profile['crawl_status'] = CRAWL_STATUS_SUCCESS
        profile['crawl_message'] = 'Public profile data extracted successfully.'
    else:
        profile['crawl_status'] = CRAWL_STATUS_PARTIAL
        profile['crawl_message'] = 'Connected but no parseable public fields were exposed.'

    return profile


def _aggregate_recent_post_stats(recent_posts):
    likes = comments = shares = views = 0
    any_field = False
    if not recent_posts:
        return None, None, None, None, 0
    for p in recent_posts:
        if isinstance(p, dict):
            lk = p.get('likes')
            cm = p.get('comments')
            sh = p.get('shares')
            vw = p.get('views')
            if lk is not None:
                try: likes += int(lk); any_field = True
                except Exception: pass
            if cm is not None:
                try: comments += int(cm); any_field = True
                except Exception: pass
            if sh is not None:
                try: shares += int(sh); any_field = True
                except Exception: pass
            if vw is not None:
                try: views += int(vw); any_field = True
                except Exception: pass
    if not any_field:
        return None, None, None, None, len(recent_posts)
    n = len(recent_posts) or 1
    return likes // n, comments // n, shares // n, views // n, len(recent_posts)


def _calculate_engagement_rate(avg_likes, avg_comments, avg_shares, followers):
    """Average Engagement Rate = (avg interactions / followers) * 100.

    Only returns a number when genuine interaction data AND follower count exist.
    """
    if followers is None or followers <= 0:
        return None, 'Insufficient public follower data.'
    inter = 0
    present = False
    if avg_likes is not None:
        inter += avg_likes
        present = True
    if avg_comments is not None:
        inter += avg_comments
        present = True
    if avg_shares is not None:
        inter += avg_shares
        present = True
    if not present or inter <= 0:
        return None, 'Insufficient public interaction data.'
    return round((inter / followers) * 100, 2), None


def _calculate_posting_frequency(recent_posts, days_horizon=30):
    """posts/week, computed from real timestamps only. None otherwise."""
    if not recent_posts:
        return None, 'Insufficient public posting history.'
    stamps = []
    for p in recent_posts:
        if isinstance(p, dict):
            ts = p.get('timestamp') or p.get('created_at') or p.get('posted_at')
            if ts:
                stamps.append(ts)
    if len(stamps) < 2:
        return None, 'Insufficient public posting history.'
    try:
        stamps_sorted = sorted(stamps)
        delta = stamps_sorted[-1] - stamps_sorted[0]
        total_days = getattr(delta, 'days', None)
        if total_days is None:
            return None, 'Timestamps are not comparable.'
        if total_days <= 0:
            total_days = max(days_horizon, 1)
        posts_per_week = (len(stamps) / total_days) * 7
        return round(posts_per_week, 2), None
    except Exception:
        return None, 'Unable to compute posting frequency.'


def _classify_content_activity(posts_per_week):
    """Deterministic thresholds: >=3 posts/week → High; >=1 → Medium; <1 → Low."""
    if posts_per_week is None:
        return None
    if posts_per_week >= 3.0:
        return 'High'
    if posts_per_week >= 1.0:
        return 'Medium'
    return 'Low'


def _calculate_profile_completeness(profile):
    """Score profile completeness from actually crawlable fields ONLY.

    Denominator = len(_PROFILE_COMPLETENESS_FIELDS_CRAWLABLE).
    Numerator = how many of those fields are truthy in the profile dict.
    """
    denom = len(_PROFILE_COMPLETENESS_FIELDS_CRAWLABLE)
    if denom == 0:
        return 0, 0, denom
    num = 0
    for key in _PROFILE_COMPLETENESS_FIELDS_CRAWLABLE:
        val = profile.get(key)
        if val:
            if isinstance(val, str) and not val.strip():
                continue
            num += 1
    pct = round((num / denom) * 100, 1) if denom else 0
    return pct, num, denom


def _analyze_sentiment_from_profile(profile):
    """Run existing sentiment wordlist method ONLY on real extracted bio/post text."""
    texts = []
    bio = profile.get('bio') or None
    if bio:
        texts.append(bio)
    recent = profile.get('recent_posts') or []
    for p in recent:
        if isinstance(p, dict):
            cap = p.get('caption') or p.get('text') or p.get('description')
            if cap:
                texts.append(cap)
    if not texts:
        return {'positive': 0, 'neutral': 0, 'negative': 0}, None, 'Insufficient public content.'
    counts = {'positive': 0, 'neutral': 0, 'negative': 0}
    pos_words = set(w.lower() for w in ('love','great','happy','amazing','best','awesome','excellent','beautiful','perfect','brilliant','success','thank','grateful','proud','excited','incredible','fantastic','outstanding'))
    neg_words = set(w.lower() for w in ('sad','bad','hate','terrible','awful','worst','disappointing','angry','fail','failed','negative','disaster','horrible','annoying','disgust','frustrated','waste','useless'))
    for t in texts:
        lower = t.lower()
        pos = sum(1 for w in pos_words if re.search(r'\b' + re.escape(w) + r'\b', lower))
        neg = sum(1 for w in neg_words if re.search(r'\b' + re.escape(w) + r'\b', lower))
        if pos > neg:
            counts['positive'] += 1
        elif neg > pos:
            counts['negative'] += 1
        else:
            counts['neutral'] += 1
    total = sum(counts.values())
    pct = {}
    if total > 0:
        for k, v in counts.items():
            pct[k] = round((v / total) * 100, 1)
    else:
        pct = {'positive': None, 'neutral': None, 'negative': None}
        return counts, pct, 'Insufficient public content.'
    return counts, pct, None


def _generate_actionable_insights(profile, completeness_pct, posts_per_week, engagement_rate, data_availability):
    """Deterministic recommendations grounded in measured facts. No fabrications."""
    tips = []
    if profile.get('bio') in (None, ''):
        tips.append({'level': 'info', 'icon': 'pen-line',
                     'text': 'Add a clear profile bio to tell visitors who you are.'})
    if profile.get('website') in (None, ''):
        tips.append({'level': 'info', 'icon': 'link',
                     'text': 'Add a website link to strengthen profile conversion.'})
    if completeness_pct is not None and completeness_pct < 80:
        tips.append({'level': 'warning', 'icon': 'shield-alert',
                     'text': 'Complete missing profile information for a stronger first impression.'})
    if posts_per_week is not None and posts_per_week < 1.0:
        tips.append({'level': 'warning', 'icon': 'calendar-clock',
                     'text': 'Increase publishing consistency (currently {:.1f} posts/week). Aim for 3+/week.'.format(posts_per_week)})
    if engagement_rate is None or data_availability.get('engagement') == 'unavailable':
        tips.append({'level': 'info', 'icon': 'database',
                     'text': 'Configure an official social provider to enable real engagement KPI tracking.'})
    if data_availability.get('followers') == 'unavailable':
        tips.append({'level': 'info', 'icon': 'users',
                     'text': 'Configure an official social provider to enable real follower/audience KPIs.'})
    if data_availability.get('growth') == 'unavailable':
        tips.append({'level': 'info', 'icon': 'trending-up',
                     'text': 'Re-analyze over time to build historical snapshots for growth & trend reporting.'})
    if not tips:
        tips.append({'level': 'success', 'icon': 'check-circle',
                     'text': 'Profile looks healthy. Continue consistent publishing.'})
    return tips


def _build_data_availability(profile, kpi):
    da = {}
    da['platform'] = 'available' if profile.get('platform') else 'unavailable'
    da['account'] = 'available' if profile.get('handle') else 'unavailable'
    da['display_name'] = 'available' if profile.get('display_name') else 'unavailable'
    da['bio'] = 'available' if profile.get('bio') else 'unavailable'
    da['profile_image'] = 'available' if profile.get('profile_image') else 'unavailable'
    da['website'] = 'available' if profile.get('website') else 'unavailable'
    da['verified'] = 'available' if profile.get('verified') is not None else 'unavailable'
    da['followers'] = 'available' if profile.get('followers') is not None or (kpi or {}).get('followers') is not None else 'unavailable'
    da['following'] = 'available' if profile.get('following') is not None else 'unavailable'
    da['posts_count'] = 'available' if profile.get('posts_count') is not None else 'unavailable'
    da['engagement'] = 'available' if (kpi or {}).get('engagement_rate') is not None else 'unavailable'
    da['posting_frequency'] = 'available' if (kpi or {}).get('posts_per_week') is not None else 'unavailable'
    da['sentiment'] = 'available' if (kpi or {}).get('sentiment_percentages') else 'unavailable'
    da['growth'] = 'available' if (kpi or {}).get('growth_available') else 'unavailable'
    return da


def _profile_to_kpi(profile):
    """Runs all deterministic KPI calculations against normalized profile.

    Returns a dict suitable for the dashboard. All formulas are documented in code
    and tests. Missing data → None / Not Available explicitly.
    """
    kpi = {}
    recent = profile.get('recent_posts') or []
    avg_likes, avg_comments, avg_shares, avg_views, n_posts = _aggregate_recent_post_stats(recent)
    kpi['avg_likes'] = avg_likes
    kpi['avg_comments'] = avg_comments
    kpi['avg_shares'] = avg_shares
    kpi['avg_views'] = avg_views
    kpi['analyzed_posts_count'] = n_posts

    eng_rate, eng_reason = _calculate_engagement_rate(avg_likes, avg_comments, avg_shares, profile.get('followers'))
    kpi['engagement_rate'] = eng_rate
    kpi['engagement_reason'] = eng_reason

    ppw, ppw_reason = _calculate_posting_frequency(recent, days_horizon=30)
    kpi['posts_per_week'] = ppw
    kpi['posts_per_week_reason'] = ppw_reason

    activity = _classify_content_activity(ppw)
    kpi['content_activity'] = activity
    kpi['content_activity_thresholds'] = 'High: >=3/wk, Medium: >=1/wk, Low: <1/wk'

    completeness_pct, num_fields, denom_fields = _calculate_profile_completeness(profile)
    kpi['profile_completeness'] = completeness_pct
    kpi['profile_completeness_parts'] = f'{num_fields} / {denom_fields}'
    kpi['profile_completeness_formula'] = (
        'Only crawlable fields included: ' + ', '.join(_PROFILE_COMPLETENESS_FIELDS_CRAWLABLE) +
        f'. Score = (non-empty / {denom_fields}) * 100'
    )

    sent_counts, sent_pct, sent_reason = _analyze_sentiment_from_profile(profile)
    kpi['sentiment_counts'] = sent_counts
    kpi['sentiment_percentages'] = sent_pct
    kpi['sentiment_reason'] = sent_reason

    kpi['growth_available'] = False  # never true from a single crawl alone (needs snapshots)
    kpi['growth_reason'] = 'Growth requires historical snapshots for the same platform + account.'
    return kpi


def _run_crawl_pipeline(handle_input, normalized_handle, detected_platform, selected_platforms, days, user):
    """Run the public profile crawler → normalizer → KPI engine. Returns (profile, kpi, snapshot) OR None on skip."""
    if not detected_platform or not normalized_handle:
        return None
    raw_profile_url = None
    if re.match(r'^https?://', handle_input or '', re.I):
        raw_profile_url = handle_input
    profile = _crawl_public_profile(detected_platform, normalized_handle, raw_profile_url)
    if not profile:
        return None
    kpi = _profile_to_kpi(profile)

    snapshot = None
    try:
        followers = profile.get('followers') or None
        engagement = kpi.get('engagement_rate') or None
        sentiment_counts = kpi.get('sentiment_counts') or {'positive': 0, 'neutral': 0, 'negative': 0}

        if any(v is not None for v in (followers, engagement, profile.get('following'), profile.get('posts_count'))):
            snap_status = 'success' if profile.get('crawl_status') == CRAWL_STATUS_SUCCESS else 'partial'
            if profile.get('crawl_status') in (CRAWL_STATUS_REQUEST_FAILED, CRAWL_STATUS_PROFILE_NOT_FOUND):
                snap_status = 'unavailable'
            snapshot = _save_social_tracking_snapshot(
                user=user,
                handle_input=handle_input,
                normalized_handle=normalized_handle,
                detected_platform=detected_platform,
                selected_platforms=list(selected_platforms or []),
                total_followers=followers,
                engagement_rate=engagement,
                sentiment_counts=sentiment_counts,
                data_source='crawl',
                status=snap_status,
            )
    except Exception:
        snapshot = None
    return profile, kpi, snapshot


def _format_int(n):
    if n is None:
        return 'Not Available'
    try:
        return f'{int(n):,}'
    except Exception:
        return 'Not Available'


def _format_ppw(ppw):
    if ppw is None:
        return 'Not Available'
    try:
        return f'{float(ppw):.1f} posts/week'
    except Exception:
        return 'Not Available'


def _format_pct(pct, suffix='%'):
    if pct is None:
        return 'Not Available'
    try:
        return f'{float(pct):.1f}{suffix}'
    except Exception:
        return 'Not Available'


def _format_engagement(rate):
    if rate is None:
        return 'Not Available'
    try:
        return f'{float(rate):.2f}%'
    except Exception:
        return 'Not Available'


def _format_activity(activity):
    if activity is None:
        return 'Not Available'
    return str(activity)


def _format_bool(val):
    if val is None:
        return 'Not Available'
    return 'Yes' if bool(val) else 'No'


def _format_source(profile_source):
    return profile_source or ANALYSIS_SOURCE_UNAVAILABLE


def _format_crawl_status(crawl_status):
    return CRAWL_STATUS_LABELS.get(crawl_status or CRAWL_STATUS_REQUEST_FAILED, 'Unknown')


def _crawl_status_badge_class(crawl_status):
    if crawl_status == CRAWL_STATUS_SUCCESS:
        return 'bg-success-soft text-success'
    if crawl_status == CRAWL_STATUS_PARTIAL:
        return 'bg-warning-soft text-warning'
    if crawl_status in (CRAWL_STATUS_PROFILE_NOT_FOUND, CRAWL_STATUS_PRIVATE_ACCOUNT, CRAWL_STATUS_REQUEST_FAILED):
        return 'bg-danger-soft text-danger'
    return 'bg-secondary-soft text-secondary'


def _build_growth_chart_from_pipeline(user, normalized_handle, detected_platform):
    """Thin alias; growth always requires 2+ snapshots."""
    return _build_growth_chart(user, normalized_handle, detected_platform)


def _build_social_tracking_result(
    *,
    handle_input,
    normalized_handle,
    selected_platforms,
    detected_platform='',
    source='unavailable',
    status='unavailable',
    message='',
    error_code='',
    total_followers=None,
    engagement_rate=None,
    sentiment_counts=None,
    platforms=None,
    growth_chart=None,
    last_sync=None,
    profile=None,
    kpi=None,
    insights=None,
    data_availability=None,
):
    profile = profile or {}
    kpi = kpi or {}

    platform_display = profile.get('platform') or detected_platform or None
    if platform_display and SUPPORTED_SOCIAL_TRACKING_PLATFORMS.get(platform_display):
        platform_label = SUPPORTED_SOCIAL_TRACKING_PLATFORMS[platform_display]
    elif platform_display:
        platform_label = str(platform_display).title()
    else:
        platform_label = 'Not Available'

    handle_display = f'@{profile.get("handle")}' if profile.get('handle') else (
        f'@{normalized_handle}' if normalized_handle else handle_input
    )

    analysis_source = _format_source(profile.get('analysis_source'))
    crawl_status = profile.get('crawl_status')
    crawl_status_label = _format_crawl_status(crawl_status)
    crawl_badge_class = _crawl_status_badge_class(crawl_status)
    crawl_message = profile.get('crawl_message') or message or ''
    analyzed_at = profile.get('analyzed_at') or last_sync or timezone.now()
    analyzed_at_display = analyzed_at.strftime('%Y-%m-%d %H:%M') if analyzed_at else 'Never Synced'

    # --- Dashboard: SECTION A: Profile Overview
    display_name = profile.get('display_name')
    website = profile.get('website')
    verified = profile.get('verified')
    profile_url = profile.get('profile_url')
    bio = profile.get('bio')
    profile_image = profile.get('profile_image')

    # --- Dashboard: SECTION B: Audience Metrics
    followers = profile.get('followers') if profile.get('followers') is not None else total_followers
    following = profile.get('following')
    if followers is not None and following is not None and following > 0:
        try:
            ffratio = round(float(followers) / float(following), 2)
        except Exception:
            ffratio = None
    else:
        ffratio = None

    # --- Dashboard: SECTION C: Content Metrics
    posts_count = profile.get('posts_count')
    posts_per_week = kpi.get('posts_per_week')
    posts_per_week_reason = kpi.get('posts_per_week_reason')
    content_activity = kpi.get('content_activity')

    # --- Dashboard: SECTION D: Engagement Metrics
    avg_likes = kpi.get('avg_likes')
    avg_comments = kpi.get('avg_comments')
    avg_shares = kpi.get('avg_shares')
    kpi_engagement_rate = kpi.get('engagement_rate') or engagement_rate
    engagement_reason = kpi.get('engagement_reason')
    if kpi_engagement_rate is not None:
        eng_display = _format_engagement(kpi_engagement_rate)
        eng_formula = 'Average Engagement Rate = ((avg likes + avg comments + avg shares) / followers) × 100'
    else:
        eng_display = 'Not Available'
        eng_formula = 'Not Available'

    # --- Dashboard: SECTION E: Sentiment
    kpi_sent_counts = kpi.get('sentiment_counts') or sentiment_counts or {'positive': 0, 'neutral': 0, 'negative': 0}
    kpi_sent_pct = kpi.get('sentiment_percentages')
    if kpi_sent_pct is None:
        total_sent = sum(kpi_sent_counts.values())
        if total_sent:
            kpi_sent_pct = {k: round((v / total_sent) * 100, 1) for k, v in kpi_sent_counts.items()}
        else:
            kpi_sent_pct = {'positive': None, 'neutral': None, 'negative': None}
    sentiment_reason = kpi.get('sentiment_reason')
    positive_pct = kpi_sent_pct.get('positive')
    if positive_pct is not None:
        sentiment_badge = f'Positive ({positive_pct:.1f}%)'
        sentiment_message_display = f'Based on {sum(kpi_sent_counts.values())} analyzed text sample(s).'
        sentiment_available = True
    else:
        sentiment_badge = 'Not Available'
        sentiment_message_display = sentiment_reason or 'Sentiment data is not available for this account yet.'
        sentiment_available = False

    # --- Dashboard: SECTION F: Growth
    growth_chart_final = growth_chart or _empty_growth_chart()
    growth_available = kpi.get('growth_available', False) or bool(growth_chart_final and growth_chart_final.get('available'))
    growth_reason = kpi.get('growth_reason') or growth_chart_final.get('message') or 'Growth requires historical snapshots for the same platform + account.'

    # --- Dashboard: SECTION G: Insights (deterministic)
    profile_completeness_pct = kpi.get('profile_completeness')
    profile_completeness_parts = kpi.get('profile_completeness_parts')
    profile_completeness_formula = kpi.get('profile_completeness_formula') or ''
    if data_availability is None:
        data_availability = _build_data_availability(profile, kpi)
    if insights is None:
        insights = _generate_actionable_insights(
            profile,
            profile_completeness_pct,
            posts_per_week,
            kpi_engagement_rate,
            data_availability,
        )

    # Last sync
    if last_sync:
        last_sync_display = last_sync.strftime('%Y-%m-%d %H:%M')
    elif analyzed_at:
        last_sync_display = analyzed_at_display
    else:
        last_sync_display = 'Never Synced'

    provider_configured = bool(os.environ.get('SOCIAL_API_URL'))
    if source == 'api':
        provider_status = 'connected'
        provider_status_text = 'Connected'
    else:
        provider_status = 'not_configured'
        provider_status_text = 'Provider Not Configured'

    # Back-compat keys preserved
    total_followers_final = followers if followers is not None else total_followers
    display_handle = f'@{normalized_handle}' if normalized_handle else handle_input
    engagement_formula_final = eng_formula
    if engagement_rate is not None and kpi_engagement_rate is None:
        eng_display = _format_engagement_rate(engagement_rate)
        engagement_formula_final = '((likes + comments + shares) / (followers * posts_in_period)) * 100'

    any_real_data = (
        total_followers_final is not None
        or bool(platforms)
        or profile.get('display_name')
        or profile.get('bio')
        or profile.get('profile_image')
        or data_availability.get('platform') == 'available'
    )

    return {
        'status': status,
        'source': source,
        'error_code': error_code,
        'message': message,
        'handle_input': handle_input,
        'account_label': display_handle,
        'normalized_handle': normalized_handle,
        'detected_platform': detected_platform,
        'selected_platforms': selected_platforms,
        'supported_platforms': SUPPORTED_SOCIAL_TRACKING_PLATFORMS,
        'provider_configured': provider_configured,
        'provider_status': provider_status,
        'provider_status_text': provider_status_text,
        'total_followers': total_followers_final,
        'total_followers_display': _format_followers(total_followers_final),
        'engagement_rate': kpi_engagement_rate or engagement_rate,
        'engagement_display': eng_display,
        'engagement_formula': engagement_formula_final,
        'sentiment_counts': kpi_sent_counts,
        'sentiment_percentages': kpi_sent_pct,
        'sentiment_badge': sentiment_badge,
        'sentiment_message': sentiment_message_display,
        'sentiment_available': sentiment_available,
        'growth_chart': growth_chart_final,
        'platforms': platforms or {},
        'last_sync': last_sync or (profile.get('analyzed_at') if profile else None),
        'last_sync_display': last_sync_display,
        'data_available': any_real_data,

        # --- New normalized dashboard structure
        'report_title': 'SOCIAL INTELLIGENCE REPORT',
        'dashboard': True,

        # SECTION A: Profile Overview
        'profile_overview': {
            'platform': platform_display,
            'platform_label': platform_label,
            'account': handle_display,
            'display_name': display_name,
            'bio': bio,
            'profile_image': profile_image,
            'website': website,
            'verified': verified,
            'verified_display': _format_bool(verified),
            'profile_url': profile_url,
            'analysis_source': analysis_source,
            'crawl_status': crawl_status,
            'crawl_status_label': crawl_status_label,
            'crawl_status_badge_class': crawl_badge_class,
            'crawl_message': crawl_message,
            'analyzed_at': analyzed_at,
            'analyzed_at_display': analyzed_at_display,
        },

        # SECTION B: Audience Metrics
        'audience_metrics': {
            'followers': followers,
            'followers_display': _format_int(followers),
            'following': following,
            'following_display': _format_int(following),
            'follower_following_ratio': ffratio,
            'follower_following_ratio_display': f'{ffratio:.2f}' if ffratio is not None else 'Not Available',
        },

        # SECTION C: Content Metrics
        'content_metrics': {
            'posts_count': posts_count,
            'posts_count_display': _format_int(posts_count),
            'posts_per_week': posts_per_week,
            'posts_per_week_display': _format_ppw(posts_per_week),
            'posts_per_week_reason': posts_per_week_reason,
            'content_activity': content_activity,
            'content_activity_display': _format_activity(content_activity),
            'content_activity_thresholds': kpi.get('content_activity_thresholds', ''),
        },

        # SECTION D: Engagement Metrics
        'engagement_metrics': {
            'engagement_rate': kpi_engagement_rate,
            'engagement_rate_display': eng_display,
            'engagement_reason': engagement_reason,
            'engagement_formula': eng_formula,
            'avg_likes': avg_likes,
            'avg_likes_display': _format_int(avg_likes),
            'avg_comments': avg_comments,
            'avg_comments_display': _format_int(avg_comments),
            'avg_shares': avg_shares,
            'avg_shares_display': _format_int(avg_shares),
        },

        # SECTION E: Sentiment
        'sentiment_section': {
            'available': sentiment_available,
            'counts': kpi_sent_counts,
            'percentages': kpi_sent_pct,
            'positive_display': _format_pct(kpi_sent_pct.get('positive')),
            'neutral_display': _format_pct(kpi_sent_pct.get('neutral')),
            'negative_display': _format_pct(kpi_sent_pct.get('negative')),
            'reason': sentiment_reason,
            'message': sentiment_message_display,
        },

        # SECTION F: Growth
        'growth_section': {
            'available': growth_available,
            'chart': growth_chart_final,
            'reason': growth_reason,
        },

        # Profile Completeness KPI
        'profile_completeness': {
            'pct': profile_completeness_pct,
            'pct_display': _format_pct(profile_completeness_pct),
            'parts': profile_completeness_parts or '0 / 0',
            'formula': profile_completeness_formula,
        },

        # Actionable Insights
        'insights': insights,

        # Data Availability panel
        'data_availability_panel': data_availability,

        # Raw normalized profile & kpi (for tests / extensibility)
        '_profile': profile,
        '_kpi': kpi,
    }


def _normalize_social_tracking_input(handle_input, selected_platforms):
    raw_value = (handle_input or '').strip()
    if not raw_value:
        return {
            'valid': False,
            'error_code': 'missing_handle',
            'message': 'Enter a company name, handle, or supported profile URL.',
        }

    resolved_platforms = list(selected_platforms or SUPPORTED_SOCIAL_TRACKING_PLATFORMS.keys())
    detected_platform = ''
    normalized_handle = raw_value

    if raw_value.startswith('http://') or raw_value.startswith('https://'):
        parsed = urlparse(raw_value)
        detected_platform = SUPPORTED_SOCIAL_TRACKING_DOMAINS.get(parsed.netloc.lower(), '')
        if not detected_platform:
            return {
                'valid': False,
                'error_code': 'unsupported_platform',
                'message': 'Unsupported profile URL. Supported platforms are X/Twitter, Instagram, TikTok, Facebook, LinkedIn, and YouTube.',
            }
        path_only = parsed.path.split('?')[0].split('#')[0]
        path_parts = [segment for segment in path_only.split('/') if segment]
        if not path_parts:
            return {
                'valid': False,
                'error_code': 'invalid_handle',
                'message': 'Enter a valid supported profile URL or a handle.',
            }
        special_prefixes = _SOCIAL_SPECIAL_PATH_PREFIXES.get(detected_platform, set())
        if len(path_parts) >= 2 and path_parts[0].lower() in special_prefixes:
            candidate = path_parts[1]
        else:
            candidate = path_parts[0]
        normalized_handle = candidate.lstrip('@').strip()
        # For facebook.com/profile.php?id=123, extract id from query string
        if detected_platform == 'facebook' and parsed.query:
            try:
                qs = parse_qs(parsed.query)
                if 'id' in qs and qs['id']:
                    normalized_handle = str(qs['id'][0]).strip()
            except Exception:
                pass
        resolved_platforms = [detected_platform]
    else:
        normalized_handle = raw_value.lstrip('@').strip()

    if not normalized_handle:
        return {
            'valid': False,
            'error_code': 'invalid_handle',
            'message': 'Enter a valid supported handle or profile URL.',
        }

    return {
        'valid': True,
        'raw_handle': raw_value,
        'normalized_handle': normalized_handle,
        'detected_platform': detected_platform,
        'selected_platforms': resolved_platforms,
    }


def _calculate_sentiment_counts(text_values):
    counts = Counter()
    for text in text_values:
        tokens = re.findall(r'\w+', (text or '').lower())
        score = 0
        for token in tokens:
            if token in POSITIVE_SENTIMENT_WORDS:
                score += 1
            if token in NEGATIVE_SENTIMENT_WORDS:
                score -= 1
        label = 'neutral'
        if score > 0:
            label = 'positive'
        elif score < 0:
            label = 'negative'
        counts[label] += 1
    return {
        'positive': counts.get('positive', 0),
        'neutral': counts.get('neutral', 0),
        'negative': counts.get('negative', 0),
    }


def _build_growth_chart(user, normalized_handle, detected_platform):
    snapshots = SocialTrackingSnapshot.objects.filter(
        user=user,
        normalized_handle=normalized_handle,
        status__in=['success', 'partial'],
        total_followers__isnull=False,
    )
    if detected_platform:
        snapshots = snapshots.filter(detected_platform=detected_platform)
    snapshots = list(snapshots.order_by('synced_at')[:12])

    if len(snapshots) < 2:
        return _empty_growth_chart()

    return {
        'available': True,
        'labels': [snapshot.synced_at.strftime('%b %d') for snapshot in snapshots],
        'values': [snapshot.total_followers for snapshot in snapshots],
        'title': 'Audience Growth Trajectory',
        'message': '',
    }


def _save_social_tracking_snapshot(
    *,
    user,
    handle_input,
    normalized_handle,
    detected_platform,
    selected_platforms,
    total_followers,
    engagement_rate,
    sentiment_counts,
    data_source,
    status,
):
    return SocialTrackingSnapshot.objects.create(
        user=user,
        handle_input=handle_input,
        normalized_handle=normalized_handle,
        detected_platform=detected_platform,
        selected_platforms=selected_platforms,
        total_followers=total_followers,
        engagement_rate=engagement_rate,
        positive_count=sentiment_counts.get('positive', 0),
        neutral_count=sentiment_counts.get('neutral', 0),
        negative_count=sentiment_counts.get('negative', 0),
        data_source=data_source,
        status=status,
        synced_at=timezone.now(),
    )


def _build_social_tracking_from_db(handle_input, normalized_handle, selected_platforms, detected_platform, days, user):
    users_qs = SocialUser.objects.filter(
        username__iexact=normalized_handle,
        platform__in=selected_platforms,
    ).order_by('platform')
    users = list(users_qs)
    if not users:
        return None

    cutoff = timezone.now() - datetime.timedelta(days=max(days or 30, 1))
    posts_qs = SocialPost.objects.filter(user__in=users, posted_at__gte=cutoff).select_related('user')
    posts = list(posts_qs)
    total_followers = sum(max(social_user.followers_count or 0, 0) for social_user in users)
    engagements = [post.likes + post.comments + post.shares for post in posts]
    engagement_rate = None
    if total_followers > 0 and posts:
        engagement_rate = round((sum(engagements) / (total_followers * len(posts))) * 100, 2)

    captions = [post.caption for post in posts if post.caption]
    sentiment_counts = _calculate_sentiment_counts(captions) if captions else {'positive': 0, 'neutral': 0, 'negative': 0}
    platform_cards = {}
    for social_user in users:
        user_posts = [post for post in posts if post.user_id == social_user.id]
        user_engagement_rate = None
        if social_user.followers_count > 0 and user_posts:
            user_total_engagement = sum(post.likes + post.comments + post.shares for post in user_posts)
            user_engagement_rate = round((user_total_engagement / (social_user.followers_count * len(user_posts))) * 100, 2)
        platform_cards[SUPPORTED_SOCIAL_TRACKING_PLATFORMS.get(social_user.platform, social_user.platform.title())] = {
            'followers': social_user.followers_count,
            'followers_display': _format_followers(social_user.followers_count),
            'engagement_rate': user_engagement_rate,
            'engagement_display': _format_engagement_rate(user_engagement_rate),
            'post_count': len(user_posts),
        }

    snapshot = _save_social_tracking_snapshot(
        user=user,
        handle_input=handle_input,
        normalized_handle=normalized_handle,
        detected_platform=detected_platform,
        selected_platforms=selected_platforms,
        total_followers=total_followers if total_followers > 0 else None,
        engagement_rate=engagement_rate,
        sentiment_counts=sentiment_counts,
        data_source='database',
        status='success' if total_followers > 0 else 'partial',
    )
    growth_chart = _build_growth_chart(user, normalized_handle, detected_platform)
    return _build_social_tracking_result(
        handle_input=handle_input,
        normalized_handle=normalized_handle,
        selected_platforms=selected_platforms,
        detected_platform=detected_platform,
        source='database',
        status='success' if total_followers > 0 else 'partial',
        message='Metrics are based on verified stored social account records.',
        total_followers=total_followers if total_followers > 0 else None,
        engagement_rate=engagement_rate,
        sentiment_counts=sentiment_counts,
        platforms=platform_cards,
        growth_chart=growth_chart,
        last_sync=snapshot.synced_at,
    )


def process_social_tracking(handle: str, platforms: list = None, days: int = 30, user=None) -> dict:
    """Process the Social Ecosystem module using real configured or stored data only."""
    resolved = _normalize_social_tracking_input(handle, platforms)
    if not resolved.get('valid'):
        return _build_social_tracking_result(
            handle_input=handle,
            normalized_handle='',
            selected_platforms=list(platforms or SUPPORTED_SOCIAL_TRACKING_PLATFORMS.keys()),
            source='error',
            status='error',
            message=resolved['message'],
            error_code=resolved['error_code'],
        )

    handle_input = resolved['raw_handle']
    normalized_handle = resolved['normalized_handle']
    detected_platform = resolved['detected_platform']
    selected_platforms = resolved['selected_platforms']

    social_api = os.environ.get('SOCIAL_API_URL')
    social_api_key = os.environ.get('SOCIAL_API_KEY')
    if social_api and _HAS_REQUESTS:
        try:
            params = {'handle': handle_input, 'platforms': ','.join(selected_platforms), 'days': days}
            headers = {}
            if social_api_key:
                headers['Authorization'] = f'Bearer {social_api_key}'
            resp = requests.get(social_api, params=params, headers=headers, timeout=15)
            if resp.ok:
                data = resp.json()
                total_followers = data.get('total_followers') or data.get('followers_count')
                engagement_rate = data.get('average_engagement_rate') or data.get('engagement_rate')
                sentiment_counts = data.get('sentiment_summary') or {'positive': 0, 'neutral': 0, 'negative': 0}
                platform_cards = data.get('platforms') or {}
                if total_followers is not None:
                    snapshot = _save_social_tracking_snapshot(
                        user=user,
                        handle_input=handle_input,
                        normalized_handle=normalized_handle,
                        detected_platform=detected_platform,
                        selected_platforms=selected_platforms,
                        total_followers=total_followers,
                        engagement_rate=engagement_rate,
                        sentiment_counts=sentiment_counts,
                        data_source='api',
                        status='success',
                    )
                    growth_chart = _build_growth_chart(user, normalized_handle, detected_platform)
                    return _build_social_tracking_result(
                        handle_input=handle_input,
                        normalized_handle=normalized_handle,
                        selected_platforms=selected_platforms,
                        detected_platform=detected_platform,
                        source='api',
                        status='success',
                        message='Metrics are based on the configured social data provider.',
                        total_followers=total_followers,
                        engagement_rate=engagement_rate,
                        sentiment_counts=sentiment_counts,
                        platforms=platform_cards,
                        growth_chart=growth_chart,
                        last_sync=snapshot.synced_at,
                    )
        except Exception:
            pass

    db_result = _build_social_tracking_from_db(
        handle_input,
        normalized_handle,
        selected_platforms,
        detected_platform,
        days,
        user,
    )
    if db_result:
        return db_result

    return _build_social_tracking_result(
        handle_input=handle_input,
        normalized_handle=normalized_handle,
        selected_platforms=selected_platforms,
        detected_platform=detected_platform,
        source='unavailable',
        status='unavailable',
        message='Live social data is not configured for this environment and no verified stored records were found for the submitted account.',
    )

def process_keyword_research(query: str) -> dict:
    """Simulated keyword research processor.

    Returns suggested keyword phrases and a simple trend chart. If an external
    keyword API is configured (KEYWORD_API_URL), it will be used when available.
    """
    seed = sum(ord(c) for c in query)

    # External API hook
    kw_api = os.environ.get('KEYWORD_API_URL')
    kw_api_key = os.environ.get('KEYWORD_API_KEY')
    if kw_api and _HAS_REQUESTS:
        try:
            headers = {}
            if kw_api_key:
                headers['Authorization'] = f'Bearer {kw_api_key}'
            resp = requests.get(kw_api, params={'query': query}, headers=headers, timeout=10)
            if resp.ok:
                data = resp.json()
                data['source'] = 'api'
                return data
        except Exception:
            pass

    # Simulate keyword suggestions by combining query tokens and common modifiers
    tokens = [t for t in query.split() if t]
    base = " ".join(tokens[:3]) or query
    modifiers = ['best', 'top', '2026', 'pricing', 'examples', 'tools']
    suggested = [f"{base} {m}" for m in modifiers[:3]] + [f"{t} {tokens[0]}" for t in modifiers[3:5]]

    labels = ['Week -3', 'Week -2', 'Week -1', 'This Week']
    values = [max(1, (seed % 50) + i * 5) for i in range(4)]

    return {
        'query': query,
        'suggested_keywords': suggested,
        'chart': {
            'labels': labels,
            'values': values,
            'title': 'Interest Over Time'
        },
        'source': 'simulated'
    }
