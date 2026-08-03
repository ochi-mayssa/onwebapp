from __future__ import annotations

import logging
import time
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlparse

from django.db.models import QuerySet
from django.utils import timezone

from ..models import SEOMonitoringSnapshot, SEONotificationEndpoint
from .analyzer import pop_analysis_timing_report
from .link_checker import build_internal_link_health
from .topic_intelligence import build_topic_intelligence, build_topic_intelligence_from_page_audit
from .utils import extract_domain, normalize_url

DECIMAL_ZERO = Decimal("0.00")
DECIMAL_HUNDRED = Decimal("100.00")
logger = logging.getLogger(__name__)

CHART_METRICS = [
    ("health_score", "Health Score", "#0d6efd"),
    ("visibility_score", "Visibility Score", "#6f42c1"),
    ("technical_score", "Technical Score", "#198754"),
    ("performance_score", "Performance Score", "#fd7e14"),
    ("broken_links", "Broken Links", "#dc3545"),
    ("redirects", "Redirects", "#ffc107"),
    ("internal_links", "Internal Links", "#20c997"),
    ("external_links", "External Links", "#0dcaf0"),
    ("issues_count", "Issues Count", "#6c757d"),
]


def record_website_snapshot(task, result) -> SEOMonitoringSnapshot | None:
    if not task or not result:
        return None

    root_page = task.page_audits.order_by("id").first()
    issues = list(task.issues.all())
    topic_started_at = time.perf_counter()
    topic = (
        build_topic_intelligence_from_page_audit(
            root_page,
            result.final_url,
            result=result,
            issues=issues,
        )
        if root_page
        else build_topic_intelligence(url=result.final_url, page_title=task.domain)
    )
    topic_elapsed = round(time.perf_counter() - topic_started_at, 4)

    source_identifier = f"website:{task.id}"
    word_count_total = sum(page.word_count or 0 for page in task.page_audits.all())
    tracked_items = {
        "issue_signatures": sorted(
            {f"{issue.severity}:{issue.category}:{issue.name}" for issue in issues}
        ),
        "page_urls": sorted(
            {
                page.final_url or page.url
                for page in task.page_audits.all()
                if (page.final_url or page.url)
            }
        ),
    }
    metadata = {
        "topic_intelligence": {
            "primary_keyword": topic.get("primary_keyword"),
            "search_intent": topic.get("search_intent"),
            "topic_cluster": topic.get("topic_cluster"),
            "ai_visibility_potential": topic.get("ai_visibility_potential"),
        },
        "recommendation_count": len(topic.get("action_priority", {}).get("all_recommendations", [])),
        "critical_issue_names": [issue.name for issue in issues if issue.severity == "critical"][:5],
        "word_count_total": word_count_total,
        "status": task.status,
    }
    defaults = {
        "user": task.user,
        "website": result.final_url,
        "domain": task.domain,
        "analysis_type": "website",
        "health_score": _quantize(result.health_score),
        "visibility_score": _quantize(topic.get("ai_visibility_potential")),
        "ai_opportunity_score": _quantize(result.ai_opportunity_score),
        "technical_score": _quantize(result.technical_score),
        "performance_score": _quantize(result.performance_score),
        "content_score": _quantize(result.on_page_score),
        "security_score": _quantize(100 if result.https_status else 40),
        "broken_links": result.broken_internal_links_count,
        "redirects": result.redirect_count,
        "internal_links": result.internal_links_count,
        "external_links": None,
        "indexed_pages": result.pages_crawled,
        "issues_count": result.total_issues,
        "working_links": max(
            result.internal_links_count - result.broken_internal_links_count - result.redirect_count,
            0,
        ),
        "errors_count": 0,
        "tracked_items": tracked_items,
        "metadata": metadata,
    }
    snapshot, _created = SEOMonitoringSnapshot.objects.update_or_create(
        source_identifier=source_identifier,
        defaults=defaults,
    )

    timing_report = pop_analysis_timing_report(task.id)
    if timing_report is not None:
        timing_report["topic_intelligence_time"] = topic_elapsed
        timing_report["total_execution_time"] = round(
            float(timing_report.get("total_execution_time", 0.0)) + topic_elapsed,
            4,
        )
        logger.info(
            "Website SEO final timing report for %s: total=%ss crawl=%ss parsing=%ss seo=%ss ai=%ss topic=%ss recommendations=%ss report=%ss pages=%s requests=%s cache_hits=%s stage_breakdown=%s",
            task.url,
            timing_report["total_execution_time"],
            timing_report.get("crawl_time", 0.0),
            timing_report.get("parsing_time", 0.0),
            timing_report.get("seo_analysis_time", 0.0),
            timing_report.get("ai_analysis_time", 0.0),
            timing_report.get("topic_intelligence_time", 0.0),
            timing_report.get("ai_recommendations_time", 0.0),
            timing_report.get("report_generation_time", 0.0),
            timing_report.get("pages_crawled", 0),
            timing_report.get("requests_performed", 0),
            timing_report.get("cached_requests_reused", 0),
            timing_report.get("stage_breakdown", {}),
        )
    return snapshot


