import re
from uuid import UUID, uuid4

from django.http import Http404, HttpResponse, JsonResponse
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import format_html
from django.utils import timezone
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

from services.decorators import require_seo_intelligence

from .forms import (
    FreeWebsitePreCheckForm,
    LinkCheckerForm,
    SEOMonitoringFilterForm,
    SEOTaskForm,
    SitemapIntelligenceForm,
    URLIntelligenceForm,
)
from .services.pre_check import perform_free_website_pre_check
from .models import (
    SEOMonitoringSnapshot,
    SEOResult,
    SEOTask,
    URLIntelligenceIssue,
    URLIntelligenceResult,
    URLIntelligenceTask,
)
from .services.analyzer import analyze
from .services.crawler import crawl
from .services.link_checker import analyze_links
from .services.link_progress import (
    get_completed_link_report,
    get_link_progress,
    start_link_analysis,
)
from .services.monitoring import (
    build_export_rows,
    build_monitoring_dashboard,
    filter_snapshots,
    record_link_snapshot,
    record_website_snapshot,
)
from .services.monitoring_exports import (
    build_csv_export,
    build_excel_export,
    build_pdf_export,
)
from .services.pdf_report import (
    build_link_checker_pdf,
    build_url_intelligence_pdf,
    build_website_checker_pdf,
)
from .services.topic_intelligence import (
    build_sitemap_intelligence_report,
    build_topic_intelligence_from_page_audit,
)
from .services.modular_sitemap_intelligence import build_modular_sitemap_intelligence_report
from .services.url_intelligence import analyze_url_intelligence_task, classify_http_response
from .services.url_intelligence_scoring import score_to_label

LINK_REPORTS_SESSION_KEY = "seo_link_checker_reports"
MAX_LINK_REPORTS = 10


URL_INTELLIGENCE_CANONICAL_LABELS = {
    "self": "Self-Canonical",
    "other": "Canonical to Another URL",
    "missing": "Canonical Missing",
    "conflict": "Canonical Conflict",
    "not_evaluated": "Not Evaluated",
    "unknown": "Unknown",
}

URL_INTELLIGENCE_INDEXABILITY_LABELS = {
    "indexable": "Indexable",
    "noindex": "Noindex",
    "blocked": "Blocked",
    "redirected": "Redirected",
    "not_evaluated_auth_required": "Not Evaluated — Authentication Required",
    "not_evaluated_access_restricted": "Not Evaluated — Access Restricted",
    "not_evaluated_rate_limited": "Not Evaluated — Rate Limited",
    "not_found": "Not Indexable — Not Found",
    "gone": "Not Indexable — Gone",
    "server_error": "Temporarily Unavailable — Server Error",
    "error": "Error",
    "unknown": "Unknown",
}


def get_canonical_status_label(result):
    canonical_status = result.canonical_status
    structure_payload = result.structure_payload or {}

    if canonical_status == "not_evaluated":
        return "Not Evaluated"
    if canonical_status == "self":
        return "Self-Canonical"
    if structure_payload.get("canonical_to_clean_url"):
        return "Canonical to Clean URL"
    if canonical_status == "other":
        return "Canonical to Another URL"
    if canonical_status == "missing":
        return "Canonical Missing"
    return URL_INTELLIGENCE_CANONICAL_LABELS.get(
        canonical_status,
        canonical_status.replace("_", " ").title(),
    )


