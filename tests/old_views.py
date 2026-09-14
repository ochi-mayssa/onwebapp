from uuid import UUID, uuid4

from django.http import Http404, HttpResponse, JsonResponse
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .forms import LinkCheckerForm, SEOMonitoringFilterForm, SEOTaskForm, SitemapIntelligenceForm
from .models import SEOMonitoringSnapshot, SEOResult, SEOTask
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
from .services.pdf_report import build_link_checker_pdf, build_website_checker_pdf
from .services.topic_intelligence import (
    build_sitemap_intelligence_report,
    build_topic_intelligence_from_page_audit,
)
from .services.modular_sitemap_intelligence import build_modular_sitemap_intelligence_report

LINK_REPORTS_SESSION_KEY = "seo_link_checker_reports"
MAX_LINK_REPORTS = 10


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


class DashboardView(View):
    """Website SEO Checker results dashboard."""

    def get(self, request, task_id):
        task = get_object_or_404(SEOTask, id=task_id)
        try:
            result = task.result
        except SEOResult.DoesNotExist:
            result = None
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
            },
        )


def checker_view(request):
    return IndexView.as_view()(request)


def link_checker_view(request):
    initial_type = request.GET.get("analysis_type") or request.GET.get("type") or "internal"
    return _handle_link_checker_request(request, initial_type=initial_type)


def sitemap_view(request):
    if request.method == "POST":
        print("=== POST request received ===")
        print("request.POST keys:", list(request.POST.keys()))
        print("request.POST['target_keyword'] (raw):", repr(request.POST.get("target_keyword")))
        form = SitemapIntelligenceForm(request.POST)
        if form.is_valid():
            url = form.cleaned_data["url"]
            target_keyword = form.cleaned_data.get("target_keyword", "").strip()
            sitemap_url = form.cleaned_data.get("sitemap_url")
            print("form.cleaned_data['target_keyword'] (stripped):", repr(target_keyword))
            report = build_modular_sitemap_intelligence_report(
                url=url,
                target_keyword=target_keyword,
                sitemap_url=sitemap_url
            )
            print("report['target_keyword'] (after build):", repr(report.get("target_keyword")))
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
            print("Form invalid!", form.errors)
    else:
        form = SitemapIntelligenceForm()

    return render(
        request,
        "seo_analyzer/sitemap.html",
        {
            "form": form,
        },
    )


def backlink_view(request):
    return _handle_link_checker_request(request, initial_type="backlinks", forced_analysis_type="backlinks")


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


def index(request):
    return IndexView.as_view()(request)


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