def record_link_snapshot(report_data: dict[str, Any], *, user=None) -> SEOMonitoringSnapshot | None:
    if not report_data:
        return None

    analysis_type = report_data.get("analysis_type")
    if analysis_type not in {"internal", "external", "backlinks"}:
        return None

    url = normalize_url(report_data.get("final_url") or report_data.get("url") or "")
    domain = extract_domain(url)
    summary = report_data.get("summary", {})
    topic = report_data.get("topic_intelligence") or build_topic_intelligence(url=url, page_title=domain)
    total_links = summary.get("total_links") or 0
    broken_links = summary.get("broken_links_count") or 0
    redirects = summary.get("redirect_links_count") or 0
    errors = summary.get("error_links_count") or 0
    working_links = summary.get("working_links_count") or 0

    if analysis_type == "internal":
        score = Decimal(str((report_data.get("health") or build_internal_link_health(summary)).get("score", 0)))
    else:
        score = _build_link_health_score(summary)
    security_score = _build_link_security_score(report_data)
    content_score = topic.get("content_quality", {}).get("content_focus_score")
    ai_opportunity_score = topic.get("keyword_intelligence", {}).get("keyword_opportunity_score")
    tracked_items = _build_link_tracked_items(report_data)
    metadata = {
        "analysis_type_label": report_data.get("analysis_type_label"),
        "status_badge": report_data.get("status_badge", {}).get("label"),
        "provider_required": report_data.get("provider_required", False),
        "recommendations": [
            item.get("text", "") if isinstance(item, dict) else item
            for item in (report_data.get("recommendations", [])[:6])
        ],
        "performance_log": report_data.get("performance_log", {}),
        "topic_intelligence": {
            "primary_keyword": topic.get("primary_keyword"),
            "search_intent": topic.get("search_intent"),
            "topic_cluster": topic.get("topic_cluster"),
            "ai_visibility_potential": topic.get("ai_visibility_potential"),
        },
    }

    source_identifier = f"link:{report_data.get('task_id')}"
    defaults = {
        "user": user,
        "website": url,
        "domain": domain,
        "analysis_type": analysis_type,
        "health_score": _quantize(score),
        "visibility_score": _quantize(topic.get("ai_visibility_potential")),
        "ai_opportunity_score": _quantize(ai_opportunity_score),
        "technical_score": _quantize(score),
        "performance_score": None,
        "content_score": _quantize(content_score),
        "security_score": _quantize(security_score),
        "broken_links": broken_links,
        "redirects": redirects,
        "internal_links": total_links if analysis_type == "internal" else None,
        "external_links": total_links if analysis_type in {"external", "backlinks"} else None,
        "indexed_pages": None,
        "issues_count": summary.get("total_issues"),
        "working_links": working_links,
        "errors_count": errors,
        "tracked_items": tracked_items,
        "metadata": metadata,
    }
    snapshot, _created = SEOMonitoringSnapshot.objects.update_or_create(
        source_identifier=source_identifier,
        defaults=defaults,
    )
    return snapshot