def _safe_score(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _score_to_display(value, fallback="Not Available"):
    score = _safe_score(value)
    if score is None:
        return fallback
    return f"{int(round(score))}/100"


def _score_status(value):
    score = _safe_score(value)
    if score is None:
        return "Not Available"
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Healthy"
    if score >= 50:
        return "Warning"
    return "Critical"


def _score_progress_class(value):
    score = _safe_score(value)
    if score is None:
        return "secondary"
    if score >= 85:
        return "success"
    if score >= 70:
        return "primary"
    if score >= 50:
        return "warning"
    return "danger"


class SEOHomeView(View):
    """SEO tools landing page for the active root-level app."""

    def get(self, request):
        recent_audits = SEOTask.objects.filter(status="completed").order_by("-created_at")[:6]
        recent_snapshots = SEOMonitoringSnapshot.objects.order_by("-created_at")[:6]
        return render(
            request,
            "seo_analyzer/seo_home.html",
            {
                "recent_audits": recent_audits,
                "recent_snapshots": recent_snapshots,
            },
        )


@method_decorator(require_seo_intelligence, name='dispatch')
class IndexView(View):
    """Website SEO Checker landing page with form and recent audits."""

    def get(self, request):
        form = SEOTaskForm()
        recent_audits = SEOTask.objects.filter(status="completed").order_by("-created_at")[:10]
        return render(
            request,
            "seo_analyzer/index.html",
            {
                "form": form,
                "recent_audits": recent_audits,
            },
        )

    def post(self, request):
        form = SEOTaskForm(request.POST)
        recent_audits = SEOTask.objects.filter(status="completed").order_by("-created_at")[:10]
        if form.is_valid():
            task = form.save(commit=False)
            if request.user.is_authenticated:
                task.user = request.user
            task.save()

            crawl_data = crawl(task)
            if crawl_data.get("crawl_succeeded") and task.status != "failed":
                analyze(task, crawl_data)
                task.refresh_from_db()
                try:
                    record_website_snapshot(task, task.result)
                except SEOResult.DoesNotExist:
                    pass

            return redirect("seo_analyzer:dashboard", task_id=task.id)
        return render(
            request,
            "seo_analyzer/index.html",
            {
                "form": form,
                "recent_audits": recent_audits,
            },
        )


@method_decorator(require_seo_intelligence, name='dispatch')
class DashboardView(View):
    """Website SEO Checker results dashboard."""

    def get(self, request, task_id):
        task = get_object_or_404(SEOTask, id=task_id)
        try:
            result = task.result
        except SEOResult.DoesNotExist:
            result = None
        url_result = None
        root_page = task.page_audits.order_by("id").first()

        issues = task.issues.all().order_by("severity", "-created_at") if result else task.issues.none()
        critical_issues = issues.filter(severity="critical")
        high_issues = issues.filter(severity="high")
        medium_issues = issues.filter(severity="medium")
        low_issues = issues.filter(severity="low")
        topic_intelligence = (
            build_topic_intelligence_from_page_audit(
                root_page,
                result.final_url if result else task.url,
                result=result,
                issues=list(issues),
            )
            if root_page
            else None
        )

        recommendations = []
        if result:
            seen = set()
            for issue in issues:
                fix = (issue.recommended_fix or "").strip()
                if fix and fix not in seen:
                    seen.add(fix)
                    recommendations.append(fix)
                if len(recommendations) >= 5:
                    break

        if not recommendations and topic_intelligence:
            recommendations.append(
                topic_intelligence.get("executive_summary", {}).get(
                    "top_ai_recommendations",
                    ["Improve the priority issues surfaced by the analysis."],
                )[0]
            )

        page_audits = list(task.page_audits.all())
        missing_h1 = sum(1 for page in page_audits if (page.h1_count or 0) == 0)
        missing_meta_title = sum(1 for page in page_audits if not (page.title_tag or "").strip())
        missing_meta_description = sum(1 for page in page_audits if not (page.meta_description or "").strip())
        missing_alt = sum(page.images_missing_alt or 0 for page in page_audits)

        historical_data_available = SEOMonitoringSnapshot.objects.filter(domain=task.domain).exists()

        overview_kpis = [
            {
                "label": "Overall SEO Score",
                "score": _score_to_display(result.health_score if result else None),
                "status": _score_status(result.health_score if result else None),
                "progress_class": _score_progress_class(result.health_score if result else None),
                "description": "Weighted review of the latest website audit signal.",
            },
            {
                "label": "Visibility Score",
                "score": _score_to_display(topic_intelligence.get("executive_summary", {}).get("ai_visibility_potential") if topic_intelligence else None),
                "status": _score_status(topic_intelligence.get("executive_summary", {}).get("ai_visibility_potential") if topic_intelligence else None),
                "progress_class": _score_progress_class(topic_intelligence.get("executive_summary", {}).get("ai_visibility_potential") if topic_intelligence else None),
                "description": "Search visibility potential derived from the topic intelligence layer.",
            },
            {
                "label": "Technical Health",
                "score": _score_to_display(result.technical_score if result else None),
                "status": _score_status(result.technical_score if result else None),
                "progress_class": _score_progress_class(result.technical_score if result else None),
                "description": "Technical foundation and crawl-readiness signals.",
            },
            {
                "label": "Content Health",
                "score": _score_to_display(result.on_page_score if result else None),
                "status": _score_status(result.on_page_score if result else None),
                "progress_class": _score_progress_class(result.on_page_score if result else None),
                "description": "On-page quality and content readiness.",
            },
            {
                "label": "Link Health",
                "score": _score_to_display(result.health_score if result else None),
                "status": _score_status(result.health_score if result else None),
                "progress_class": _score_progress_class(result.health_score if result else None),
                "description": "Link structure, navigation integrity, and crawl efficiency.",
            },
            {
                "label": "Crawl Status",
                "score": f"{min((result.pages_crawled or 0) * 10, 100)}/100" if result and (result.pages_crawled or 0) else "Not Available",
                "status": "Completed" if result and (result.pages_crawled or 0) else "Not Available",
                "progress_class": "success" if result and (result.pages_crawled or 0) else "secondary",
                "description": "Progress of the latest crawl coverage for this audit.",
            },
        ]

        health_breakdown = [
            {"label": "Healthy", "count": max((result.total_issues or 0) - (result.critical_issues or 0) - (result.high_issues or 0) - (result.medium_issues or 0) - (result.low_issues or 0), 0), "class": "success"},
            {"label": "Warnings", "count": (result.high_issues or 0) + (result.medium_issues or 0), "class": "warning"},
            {"label": "Critical", "count": result.critical_issues or 0, "class": "danger"},
            {"label": "Errors", "count": max((result.total_issues or 0) - ((result.critical_issues or 0) + (result.high_issues or 0) + (result.medium_issues or 0) + (result.low_issues or 0)), 0), "class": "secondary"},
        ]

        content_analysis = {
            "pages_crawled": result.pages_crawled if result else "Not Analyzed",
            "duplicate_content": "Not Analyzed",
            "thin_content": "Not Analyzed",
            "missing_h1": missing_h1,
            "missing_meta_title": missing_meta_title,
            "missing_meta_description": missing_meta_description,
            "missing_alt": missing_alt,
            "readability_score": "Not Analyzed",
            "content_score": _score_to_display(result.on_page_score if result else None),
        }

        url_cards = [
            {
                "label": "Good URLs",
                "value": 1 if url_result and (url_result.health_score or 0) >= 80 else 0 if url_result else "Not Available",
                "description": "URLs that passed the latest URL intelligence checks.",
            },
            {
                "label": "Long URLs",
                "value": 1 if url_result and (url_result.url_length or 0) > 90 else 0 if url_result else "Not Available",
                "description": "URLs that may need length optimization.",
            },
            {
                "label": "Redirect Chains",
                "value": url_result.redirect_count if url_result else "Not Available",
                "description": "Redirect depth found in the URL analysis.",
            },
            {
                "label": "Canonical Issues",
                "value": 1 if url_result and url_result.canonical_status not in {"self", "unknown", "not_evaluated"} else 0 if url_result else "Not Available",
                "description": "Canonical conflicts and missing signals.",
            },
            {
                "label": "Dynamic URLs",
                "value": 1 if url_result and url_result.dynamic_url_detected else 0 if url_result else "Not Available",
                "description": "URLs containing dynamic parameters that may reduce clarity.",
            },
            {
                "label": "Indexability",
                "value": url_result.indexability_status.replace("_", " ").title() if url_result and url_result.indexability_status else "Not Available",
                "description": "Current indexability state from the analysis.",
            },
        ]

        link_health_cards = [
            {
                "label": "Internal Links",
                "value": result.internal_links_count if result else "Not Available",
                "description": "Internal pathways discovered during the crawl.",
            },
            {
                "label": "Broken Links",
                "value": result.broken_internal_links_count if result else "Not Available",
                "description": "Broken internal links found during the crawl.",
            },
            {
                "label": "External Links",
                "value": "Not Analyzed",
                "description": "External link detail is not present in this report.",
            },
            {
                "label": "Orphan Pages",
                "value": result.orphan_pages_count if result else "Not Available",
                "description": "Pages discovered without inbound navigation.",
            },
            {
                "label": "Link Health Score",
                "value": _score_to_display(result.health_score if result else None),
                "description": "Overall link-signal strength from the current audit.",
            },
        ]

        technical_seo_cards = [
            {
                "label": "HTTPS",
                "status": "Healthy" if result and result.https_status else "Critical" if result else "Not Checked",
                "description": "TLS security signal for the site root.",
            },
            {
                "label": "Robots.txt",
                "status": "Healthy" if any(page.has_robots for page in page_audits) else "Not Checked",
                "description": "Bot access directives captured by the crawl.",
            },
            {
                "label": "XML Sitemap",
                "status": "Healthy" if any(page.has_sitemap for page in page_audits) else "Not Checked",
                "description": "Sitemap discovery coverage from the crawl.",
            },
            {
                "label": "Canonical",
                "status": "Healthy" if any(page.has_canonical for page in page_audits) else "Warning" if page_audits else "Not Checked",
                "description": "Canonical tag presence from crawled pages.",
            },
            {
                "label": "Schema",
                "status": "Not Checked",
                "description": "Structured data coverage is not present in this report.",
            },
            {
                "label": "Mobile Friendly",
                "status": "Not Checked",
                "description": "Mobile experience checks are not available in this audit.",
            },
            {
                "label": "Core Web Vitals",
                "status": "Not Checked",
                "description": "Performance metrics are not available in this report.",
            },
        ]

        broken_links_rows = []
        if result and (result.broken_internal_links_count or 0) > 0:
            broken_links_rows.append(
                {
                    "url": task.url,
                    "status": "404",
                    "found_on": task.domain,
                    "issue_type": "Broken Internal Link",
                    "recommendation": "Update the affected internal URL to a valid destination.",
                    "action": "Review Link",
                }
            )
        elif issues:
            broken_links_rows.append(
                {
                    "url": task.url,
                    "status": "Healthy",
                    "found_on": task.domain,
                    "issue_type": "No Broken Link Detail",
                    "recommendation": "No broken-link details were surfaced by the current audit.",
                    "action": "No Action",
                }
            )

        chart_sections = [
            {
                "title": "Issue Severity",
                "values": [
                    ("Critical", result.critical_issues or 0),
                    ("High", result.high_issues or 0),
                    ("Medium", result.medium_issues or 0),
                    ("Low", result.low_issues or 0),
                ],
            },
            {
                "title": "Health Breakdown",
                "values": [(item["label"], item["count"]) for item in health_breakdown],
            },
        ]

        return render(
            request,
            "seo_analyzer/dashboard.html",
            {
                "task": task,
                "result": result,
                "audit_failed": task.status == "failed" or result is None,
                "issues": issues,
                "critical_issues": critical_issues,
                "high_issues": high_issues,
                "medium_issues": medium_issues,
                "low_issues": low_issues,
                "recommendations": recommendations,
                "topic_intelligence": topic_intelligence,
                "overview_kpis": overview_kpis,
                "health_breakdown": health_breakdown,
                "issue_priority": [
                    {"label": "Critical Issues", "count": result.critical_issues or 0, "anchor": "critical-issues"},
                    {"label": "High Priority", "count": result.high_issues or 0, "anchor": "high-issues"},
                    {"label": "Medium", "count": result.medium_issues or 0, "anchor": "medium-issues"},
                    {"label": "Low", "count": result.low_issues or 0, "anchor": "low-issues"},
                ],
                "content_analysis": content_analysis,
                "url_cards": url_cards,
                "link_health_cards": link_health_cards,
                "technical_seo_cards": technical_seo_cards,
                "broken_links_rows": broken_links_rows,
                "chart_sections": chart_sections,
                "historical_data_available": historical_data_available,
                "page_audits": page_audits,
            },
        )


@require_seo_intelligence
def checker_view(request):
    return IndexView.as_view()(request)


@require_seo_intelligence
def link_checker_view(request):
    initial_type = request.GET.get("analysis_type") or request.GET.get("type") or "internal"
    return _handle_link_checker_request(request, initial_type=initial_type)


def sitemap_view(request):
    if request.method == "POST":
        print("=== POST request received ===", flush=True)
        print("request.POST:", dict(request.POST), flush=True)
        form = SitemapIntelligenceForm(request.POST)
        if form.is_valid():
            url = form.cleaned_data["url"]
            target_keyword = form.cleaned_data.get("target_keyword", "").strip()
            sitemap_url = form.cleaned_data.get("sitemap_url")
            print("form.cleaned_data:", form.cleaned_data, flush=True)
            print("target_keyword:", repr(target_keyword), flush=True)
            report = build_modular_sitemap_intelligence_report(
                url=url,
                target_keyword=target_keyword,
                sitemap_url=sitemap_url
            )
            print(
                "report['analysis_context']['target_keyword']:",
                repr(report.get("analysis_context", {}).get("target_keyword")),
                flush=True,
            )
            print(
                "report['executive_summary']['target_keyword']:",
                repr(report.get("executive_summary", {}).get("target_keyword")),
                flush=True,
            )
            return render(
                request,
                "seo_analyzer/sitemap.html",
                {
                    "form": form,
                    "report": report,
                    "topic_intelligence": report["topic_intelligence"],
                },
            )
        else:
            print("Form invalid!", form.errors, flush=True)
    else:
        form = SitemapIntelligenceForm()

    return render(
        request,
        "seo_analyzer/sitemap.html",
        {
            "form": form,
        },
    )


@require_seo_intelligence
def backlink_view(request):
    return _handle_link_checker_request(request, initial_type="backlinks", forced_analysis_type="backlinks")


@require_seo_intelligence
def executive_kpi_dashboard(request):
    website_task = SEOTask.objects.filter(status="completed").order_by("-created_at").first()
    website_result = None
    if website_task is not None:
        try:
            website_result = website_task.result
        except SEOResult.DoesNotExist:
            website_result = None

    url_task = URLIntelligenceTask.objects.filter(status="completed").order_by("-created_at").first()
    url_result = None
    if url_task is not None:
        try:
            url_result = url_task.result
        except URLIntelligenceResult.DoesNotExist:
            url_result = None

    internal_snapshot = SEOMonitoringSnapshot.objects.filter(analysis_type="internal").order_by("-created_at").first()
    external_snapshot = SEOMonitoringSnapshot.objects.filter(analysis_type="external").order_by("-created_at").first()
    backlink_snapshot = SEOMonitoringSnapshot.objects.filter(analysis_type="backlinks").order_by("-created_at").first()

    website_score = _safe_score(getattr(website_result, "health_score", None))
    url_score = _safe_score(getattr(url_result, "health_score", None))
    link_score = _safe_score(getattr(internal_snapshot or external_snapshot, "health_score", None))
    backlink_score = _safe_score(getattr(backlink_snapshot, "health_score", None))

    overall_score = None
    scores = [score for score in [website_score, url_score] if score is not None]
    if scores:
        overall_score = round(sum(scores) / len(scores), 1)

    module_cards = [
        {
            "label": "Website Checker",
            "score": f"{int(website_score)}" if website_score is not None else "Not Connected",
            "status": "Connected" if website_result else "Not Connected",
            "detail": (
                f"{website_result.total_issues or 0} issues and {website_result.pages_crawled or 0} pages audited"
                if website_result
                else "No completed website audit found yet."
            ),
            "source": "Latest SEO Checker result",
        },
        {
            "label": "URL Intelligence",
            "score": f"{int(url_score)}" if url_score is not None else "Not Connected",
            "status": "Connected" if url_result else "Not Connected",
            "detail": (
                f"Keyword relevance {getattr(url_result, 'keyword_relevance_score', None) or 'Not Available'}"
                if url_result
                else "No completed URL analysis found yet."
            ),
            "source": "Latest URL Intelligence result",
        },
        {
            "label": "Link Checker",
            "score": f"{int(link_score)}" if link_score is not None else "Not Connected",
            "status": "Connected" if internal_snapshot or external_snapshot else "Not Connected",
            "detail": (
                f"{(internal_snapshot or external_snapshot).broken_links or 0} broken links and {(internal_snapshot or external_snapshot).redirects or 0} redirect events"
                if (internal_snapshot or external_snapshot)
                else "No link monitoring snapshot found yet."
            ),
            "source": "Latest monitoring snapshot",
        },
        {
            "label": "Sitemap Intelligence",
            "score": (
                f"{getattr(website_result, 'sitemap_entries_found', 0)}"
                if website_result and getattr(website_result, "sitemap_entries_found", None) is not None
                else "Not Connected"
            ),
            "status": "Connected" if website_result and getattr(website_result, "sitemap_entries_found", None) is not None else "Not Connected",
            "detail": (
                "Sitemap entries are available from the latest website audit."
                if website_result and getattr(website_result, "sitemap_entries_found", None) is not None
                else "No sitemap entries have been captured yet."
            ),
            "source": "Website checker audit data",
        },
        {
            "label": "Backlink Analyzer",
            "score": f"{int(backlink_score)}" if backlink_score is not None else "Not Connected",
            "status": "Connected" if backlink_snapshot else "Not Connected",
            "detail": (
                f"{backlink_snapshot.external_links or 0} outbound links monitored"
                if backlink_snapshot
                else "No backlink monitoring snapshot is linked yet."
            ),
            "source": "Latest backlink snapshot",
        },
    ]

    issue_items = []
    if website_task:
        for issue in website_task.issues.all()[:4]:
            issue_items.append(
                {
                    "title": issue.name,
                    "severity": issue.get_severity_display(),
                    "detail": issue.description or "No additional detail captured.",
                }
            )
    if not issue_items and url_result:
        issue_items.append(
            {
                "title": "URL quality checks pending",
                "severity": "Info",
                "detail": "The latest URL analysis is available but has not yet surfaced named issues.",
            }
        )

    recommendation_items = []
    if website_task:
        for issue in website_task.issues.filter(recommended_fix__isnull=False).exclude(recommended_fix="")[:3]:
            recommendation_items.append(issue.recommended_fix)
    if url_result and getattr(url_result, "recommendations_payload", None):
        for item in url_result.recommendations_payload[:3]:
            if isinstance(item, dict):
                recommendation_items.append(item.get("title") or item.get("description") or "Apply the latest URL recommendation")
            else:
                recommendation_items.append(str(item))

    if not recommendation_items:
        recommendation_items.append("No recommendations have been captured yet. Add another completed audit to populate this list.")

    trend_summary = "Historical trend placeholder: add another completed analysis to populate the momentum view."
    if SEOMonitoringSnapshot.objects.exists():
        trend_summary = "Historical trend is available from the monitoring snapshots already captured."

    return render(
        request,
        "seo_analyzer/executive_kpi_dashboard.html",
        {
            "website_task": website_task,
            "website_result": website_result,
            "url_task": url_task,
            "url_result": url_result,
            "internal_snapshot": internal_snapshot,
            "external_snapshot": external_snapshot,
            "backlink_snapshot": backlink_snapshot,
            "module_cards": module_cards,
            "overall_score": overall_score,
            "priority_issues": issue_items,
            "recommendations": recommendation_items,
            "trend_summary": trend_summary,
            "data_sources": [
                "Website Checker",
                "URL Intelligence",
                "Link Checker",
                "Sitemap Intelligence",
                "Backlink Analyzer",
            ],
            "snapshot_count": SEOMonitoringSnapshot.objects.count(),
        },
    )


@require_seo_intelligence
def url_intelligence_view(request):
    if request.method == "POST":
        form = URLIntelligenceForm(request.POST)
        if form.is_valid():
            task = URLIntelligenceTask(
                url=form.cleaned_data["url"],
                target_keyword=form.cleaned_data.get("target_keyword", "").strip(),
                status="pending",
            )
            if request.user.is_authenticated:
                task.user = request.user
            task.started_at = timezone.now()
            task.save()
            try:
                report = analyze_url_intelligence_task(task)
                _persist_url_intelligence_report(task, report)
            except Exception:
                form.add_error(None, task.error_message or "We could not analyze that URL right now.")
            else:
                return redirect("seo_analyzer:url_intelligence_results", task_id=task.id)
    else:
        form = URLIntelligenceForm()

    return render(
        request,
        "seo_analyzer/url_intelligence.html",
        {
            "form": form,
        },
    )


@require_seo_intelligence
def url_intelligence_results_view(request, task_id):
    task = get_object_or_404(URLIntelligenceTask, id=task_id)
    result = get_object_or_404(URLIntelligenceResult, task=task)
    issues = list(task.issues.all())
    http_access = classify_http_response(
        result.http_status_code,
        request_failed=result.http_status_code is None,
    )
    score_labels = {
        "overall": score_to_label(result.health_score),
        "structure": score_to_label(result.structure_score),
        "technical": score_to_label(result.technical_score),
        "canonical": score_to_label(result.canonical_score),
        "indexability": score_to_label(result.indexability_score),
        "seo_friendliness": score_to_label(result.seo_friendliness_score),
        "keyword": score_to_label(result.keyword_relevance_score),
    }
    return render(
        request,
        "seo_analyzer/url_intelligence_results.html",
        {
            "task": task,
            "result": result,
            "issues": issues,
            "quality_checks": result.quality_checks,
            "recommendations": result.recommendations_payload,
            "optimized_url": result.optimized_url_payload,
            "structure": result.structure_payload,
            "parameters": result.parameters_payload,
            "score_labels": score_labels,
            "keyword_evaluated": result.keyword_relevance_score is not None,
            "access_status_label": http_access["label"],
            "access_status_explanation": http_access["explanation"],
            "canonical_status_label": get_canonical_status_label(result),
            "indexability_status_label": URL_INTELLIGENCE_INDEXABILITY_LABELS.get(
                result.indexability_status,
                result.indexability_status.replace("_", " ").title(),
            ),
        },
    )


@require_seo_intelligence
@never_cache
def link_progress_view(request, task_id):
    progress = get_link_progress(str(task_id))
    if not progress:
        raise Http404("Link analysis progress was not found or has expired.")
    return JsonResponse(progress)


def monitoring_view(request):
    form = SEOMonitoringFilterForm(request.GET or None)
    if form.is_valid():
        cleaned = form.cleaned_data
    else:
        cleaned = {
            "website": "",
            "analysis_type": "all",
            "range_key": "30d",
            "start_date": None,
            "end_date": None,
        }

    queryset = filter_snapshots(
        website=cleaned.get("website", ""),
        analysis_type=cleaned.get("analysis_type", "all"),
        range_key=cleaned.get("range_key", "30d"),
        start_date=cleaned.get("start_date"),
        end_date=cleaned.get("end_date"),
    )
    dashboard = build_monitoring_dashboard(queryset)

    return render(
        request,
        "seo_analyzer/monitoring.html",
        {
            "form": form,
            "dashboard": dashboard,
            "active_filters": cleaned,
        },
    )


def monitoring_export_view(request, export_format):
    form = SEOMonitoringFilterForm(request.GET or None)
    form.is_valid()
    cleaned = getattr(form, "cleaned_data", {}) or {}
    queryset = filter_snapshots(
        website=cleaned.get("website", ""),
        analysis_type=cleaned.get("analysis_type", "all"),
        range_key=cleaned.get("range_key", "30d"),
        start_date=cleaned.get("start_date"),
        end_date=cleaned.get("end_date"),
    )
    rows = build_export_rows(queryset)

    filename_stub = "seo-monitoring-history"
    if export_format == "csv":
        return build_csv_export(rows, f"{filename_stub}.csv")
    if export_format == "xlsx":
        return build_excel_export(rows, f"{filename_stub}.xlsx")
    if export_format == "pdf":
        return build_pdf_export(
            rows=rows,
            filename=f"{filename_stub}.pdf",
            title="OnWebApp SEO Monitoring",
            subtitle="Historical intelligence export for the selected monitoring filters.",
        )
    raise Http404("Unsupported monitoring export format.")


@require_seo_intelligence
def index(request):
    return IndexView.as_view()(request)


@require_seo_intelligence
def link_results(request, task_id):
    report_data = _get_link_report(request, task_id)
    if not report_data:
        raise Http404("Link analysis result not found. Please run a new analysis.")
    return render(
        request,
        "seo_analyzer/link_results.html",
        {
            "report": report_data,
            "links": report_data.get("links", []),
            "error_links": report_data.get("error_links", []),
            "topic_intelligence": report_data.get("topic_intelligence"),
        },
    )


@require_seo_intelligence
def download_report(request, report_type, task_id):
    if report_type == "website":
        task = get_object_or_404(SEOTask, id=task_id)
        if task.status == "failed":
            raise Http404("PDF reports are not available for failed audits.")
        result = get_object_or_404(SEOResult, task=task)
        issues = list(task.issues.all().order_by("severity", "-created_at"))
        pdf_bytes = build_website_checker_pdf(task, result, issues)
        filename = f"website-seo-report-{task.id}.pdf"
    elif report_type == "link":
        report_data = _get_link_report(request, task_id)
        if not report_data:
            raise Http404("Link report not found. Please run a new analysis.")
        pdf_bytes = build_link_checker_pdf(report_data)
        filename = f"link-checker-report-{task_id}.pdf"
    elif report_type == "url":
        task = get_object_or_404(URLIntelligenceTask, id=task_id)
        result = get_object_or_404(URLIntelligenceResult, task=task)
        issues = list(task.issues.all().order_by("severity", "-created_at"))
        pdf_bytes = build_url_intelligence_pdf(task, result, issues)
        safe_domain = re.sub(r"[^A-Za-z0-9.\-]+", "_", result.domain or "url-report").strip("._")
        filename = f'OnWebApp_URL_Intelligence_Report_{safe_domain or "url-report"}.pdf'
    else:
        raise Http404("Unknown report type.")

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _handle_link_checker_request(request, initial_type="internal", forced_analysis_type=None):
    if initial_type not in {"internal", "external", "backlinks"}:
        initial_type = "internal"

    if request.method == "POST":
        form = LinkCheckerForm(request.POST)
        if form.is_valid():
            analysis_type = forced_analysis_type or form.cleaned_data["analysis_type"]
            if _is_ajax_request(request):
                task_id = start_link_analysis(form.cleaned_data["url"], analysis_type)
                return JsonResponse(
                    {
                        "task_id": task_id,
                        "status": "accepted",
                        "progress_url": request.build_absolute_uri(
                            reverse("seo_analyzer:link_progress", kwargs={"task_id": task_id})
                        ),
                        "result_url": request.build_absolute_uri(
                            reverse("seo_analyzer:link_results", kwargs={"task_id": task_id})
                        ),
                    },
                    status=202,
                )
            report_data = analyze_links(form.cleaned_data["url"], analysis_type)
            task_id = str(uuid4())
            report_data["task_id"] = task_id
            record_link_snapshot(report_data, user=_request_user_or_none(request))
            _store_link_report(request, task_id, report_data)
            return redirect("seo_analyzer:link_results", task_id=task_id)
        if _is_ajax_request(request):
            return JsonResponse(
                {
                    "status": "invalid",
                    "errors": form.errors,
                },
                status=400,
            )
    else:
        form = LinkCheckerForm(initial={"analysis_type": forced_analysis_type or initial_type})

    return render(
        request,
        "seo_analyzer/link_checker.html",
        {
            "form": form,
            "selected_analysis_type": forced_analysis_type or initial_type,
        },
    )


def _store_link_report(request, task_id: str, report_data: dict) -> None:
    reports = request.session.get(LINK_REPORTS_SESSION_KEY, {})
    reports[task_id] = report_data

    if len(reports) > MAX_LINK_REPORTS:
        ordered_keys = sorted(
            reports.keys(),
            key=lambda key: reports[key].get("analyzed_at", ""),
        )
        for stale_key in ordered_keys[:-MAX_LINK_REPORTS]:
            reports.pop(stale_key, None)

    request.session[LINK_REPORTS_SESSION_KEY] = reports
    request.session.modified = True


def _get_link_report(request, task_id) -> dict | None:
    try:
        task_id = str(UUID(str(task_id)))
    except ValueError:
        task_id = str(task_id)
    reports = request.session.get(LINK_REPORTS_SESSION_KEY, {})
    report = reports.get(task_id)
    if report:
        return report
    report = get_completed_link_report(task_id)
    if report:
        record_link_snapshot(report, user=_request_user_or_none(request))
    return report


def _is_ajax_request(request) -> bool:
    requested_with = request.headers.get("x-requested-with", "")
    accepted_types = request.headers.get("accept", "")
    return requested_with.lower() == "xmlhttprequest" or "application/json" in accepted_types.lower()


def _request_user_or_none(request):
    if getattr(request, "user", None) and request.user.is_authenticated:
        return request.user
    return None


def _persist_url_intelligence_report(task, report):
    URLIntelligenceResult.objects.update_or_create(
        task=task,
        defaults={
            "original_url": report["original_url"],
            "final_url": report["final_url"],
            "http_status_code": report["http_status_code"],
            "response_time": report["response_time"],
            "https_status": report["https_status"],
            "redirect_detected": report["redirect_detected"],
            "redirect_count": report["redirect_count"],
            "protocol": report["protocol"],
            "domain": report["domain"],
            "subdomain": report["subdomain"],
            "path": report["path"],
            "slug": report["slug"],
            "url_length": report["url_length"],
            "url_depth": report["url_depth"],
            "trailing_slash": report["trailing_slash"],
            "has_uppercase": report["has_uppercase"],
            "has_underscores": report["has_underscores"],
            "hyphen_count": report["hyphen_count"],
            "special_character_count": report["special_character_count"],
            "encoded_space_detected": report["encoded_space_detected"],
            "numeric_slug_detected": report["numeric_slug_detected"],
            "query_params_count": report["query_params_count"],
            "tracking_params_count": report["tracking_params_count"],
            "functional_params_count": report["functional_params_count"],
            "unnecessary_params_count": report["unnecessary_params_count"],
            "has_fragment": report["has_fragment"],
            "dynamic_url_detected": report["dynamic_url_detected"],
            "canonical_url": report["canonical_url"],
            "canonical_status": report["canonical_status"],
            "canonical_matches": report["canonical_matches"],
            "meta_robots": report["meta_robots"],
            "x_robots_tag": report["x_robots_tag"],
            "indexability_status": report["indexability_status"],
            "health_score": report["health_score"],
            "structure_score": report["structure_score"],
            "technical_score": report["technical_score"],
            "canonical_score": report["canonical_score"],
            "indexability_score": report["indexability_score"],
            "seo_friendliness_score": report["seo_friendliness_score"],
            "keyword_relevance_score": report["keyword_relevance_score"],
            "keyword_match_status": report["keyword_match_status"],
            "critical_issues": report["critical_issues"],
            "high_issues": report["high_issues"],
            "medium_issues": report["medium_issues"],
            "low_issues": report["low_issues"],
            "informational_issues": report["informational_issues"],
            "total_issues": report["total_issues"],
            "redirect_chain": report["redirect_chain"],
            "parameters_payload": report["parameters_payload"],
            "structure_payload": report["structure_payload"],
            "quality_checks": report["quality_checks"],
            "recommendations_payload": report["recommendations"],
            "optimized_url_payload": report["optimized_url_payload"],
        },
    )

    task.issues.all().delete()
    URLIntelligenceIssue.objects.bulk_create(
        [
            URLIntelligenceIssue(
                task=task,
                name=issue["name"],
                severity=issue["severity"],
                category=issue["category"],
                evidence=issue.get("evidence", ""),
                description=issue["description"],
                seo_impact=issue.get("seo_impact", ""),
                business_impact=issue.get("business_impact", ""),
                recommended_fix=issue.get("recommended_fix", ""),
            )
            for issue in report["issues"]
        ]
    )


def free_website_pre_check_view(request):
    """View for FREE Website Pre-Check"""
    form = FreeWebsitePreCheckForm()
    results = None

    if request.method == "POST":
        form = FreeWebsitePreCheckForm(request.POST)
        if form.is_valid():
            url = form.cleaned_data["url"]
            results = perform_free_website_pre_check(url)

    return render(
        request,
        "seo_analyzer/free_pre_check.html",
        {
            "form": form,
            "results": results,
        },
    )