def filter_snapshots(
    *,
    website: str = "",
    analysis_type: str = "all",
    range_key: str = "30d",
    start_date=None,
    end_date=None,
) -> QuerySet[SEOMonitoringSnapshot]:
    queryset = SEOMonitoringSnapshot.objects.all()
    website = (website or "").strip()
    if website:
        website_value = website.lower()
        parsed = urlparse(website_value if "://" in website_value else f"https://{website_value}")
        domain = parsed.netloc or website_value
        queryset = queryset.filter(domain__icontains=domain)

    if analysis_type and analysis_type != "all":
        queryset = queryset.filter(analysis_type=analysis_type)

    now = timezone.now()
    if range_key == "custom" and (start_date or end_date):
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)
    else:
        window_days = {
            "7d": 7,
            "30d": 30,
            "90d": 90,
            "365d": 365,
        }.get(range_key, 30)
        queryset = queryset.filter(created_at__gte=now - timedelta(days=window_days))

    return queryset.order_by("-created_at")


def build_monitoring_dashboard(queryset: QuerySet[SEOMonitoringSnapshot]) -> dict[str, Any]:
    snapshots_desc = list(queryset.order_by("-created_at", "-id")[:200])
    snapshots = list(reversed(snapshots_desc))
    latest_snapshot = snapshots_desc[0] if snapshots_desc else None
    previous_snapshot = snapshots_desc[1] if len(snapshots_desc) > 1 else None

    weekly_snapshots = [
        snapshot
        for snapshot in snapshots
        if snapshot.created_at >= timezone.now() - timedelta(days=7)
    ]
    monthly_snapshots = [
        snapshot
        for snapshot in snapshots
        if snapshot.created_at >= timezone.now() - timedelta(days=30)
    ]
    current_vs_previous = build_snapshot_comparison(latest_snapshot, previous_snapshot)
    weekly_change = _build_period_change(weekly_snapshots, "health_score")
    monthly_change = _build_period_change(monthly_snapshots, "health_score")

    chart_cards = [_build_chart_card(snapshots, field, label, color) for field, label, color in CHART_METRICS]
    change_detection = build_change_detection(latest_snapshot, previous_snapshot)
    priority_items = [item for item in change_detection if item["status"] in {"NEW", "FIXED"}][:6]

    return {
        "snapshots": snapshots_desc[:20],
        "latest_snapshot": latest_snapshot,
        "previous_snapshot": previous_snapshot,
        "current_vs_previous": current_vs_previous,
        "timeline": snapshots_desc[:10],
        "chart_cards": chart_cards,
        "weekly_summary": build_weekly_summary(weekly_snapshots),
        "change_detection": change_detection,
        "priority_items": priority_items,
        "summary_cards": {
            "current_health": _format_metric_value(latest_snapshot.health_score if latest_snapshot else None),
            "previous_health": _format_metric_value(previous_snapshot.health_score if previous_snapshot else None),
            "weekly_change": _format_delta_label(weekly_change, suffix=" pts"),
            "monthly_change": _format_delta_label(monthly_change, suffix=" pts"),
            "ai_trend": _build_ai_trend_label(latest_snapshot, previous_snapshot),
        },
        "notification_architecture": {
            "channels": [
                {
                    "label": endpoint.get_channel_type_display(),
                    "destination": endpoint.destination,
                    "is_active": endpoint.is_active,
                }
                for endpoint in SEONotificationEndpoint.objects.all()[:10]
            ],
            "supported_channels": ["Email Alerts", "Slack", "Microsoft Teams", "Webhook"],
        },
        "filter_summary": {
            "total_snapshots": len(snapshots_desc),
            "analysis_types": sorted({snapshot.get_analysis_type_display() for snapshot in snapshots_desc}),
            "domains": sorted({snapshot.domain for snapshot in snapshots_desc})[:5],
        },
    }


def build_snapshot_comparison(current, previous) -> list[dict[str, Any]]:
    metrics = [
        ("health_score", "Health Score", "score"),
        ("visibility_score", "Visibility Score", "score"),
        ("ai_opportunity_score", "AI Opportunity Score", "score"),
        ("technical_score", "Technical Score", "score"),
        ("performance_score", "Performance Score", "score"),
        ("content_score", "Content Score", "score"),
        ("security_score", "Security Score", "score"),
        ("broken_links", "Broken Links", "count"),
        ("redirects", "Redirects", "count"),
        ("internal_links", "Internal Links", "count"),
        ("external_links", "External Links", "count"),
        ("indexed_pages", "Indexed Pages", "count"),
        ("issues_count", "Issues Count", "count"),
    ]

    comparison = []
    for field, label, kind in metrics:
        current_value = getattr(current, field, None) if current else None
        previous_value = getattr(previous, field, None) if previous else None
        if current_value is None and previous_value is None:
            continue
        delta = _calculate_delta(current_value, previous_value)
        comparison.append(
            {
                "label": label,
                "current": _format_metric_value(current_value),
                "previous": _format_metric_value(previous_value),
                "delta": _format_delta_label(delta, suffix="%" if kind == "score" else ""),
                "trend": _delta_trend(field, delta),
            }
        )
    return comparison


def build_change_detection(current, previous) -> list[dict[str, Any]]:
    if not current:
        return []

    current_items = current.tracked_items or {}
    previous_items = previous.tracked_items if previous else {}

    change_events = []
    change_events.extend(
        _set_change_events(
            label_prefix="Broken Links",
            status_new="NEW",
            status_removed="FIXED",
            current_values=current_items.get("broken_links", []),
            previous_values=previous_items.get("broken_links", []),
        )
    )
    change_events.extend(
        _set_change_events(
            label_prefix="Redirects",
            status_new="NEW",
            status_removed="REMOVED",
            current_values=current_items.get("redirect_links", []),
            previous_values=previous_items.get("redirect_links", []),
        )
    )
    change_events.extend(
        _set_change_events(
            label_prefix="Internal Links",
            status_new="NEW",
            status_removed="REMOVED",
            current_values=current_items.get("internal_links", []),
            previous_values=previous_items.get("internal_links", []),
        )
    )
    change_events.extend(
        _set_change_events(
            label_prefix="External Links",
            status_new="NEW",
            status_removed="REMOVED",
            current_values=current_items.get("external_links", []),
            previous_values=previous_items.get("external_links", []),
        )
    )

    content_growth = _calculate_delta(
        (current.metadata or {}).get("word_count_total"),
        (previous.metadata or {}).get("word_count_total") if previous else None,
    )
    if content_growth and content_growth > 0:
        change_events.append(
            {
                "status": "NEW",
                "label": "Content Growth",
                "count": int(content_growth),
                "detail": f"Content expanded by {int(content_growth)} words.",
            }
        )

    health_delta = _calculate_delta(
        getattr(current, "health_score", None),
        getattr(previous, "health_score", None) if previous else None,
    )
    if health_delta:
        change_events.append(
            {
                "status": "TREND",
                "label": "SEO Score Changes",
                "count": float(health_delta),
                "detail": f"Health Score changed by {_format_delta_label(health_delta, suffix=' pts')}.",
            }
        )

    return change_events


def build_weekly_summary(snapshots: list[SEOMonitoringSnapshot]) -> str:
    if len(snapshots) < 2:
        return (
            "SEO Weekly Summary: Monitoring has started. Run additional analyses this week to unlock "
            "trend intelligence, change detection, and executive comparisons."
        )

    first = snapshots[0]
    last = snapshots[-1]
    health_delta = _calculate_delta(last.health_score, first.health_score)
    broken_delta = _calculate_delta(first.broken_links, last.broken_links)
    redirect_delta = _calculate_delta(first.redirects, last.redirects)
    internal_delta = _calculate_delta(last.internal_links, first.internal_links)
    health_state = "Good" if (last.health_score or DECIMAL_ZERO) >= Decimal("80") else "Needs Improvement"

    return (
        "SEO Weekly Summary: "
        f"Health Score {_describe_signed_delta(health_delta, 'improved', 'declined', 'remained stable')} . "
        f"Broken links {_describe_signed_delta(broken_delta, 'reduced', 'increased', 'remained stable')} . "
        f"Redirects {_describe_signed_delta(redirect_delta, 'reduced', 'increased', 'remained stable')} . "
        f"Internal linking {_describe_signed_delta(internal_delta, 'improved significantly', 'declined', 'remained stable')} . "
        f"Technical SEO health is now considered {health_state}."
    )


def build_export_rows(queryset: QuerySet[SEOMonitoringSnapshot]) -> list[dict[str, Any]]:
    rows = []
    for snapshot in queryset.order_by("-created_at")[:1000]:
        rows.append(
            {
                "Website": snapshot.website,
                "Domain": snapshot.domain,
                "Analysis Type": snapshot.get_analysis_type_display(),
                "Date": snapshot.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "Health Score": _format_metric_value(snapshot.health_score),
                "Visibility Score": _format_metric_value(snapshot.visibility_score),
                "AI Opportunity Score": _format_metric_value(snapshot.ai_opportunity_score),
                "Technical Score": _format_metric_value(snapshot.technical_score),
                "Performance Score": _format_metric_value(snapshot.performance_score),
                "Content Score": _format_metric_value(snapshot.content_score),
                "Security Score": _format_metric_value(snapshot.security_score),
                "Broken Links": _format_metric_value(snapshot.broken_links),
                "Redirects": _format_metric_value(snapshot.redirects),
                "Internal Links": _format_metric_value(snapshot.internal_links),
                "External Links": _format_metric_value(snapshot.external_links),
                "Indexed Pages": _format_metric_value(snapshot.indexed_pages),
                "Issues Count": _format_metric_value(snapshot.issues_count),
                "Working Links": _format_metric_value(snapshot.working_links),
                "Errors": _format_metric_value(snapshot.errors_count),
            }
        )
    return rows


def _build_link_tracked_items(report_data: dict[str, Any]) -> dict[str, Any]:
    analysis_type = report_data.get("analysis_type")
    links = report_data.get("links", [])
    tracked = {
        "broken_links": sorted({link.get("link_url") or link.get("source_url") for link in links if link.get("status") == "broken" and (link.get("link_url") or link.get("source_url"))}),
        "redirect_links": sorted({link.get("link_url") or link.get("source_url") for link in links if link.get("status") == "redirect" and (link.get("link_url") or link.get("source_url"))}),
        "internal_links": [],
        "external_links": [],
    }
    if analysis_type == "internal":
        tracked["internal_links"] = sorted({link.get("link_url") for link in links if link.get("link_url")})
    elif analysis_type in {"external", "backlinks"}:
        tracked["external_links"] = sorted(
            {
                link.get("link_url") or link.get("source_url")
                for link in links
                if link.get("link_url") or link.get("source_url")
            }
        )
    return tracked


def _build_link_health_score(summary: dict[str, Any]) -> Decimal:
    total_links = summary.get("total_links") or 0
    if total_links <= 0:
        return Decimal("0.00")

    penalties = (
        Decimal(summary.get("broken_links_count") or 0) * Decimal("1.0")
        + Decimal(summary.get("redirect_links_count") or 0) * Decimal("0.5")
        + Decimal(summary.get("error_links_count") or 0) * Decimal("0.75")
    )
    score = DECIMAL_HUNDRED - ((penalties / Decimal(total_links)) * DECIMAL_HUNDRED)
    return max(DECIMAL_ZERO, min(DECIMAL_HUNDRED, score))


def _build_link_security_score(report_data: dict[str, Any]) -> Decimal | None:
    if report_data.get("analysis_type") == "external":
        security = report_data.get("external_insights", {}).get("security_analysis", {})
        total_https = security.get("https_external_links")
        total_http = security.get("http_external_links")
        if total_https is None or total_http is None:
            return None
        total = total_https + total_http
        if total == 0:
            return None
        return (Decimal(total_https) / Decimal(total)) * DECIMAL_HUNDRED
    if report_data.get("analysis_type") == "internal":
        url = report_data.get("final_url") or report_data.get("url") or ""
        return Decimal("100.00") if url.startswith("https://") else Decimal("40.00")
    return None


def _build_chart_card(
    snapshots: list[SEOMonitoringSnapshot],
    field: str,
    label: str,
    color: str,
) -> dict[str, Any]:
    values = []
    labels = []
    for snapshot in snapshots:
        value = getattr(snapshot, field, None)
        if value is None:
            continue
        values.append(float(value))
        labels.append(snapshot.created_at.strftime("%b %d"))

    if not values:
        return {
            "label": label,
            "color": color,
            "empty": True,
            "latest": "Not Measured",
            "delta": "Not Measured",
            "points": "",
            "labels": labels,
        }

    return {
        "label": label,
        "color": color,
        "empty": False,
        "latest": _format_metric_value(values[-1]),
        "delta": _format_delta_label(values[-1] - values[0]),
        "points": _build_svg_points(values),
        "labels": labels,
    }


def _build_svg_points(values: list[float], width: int = 280, height: int = 90) -> str:
    if len(values) == 1:
        return f"0,{height / 2} {width},{height / 2}"

    min_value = min(values)
    max_value = max(values)
    spread = max(max_value - min_value, 1)
    step_x = width / max(len(values) - 1, 1)
    points = []
    for index, value in enumerate(values):
        x = round(index * step_x, 2)
        normalized = (value - min_value) / spread
        y = round(height - (normalized * (height - 12)) - 6, 2)
        points.append(f"{x},{y}")
    return " ".join(points)


def _build_period_change(snapshots: list[SEOMonitoringSnapshot], field: str):
    if len(snapshots) < 2:
        return None
    return _calculate_delta(getattr(snapshots[-1], field, None), getattr(snapshots[0], field, None))


def _build_ai_trend_label(current, previous) -> str:
    if not current:
        return "Monitoring Starting"
    delta = _calculate_delta(
        getattr(current, "health_score", None),
        getattr(previous, "health_score", None) if previous else None,
    )
    if delta is None:
        return "Baseline Established"
    if delta > 0:
        return "Improving"
    if delta < 0:
        return "Needs Attention"
    return "Stable"


def _calculate_delta(current, previous):
    if current is None or previous is None:
        return None
    return Decimal(str(current)) - Decimal(str(previous))


def _delta_trend(field: str, delta) -> str:
    if delta is None or delta == 0:
        return "neutral"
    negative_is_good = {"broken_links", "redirects", "issues_count", "errors_count"}
    if field in negative_is_good:
        return "up" if delta < 0 else "down"
    return "up" if delta > 0 else "down"


def _set_change_events(
    *,
    label_prefix: str,
    status_new: str,
    status_removed: str,
    current_values: list[str],
    previous_values: list[str],
) -> list[dict[str, Any]]:
    current_set = set(current_values or [])
    previous_set = set(previous_values or [])
    introduced = sorted(current_set - previous_set)
    removed = sorted(previous_set - current_set)
    events = []
    if introduced:
        events.append(
            {
                "status": status_new,
                "label": label_prefix,
                "count": len(introduced),
                "detail": ", ".join(introduced[:3]),
            }
        )
    if removed:
        events.append(
            {
                "status": status_removed,
                "label": label_prefix,
                "count": len(removed),
                "detail": ", ".join(removed[:3]),
            }
        )
    return events


def _describe_signed_delta(value, positive_label: str, negative_label: str, neutral_label: str) -> str:
    if value is None or value == 0:
        return neutral_label
    if value > 0:
        return f"{positive_label} by {abs(value):.0f}"
    return f"{negative_label} by {abs(value):.0f}"


def _format_metric_value(value) -> str:
    if value is None or value == "":
        return "Not Measured"
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, Decimal):
        return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
    return str(value)


def _format_delta_label(delta, suffix: str = "") -> str:
    if delta is None:
        return "Not Measured"
    prefix = "+" if delta > 0 else ""
    if isinstance(delta, Decimal):
        return f"{prefix}{delta.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}{suffix}"
    return f"{prefix}{delta}{suffix}"


def _quantize(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
