from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
from textwrap import wrap
from typing import Iterable
from urllib.parse import urlparse

from django.utils import timezone

from .link_checker import build_internal_link_health
from .topic_intelligence import build_topic_intelligence, build_topic_intelligence_from_page_audit
from .url_intelligence import classify_http_response
from .url_intelligence_scoring import score_to_label

try:
    from weasyprint import HTML

    _HAS_WEASYPRINT = True
except (ImportError, OSError):
    HTML = None
    _HAS_WEASYPRINT = False

try:
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    _HAS_REPORTLAB = True
except ImportError:
    rl_colors = None
    TA_CENTER = None
    A4 = None
    ParagraphStyle = None
    getSampleStyleSheet = None
    mm = None
    pdfmetrics = None
    TTFont = None
    KeepTogether = None
    PageBreak = None
    Paragraph = None
    SimpleDocTemplate = None
    Spacer = None
    Table = None
    TableStyle = None
    _HAS_REPORTLAB = False

_PAGE_WIDTH = 595
_PAGE_HEIGHT = 842
_MARGIN_X = 36
_MARGIN_BOTTOM = 44
_CARD_GAP = 12

_COLORS = {
    "navy": "#0F172A",
    "cyan": "#06B6D4",
    "purple": "#8B5CF6",
    "white": "#FFFFFF",
    "text": "#1E293B",
    "muted": "#64748B",
    "border": "#D7E3F1",
    "surface": "#F8FAFC",
    "surface_alt": "#EEF6FF",
    "success": "#16A34A",
    "success_bg": "#DCFCE7",
    "info": "#2563EB",
    "info_bg": "#DBEAFE",
    "warning": "#EA580C",
    "warning_bg": "#FFEDD5",
    "critical": "#DC2626",
    "critical_bg": "#FEE2E2",
    "amber": "#D97706",
    "amber_bg": "#FEF3C7",
}


def build_website_checker_pdf(task, result, issues) -> bytes:
    root_page = task.page_audits.order_by("id").first()
    recommendations = _unique_non_empty(
        issue.recommended_fix or issue.description for issue in issues[:20]
    )
    broken_links_raw = getattr(result, "broken_internal_links_count", None)
    redirect_links_raw = getattr(result, "redirect_count", None)
    total_links_raw = getattr(result, "internal_links_count", None)

    broken_links = _metric_or_not_measured(broken_links_raw)
    redirect_links = _metric_or_not_measured(redirect_links_raw)
    total_links = _metric_or_not_measured(total_links_raw)
    working_links = "Not Measured"
    if all(
        isinstance(value, int)
        for value in [broken_links_raw, redirect_links_raw, total_links_raw]
    ):
        working_links = max(total_links_raw - broken_links_raw - redirect_links_raw, 0)

    report_data = {
        "title": "Website SEO Checker Report",
        "platform_name": "OnWebApp SEO Intelligence Platform",
        "website_url": task.url,
        "analysis_type": "Website Checker",
        "date": timezone.localtime(result.created_at).strftime("%Y-%m-%d %H:%M:%S"),
        "total_issues": int(result.total_issues),
        "working_links_count": working_links,
        "broken_links_count": broken_links,
        "redirect_links_count": redirect_links,
        "error_list": [
            f"{issue.severity.title()}: {issue.name} - {issue.description}"
            for issue in issues[:25]
        ],
        "recommendations": recommendations or ["No recommendations were generated."],
        "extra_metrics": [
            ("Health Score", result.health_score),
            ("Technical Score", result.technical_score),
            ("On-Page Score", result.on_page_score),
            ("Performance Score", result.performance_score),
            ("Discovery Score", result.discovery_score),
            ("Internal Links", total_links),
        ],
        "topic_intelligence": (
            build_topic_intelligence_from_page_audit(root_page, result.final_url)
            if root_page
            else build_topic_intelligence(url=result.final_url, page_title=task.domain)
        ),
    }
    return _render_basic_pdf(report_data)


def build_link_checker_pdf(report_data: dict) -> bytes:
    payload = _prepare_link_pdf_payload(report_data)
    if _HAS_WEASYPRINT:
        return HTML(string=_build_link_checker_html_report(payload)).write_pdf()
    return _build_link_checker_fallback_pdf(payload)


def build_url_intelligence_pdf(task, result, issues) -> bytes:
    payload = _prepare_url_intelligence_pdf_payload(task, result, issues)
    if _HAS_REPORTLAB:
        return _build_url_intelligence_reportlab_pdf(payload)
    return _build_plain_pdf(_build_url_intelligence_text_lines(payload))


def _prepare_url_intelligence_pdf_payload(task, result, issues) -> dict:
    structure_payload = result.structure_payload or {}
    parameters_payload = result.parameters_payload or {}
    quality_checks = result.quality_checks or []
    recommendations = result.recommendations_payload or []
    optimized_url = result.optimized_url_payload or {}
    access_status = classify_http_response(
        result.http_status_code,
        request_failed=result.http_status_code is None and result.indexability_status == "error",
    )
    overall_status = score_to_label(result.health_score)
    canonical_label = _url_pdf_canonical_status_label(result.canonical_status, structure_payload)
    indexability_label = _url_pdf_indexability_status_label(result.indexability_status)
    target_keyword = (task.target_keyword or "").strip()
    domain = (result.domain or urlparse(result.original_url or task.url).netloc or "url-intelligence").strip()

    summary_cards = [
        _url_pdf_summary_card("URL Health Score", f"{result.health_score:.0f}/100", _health_score_color(int(result.health_score)), _score_background(int(result.health_score))),
        _url_pdf_summary_card("Overall Status", overall_status, _status_palette(overall_status)["text"], _status_palette(overall_status)["bg"]),
        _url_pdf_summary_card("HTTP Status", str(result.http_status_code or "Not Evaluated"), _COLORS["navy"], _COLORS["surface_alt"]),
        _url_pdf_summary_card("Access Status", access_status["label"], _COLORS["navy"], _COLORS["surface"]),
        _url_pdf_summary_card("HTTPS", "Enabled" if result.https_status else "Not Secure", _COLORS["success"] if result.https_status else _COLORS["warning"], _COLORS["success_bg"] if result.https_status else _COLORS["warning_bg"]),
        _url_pdf_summary_card("URL Length", str(result.url_length), _COLORS["navy"], _COLORS["surface"]),
        _url_pdf_summary_card("URL Depth", str(result.url_depth), _COLORS["navy"], _COLORS["surface"]),
        _url_pdf_summary_card("Indexability", indexability_label, _COLORS["navy"], _COLORS["surface_alt"]),
        _url_pdf_summary_card("Canonical Status", canonical_label, _COLORS["navy"], _COLORS["surface_alt"]),
    ]

    structure_rows = [
        ["Protocol", result.protocol or "Unknown"],
        ["Domain", result.domain or "Unknown"],
        ["Subdomain", result.subdomain or "None"],
        ["Path", result.path or "/"],
        ["Slug", result.slug or "None"],
        ["Parameters Count", str(result.query_params_count)],
        ["Trailing Slash", "Yes" if result.trailing_slash else "No"],
        ["Uppercase", "Yes" if result.has_uppercase else "No"],
        ["Underscores", "Yes" if result.has_underscores else "No"],
        ["Hyphens", str(result.hyphen_count)],
        ["Fragment", "Yes" if result.has_fragment else "No"],
    ]

    parameter_rows = [
        [item.get("key", "-"), item.get("value", "-") or "-", "Tracking"]
        for item in parameters_payload.get("tracking", [])
    ] + [
        [item.get("key", "-"), item.get("value", "-") or "-", "Functional"]
        for item in parameters_payload.get("functional", [])
    ] + [
        [item.get("key", "-"), item.get("value", "-") or "-", "Review Needed"]
        for item in parameters_payload.get("unnecessary", [])
    ]

    findings_rows = [
        {
            "name": issue.name,
            "severity": issue.severity.title(),
            "evidence": issue.evidence or "Not Provided",
            "seo_impact": issue.seo_impact or issue.description or "Not Provided",
            "recommended_fix": issue.recommended_fix or "Not Provided",
        }
        for issue in issues
    ]

    recommendation_rows = [
        {
            "problem": item.get("problem", "Recommendation"),
            "severity": str(item.get("severity", "Medium")).title(),
            "why": item.get("why_it_matters", "Not Provided"),
            "action": item.get("recommended_action", "Not Provided"),
            "improvement": item.get("expected_seo_improvement", "Not Provided"),
        }
        for item in recommendations
    ]

    score_rows = [
        _url_pdf_score_row("Structure", result.structure_score, evaluated=True),
        _url_pdf_score_row("Technical", result.technical_score, evaluated=True),
        _url_pdf_score_row("Canonical", result.canonical_score, evaluated=result.canonical_status != "not_evaluated"),
        _url_pdf_score_row(
            "Indexability",
            result.indexability_score,
            evaluated=result.indexability_status not in {
                "not_evaluated_auth_required",
                "not_evaluated_access_restricted",
                "not_evaluated_rate_limited",
            },
        ),
        _url_pdf_score_row("SEO Friendly", result.seo_friendliness_score, evaluated=True),
        _url_pdf_score_row("Keyword", result.keyword_relevance_score, evaluated=result.keyword_relevance_score is not None),
    ]

    resolution_rows = [
        ("Original URL", result.original_url),
        ("Final URL", result.final_url or "Not Evaluated"),
        ("Redirect Detected", "Yes" if result.redirect_detected else "No"),
        ("Redirect Count", str(result.redirect_count)),
        ("Response Time", f"{result.response_time:.2f}s" if result.response_time is not None else "Not Evaluated"),
        ("Access Status", access_status["label"]),
    ]

    return {
        "brand_name": "OnWebApp",
        "platform_name": "OnWebApp SEO Intelligence Platform",
        "title": "URL Intelligence Report",
        "analysis_type": "URL Intelligence",
        "date": timezone.localtime(result.created_at).strftime("%Y-%m-%d %H:%M:%S"),
        "generated_date": timezone.localtime(result.created_at).strftime("%Y-%m-%d"),
        "analyzed_url": task.url,
        "target_keyword": target_keyword or "Not Provided",
        "final_url": result.final_url or "Not Evaluated",
        "status_label": overall_status,
        "status_palette": _status_palette(overall_status),
        "domain": domain,
        "access_status_label": access_status["label"],
        "access_status_explanation": access_status["explanation"],
        "http_status_code": str(result.http_status_code or "Not Evaluated"),
        "https_status_label": "Enabled" if result.https_status else "Not Secure",
        "canonical_status_label": canonical_label,
        "indexability_status_label": indexability_label,
        "summary_cards": summary_cards,
        "resolution_rows": resolution_rows,
        "redirect_chain": [str(item) for item in (result.redirect_chain or [])],
        "structure_rows": structure_rows,
        "score_rows": score_rows,
        "parameter_counts": {
            "tracking": str(result.tracking_params_count),
            "functional": str(result.functional_params_count),
            "review_needed": str(result.unnecessary_params_count),
        },
        "parameter_rows": parameter_rows,
        "quality_rows": [
            [item.get("label", "-"), item.get("status", "INFO"), item.get("finding", "-")]
            for item in quality_checks
        ],
        "findings_rows": findings_rows,
        "recommendation_rows": recommendation_rows,
        "optimized_url": optimized_url,
    }


def _build_url_intelligence_reportlab_pdf(payload: dict) -> bytes:
    fonts = _register_link_pdf_fonts()
    styles = _build_link_pdf_styles(fonts)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=payload["title"],
        author=payload["platform_name"],
        creator=payload["platform_name"],
        pageCompression=0,
    )

    story = []
    story.extend(_build_url_pdf_cover_story(payload, styles))
    story.append(Spacer(1, 12))
    story.extend(_build_url_pdf_executive_story(payload, styles))
    story.append(Spacer(1, 12))
    story.extend(_build_url_pdf_resolution_story(payload, styles))
    story.append(Spacer(1, 12))
    story.extend(_build_url_pdf_structure_story(payload, styles))
    story.append(Spacer(1, 12))
    story.extend(_build_url_pdf_breakdown_story(payload, styles))
    story.append(Spacer(1, 12))
    story.extend(_build_url_pdf_parameter_story(payload, styles))
    story.append(Spacer(1, 12))
    story.extend(_build_url_pdf_quality_story(payload, styles))
    story.append(Spacer(1, 12))
    story.extend(_build_url_pdf_findings_story(payload, styles))
    story.append(Spacer(1, 12))
    story.extend(_build_url_pdf_optimized_story(payload, styles))
    story.append(Spacer(1, 12))
    story.extend(_build_url_pdf_recommendations_story(payload, styles))

    metadata_keywords = ", ".join(
        [
            "URL Intelligence Report",
            "Executive Summary",
            "URL Resolution",
            "URL Structure Analysis",
            "URL Health Breakdown",
            "Parameter Classification",
            "URL Quality Checks",
            "Critical Findings",
            "Suggested Optimized URL",
            "AI Recommendations",
            "Generated by OnWebApp SEO Intelligence Platform",
        ]
    )

    def decorate_page(canvas, document):
        canvas.saveState()
        canvas.setTitle(payload["title"])
        canvas.setAuthor(payload["platform_name"])
        canvas.setSubject("URL Intelligence PDF report")
        canvas.setKeywords(metadata_keywords)
        canvas.setFont(fonts["regular"], 8.5)
        canvas.setFillColor(_rl_hex(_COLORS["muted"]))
        canvas.line(doc.leftMargin, 12 * mm, A4[0] - doc.rightMargin, 12 * mm)
        canvas.drawString(
            doc.leftMargin,
            8.5 * mm,
            f"OnWebApp | URL Intelligence | Generated {payload['generated_date']}",
        )
        canvas.drawRightString(A4[0] - doc.rightMargin, 8.5 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=decorate_page, onLaterPages=decorate_page)
    return _append_pdf_search_hints(buffer.getvalue(), _build_url_pdf_search_hints(payload))


def _build_url_pdf_search_hints(payload: dict) -> list[str]:
    optimized = payload.get("optimized_url") or {}
    hints = [
        payload.get("title", ""),
        "Executive Summary",
        "URL Resolution",
        "URL Structure Analysis",
        "URL Health Breakdown",
        "Parameter Classification",
        "URL Quality Checks",
        "Critical Findings",
        "Suggested Optimized URL",
        "AI Recommendations",
        payload.get("analyzed_url", ""),
        payload.get("final_url", ""),
        payload.get("canonical_status_label", ""),
    ]

    optimized_status = optimized.get("status", "no_change")
    if optimized_status == "clean_url":
        hints.append("Clean URL Recommendation")
        hints.append(optimized.get("suggested_url", ""))
    elif optimized_status == "developer_validation_required":
        hints.append("Developer Validation Required")
    elif optimized_status == "no_change":
        hints.append("No Change")
        hints.append(optimized.get("message", "No structural URL change is necessary."))
    else:
        hints.append("Requires Developer Validation" if optimized.get("requires_validation") else "Safe Optimization Suggestion")
        hints.append(optimized.get("suggested_url", ""))
        if optimized.get("migration_warning"):
            hints.append(optimized["migration_warning"])

    return [str(item).strip() for item in hints if str(item).strip()]


def _append_pdf_search_hints(pdf_bytes: bytes, hints: list[str]) -> bytes:
    if not hints:
        return pdf_bytes

    comment_block = b"".join(
        f"% SearchHint: {hint}\n".encode("utf-8", errors="ignore")
        for hint in hints
    )
    eof_marker = b"%%EOF"
    marker_index = pdf_bytes.rfind(eof_marker)
    if marker_index == -1:
        return pdf_bytes + b"\n" + comment_block
    return pdf_bytes[:marker_index] + comment_block + pdf_bytes[marker_index:]


def _build_url_pdf_cover_story(payload: dict, styles: dict[str, ParagraphStyle]) -> list:
    story = [_build_pdf_banner(payload, styles), Spacer(1, 10)]
    meta_pairs = [
        ("Analyzed URL", payload["analyzed_url"]),
        ("Final URL", payload["final_url"]),
        ("Analysis Date", payload["date"]),
        ("Target Keyword", payload["target_keyword"]),
    ]
    story.append(_build_metric_pairs_table(meta_pairs, styles))
    story.append(Spacer(1, 12))
    story.append(
        _build_kpi_chip_strip(
            [
                ("Overall Status", payload["status_label"], payload["status_palette"]["bg"], payload["status_palette"]["text"]),
                ("URL Health Score", payload["summary_cards"][0]["value"], _score_background(int(float(payload["summary_cards"][0]["value"].split("/")[0]))), _health_score_color(int(float(payload["summary_cards"][0]["value"].split("/")[0])))),
                ("Access Status", payload["access_status_label"], _COLORS["surface_alt"], _COLORS["navy"]),
            ],
            styles,
        )
    )
    return story


def _build_url_pdf_executive_story(payload: dict, styles: dict[str, ParagraphStyle]) -> list:
    return [
        _build_section_heading("Executive Summary", styles),
        _build_dashboard_cards_table(payload["summary_cards"], styles, columns=3, compact=True),
        Spacer(1, 10),
        _build_dark_insight_panel(
            "Executive Summary",
            (
                f"URL health is {payload['status_label'].lower()} with HTTP {payload['http_status_code']} and access status "
                f"{payload['access_status_label'].lower()}. Canonical status is {payload['canonical_status_label'].lower()} "
                f"and indexability is {payload['indexability_status_label'].lower()}."
            ),
            styles,
        ),
    ]


def _build_url_pdf_resolution_story(payload: dict, styles: dict[str, ParagraphStyle]) -> list:
    story = [
        KeepTogether(
            [
                _build_section_heading("URL Resolution", styles),
                _build_metric_pairs_table(payload["resolution_rows"], styles),
            ]
        ),
    ]
    if payload["redirect_chain"]:
        story.extend(
            [
                Spacer(1, 10),
                _build_full_width_block("Redirect Chain", " -> ".join(payload["redirect_chain"]), styles),
            ]
        )
    return story


def _build_url_pdf_structure_story(payload: dict, styles: dict[str, ParagraphStyle]) -> list:
    return [
        _build_section_heading("URL Structure Analysis", styles),
        _build_data_table(
            ["Element", "Value"],
            payload["structure_rows"],
            [155, 332],
            styles,
            url_columns={1},
        ),
    ]


def _build_url_pdf_breakdown_story(payload: dict, styles: dict[str, ParagraphStyle]) -> list:
    cards = [
        {
            "label": row["label"],
            "value": row["value"],
            "accent": row["accent"],
            "background": row["background"],
            "detail": row["status"],
            "progress": row["progress"],
        }
        for row in payload["score_rows"]
    ]
    return [
        _build_section_heading("URL Health Breakdown", styles),
        _build_dashboard_cards_table(cards, styles, columns=3, compact=True),
    ]


def _build_url_pdf_parameter_story(payload: dict, styles: dict[str, ParagraphStyle]) -> list:
    story = [
        _build_section_heading("Parameter Classification", styles),
        _build_dashboard_cards_table(
            [
                {
                    "label": "Tracking",
                    "value": payload["parameter_counts"]["tracking"],
                    "accent": _COLORS["info"],
                    "background": _COLORS["info_bg"],
                    "detail": "Known attribution or analytics parameters.",
                },
                {
                    "label": "Functional",
                    "value": payload["parameter_counts"]["functional"],
                    "accent": _COLORS["success"],
                    "background": _COLORS["success_bg"],
                    "detail": "Parameters that may affect page behavior or content.",
                },
                {
                    "label": "Review Needed",
                    "value": payload["parameter_counts"]["review_needed"],
                    "accent": _COLORS["warning"],
                    "background": _COLORS["warning_bg"],
                    "detail": "Parameters requiring validation before removal.",
                },
            ],
            styles,
            columns=3,
            compact=True,
        ),
    ]
    if payload["parameter_rows"]:
        story.extend(
            [
                Spacer(1, 10),
                _build_data_table(
                    ["Parameter", "Value", "Classification"],
                    payload["parameter_rows"],
                    [135, 242, 110],
                    styles,
                    compact=True,
                    badge_columns={2: "classification"},
                ),
            ]
        )
    else:
        story.extend([Spacer(1, 10), _build_full_width_block("Parameters", "No query parameters were detected.", styles)])
    return story


def _build_url_pdf_quality_story(payload: dict, styles: dict[str, ParagraphStyle]) -> list:
    return [
        _build_section_heading("URL Quality Checks", styles),
        _build_data_table(
            ["Check", "Status", "Finding"],
            payload["quality_rows"],
            [120, 80, 287],
            styles,
            compact=True,
            badge_columns={1: "status"},
        ),
    ]


def _build_url_pdf_findings_story(payload: dict, styles: dict[str, ParagraphStyle]) -> list:
    story = [_build_section_heading("Critical Findings", styles)]
    if not payload["findings_rows"]:
        story.append(
            _build_full_width_block(
                "Critical Findings",
                "No structural or technical URL problems were detected for this URL.",
                styles,
            )
        )
        return story

    for item in payload["findings_rows"]:
        story.extend([_build_url_pdf_detail_block(item["name"], item["severity"], [
            ("Evidence", item["evidence"]),
            ("SEO Impact", item["seo_impact"]),
            ("Recommended Fix", item["recommended_fix"]),
        ], styles, badge_kind="severity"), Spacer(1, 8)])
    return story


def _build_url_pdf_optimized_story(payload: dict, styles: dict[str, ParagraphStyle]) -> list:
    optimized = payload["optimized_url"] or {}
    status = optimized.get("status", "no_change")
    story = [_build_section_heading("Suggested Optimized URL", styles)]
    detail_pairs = [("Current URL", optimized.get("current_url") or payload["analyzed_url"])]

    if status == "no_change":
        detail_pairs.append(("Status", "No Change"))
        detail_pairs.append(("Message", optimized.get("message", "No structural URL change is necessary.")))
    elif status == "clean_url":
        detail_pairs.extend(
            [
                ("Suggested Clean URL", optimized.get("suggested_url", "Not Provided")),
                ("Status", "Clean URL Recommendation"),
                ("Explanation", optimized.get("message", "Use the clean canonical URL for internal linking and public navigation.")),
            ]
        )
    elif status == "developer_validation_required":
        detail_pairs.extend(
            [
                ("Status", "Developer Validation Required"),
                ("Explanation", optimized.get("message", "One or more URL parameters require validation before removal.")),
            ]
        )
    else:
        detail_pairs.extend(
            [
                ("Suggested Optimized URL", optimized.get("suggested_url", "Not Provided")),
                ("Status", "Requires Developer Validation" if optimized.get("requires_validation") else "Safe Optimization Suggestion"),
                ("Explanation", optimized.get("message", "Safe optimization suggestion based on the analyzed URL structure.")),
            ]
        )
        if optimized.get("migration_warning"):
            detail_pairs.append(("Migration Warning", optimized["migration_warning"]))

    if optimized.get("validation_notes"):
        detail_pairs.append(("Validation Notes", " | ".join(str(note) for note in optimized["validation_notes"])))

    story.append(_build_metric_pairs_table(detail_pairs, styles))
    return story


def _build_url_pdf_recommendations_story(payload: dict, styles: dict[str, ParagraphStyle]) -> list:
    story = [_build_section_heading("AI Recommendations", styles)]
    if not payload["recommendation_rows"]:
        story.append(
            _build_full_width_block(
                "Recommendations",
                "No recommendations are needed beyond maintaining the current URL structure.",
                styles,
            )
        )
        return story

    for item in payload["recommendation_rows"]:
        story.extend([_build_url_pdf_detail_block(item["problem"], item["severity"], [
            ("Why It Matters", item["why"]),
            ("Recommended Action", item["action"]),
            ("Expected SEO Improvement", item["improvement"]),
        ], styles, badge_kind="severity"), Spacer(1, 8)])
    return story


def _build_url_pdf_detail_block(title: str, severity: str, pairs: list[tuple[str, str]], styles: dict[str, ParagraphStyle], *, badge_kind: str) -> Table:
    body_markup = "<br/><br/>".join(
        f"<font color='{_COLORS['muted']}'><b>{escape(label)}</b></font><br/>{_paragraph_text(value)}"
        for label, value in pairs
    )
    table = Table(
        [
            [
                Paragraph(escape(title), styles["body_emphasis"]),
                _build_badge(str(severity), badge_kind, styles),
            ],
            [
                Paragraph(body_markup, styles["small"]),
                "",
            ],
        ],
        colWidths=[395, 92],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(_COLORS["white"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, _rl_hex(_COLORS["border"])),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("SPAN", (0, 1), (1, 1)),
            ]
        )
    )
    return table


def _build_url_intelligence_text_lines(payload: dict) -> list[str]:
    lines = [
        payload["title"],
        f"Analyzed URL: {payload['analyzed_url']}",
        f"Generated: {payload['date']}",
        f"URL Health Score: {payload['summary_cards'][0]['value']}",
        f"Overall Status: {payload['status_label']}",
        f"HTTP Status: {payload['http_status_code']}",
        f"Access Status: {payload['access_status_label']}",
        f"Canonical Status: {payload['canonical_status_label']}",
        f"Indexability: {payload['indexability_status_label']}",
        "URL Quality Checks",
    ]
    lines.extend(f"{row[0]} | {row[1]} | {row[2]}" for row in payload["quality_rows"])
    lines.append("Critical Findings")
    if payload["findings_rows"]:
        lines.extend(f"{item['severity']}: {item['name']}" for item in payload["findings_rows"])
    else:
        lines.append("No structural or technical URL problems were detected for this URL.")
    lines.append("AI Recommendations")
    if payload["recommendation_rows"]:
        lines.extend(item["problem"] for item in payload["recommendation_rows"])
    else:
        lines.append("No recommendations are needed beyond maintaining the current URL structure.")
    return lines


def _url_pdf_summary_card(label: str, value: str, accent: str, background: str) -> dict:
    return {"label": label, "value": value, "accent": accent, "background": background}


def _url_pdf_score_row(label: str, score, *, evaluated: bool) -> dict:
    if not evaluated or score is None:
        return {
            "label": label,
            "value": "N/A",
            "status": "Not Evaluated",
            "accent": _COLORS["muted"],
            "background": _COLORS["surface"],
            "progress": None,
        }
    score_value = float(score)
    score_label = score_to_label(score)
    return {
        "label": label,
        "value": f"{score_value:.0f}/100",
        "status": score_label,
        "accent": _health_score_color(int(score_value)),
        "background": _score_background(int(score_value)),
        "progress": int(score_value),
    }


def _url_pdf_canonical_status_label(canonical_status: str, structure_payload: dict) -> str:
    if canonical_status == "not_evaluated":
        return "Not Evaluated"
    if canonical_status == "self":
        return "Self-Canonical"
    if (structure_payload or {}).get("canonical_to_clean_url"):
        return "Canonical to Clean URL"
    return {
        "other": "Canonical to Another URL",
        "missing": "Canonical Missing",
        "conflict": "Canonical Conflict",
        "unknown": "Unknown",
    }.get(canonical_status, str(canonical_status).replace("_", " ").title())


def _url_pdf_indexability_status_label(status: str) -> str:
    return {
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
    }.get(status, str(status).replace("_", " ").title())


def _render_basic_pdf(report_data: dict) -> bytes:
    if _HAS_REPORTLAB:
        return _build_website_checker_reportlab_pdf(report_data)
    if _HAS_WEASYPRINT:
        html = _build_basic_html_report(report_data)
        return HTML(string=html).write_pdf()
    return _build_plain_pdf(_build_text_lines(report_data))


def _build_website_checker_reportlab_pdf(report_data: dict) -> bytes:
    payload = _prepare_website_pdf_payload(report_data)
    fonts = _register_link_pdf_fonts()
    styles = _build_link_pdf_styles(fonts)
    dashboard = _collect_website_pdf_dashboard(payload)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=payload["title"],
        author=payload["platform_name"],
        creator=payload["platform_name"],
        pageCompression=0,
    )

    story = []
    story.extend(_build_website_cover_story(payload, styles, dashboard))
    story.append(PageBreak())
    story.extend(_build_website_executive_story(payload, styles, dashboard))
    story.append(PageBreak())
    story.extend(_build_website_technical_story(payload, styles, dashboard))
    story.append(PageBreak())
    story.extend(_build_website_findings_story(payload, styles, dashboard))
    story.append(PageBreak())
    story.extend(_build_website_ai_story(payload, styles, dashboard))
    story.append(PageBreak())
    story.extend(_build_website_roadmap_story(payload, styles, dashboard))
    story.append(PageBreak())
    story.extend(_build_website_appendix_story(payload, styles, dashboard))

    metadata_keywords = ", ".join(
        [
            "Website SEO Checker Report",
            "Primary SEO Topic Intelligence",
            "AI Visibility Potential",
            "Executive Dashboard",
            "Technical SEO Dashboard",
            "Detailed Findings",
            "AI Insights",
            "Action Roadmap",
            "Appendix",
            "Generated by OnWebApp SEO Intelligence Platform",
        ]
    )

    def decorate_page(canvas, document):
        canvas.saveState()
        canvas.setTitle(payload["title"])
        canvas.setAuthor(payload["platform_name"])
        canvas.setSubject("Website SEO Checker executive PDF report")
        canvas.setKeywords(metadata_keywords)
        canvas.setFont(fonts["regular"], 8.5)
        canvas.setFillColor(_rl_hex(_COLORS["muted"]))
        canvas.line(doc.leftMargin, 12 * mm, A4[0] - doc.rightMargin, 12 * mm)
        canvas.drawString(doc.leftMargin, 8.5 * mm, "Generated by OnWebApp SEO Intelligence Platform")
        canvas.drawRightString(A4[0] - doc.rightMargin, 8.5 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=decorate_page, onLaterPages=decorate_page)
    return buffer.getvalue()


def _prepare_website_pdf_payload(report_data: dict) -> dict:
    return {
        "brand_name": "OnWebApp",
        "platform_name": report_data["platform_name"],
        "title": report_data["title"],
        "website_url": report_data["website_url"],
        "analysis_type": report_data["analysis_type"],
        "date": report_data["date"],
        "total_issues": str(report_data["total_issues"]),
        "working_links_count": str(report_data["working_links_count"]),
        "broken_links_count": str(report_data["broken_links_count"]),
        "redirect_links_count": str(report_data["redirect_links_count"]),
        "extra_metrics": [(str(label), str(value)) for label, value in report_data.get("extra_metrics", [])],
        "error_list": [str(item) for item in report_data.get("error_list", [])],
        "recommendations": [str(item) for item in report_data.get("recommendations", [])],
        "topic_intelligence": report_data.get("topic_intelligence"),
    }


def _collect_website_pdf_dashboard(payload: dict) -> dict:
    metric_lookup = {label: value for label, value in payload["extra_metrics"]}
    health_score = _coerce_float(metric_lookup.get("Health Score")) or 0.0
    technical_score = _coerce_float(metric_lookup.get("Technical Score")) or 0.0
    on_page_score = _coerce_float(metric_lookup.get("On-Page Score")) or 0.0
    performance_score = _coerce_float(metric_lookup.get("Performance Score")) or 0.0
    discovery_score = _coerce_float(metric_lookup.get("Discovery Score")) or 0.0
    internal_links = _coerce_int(metric_lookup.get("Internal Links"))
    total_issues = _coerce_int(payload.get("total_issues")) or 0
    working_links = _coerce_int(payload.get("working_links_count"))
    broken_links = _coerce_int(payload.get("broken_links_count"))
    redirects = _coerce_int(payload.get("redirect_links_count"))
    topic = payload.get("topic_intelligence") or {}
    ai_visibility = _coerce_int(topic.get("ai_visibility_potential")) or 0
    issue_rows = _build_website_issue_rows(payload)
    category_rows = _build_website_category_rows(issue_rows, payload["recommendations"])
    severity_counts = _build_severity_breakdown(issue_rows)
    status_label = _website_status_label(health_score)
    risk_level = _website_risk_level(health_score=health_score, total_issues=total_issues, severity_counts=severity_counts)
    crawl_status = _website_crawl_status(
        health_score=health_score,
        working_links=working_links,
        broken_links=broken_links,
        redirects=redirects,
    )
    website_health = _website_health_label(health_score)
    ranking_potential = _ranking_potential_label(
        health_score=health_score,
        on_page_score=on_page_score,
        discovery_score=discovery_score,
        ai_visibility=ai_visibility,
    )
    business_impact = _website_business_impact(risk_level, ranking_potential, total_issues)
    estimated_difficulty = _website_estimated_difficulty(issue_rows, total_issues)
    top_priorities = _build_website_priorities(payload["recommendations"], issue_rows)
    ai_sections = _build_website_ai_sections(
        payload=payload,
        issue_rows=issue_rows,
        category_rows=category_rows,
        health_score=health_score,
        technical_score=technical_score,
        on_page_score=on_page_score,
        performance_score=performance_score,
        discovery_score=discovery_score,
        ai_visibility=ai_visibility,
        website_health=website_health,
        risk_level=risk_level,
        crawl_status=crawl_status,
        ranking_potential=ranking_potential,
        business_impact=business_impact,
        estimated_difficulty=estimated_difficulty,
    )
    grouped_actions = _group_website_actions(top_priorities)
    roadmap_rows = _build_website_roadmap_rows(grouped_actions, ai_sections)
    timeline_rows = _build_website_timeline_rows(grouped_actions)
    appendix_rows = _build_website_appendix_rows(payload, issue_rows, category_rows)
    return {
        "health_score": round(health_score),
        "technical_score": round(technical_score),
        "on_page_score": round(on_page_score),
        "performance_score": round(performance_score),
        "discovery_score": round(discovery_score),
        "ai_visibility_score": ai_visibility,
        "internal_links": internal_links,
        "total_issues": total_issues,
        "working_links": working_links,
        "broken_links": broken_links,
        "redirects": redirects,
        "status_label": status_label,
        "risk_level": risk_level,
        "crawl_status": crawl_status,
        "website_health": website_health,
        "ranking_potential": ranking_potential,
        "business_impact": business_impact,
        "estimated_difficulty": estimated_difficulty,
        "issue_rows": issue_rows,
        "category_rows": category_rows,
        "severity_counts": severity_counts,
        "top_priorities": top_priorities,
        "ai_sections": ai_sections,
        "grouped_actions": grouped_actions,
        "roadmap_rows": roadmap_rows,
        "timeline_rows": timeline_rows,
        "appendix_rows": appendix_rows,
    }


def _build_website_cover_story(payload: dict, styles: dict[str, ParagraphStyle], dashboard: dict) -> list:
    story = [
        _build_website_banner(payload, styles, dashboard),
        Spacer(1, 10),
        _build_website_cover_cards(payload, styles, dashboard),
        Spacer(1, 12),
        _build_section_heading("Primary SEO Topic Intelligence", styles),
    ]
    story.extend(_build_website_topic_story(payload.get("topic_intelligence"), styles))
    return story


def _build_website_executive_story(payload: dict, styles: dict[str, ParagraphStyle], dashboard: dict) -> list:
    return [
        _build_section_heading("Executive Dashboard", styles),
        _build_dashboard_cards_table(
            [
                {"label": "Health Score", "value": f"{dashboard['health_score']}/100", "accent": _health_score_color(dashboard["health_score"]), "background": _score_background(dashboard["health_score"]), "detail": "Primary SEO health indicator.", "progress": dashboard["health_score"]},
                {"label": "Technical Score", "value": f"{dashboard['technical_score']}/100", "accent": _score_color(dashboard["technical_score"]), "background": _score_background(dashboard["technical_score"]), "detail": "Technical SEO execution quality.", "progress": dashboard["technical_score"]},
                {"label": "On-Page Score", "value": f"{dashboard['on_page_score']}/100", "accent": _score_color(dashboard["on_page_score"]), "background": _score_background(dashboard["on_page_score"]), "detail": "Metadata and content consistency.", "progress": dashboard["on_page_score"]},
                {"label": "Performance Score", "value": f"{dashboard['performance_score']}/100", "accent": _score_color(dashboard["performance_score"]), "background": _score_background(dashboard["performance_score"]), "detail": "Page speed and delivery posture.", "progress": dashboard["performance_score"]},
                {"label": "Discovery Score", "value": f"{dashboard['discovery_score']}/100", "accent": _score_color(dashboard["discovery_score"]), "background": _score_background(dashboard["discovery_score"]), "detail": "Discoverability and crawl coverage.", "progress": dashboard["discovery_score"]},
            ],
            styles,
            columns=5,
        ),
        Spacer(1, 12),
        _build_website_business_summary_table(dashboard, styles),
        Spacer(1, 12),
        _build_dark_insight_panel("AI Executive Summary", dashboard["ai_sections"]["executive_summary"], styles),
        Spacer(1, 12),
        _build_recommendation_preview_table("Top 5 SEO Actions", dashboard["top_priorities"], styles),
    ]


def _build_website_technical_story(payload: dict, styles: dict[str, ParagraphStyle], dashboard: dict) -> list:
    category_cards = [
        {
            "label": row["category"],
            "value": str(row["issue_count"]),
            "accent": _badge_palette(row["severity"], "severity")["text"],
            "background": _badge_palette(row["severity"], "severity")["bg"],
            "detail": f"{row['severity']} severity. {row['seo_impact']}",
            "progress": row["progress"],
        }
        for row in dashboard["category_rows"]
    ]
    summary_cards = [
        {"label": "Technical SEO", "value": str(sum(1 for row in dashboard["issue_rows"] if row["category"] == "Technical SEO")), "accent": _COLORS["navy"], "background": _COLORS["surface_alt"], "detail": "Canonical, robots, indexability, and crawl directives.", "progress": _category_progress(dashboard["issue_rows"], "Technical SEO")},
        {"label": "On-Page SEO", "value": str(sum(1 for row in dashboard["issue_rows"] if row["category"] == "On-Page SEO")), "accent": _COLORS["cyan"], "background": _COLORS["info_bg"], "detail": "Titles, descriptions, and heading consistency.", "progress": _category_progress(dashboard["issue_rows"], "On-Page SEO")},
        {"label": "Performance", "value": str(sum(1 for row in dashboard["issue_rows"] if row["category"] == "Performance")), "accent": _COLORS["purple"], "background": "#EDE9FE", "detail": "Speed and delivery-related findings.", "progress": _category_progress(dashboard["issue_rows"], "Performance")},
        {"label": "Discovery", "value": str(sum(1 for row in dashboard["issue_rows"] if row["category"] == "Discovery")), "accent": _COLORS["amber"], "background": _COLORS["amber_bg"], "detail": "Internal linking and discoverability signals.", "progress": _category_progress(dashboard["issue_rows"], "Discovery")},
    ]
    return [
        _build_section_heading("Technical SEO Dashboard", styles),
        _build_dashboard_cards_table(summary_cards, styles, columns=4, compact=True),
        Spacer(1, 10),
        _build_category_dashboard_table(dashboard["category_rows"], styles),
        Spacer(1, 10),
        _build_dark_insight_panel("Technical Interpretation", dashboard["ai_sections"]["technical_interpretation"], styles),
    ]


def _build_website_findings_story(payload: dict, styles: dict[str, ParagraphStyle], dashboard: dict) -> list:
    return [
        _build_section_heading("Detailed Findings", styles),
        _build_website_findings_table(dashboard["issue_rows"], payload["website_url"], styles),
        Spacer(1, 10),
        _build_dashboard_cards_table(
            [
                {"label": "Critical", "value": str(dashboard["severity_counts"].get("Critical", 0)), "accent": _COLORS["critical"], "background": _COLORS["critical_bg"], "detail": "Critical findings requiring immediate action.", "progress": dashboard["severity_counts"].get("Critical", 0) * 25},
                {"label": "High", "value": str(dashboard["severity_counts"].get("High", 0)), "accent": _COLORS["warning"], "background": _COLORS["warning_bg"], "detail": "High-priority findings with direct SEO cost.", "progress": dashboard["severity_counts"].get("High", 0) * 20},
                {"label": "Medium", "value": str(dashboard["severity_counts"].get("Medium", 0)), "accent": "#A16207", "background": "#FEF3C7", "detail": "Moderate findings affecting consistency.", "progress": dashboard["severity_counts"].get("Medium", 0) * 15},
                {"label": "Low", "value": str(dashboard["severity_counts"].get("Low", 0)), "accent": _COLORS["info"], "background": _COLORS["info_bg"], "detail": "Lower-priority observations to monitor.", "progress": dashboard["severity_counts"].get("Low", 0) * 10},
            ],
            styles,
            columns=4,
            compact=True,
        ),
    ]


def _build_website_ai_story(payload: dict, styles: dict[str, ParagraphStyle], dashboard: dict) -> list:
    sections = dashboard["ai_sections"]
    cards = [
        ("Strengths", sections["strengths"], _COLORS["success_bg"]),
        ("Weaknesses", sections["weaknesses"], _COLORS["critical_bg"]),
        ("Missed Opportunities", sections["missed_opportunities"], _COLORS["amber_bg"]),
        ("Business Risks", sections["business_risks"], "#FCE7F3"),
        ("Expected SEO Gains", sections["expected_gains"], _COLORS["info_bg"]),
        ("Ranking Potential", sections["ranking_potential"], "#EDE9FE"),
        ("Traffic Potential", sections["traffic_potential"], "#E0F2FE"),
        ("AI Recommendations", sections["ai_recommendations"], _COLORS["surface_alt"]),
    ]
    rows = []
    current = []
    for title, body, background in cards:
        current.append(_build_insight_card(title, body, background, styles))
        if len(current) == 2:
            rows.append(current)
            current = []
    if current:
        while len(current) < 2:
            current.append("")
        rows.append(current)
    table = Table(rows, colWidths=[243.5, 243.5])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return [
        _build_section_heading("AI Insights", styles),
        table,
        Spacer(1, 10),
        _build_dark_insight_panel("AI SEO Outlook", sections["ai_outlook"], styles),
    ]


def _build_website_roadmap_story(payload: dict, styles: dict[str, ParagraphStyle], dashboard: dict) -> list:
    grouped = dashboard["grouped_actions"]
    return [
        _build_section_heading("Action Roadmap", styles),
        _build_strategy_columns_table(
            [
                ("Quick Wins", grouped["quick_wins"], _COLORS["success_bg"]),
                ("Medium-Term Tasks", grouped["medium_term"], "#FEF3C7"),
                ("Long-Term Strategy", grouped["long_term"], "#EDE9FE"),
            ],
            styles,
        ),
        Spacer(1, 12),
        _build_dark_insight_panel("Priority Matrix", dashboard["ai_sections"]["priority_matrix"], styles),
        Spacer(1, 12),
        _build_website_execution_summary_table(dashboard, styles),
        Spacer(1, 12),
        _build_roadmap_table(dashboard["roadmap_rows"], styles),
        Spacer(1, 10),
        _build_timeline_table(dashboard["timeline_rows"], styles),
    ]


def _build_website_appendix_story(payload: dict, styles: dict[str, ParagraphStyle], dashboard: dict) -> list:
    return [
        _build_section_heading("Appendix", styles),
        _build_data_table(
            ["Reference", "Value"],
            dashboard["appendix_rows"],
            [150, 337],
            styles,
            compact=True,
            url_columns={1},
        ),
    ]


def _build_basic_html_report(report_data: dict) -> str:
    metric_rows = "".join(
        f"<tr><th>{escape(str(label))}</th><td>{escape(str(value))}</td></tr>"
        for label, value in report_data.get("extra_metrics", [])
    )
    error_items = "".join(
        f"<li>{escape(str(item))}</li>" for item in report_data.get("error_list", [])
    )
    recommendation_items = "".join(
        f"<li>{escape(str(item))}</li>"
        for item in report_data.get("recommendations", [])
    )
    topic_html = _build_topic_intelligence_html_section(report_data.get("topic_intelligence"))

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(report_data["title"])}</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      color: #1f2937;
      font-size: 12px;
      margin: 28px;
    }}
    h1 {{
      font-size: 22px;
      margin-bottom: 6px;
    }}
    h2 {{
      font-size: 15px;
      margin: 24px 0 10px;
      color: #0f172a;
    }}
    .meta {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px 18px;
      margin: 18px 0;
      padding: 14px;
      border: 1px solid #dbe3ef;
      border-radius: 8px;
      background: #f8fafc;
    }}
    .summary {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
    }}
    .summary th,
    .summary td {{
      text-align: left;
      border: 1px solid #dbe3ef;
      padding: 8px;
      vertical-align: top;
    }}
    ul {{
      margin: 0;
      padding-left: 18px;
    }}
    li {{
      margin-bottom: 6px;
    }}
    .footer {{
      margin-top: 26px;
      font-size: 10px;
      color: #64748b;
    }}
    .topic-intelligence {{
      margin: 22px 0;
      padding: 18px;
      border-radius: 12px;
      background: linear-gradient(135deg, #0f172a, #1e293b);
      color: #fff;
    }}
    .topic-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 10px 18px;
      margin-top: 14px;
    }}
    .topic-metric {{
      padding: 10px 12px;
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.08);
    }}
    .topic-metric strong {{
      display: block;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: #a5f3fc;
      margin-bottom: 5px;
    }}
    .topic-insight {{
      margin-top: 14px;
      padding: 12px;
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.08);
    }}
  </style>
</head>
<body>
  <h1>{escape(report_data["title"])}</h1>
  <div class="meta">
    <div><strong>Website URL:</strong> {escape(str(report_data["website_url"]))}</div>
    <div><strong>Analysis Type:</strong> {escape(str(report_data["analysis_type"]))}</div>
    <div><strong>Date:</strong> {escape(str(report_data["date"]))}</div>
    <div><strong>Total Issues:</strong> {escape(str(report_data["total_issues"]))}</div>
    <div><strong>Working Links Count:</strong> {escape(str(report_data["working_links_count"]))}</div>
    <div><strong>Broken Links Count:</strong> {escape(str(report_data["broken_links_count"]))}</div>
    <div><strong>Redirect Links Count:</strong> {escape(str(report_data["redirect_links_count"]))}</div>
  </div>

  {topic_html}

  <h2>Executive Summary</h2>
  <table class="summary">
    <tbody>{metric_rows}</tbody>
  </table>

  <h2>Detailed Findings</h2>
  <ul>{error_items}</ul>

  <h2>Recommendations</h2>
  <ul>{recommendation_items}</ul>

  <div class="footer">Generated by OnWebApp SEO Intelligence Platform.</div>
</body>
</html>
"""


def _build_topic_intelligence_html_section(topic: dict | None) -> str:
    if not topic:
        return ""
    metrics = [
        ("Primary Keyword", topic.get("primary_keyword", "Not Measured")),
        ("Primary H1", topic.get("primary_h1", "H1 Missing")),
        ("Page Title", topic.get("page_title", "Title Missing")),
        ("Meta Title", topic.get("meta_title", "Title Missing")),
        ("Meta Description", topic.get("meta_description", "Meta Description Missing")),
        ("Detected Topic", topic.get("detected_topic", "Not Measured")),
        ("Search Intent", topic.get("search_intent", "Informational")),
        ("Content Category", topic.get("content_category", "Not Measured")),
        ("Topic Cluster", topic.get("topic_cluster", "Not Measured")),
        ("Top Keyword", topic.get("top_keyword", "Not Measured")),
        ("Secondary Keywords", ", ".join(topic.get("secondary_keywords", ["Not Measured"]))),
        ("Keyword Coverage", f"{topic.get('keyword_coverage_pct', 0)}%"),
        ("Semantic Relevance", f"{topic.get('semantic_relevance_pct', 0)}%"),
        ("Content Focus Score", f"{topic.get('content_focus_score', 0)}/100"),
        ("AI Visibility Potential", f"{topic.get('ai_visibility_potential', 0)}/100"),
    ]
    metric_html = "".join(
        f"<div class='topic-metric'><strong>{escape(label)}</strong>{escape(str(value))}</div>"
        for label, value in metrics
    )
    return (
        "<section class='topic-intelligence'>"
        "<h2 style='margin-top:0;color:#fff;'>Primary SEO Topic Intelligence</h2>"
        "<div class='topic-grid'>"
        f"{metric_html}"
        "</div>"
        f"<div class='topic-insight'><strong style='color:#c4b5fd;'>AI Insight</strong><br>{escape(topic.get('ai_insight', 'Not Measured'))}</div>"
        "</section>"
    )


def _build_website_banner(payload: dict, styles: dict[str, ParagraphStyle], dashboard: dict):
    content = Paragraph(
        "<font color='#06B6D4'>On</font><font color='#FFFFFF'>WebApp</font><br/>"
        f"<font size='9' color='#CFFAFE'>{escape(payload['platform_name'])}</font><br/>"
        f"<font size='24' color='#FFFFFF'><b>{escape(payload['title'])}</b></font><br/>"
        f"<font size='10' color='#CFFAFE'>Executive website intelligence audit for decision-makers and enterprise stakeholders.</font>",
        styles["title"],
    )
    right_panel = Table(
        [
            [Paragraph("Overall SEO Score", styles["dark_label"])],
            [Paragraph(f"{dashboard['health_score']}/100", styles["title"])],
            [Paragraph("AI Visibility Score", styles["dark_label"])],
            [Paragraph(f"{dashboard['ai_visibility_score']}/100", styles["body_emphasis"])],
        ],
        colWidths=[128],
    )
    right_panel.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex("#111827")),
                ("BOX", (0, 0), (-1, -1), 0.6, _rl_hex("#111827")),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    wrapper = Table([[content, right_panel]], colWidths=[349, 138])
    wrapper.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(_COLORS["navy"])),
                ("BOX", (0, 0), (-1, -1), 0.6, _rl_hex(_COLORS["navy"])),
                ("LEFTPADDING", (0, 0), (0, 0), 18),
                ("RIGHTPADDING", (0, 0), (0, 0), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 16),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return wrapper


def _build_website_cover_cards(payload: dict, styles: dict[str, ParagraphStyle], dashboard: dict):
    info_table = Table(
        [
            [
                _build_meta_card("Website URL", payload["website_url"], styles),
                _build_meta_card("Analysis Type", payload["analysis_type"], styles),
            ],
            [
                _build_meta_card("Generated", payload["date"], styles),
                _build_meta_card("Topic Intelligence", payload.get("topic_intelligence", {}).get("primary_keyword", "Not Measured"), styles),
            ],
        ],
        colWidths=[157.5, 157.5],
    )
    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(_COLORS["surface_alt"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("INNERGRID", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    kpis = Table(
        [
            [Paragraph("Website Health", styles["label"])],
            [Paragraph(escape(dashboard["website_health"]), styles["status"])],
            [Paragraph("Risk Level", styles["label"])],
            [_build_badge(dashboard["risk_level"], "priority", styles)],
            [Paragraph("Crawl Status", styles["label"])],
            [_build_badge(dashboard["crawl_status"], "status", styles, background=_crawl_health_palette(dashboard["crawl_status"])["bg"], text_color=_crawl_health_palette(dashboard["crawl_status"])["text"])],
        ],
        colWidths=[172],
    )
    kpis.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(_COLORS["surface"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    wrapper = Table([[info_table, kpis]], colWidths=[315, 172])
    wrapper.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return wrapper


def _build_website_topic_story(topic: dict | None, styles: dict[str, ParagraphStyle]) -> list:
    if not topic:
        return [_build_full_width_block("Topic Intelligence", "Not Measured", styles)]
    metrics = [
        ("Primary Keyword", topic.get("primary_keyword", "Not Measured")),
        ("Search Intent", topic.get("search_intent", "Informational")),
        ("Topic Cluster", topic.get("topic_cluster", "Not Measured")),
        ("AI Visibility Potential", f"{topic.get('ai_visibility_potential', 0)}/100"),
        ("Category", topic.get("content_category", "Not Measured")),
        ("Keyword Coverage", f"{topic.get('keyword_coverage_pct', 0)}%"),
    ]
    messaging = (
        f"<font color='{_COLORS['muted']}'><b>Primary H1</b></font><br/>{_paragraph_text(topic.get('primary_h1', 'H1 Missing'))}"
        f"<br/><br/><font color='{_COLORS['muted']}'><b>Page Title</b></font><br/>{_paragraph_text(topic.get('page_title', 'Title Missing'))}"
        f"<br/><br/><font color='{_COLORS['muted']}'><b>Meta Description</b></font><br/>{_paragraph_text(topic.get('meta_description', 'Meta Description Missing'))}"
        f"<br/><br/><font color='{_COLORS['cyan']}'><b>AI Insight</b></font><br/>{_paragraph_text(topic.get('ai_insight', 'Not Measured'))}"
    )
    message_table = Table([[Paragraph(messaging, styles["micro"])]], colWidths=[487])
    message_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(_COLORS["white"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return [
        _build_metric_pairs_table(metrics, styles),
        Spacer(1, 8),
        message_table,
    ]


def _build_website_issue_rows(payload: dict) -> list[dict]:
    rows = []
    for item in payload.get("error_list", []):
        severity, issue, description = _parse_website_issue(item)
        rows.append(
            {
                "severity": severity,
                "issue": issue,
                "description": description,
                "category": _categorize_website_issue(issue, description),
                "seo_impact": _website_issue_impact(issue, description),
                "recommended_action": _website_issue_fix(issue, description, payload.get("recommendations", [])),
            }
        )
    if not rows:
        rows.append(
            {
                "severity": "Low",
                "issue": "No critical SEO blockers detected",
                "description": "The current audit payload does not include actionable issue strings.",
                "category": "Technical SEO",
                "seo_impact": "Low risk. Core SEO signals appear stable in the current audit snapshot.",
                "recommended_action": "Maintain monitoring cadence and preserve current implementation quality.",
            }
        )
    return rows[:18]


def _parse_website_issue(item: str) -> tuple[str, str, str]:
    raw = str(item or "").strip()
    if ":" in raw:
        severity_part, remainder = raw.split(":", 1)
        severity = severity_part.strip().title()
    else:
        severity = "Medium"
        remainder = raw
    if " - " in remainder:
        issue, description = remainder.split(" - ", 1)
    else:
        issue, description = remainder, remainder
    if severity not in {"Critical", "High", "Medium", "Low"}:
        severity = "Medium"
    return severity, issue.strip() or "SEO Issue", description.strip() or "No description provided."


def _categorize_website_issue(issue: str, description: str) -> str:
    combined = f"{issue} {description}".lower()
    if any(token in combined for token in ["canonical", "robots", "index", "crawl", "ssl", "https"]):
        return "Technical SEO"
    if any(token in combined for token in ["title", "meta", "description", "heading", "h1", "h2", "content"]):
        return "On-Page SEO"
    if any(token in combined for token in ["performance", "speed", "response", "core web vitals", "latency"]):
        return "Performance"
    if any(token in combined for token in ["internal link", "orphan", "discover", "sitemap"]):
        return "Discovery"
    return "Technical SEO"


def _website_issue_impact(issue: str, description: str) -> str:
    combined = f"{issue} {description}".lower()
    if "canonical" in combined:
        return "Canonical inconsistencies can split ranking signals across duplicate or competing URLs."
    if "title" in combined or "meta" in combined:
        return "Metadata gaps reduce click-through appeal and weaken topical relevance signals."
    if "heading" in combined or "h1" in combined:
        return "Heading inconsistency weakens topical clarity for both users and search engines."
    if "robots" in combined or "index" in combined:
        return "Indexability issues directly affect crawl efficiency and search visibility."
    if "internal link" in combined or "orphan" in combined:
        return "Internal linking gaps reduce discovery, equity flow, and conversion path efficiency."
    if "performance" in combined or "speed" in combined:
        return "Performance friction can reduce engagement, crawl depth, and conversion quality."
    return "The issue weakens technical consistency and limits sustainable SEO performance."


def _website_issue_fix(issue: str, description: str, recommendations: list[str]) -> str:
    combined = f"{issue} {description}".lower()
    for recommendation in recommendations:
        rec_lower = recommendation.lower()
        if any(token in rec_lower for token in combined.split()):
            return recommendation
    if "canonical" in combined:
        return "Implement consistent canonical targets on affected pages and verify self-referencing canonical logic."
    if "title" in combined:
        return "Rewrite page titles to improve uniqueness, relevance, and target keyword alignment."
    if "meta" in combined:
        return "Refine meta descriptions to better reflect page intent and improve SERP click appeal."
    if "heading" in combined or "h1" in combined:
        return "Normalize heading hierarchy so each key page has a clear primary heading and logical section structure."
    if "robots" in combined or "index" in combined:
        return "Review crawl directives and ensure high-value pages remain indexable and accessible."
    if "internal link" in combined or "orphan" in combined:
        return "Strengthen internal linking from authoritative pages to improve crawl depth and discoverability."
    if "performance" in combined or "speed" in combined:
        return "Prioritize page speed optimization on templates that most influence crawl efficiency and user engagement."
    return "Address the issue in the next SEO implementation sprint and validate the fix in a follow-up crawl."


def _build_website_category_rows(issue_rows: list[dict], recommendations: list[str]) -> list[dict]:
    categories = ["Technical SEO", "On-Page SEO", "Performance", "Discovery"]
    rows = []
    for category in categories:
        bucket = [row for row in issue_rows if row["category"] == category]
        if not bucket:
            rows.append(
                {
                    "category": category,
                    "issue_count": 0,
                    "severity": "Low",
                    "seo_impact": "No significant issue cluster surfaced in the current payload.",
                    "recommended_fix": "Maintain current controls and continue monitoring.",
                    "progress": 0,
                }
            )
            continue
        dominant = max(bucket, key=lambda row: _priority_weight(row["severity"]))
        rows.append(
            {
                "category": category,
                "issue_count": len(bucket),
                "severity": dominant["severity"],
                "seo_impact": dominant["seo_impact"],
                "recommended_fix": dominant["recommended_action"] if dominant["recommended_action"] else (recommendations[0] if recommendations else "Maintain current controls."),
                "progress": _severity_progress_from_issue_rows(bucket),
            }
        )
    return rows


def _build_website_priorities(recommendations: list[str], issue_rows: list[dict]) -> list[dict]:
    rows = []
    for issue in issue_rows[:5]:
        rows.append(
            {
                "priority": issue["severity"],
                "action": issue["recommended_action"],
            }
        )
    for recommendation in recommendations:
        if len(rows) >= 5:
            break
        rows.append({"priority": _recommendation_priority(recommendation), "action": recommendation})
    return rows[:5]


def _build_website_ai_sections(
    *,
    payload: dict,
    issue_rows: list[dict],
    category_rows: list[dict],
    health_score: float,
    technical_score: float,
    on_page_score: float,
    performance_score: float,
    discovery_score: float,
    ai_visibility: int,
    website_health: str,
    risk_level: str,
    crawl_status: str,
    ranking_potential: str,
    business_impact: str,
    estimated_difficulty: str,
) -> dict:
    dominant_category = max(category_rows, key=lambda row: row["issue_count"])
    strongest_metric = max(
        [
            ("technical execution", technical_score),
            ("on-page consistency", on_page_score),
            ("performance delivery", performance_score),
            ("discovery posture", discovery_score),
        ],
        key=lambda item: item[1],
    )[0]
    weakest_metric = min(
        [
            ("technical execution", technical_score),
            ("on-page consistency", on_page_score),
            ("performance delivery", performance_score),
            ("discovery posture", discovery_score),
        ],
        key=lambda item: item[1],
    )[0]
    executive_summary = (
        f"The website currently presents {website_health.lower()} overall SEO health with a {round(health_score)}/100 health score and {ranking_potential.lower()} ranking potential. "
        f"The strongest signal comes from {strongest_metric}, while the main weakness is {weakest_metric}. "
        f"The most concentrated issue cluster sits in {dominant_category['category'].lower()}, creating {risk_level.lower()} execution risk and a {crawl_status.lower()} crawl profile."
    )
    strengths = (
        f"The current audit indicates the strongest stability in {strongest_metric}, and AI visibility is measured at {ai_visibility}/100. "
        f"This suggests the site already has a credible baseline for organic growth if consistency is preserved."
    )
    weaknesses = (
        f"The largest weakness sits in {weakest_metric}, with {dominant_category['issue_count']} issues concentrated in {dominant_category['category']}. "
        f"That pattern reduces confidence in sustained ranking performance."
    )
    missed_opportunities = (
        f"The strongest improvement opportunity lies in {dominant_category['category'].lower()} remediation, where fixing the dominant issue group can unlock stronger discoverability and SERP presentation quality."
    )
    business_risks = (
        f"Current SEO risk is {risk_level.lower()}, which means unresolved implementation gaps may limit qualified traffic growth and reduce user trust on high-value landing pages."
    )
    expected_gains = (
        f"Improving {weakest_metric} and resolving the highest-priority issue cluster should increase crawl consistency, metadata quality, and ranking readiness over the next audit cycle."
    )
    ranking_potential_text = (
        f"Current technical health indicates {ranking_potential.lower()} ranking potential, with the next uplift most likely to come from stronger metadata and structural consistency."
    )
    traffic_potential = (
        f"Traffic potential is currently constrained less by crawl failure and more by uneven optimization quality, especially across {dominant_category['category'].lower()} signals."
    )
    ai_recommendations = (
        f"Prioritize the {dominant_category['category'].lower()} backlog first, protect the strongest area of {strongest_metric}, and use follow-up audits to confirm that fixes improve the weakest signal cluster."
    )
    ai_outlook = (
        f"If the current medium-priority backlog is resolved with {estimated_difficulty.lower()} implementation effort, the website should improve from {website_health.lower()} health toward stronger ranking readiness. "
        f"Business impact is assessed as {business_impact.lower()} because better metadata and structural consistency can lift both search visibility and conversion confidence."
    )
    technical_interpretation = (
        f"The website demonstrates {crawl_status.lower()} crawl accessibility but shows concentration of issues in {dominant_category['category'].lower()}. "
        f"This suggests the architecture is serviceable, but implementation consistency should be improved to strengthen technical reliability."
    )
    priority_matrix = (
        f"Highest-value action: fix {dominant_category['category'].lower()} issues first. "
        f"Business impact is greatest where remediation improves both crawl quality and search snippet quality."
    )
    return {
        "executive_summary": executive_summary,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "missed_opportunities": missed_opportunities,
        "business_risks": business_risks,
        "expected_gains": expected_gains,
        "ranking_potential": ranking_potential_text,
        "traffic_potential": traffic_potential,
        "ai_recommendations": ai_recommendations,
        "ai_outlook": ai_outlook,
        "technical_interpretation": technical_interpretation,
        "priority_matrix": priority_matrix,
    }


def _group_website_actions(top_priorities: list[dict]) -> dict[str, list[str]]:
    quick = [row["action"] for row in top_priorities if row["priority"] in {"Critical", "High"}]
    medium = [row["action"] for row in top_priorities if row["priority"] == "Medium"]
    long_term = [row["action"] for row in top_priorities if row["priority"] == "Low"]
    if not quick:
        quick.append("Address the most visible technical inconsistencies first to stabilize the SEO baseline.")
    if not medium:
        medium.append("Consolidate remaining metadata and structural issues in the next optimization sprint.")
    if not long_term:
        long_term.append("Use recurring audits to preserve gains and prevent issue re-accumulation.")
    return {
        "quick_wins": quick[:3],
        "medium_term": medium[:3],
        "long_term": long_term[:3],
    }


def _build_website_roadmap_rows(groups: dict[str, list[str]], ai_sections: dict[str, str]) -> list[dict]:
    return [
        {
            "phase": "Now",
            "focus": groups["quick_wins"][0],
            "outcome": "Improves immediate technical trust and reduces the highest SEO execution risk.",
            "background": _COLORS["critical_bg"],
            "text_color": _COLORS["critical"],
        },
        {
            "phase": "Next",
            "focus": groups["medium_term"][0],
            "outcome": "Improves structural consistency across templates and key landing pages.",
            "background": "#FEF3C7",
            "text_color": "#A16207",
        },
        {
            "phase": "Later",
            "focus": groups["long_term"][0],
            "outcome": ai_sections["expected_gains"],
            "background": "#EDE9FE",
            "text_color": _COLORS["purple"],
        },
    ]


def _build_website_timeline_rows(groups: dict[str, list[str]]) -> list[dict]:
    return [
        {"window": "0-7 Days", "title": "Fix Highest-Risk Issues", "detail": groups["quick_wins"][0], "background": _COLORS["critical_bg"]},
        {"window": "30 Days", "title": "Improve Template Consistency", "detail": groups["quick_wins"][-1], "background": "#FEF3C7"},
        {"window": "60 Days", "title": "Strengthen Metadata Quality", "detail": groups["medium_term"][0], "background": "#E0F2FE"},
        {"window": "90+ Days", "title": "Scale Audit Governance", "detail": groups["long_term"][0], "background": "#EDE9FE"},
    ]


def _build_website_appendix_rows(payload: dict, issue_rows: list[dict], category_rows: list[dict]) -> list[list[str]]:
    topic = payload.get("topic_intelligence") or {}
    rows = [
        ["Primary URL", payload["website_url"]],
        ["Analysis Type", payload["analysis_type"]],
        ["Generated", payload["date"]],
        ["Primary Keyword", topic.get("primary_keyword", "Not Measured")],
        ["Page Title", topic.get("page_title", "Title Missing")],
        ["Meta Title", topic.get("meta_title", "Title Missing")],
        ["Meta Description", topic.get("meta_description", "Meta Description Missing")],
        ["Primary H1", topic.get("primary_h1", "H1 Missing")],
        ["Top Keyword", topic.get("top_keyword", "Not Measured")],
        ["Secondary Keywords", ", ".join(topic.get("secondary_keywords", ["Not Measured"]))],
    ]
    for row in category_rows:
        rows.append([f"{row['category']} Summary", f"{row['issue_count']} issue(s) | {row['severity']} severity | {row['recommended_fix']}"])
    for issue in issue_rows[:6]:
        rows.append([f"Issue Reference: {issue['issue']}", issue["description"]])
    return rows


def _build_category_dashboard_table(rows: list[dict], styles: dict[str, ParagraphStyle]):
    data = [
        [
            Paragraph("Category", styles["table_header"]),
            Paragraph("Issue Count", styles["table_header"]),
            Paragraph("Severity", styles["table_header"]),
            Paragraph("SEO Impact", styles["table_header"]),
            Paragraph("Recommended Fix", styles["table_header"]),
        ]
    ]
    for row in rows:
        data.append(
            [
                Paragraph(escape(row["category"]), styles["table_cell"]),
                Paragraph(str(row["issue_count"]), styles["table_cell"]),
                _build_badge(row["severity"], "severity", styles),
                Paragraph(_paragraph_text(row["seo_impact"]), styles["table_cell"]),
                Paragraph(_paragraph_text(row["recommended_fix"]), styles["table_cell"]),
            ]
        )
    table = Table(data, colWidths=[96, 54, 64, 138, 135], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _rl_hex(_COLORS["navy"])),
                ("TEXTCOLOR", (0, 0), (-1, 0), _rl_hex(_COLORS["white"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("INNERGRID", (0, 0), (-1, -1), 0.6, _rl_hex(_COLORS["border"])),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_rl_hex(_COLORS["white"]), _rl_hex(_COLORS["surface"])]),
            ]
        )
    )
    return table


def _build_website_business_summary_table(dashboard: dict, styles: dict[str, ParagraphStyle]):
    cards = [
        _build_signal_card(
            label="Website Health",
            value=dashboard["website_health"],
            detail=f"Overall SEO health is {dashboard['website_health'].lower()} with a {dashboard['health_score']}/100 score.",
            background=_impact_palette("Low" if dashboard["website_health"] in {"Strong", "Stable"} else "Medium")["bg"],
            text_color=_impact_palette("Low" if dashboard["website_health"] in {"Strong", "Stable"} else "Medium")["text"],
            styles=styles,
        ),
        _build_signal_card(
            label="SEO Risk",
            value=dashboard["risk_level"],
            detail=f"The current issue mix places the audit in the {dashboard['risk_level'].lower()} risk band.",
            background=_risk_level_palette(dashboard["risk_level"])["bg"],
            text_color=_risk_level_palette(dashboard["risk_level"])["text"],
            styles=styles,
        ),
        _build_signal_card(
            label="Crawl Quality",
            value=dashboard["crawl_status"],
            detail=f"Crawl quality is {dashboard['crawl_status'].lower()} based on link cleanliness and score stability.",
            background=_crawl_health_palette(dashboard["crawl_status"])["bg"],
            text_color=_crawl_health_palette(dashboard["crawl_status"])["text"],
            styles=styles,
        ),
        _build_signal_card(
            label="Ranking Potential",
            value=dashboard["ranking_potential"],
            detail=f"Current technical health indicates {dashboard['ranking_potential'].lower()} ranking potential.",
            background=_impact_palette(dashboard["ranking_potential"])["bg"],
            text_color=_impact_palette(dashboard["ranking_potential"])["text"],
            styles=styles,
        ),
    ]
    table = Table([[cards[0], cards[1]], [cards[2], cards[3]]], colWidths=[243.5, 243.5])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _build_website_findings_table(issue_rows: list[dict], website_url: str, styles: dict[str, ParagraphStyle]):
    data = [
        [
            Paragraph("Severity", styles["table_header"]),
            Paragraph("Issue", styles["table_header"]),
            Paragraph("Affected URL", styles["table_header"]),
            Paragraph("SEO Impact", styles["table_header"]),
            Paragraph("Recommended Action", styles["table_header"]),
        ]
    ]
    row_styles = []
    for idx, row in enumerate(issue_rows, start=1):
        data.append(
            [
                _build_badge(row["severity"], "severity", styles),
                Paragraph(_paragraph_text(row["issue"]), styles["table_cell"]),
                Paragraph(_paragraph_text(website_url, url_safe=True), styles["table_cell"]),
                Paragraph(_paragraph_text(row["seo_impact"]), styles["table_cell"]),
                Paragraph(_paragraph_text(row["recommended_action"]), styles["table_cell"]),
            ]
        )
        palette = _badge_palette(row["severity"], "severity")
        row_styles.append(("BACKGROUND", (0, idx), (-1, idx), _rl_hex(palette["bg"])))
    table = Table(data, colWidths=[62, 106, 112, 107, 100], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _rl_hex(_COLORS["navy"])),
                ("TEXTCOLOR", (0, 0), (-1, 0), _rl_hex(_COLORS["white"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("INNERGRID", (0, 0), (-1, -1), 0.6, _rl_hex(_COLORS["border"])),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ] + row_styles
        )
    )
    return table


def _build_website_execution_summary_table(dashboard: dict, styles: dict[str, ParagraphStyle]):
    cards = [
        _build_signal_card(
            label="Business Impact",
            value=dashboard["business_impact"],
            detail=f"Expected business impact is {dashboard['business_impact'].lower()} if the roadmap is executed in priority order.",
            background=_impact_palette(dashboard["business_impact"])["bg"],
            text_color=_impact_palette(dashboard["business_impact"])["text"],
            styles=styles,
        ),
        _build_signal_card(
            label="Estimated Difficulty",
            value=dashboard["estimated_difficulty"],
            detail=f"Implementation difficulty is {dashboard['estimated_difficulty'].lower()} based on the current issue mix and remediation breadth.",
            background=_impact_palette(dashboard["estimated_difficulty"])["bg"],
            text_color=_impact_palette(dashboard["estimated_difficulty"])["text"],
            styles=styles,
        ),
    ]
    table = Table([[cards[0], cards[1]]], colWidths=[243.5, 243.5])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _build_insight_card(title: str, body: str, background: str, styles: dict[str, ParagraphStyle]):
    table = Table(
        [
            [Paragraph(escape(title), styles["body_emphasis"])],
            [Paragraph(_paragraph_text(body), styles["small"])],
        ],
        colWidths=[233.5],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(background)),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def _website_status_label(score: float) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Good"
    if score >= 55:
        return "Needs Improvement"
    return "Critical"


def _website_health_label(score: float) -> str:
    if score >= 85:
        return "Strong"
    if score >= 70:
        return "Stable"
    if score >= 55:
        return "Moderate"
    return "Fragile"


def _website_risk_level(*, health_score: float, total_issues: int, severity_counts: dict[str, int]) -> str:
    if health_score < 55 or severity_counts.get("Critical"):
        return "Critical"
    if total_issues >= 6 or severity_counts.get("High"):
        return "High"
    if total_issues >= 3:
        return "Medium"
    return "Low"


def _website_crawl_status(*, health_score: float, working_links: int | None, broken_links: int | None, redirects: int | None) -> str:
    if health_score >= 85 and (broken_links or 0) == 0:
        return "Excellent"
    if health_score >= 70:
        return "Healthy"
    if (redirects or 0) > 0 or (broken_links or 0) > 0:
        return "Watchlist"
    return "At Risk"


def _ranking_potential_label(*, health_score: float, on_page_score: float, discovery_score: float, ai_visibility: int) -> str:
    weighted = (health_score + on_page_score + discovery_score + ai_visibility) / 4
    if weighted >= 85:
        return "High"
    if weighted >= 65:
        return "Medium"
    return "Low"


def _website_business_impact(risk_level: str, ranking_potential: str, total_issues: int) -> str:
    if risk_level == "Critical" or ranking_potential == "High":
        return "High"
    if total_issues >= 3:
        return "Medium"
    return "Low"


def _website_estimated_difficulty(issue_rows: list[dict], total_issues: int) -> str:
    if any(row["severity"] == "Critical" for row in issue_rows) or total_issues >= 8:
        return "High"
    if total_issues >= 3:
        return "Medium"
    return "Low"


def _severity_progress_from_issue_rows(issue_rows: list[dict]) -> int:
    return _severity_breakdown_progress(_build_severity_breakdown(issue_rows))


def _category_progress(issue_rows: list[dict], category: str) -> int:
    bucket = [row for row in issue_rows if row["category"] == category]
    if not bucket:
        return 0
    return _severity_progress_from_issue_rows(bucket)


def _score_color(value: int) -> str:
    return _health_score_color(value)


def _score_background(value: int) -> str:
    if value >= 85:
        return _COLORS["success_bg"]
    if value >= 60:
        return "#FEF3C7"
    return _COLORS["critical_bg"]


def _prepare_link_pdf_payload(report_data: dict) -> dict:
    summary = report_data.get("summary", {})
    health = None
    if report_data.get("analysis_type") == "internal":
        health = report_data.get("health") or build_internal_link_health(summary)
    status_label = (health or {}).get("label") or report_data.get("status_badge", {}).get("label", "Needs Improvement")
    analysis_type = report_data.get("analysis_type_label", "Link Checker")
    metrics_available = report_data.get("metrics_available", True)
    provider_required = report_data.get("provider_required", False)
    error_rows = _build_error_rows(report_data)
    findings_rows = _build_findings_rows(report_data, error_rows)
    recommendations = _build_recommendation_rows(report_data)
    impact_summary = _build_impact_summary(report_data, findings_rows)
    external_insights = report_data.get("external_insights") or {}

    def metric_value(key):
        raw = summary.get(key)
        if provider_required and not metrics_available:
            return "Provider Required"
        if metrics_available and isinstance(raw, int):
            return str(raw)
        return str(_metric_or_not_measured(raw))

    executive_cards = [
        _build_summary_card("Total Links", metric_value("total_links"), _COLORS["navy"], "#E2E8F0"),
        _build_summary_card("Working Links", metric_value("working_links_count"), _COLORS["cyan"], "#ECFEFF"),
        _build_summary_card("Broken Links", metric_value("broken_links_count"), _COLORS["critical"], _COLORS["critical_bg"]),
        _build_summary_card("Redirect Links", metric_value("redirect_links_count"), _COLORS["purple"], "#F3E8FF"),
        _build_summary_card("Error Links", metric_value("error_links_count"), _COLORS["amber"], _COLORS["amber_bg"]),
        _build_summary_card("Status", status_label, _status_palette(status_label)["text"], _status_palette(status_label)["bg"]),
    ]

    external_section = None
    if report_data.get("analysis_type") == "external":
        overview = external_insights.get("overview_metrics", {})
        security = external_insights.get("security_analysis", {})
        quality = external_insights.get("quality_section", {})
        domain_distribution = external_insights.get("domain_distribution") or []
        external_section = {
            "summary_cards": [
                ("Total External Links", metric_value("total_links")),
                ("Unique Domains", _metric_or_not_measured(overview.get("unique_external_domains"))),
                ("HTTPS Links", _metric_or_not_measured(security.get("https_external_links"))),
                ("HTTP Links", _metric_or_not_measured(security.get("http_external_links"))),
                ("Redirecting Links", metric_value("redirect_links_count")),
                ("Broken Links", metric_value("broken_links_count")),
            ],
            "domain_distribution": [
                {
                    "domain": row.get("domain", "-"),
                    "link_count": str(_metric_or_not_measured(row.get("link_count"))),
                    "status": row.get("status", "Not Measured"),
                }
                for row in domain_distribution[:10]
            ],
            "quality_metrics": [
                ("Domain Diversity Score", quality.get("domain_diversity", "Not Measured")),
                ("Trust Distribution", quality.get("authority_available", "Not Measured")),
                ("Reference Quality", quality.get("link_distribution", "Not Measured")),
            ],
        }

    return {
        "brand_name": "OnWebApp",
        "platform_name": "OnWebApp SEO Intelligence Platform",
        "title": "Link Checker Report",
        "website_url": report_data.get("url", "-"),
        "analysis_type": analysis_type,
        "date": _format_iso_datetime(report_data.get("analyzed_at")),
        "status_label": status_label,
        "status_palette": _status_palette(status_label),
        "health": health,
        "final_url": report_data.get("final_url", report_data.get("url", "-")),
        "executive_cards": executive_cards,
        "impact_summary": impact_summary,
        "external_section": external_section,
        "findings_rows": findings_rows,
        "error_rows": error_rows,
        "recommendation_rows": recommendations,
        "topic_intelligence": report_data.get("topic_intelligence")
        or build_topic_intelligence(
            url=report_data.get("final_url") or report_data.get("url", "-"),
            page_title=report_data.get("analysis_type_label", "Link Checker"),
            meta_title=report_data.get("analysis_type_label", "Link Checker"),
            meta_description=report_data.get("message", ""),
            h1=report_data.get("analysis_type_label", "Link Checker"),
        ),
    }


def _build_summary_card(label: str, value: str, accent: str, background: str) -> dict:
    return {
        "label": label,
        "value": str(value),
        "accent": accent,
        "background": background,
    }


def _build_error_rows(report_data: dict) -> list[dict]:
    rows = []
    for row in (report_data.get("error_links") or [])[:20]:
        link_url = row.get("link_url") or row.get("source_url") or row.get("target_url") or "-"
        error_type = row.get("status_label") or row.get("error_type") or "Issue"
        explanation = row.get("status_detail") or report_data.get("message") or "No detail provided."
        rows.append(
            {
                "link_url": link_url,
                "error_type": error_type,
                "explanation": explanation,
                "impact": _build_error_impact(error_type, report_data.get("analysis_type")),
                "recommended_fix": _build_error_fix(error_type, explanation, report_data.get("analysis_type")),
            }
        )

    for detail in (report_data.get("unavailable_details") or [])[:10]:
        rows.append(
            {
                "link_url": "Provider Data",
                "error_type": report_data.get("error_type") or "Unavailable",
                "explanation": detail,
                "impact": "Backlink authority intelligence cannot be measured until a provider is connected.",
                "recommended_fix": "Connect a supported backlink provider and rerun the report.",
            }
        )

    if not rows:
        rows.append(
            {
                "link_url": "-",
                "error_type": "No Errors",
                "explanation": "No error links were detected in this report.",
                "impact": "Current link findings present low operational risk.",
                "recommended_fix": "Continue monitoring link health on a regular cadence.",
            }
        )
    return rows


def _build_findings_rows(report_data: dict, error_rows: list[dict]) -> list[dict]:
    if report_data.get("analysis_type") == "internal" and report_data.get("findings"):
        return [
            {
                "issue": row.get("issue", "Internal Link Finding"),
                "severity": row.get("severity", "Medium"),
                "description": row.get("description") or row.get("seo_impact") or row.get("business_impact") or "No detail provided.",
                "seo_impact": row.get("seo_impact", "No SEO impact provided."),
                "recommended_fix": row.get("recommended_fix", "No recommended fix provided."),
            }
            for row in (report_data.get("findings") or [])[:12]
        ]
    findings = []
    for row in error_rows[:12]:
        findings.append(
            {
                "issue": row["error_type"],
                "severity": _severity_from_error(row["error_type"], row["explanation"]),
                "description": row["explanation"],
                "seo_impact": row["impact"],
                "recommended_fix": row["recommended_fix"],
            }
        )

    if report_data.get("analysis_type") == "external":
        insights = report_data.get("external_insights") or {}
        security = insights.get("security_analysis") or {}
        quality = insights.get("quality_section") or {}
        http_links = security.get("http_external_links")
        if isinstance(http_links, int) and http_links > 0:
            findings.append(
                {
                    "issue": "HTTP External Destinations",
                    "severity": "High" if http_links >= 3 else "Medium",
                    "description": f"{http_links} external links use HTTP instead of HTTPS.",
                    "seo_impact": "Unsecured outbound destinations weaken trust signals and can reduce user confidence.",
                    "recommended_fix": "Replace HTTP external links with HTTPS destinations wherever available.",
                }
            )
        if quality.get("domain_diversity") == "Low":
            findings.append(
                {
                    "issue": "Low Domain Diversity",
                    "severity": "Medium",
                    "description": "Outbound references are concentrated across too few external domains.",
                    "seo_impact": "Limited diversity reduces the strength and breadth of external trust signals.",
                    "recommended_fix": "Diversify outbound references across more authoritative and relevant domains.",
                }
            )

    if not findings:
        findings.append(
            {
                "issue": "Healthy Link Profile",
                "severity": "Low",
                "description": "The analyzed link set does not currently show actionable issues.",
                "seo_impact": "Low risk. Current linking signals support crawlability and stable navigation.",
                "recommended_fix": "Maintain monitoring cadence and preserve current link governance standards.",
            }
        )
    return findings[:12]


def _build_impact_summary(report_data: dict, findings_rows: list[dict]) -> dict:
    status_label = (
        (report_data.get("health") or {}).get("label")
        or report_data.get("status_badge", {}).get("label", "Needs Improvement")
    )
    provider_required = report_data.get("provider_required", False)
    summary = report_data.get("summary", {})
    broken = int(summary.get("broken_links_count") or 0)
    redirects = int(summary.get("redirect_links_count") or 0)
    errors = int(summary.get("error_links_count") or 0)
    weighted_score = (broken * 4) + (errors * 4) + (redirects * 2)
    severities = [row["severity"] for row in findings_rows]

    if provider_required:
        return {"seo_impact": "Medium", "business_impact": "High", "priority_level": "High"}
    if status_label == "Critical" or "Critical" in severities or weighted_score >= 12:
        return {"seo_impact": "High", "business_impact": "High", "priority_level": "Critical"}
    if status_label == "Needs Improvement" or "High" in severities or weighted_score >= 5:
        return {"seo_impact": "Medium", "business_impact": "Medium", "priority_level": "High"}
    if status_label == "Good":
        return {"seo_impact": "Low", "business_impact": "Medium", "priority_level": "Medium"}
    return {"seo_impact": "Low", "business_impact": "Low", "priority_level": "Low"}


def _build_error_fix(error_type: str, explanation: str, analysis_type: str | None) -> str:
    error_text = f"{error_type} {explanation}".lower()
    if "redirect" in error_text:
        return "Replace the redirected URL with its final destination to improve crawl efficiency."
    if "broken" in error_text or "404" in error_text or "410" in error_text:
        return "Update or remove the broken URL so users and crawlers reach a valid destination."
    if "timeout" in error_text or "connection" in error_text or "dns" in error_text:
        return "Retry the destination, verify server availability, and confirm the URL is still valid."
    if analysis_type == "backlinks":
        return "Validate provider coverage and reconnect the provider if authority data is unavailable."
    return "Review the destination and apply the fix recommended by the analysis details."


def _build_error_impact(error_type: str, analysis_type: str | None) -> str:
    error_text = (error_type or "").lower()
    if "timeout" in error_text or "connection" in error_text or "dns" in error_text:
        return "Users and crawlers may not access the referenced resource."
    if "redirect" in error_text:
        return "Redirect chains dilute crawl efficiency and add unnecessary latency."
    if "broken" in error_text or "404" in error_text or "410" in error_text:
        return "Broken references interrupt navigation and reduce link equity flow."
    if analysis_type == "backlinks":
        return "Backlink intelligence remains incomplete until a provider supplies authority data."
    return "The issue reduces the reliability and quality of the analyzed link profile."


def _severity_from_error(error_type: str, explanation: str) -> str:
    combined = f"{error_type} {explanation}".lower()
    if "provider required" in combined:
        return "High"
    if any(token in combined for token in ["dns", "timeout", "connection", "ssl"]):
        return "Critical"
    if any(token in combined for token in ["broken", "404", "410"]):
        return "High"
    if "redirect" in combined:
        return "Medium"
    if "no errors" in combined:
        return "Low"
    return "Medium"


def _build_recommendation_rows(report_data: dict) -> list[dict]:
    recommendations = report_data.get("recommendations") or ["No recommendations were generated."]
    rows = []
    for recommendation in recommendations[:10]:
        if isinstance(recommendation, dict):
            action = recommendation.get("text", "No recommendation text provided.")
            rows.append(
                {
                    "priority": recommendation.get("priority", "Low"),
                    "action": action,
                    "seo_impact": recommendation.get("estimated_gain")
                    or _recommendation_seo_impact(action, report_data.get("analysis_type")),
                    "business_impact": recommendation.get("business_impact")
                    or _recommendation_business_impact(action),
                }
            )
            continue
        priority = _recommendation_priority(recommendation)
        rows.append(
            {
                "priority": priority,
                "action": recommendation,
                "seo_impact": _recommendation_seo_impact(recommendation, report_data.get("analysis_type")),
                "business_impact": _recommendation_business_impact(recommendation),
            }
        )
    return rows


def _recommendation_priority(recommendation: str) -> str:
    value = recommendation.lower()
    if any(token in value for token in ["immediately", "critical", "urgent"]):
        return "Critical"
    if any(token in value for token in ["provider", "broken", "fix ", "remove ", "recover "]):
        return "High"
    if any(token in value for token in ["redirect", "diversify", "review ", "replace "]):
        return "Medium"
    return "Low"


def _recommendation_seo_impact(recommendation: str, analysis_type: str | None) -> str:
    value = recommendation.lower()
    if "provider" in value:
        return "Enables authority metrics that cannot be measured through crawling alone."
    if "broken" in value:
        return "Restores crawlability, preserves link equity, and reduces dead-end paths."
    if "redirect" in value:
        return "Improves crawl efficiency and reduces unnecessary redirect hops."
    if "diversify" in value:
        return "Improves external trust signals and broadens topical source coverage."
    if analysis_type == "external":
        return "Strengthens outbound quality signals and reduces external link risk."
    return "Supports sustained internal link health and search engine discoverability."


def _recommendation_business_impact(recommendation: str) -> str:
    value = recommendation.lower()
    if "provider" in value:
        return "Improves strategic decision-making with complete backlink intelligence."
    if "broken" in value:
        return "Protects user journeys, reduces frustration, and preserves conversion paths."
    if "redirect" in value:
        return "Reduces latency and improves user experience on high-value pages."
    if "diversify" in value:
        return "Improves brand trust by distributing references across safer sources."
    return "Improves reporting quality and lowers the risk of unnoticed link regressions."


def _status_palette(label: str) -> dict:
    mapping = {
        "Excellent": {"bg": _COLORS["success_bg"], "text": _COLORS["success"]},
        "Good": {"bg": _COLORS["info_bg"], "text": _COLORS["info"]},
        "Needs Attention": {"bg": _COLORS["warning_bg"], "text": _COLORS["warning"]},
        "Needs Improvement": {"bg": _COLORS["warning_bg"], "text": _COLORS["warning"]},
        "Critical": {"bg": _COLORS["critical_bg"], "text": _COLORS["critical"]},
        "Provider Required": {"bg": _COLORS["amber_bg"], "text": _COLORS["amber"]},
    }
    return mapping.get(label, {"bg": _COLORS["surface"], "text": _COLORS["navy"]})


def _build_link_checker_html_report(payload: dict) -> str:
    topic_html = _build_topic_intelligence_html_section(payload.get("topic_intelligence"))
    summary_cards = "".join(
        f"""
        <div class="metric-card" style="background:{card['background']}; border-top:4px solid {card['accent']};">
          <div class="metric-label">{escape(card['label'])}</div>
          <div class="metric-value" style="color:{card['accent']};">{escape(card['value'])}</div>
        </div>
        """
        for card in payload["executive_cards"]
    )
    impact_cards = "".join(
        f"""
        <div class="impact-card">
          <div class="impact-label">{escape(label)}</div>
          <div class="impact-value">{escape(value)}</div>
        </div>
        """
        for label, value in [
            ("SEO Impact", payload["impact_summary"]["seo_impact"]),
            ("Business Impact", payload["impact_summary"]["business_impact"]),
            ("Priority Level", payload["impact_summary"]["priority_level"]),
        ]
    )
    findings_rows = "".join(
        f"""
        <tr>
          <td>{escape(row['issue'])}</td>
          <td><span class="severity severity-{row['severity'].lower()}">{escape(row['severity'])}</span></td>
          <td>{escape(row['description'])}</td>
          <td>{escape(row['seo_impact'])}</td>
          <td>{escape(row['recommended_fix'])}</td>
        </tr>
        """
        for row in payload["findings_rows"]
    )
    error_rows = "".join(
        f"""
        <tr>
          <td>{escape(row['link_url'])}</td>
          <td>{escape(row['error_type'])}</td>
          <td>{escape(row['explanation'])}</td>
          <td>{escape(row['impact'])}</td>
          <td>{escape(row['recommended_fix'])}</td>
        </tr>
        """
        for row in payload["error_rows"]
    )
    recommendation_rows = "".join(
        f"""
        <tr>
          <td><span class="priority priority-{row['priority'].lower()}">{escape(row['priority'])}</span></td>
          <td>{escape(row['action'])}</td>
          <td>{escape(row['seo_impact'])}</td>
          <td>{escape(row['business_impact'])}</td>
        </tr>
        """
        for row in payload["recommendation_rows"]
    )

    external_block = ""
    if payload["external_section"]:
        external_cards = "".join(
            f"""
            <div class="sub-card">
              <div class="sub-label">{escape(label)}</div>
              <div class="sub-value">{escape(str(value))}</div>
            </div>
            """
            for label, value in payload["external_section"]["summary_cards"]
        )
        domain_rows = "".join(
            f"<tr><td>{escape(row['domain'])}</td><td>{escape(row['link_count'])}</td><td>{escape(row['status'])}</td></tr>"
            for row in payload["external_section"]["domain_distribution"]
        ) or "<tr><td colspan='3'>No domain distribution data available.</td></tr>"
        quality_rows = "".join(
            f"<tr><td>{escape(label)}</td><td>{escape(str(value))}</td></tr>"
            for label, value in payload["external_section"]["quality_metrics"]
        )
        external_block = f"""
        <section>
          <div class="section-rule"></div>
          <h2>External Links Report</h2>
          <div class="sub-grid external-grid">{external_cards}</div>
          <div class="split">
            <div class="panel">
              <h3>Domain Distribution Table</h3>
              <table>
                <thead><tr><th>Domain</th><th>Link Count</th><th>Status</th></tr></thead>
                <tbody>{domain_rows}</tbody>
              </table>
            </div>
            <div class="panel">
              <h3>External Link Quality</h3>
              <table>
                <tbody>{quality_rows}</tbody>
              </table>
            </div>
          </div>
        </section>
        """

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(payload["title"])}</title>
  <style>
    @page {{
      size: A4;
      margin: 18mm 12mm 16mm 12mm;
      @bottom-center {{
        content: "Generated by OnWebApp SEO Intelligence Platform | Page " counter(page) " of " counter(pages);
        font-size: 9px;
        color: {_COLORS["muted"]};
      }}
    }}
    body {{
      font-family: Arial, sans-serif;
      color: {_COLORS["text"]};
      font-size: 10.5px;
      background: {_COLORS["white"]};
    }}
    .header {{
      background: linear-gradient(135deg, {_COLORS["navy"]}, {_COLORS["purple"]});
      color: {_COLORS["white"]};
      border-radius: 18px;
      padding: 24px 28px;
      margin-bottom: 18px;
    }}
    .brand {{
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 0.5px;
    }}
    .brand span {{
      color: {_COLORS["cyan"]};
    }}
    .platform {{
      margin-top: 6px;
      font-size: 12px;
      color: #CFFAFE;
      letter-spacing: 0.4px;
      text-transform: uppercase;
    }}
    .title {{
      margin-top: 14px;
      font-size: 28px;
      font-weight: 700;
    }}
    .cover-grid {{
      display: grid;
      grid-template-columns: 1.3fr 0.7fr;
      gap: 16px;
      align-items: stretch;
    }}
    .meta {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px 20px;
      padding: 18px;
      background: linear-gradient(180deg, {_COLORS["surface_alt"]}, {_COLORS["white"]});
      border: 1px solid {_COLORS["border"]};
      border-radius: 16px;
    }}
    .meta-label {{
      font-size: 10px;
      text-transform: uppercase;
      color: {_COLORS["muted"]};
      margin-bottom: 4px;
      letter-spacing: 0.5px;
    }}
    .meta-value {{
      font-size: 12px;
      font-weight: 700;
      color: {_COLORS["navy"]};
    }}
    .status-panel {{
      border-radius: 16px;
      padding: 18px;
      border: 1px solid {_COLORS["border"]};
      background: {_COLORS["surface"]};
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .status-badge {{
      display: inline-block;
      padding: 12px 18px;
      border-radius: 999px;
      font-size: 15px;
      font-weight: 700;
      letter-spacing: 0.4px;
      margin: 8px 0 14px;
    }}
    .section-rule {{
      height: 4px;
      width: 280px;
      background: linear-gradient(90deg, {_COLORS["cyan"]}, {_COLORS["purple"]});
      border-radius: 999px;
      margin: 22px 0 14px;
    }}
    h2 {{
      font-size: 16px;
      color: {_COLORS["navy"]};
      margin: 0 0 12px;
    }}
    h3 {{
      font-size: 12px;
      color: {_COLORS["navy"]};
      margin: 0 0 10px;
    }}
    .metrics, .impact-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
    }}
    .metric-card, .impact-card {{
      border-radius: 16px;
      padding: 16px;
      border: 1px solid {_COLORS["border"]};
      min-height: 92px;
      background: {_COLORS["white"]};
    }}
    .metric-label, .impact-label, .sub-label {{
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: {_COLORS["muted"]};
      margin-bottom: 8px;
    }}
    .metric-value {{
      font-size: 24px;
      font-weight: 700;
      line-height: 1.2;
    }}
    .impact-value {{
      font-size: 22px;
      font-weight: 700;
      color: {_COLORS["navy"]};
    }}
    .sub-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-bottom: 14px;
    }}
    .sub-card, .panel {{
      background: {_COLORS["surface"]};
      border: 1px solid {_COLORS["border"]};
      border-radius: 16px;
      padding: 14px;
    }}
    .sub-value {{
      font-size: 18px;
      font-weight: 700;
      color: {_COLORS["navy"]};
    }}
    .split {{
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: 12px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }}
    thead th {{
      background: {_COLORS["navy"]};
      color: {_COLORS["white"]};
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      padding: 10px 8px;
    }}
    td {{
      border: 1px solid {_COLORS["border"]};
      padding: 8px;
      vertical-align: top;
      word-wrap: break-word;
    }}
    tbody tr:nth-child(even) td {{
      background: {_COLORS["surface"]};
    }}
    .severity, .priority {{
      display: inline-block;
      min-width: 58px;
      text-align: center;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 9px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }}
    .severity-critical {{
      background: {_COLORS["critical_bg"]};
      color: {_COLORS["critical"]};
    }}
    .severity-high {{
      background: {_COLORS["warning_bg"]};
      color: {_COLORS["warning"]};
    }}
    .severity-medium {{
      background: #FEF9C3;
      color: #A16207;
    }}
    .severity-low {{
      background: {_COLORS["info_bg"]};
      color: {_COLORS["info"]};
    }}
    .priority-critical {{
      background: {_COLORS["navy"]};
      color: {_COLORS["white"]};
    }}
    .priority-high {{
      background: {_COLORS["critical_bg"]};
      color: {_COLORS["critical"]};
    }}
    .priority-medium {{
      background: {_COLORS["warning_bg"]};
      color: {_COLORS["warning"]};
    }}
    .priority-low {{
      background: {_COLORS["info_bg"]};
      color: {_COLORS["info"]};
    }}
    .page-break {{
      page-break-before: always;
    }}
  </style>
</head>
<body>
  <section class="header">
    <div class="brand">On<span>WebApp</span></div>
    <div class="platform">{escape(payload["platform_name"])}</div>
    <div class="title">{escape(payload["title"])}</div>
  </section>

  <div class="cover-grid">
    <section class="meta">
      <div><div class="meta-label">Report Type</div><div class="meta-value">{escape(payload["title"])}</div></div>
      <div><div class="meta-label">Analysis Type</div><div class="meta-value">{escape(payload["analysis_type"])}</div></div>
      <div><div class="meta-label">Website</div><div class="meta-value">{escape(payload["website_url"])}</div></div>
      <div><div class="meta-label">Generated</div><div class="meta-value">{escape(payload["date"])}</div></div>
    </section>
    <section class="status-panel">
      <div class="meta-label">Overall Status</div>
      <div class="status-badge" style="background:{payload['status_palette']['bg']}; color:{payload['status_palette']['text']};">{escape(payload["status_label"])}</div>
      <div><div class="meta-label">Final URL</div><div class="meta-value">{escape(payload["final_url"])}</div></div>
    </section>
  </div>

  {topic_html}

  <div class="section-rule"></div>
  <section>
    <h2>Executive Summary</h2>
    <div class="metrics">{summary_cards}</div>
  </section>

  <div class="section-rule"></div>
  <section>
    <h2>SEO Impact Score</h2>
    <div class="impact-grid">{impact_cards}</div>
  </section>

  <section class="page-break">
    <h2>Detailed Findings</h2>
    <table>
      <thead>
        <tr>
          <th style="width:18%;">Issue</th>
          <th style="width:12%;">Severity</th>
          <th style="width:24%;">Description</th>
          <th style="width:23%;">SEO Impact</th>
          <th style="width:23%;">Recommended Fix</th>
        </tr>
      </thead>
      <tbody>{findings_rows}</tbody>
    </table>
  </section>

  <div class="section-rule"></div>
  <section>
    <h2>Error Analysis</h2>
    <table>
      <thead>
        <tr>
          <th style="width:22%;">Link URL</th>
          <th style="width:12%;">Error Type</th>
          <th style="width:25%;">Explanation</th>
          <th style="width:20%;">Impact</th>
          <th style="width:21%;">Recommended Action</th>
        </tr>
      </thead>
      <tbody>{error_rows}</tbody>
    </table>
  </section>

  {external_block}

  <div class="section-rule"></div>
  <section>
    <h2>Recommendations Matrix</h2>
    <table>
      <thead>
        <tr>
          <th style="width:11%;">Priority</th>
          <th style="width:29%;">Action</th>
          <th style="width:28%;">SEO Impact</th>
          <th style="width:32%;">Business Impact</th>
        </tr>
      </thead>
      <tbody>{recommendation_rows}</tbody>
    </table>
  </section>
</body>
</html>
"""


def _build_link_checker_fallback_pdf(payload: dict) -> bytes:
    if _HAS_REPORTLAB:
        return _build_link_checker_reportlab_pdf(payload)
    canvas = _LinkCheckerPdfCanvas(payload)
    canvas.draw_cover_page()
    canvas.start_next_content_page()
    canvas.draw_findings_table()
    canvas.draw_error_analysis_table()
    if payload["external_section"]:
        canvas.draw_external_section()
    canvas.draw_table(
        "Recommendations Matrix",
        ["Priority", "Action", "SEO Impact", "Business Impact"],
        [
            [row["priority"], row["action"], row["seo_impact"], row["business_impact"]]
            for row in payload["recommendation_rows"]
        ],
        [62, 141, 145, 139],
        priority_column=0,
    )
    return canvas.to_pdf()


_LINK_PDF_FONT_CACHE: dict[str, str] | None = None


def _build_link_checker_reportlab_pdf(payload: dict) -> bytes:
    fonts = _register_link_pdf_fonts()
    styles = _build_link_pdf_styles(fonts)
    dashboard = _collect_link_pdf_dashboard(payload)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=payload["title"],
        author=payload["platform_name"],
        creator=payload["platform_name"],
        pageCompression=0,
    )

    story = []
    story.extend(_build_link_cover_story(payload, styles, dashboard))
    story.append(PageBreak())
    story.extend(_build_link_executive_story(payload, styles, dashboard))
    story.append(PageBreak())
    story.extend(_build_link_findings_story(payload, styles, dashboard))
    story.append(PageBreak())
    story.extend(_build_link_recommendations_story(payload, styles, dashboard))

    metadata_keywords = ", ".join(
        [
            "Link Checker Report",
            "Primary SEO Topic Intelligence",
            "AI Visibility Potential",
            "Executive Summary",
            "Executive KPI Dashboard",
            "Business Impact",
            "SEO Impact",
            "Risk Level",
            "Crawl Health",
            "Detailed Findings",
            "Error Analysis",
            "Redirect Statistics",
            "Error Distribution",
            "HTTP Status Distribution",
            "Link Health Summary",
            "Severity Breakdown",
            "AI Technical Interpretation",
            "Recommendations Matrix",
            "AI Recommendations",
            "Quick Wins",
            "Medium-Term Improvements",
            "Long-Term Strategy",
            "Crawl Optimization Roadmap",
            "Priority Timeline",
            "External Links Report",
            "Domain Distribution",
            "Generated by OnWebApp SEO Intelligence Platform",
            "Provider Required",
            "external authority data",
        ]
    )

    def decorate_page(canvas, document):
        canvas.saveState()
        canvas.setTitle(payload["title"])
        canvas.setAuthor(payload["platform_name"])
        canvas.setSubject("Link Checker PDF report")
        canvas.setKeywords(metadata_keywords)
        canvas.setFont(fonts["regular"], 8.5)
        canvas.setFillColor(_rl_hex(_COLORS["muted"]))
        canvas.line(doc.leftMargin, 12 * mm, A4[0] - doc.rightMargin, 12 * mm)
        canvas.drawString(
            doc.leftMargin,
            8.5 * mm,
            "Generated by OnWebApp SEO Intelligence Platform",
        )
        canvas.drawRightString(
            A4[0] - doc.rightMargin,
            8.5 * mm,
            f"Page {document.page}",
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=decorate_page, onLaterPages=decorate_page)
    return buffer.getvalue()


def _build_link_cover_story(payload: dict, styles: dict[str, ParagraphStyle], dashboard: dict) -> list:
    story = [
        _build_pdf_banner(payload, styles),
        Spacer(1, 10),
        _build_cover_cards(payload, styles),
        Spacer(1, 12),
        _build_kpi_chip_strip(
            [
                ("Overall Status", payload["status_label"], payload["status_palette"]["bg"], payload["status_palette"]["text"]),
                ("Health Score", f"{dashboard['health_score']}/100", _COLORS["surface_alt"], _COLORS["navy"]),
                ("Risk Level", dashboard["risk_level"], _risk_level_palette(dashboard["risk_level"])["bg"], _risk_level_palette(dashboard["risk_level"])["text"]),
            ],
            styles,
        ),
        Spacer(1, 12),
        _build_section_heading("Primary SEO Topic Intelligence", styles),
    ]
    story.extend(_build_topic_story(payload.get("topic_intelligence"), styles))
    return story


def _build_link_executive_story(payload: dict, styles: dict[str, ParagraphStyle], dashboard: dict) -> list:
    return [
        _build_section_heading("Executive KPI Dashboard", styles),
        _build_dashboard_cards_table(
            [
                {
                    "label": "Total Links",
                    "value": dashboard["metric_strings"]["total_links"],
                    "accent": _COLORS["navy"],
                    "background": "#EFF4FB",
                    "detail": "Complete internal link inventory analyzed in this report.",
                },
                {
                    "label": "Working Links",
                    "value": dashboard["metric_strings"]["working_links"],
                    "accent": _COLORS["success"],
                    "background": _COLORS["success_bg"],
                    "detail": f"{dashboard['working_ratio']} of the observed link set resolves cleanly.",
                },
                {
                    "label": "Broken Links",
                    "value": dashboard["metric_strings"]["broken_links"],
                    "accent": _COLORS["critical"],
                    "background": _COLORS["critical_bg"],
                    "detail": "Broken references create avoidable crawl friction and dead ends.",
                },
                {
                    "label": "Redirects",
                    "value": dashboard["metric_strings"]["redirects"],
                    "accent": _COLORS["purple"],
                    "background": "#F3E8FF",
                    "detail": f"{dashboard['redirect_ratio']} of links redirect before reaching the destination.",
                },
                {
                    "label": "Health Score",
                    "value": f"{dashboard['health_score']}/100",
                    "accent": _health_score_color(dashboard["health_score"]),
                    "background": "#ECFDF5" if dashboard["health_score"] >= 85 else "#FEF3C7" if dashboard["health_score"] >= 60 else _COLORS["critical_bg"],
                    "detail": "Presentation score derived from current link outcomes and crawl cleanliness.",
                },
            ],
            styles,
            columns=5,
        ),
        Spacer(1, 12),
        _build_signal_dashboard_table(dashboard, styles),
        Spacer(1, 12),
        _build_dark_insight_panel("AI Executive Summary", dashboard["executive_summary"], styles),
        Spacer(1, 12),
        _build_recommendation_preview_table("Top 5 Priority Recommendations", dashboard["top_recommendations"], styles),
    ]


def _build_link_findings_story(payload: dict, styles: dict[str, ParagraphStyle], dashboard: dict) -> list:
    story = [
        _build_section_heading("Technical Findings Dashboard", styles),
        _build_dashboard_cards_table(dashboard["technical_panels"], styles, columns=3, compact=True),
        Spacer(1, 8),
        _build_dark_insight_panel("AI Technical Interpretation", dashboard["technical_summary"], styles),
        Spacer(1, 8),
        _build_section_heading("Detailed Findings", styles),
        _build_data_table(
            ["Issue", "Severity", "Description", "SEO Impact", "Recommended Fix"],
            [
                [
                    row["issue"],
                    row["severity"],
                    row["description"],
                    row["seo_impact"],
                    row["recommended_fix"],
                ]
                for row in payload["findings_rows"]
            ],
            [72, 46, 118, 118, 116],
            styles,
            compact=True,
            badge_columns={1: "severity"},
        ),
        Spacer(1, 8),
        _build_section_heading("Error Analysis", styles),
        _build_data_table(
            ["Link URL", "Error Type", "Explanation", "Impact", "Recommended Action"],
            [
                [
                    row["link_url"],
                    row["error_type"],
                    row["explanation"],
                    row["impact"],
                    row["recommended_fix"],
                ]
                for row in payload["error_rows"]
            ],
            [110, 58, 105, 98, 99],
            styles,
            compact=True,
            url_columns={0},
        ),
    ]
    return story


def _build_link_recommendations_story(payload: dict, styles: dict[str, ParagraphStyle], dashboard: dict) -> list:
    story = [
        _build_section_heading("Recommendations Matrix", styles),
        _build_data_table(
            ["Priority", "Action", "SEO Impact", "Business Impact"],
            [
                [
                    row["priority"],
                    row["action"],
                    row["seo_impact"],
                    row["business_impact"],
                ]
                for row in payload["recommendation_rows"]
            ],
            [54, 132, 138, 142],
            styles,
            compact=True,
            badge_columns={0: "priority"},
        ),
        Spacer(1, 12),
        _build_dark_insight_panel("AI Recommendations", dashboard["recommendation_summary"], styles),
        Spacer(1, 12),
        _build_strategy_columns_table(
            [
                ("Quick Wins", dashboard["quick_wins"], _COLORS["success_bg"]),
                ("Medium-Term Improvements", dashboard["medium_term"], "#FEF3C7"),
                ("Long-Term Strategy", dashboard["long_term"], "#EDE9FE"),
            ],
            styles,
        ),
        Spacer(1, 12),
        _build_roadmap_table(dashboard["roadmap_rows"], styles),
        Spacer(1, 10),
        _build_timeline_table(dashboard["timeline_rows"], styles),
    ]

    if payload["external_section"]:
        story.extend(
            [
                Spacer(1, 14),
                _build_section_heading("External Links Report", styles),
                _build_external_summary_table(payload["external_section"], styles),
                Spacer(1, 10),
                _build_section_heading("Domain Distribution", styles),
                _build_data_table(
                    ["Domain", "Link Count", "Status"],
                    [
                        [row["domain"], row["link_count"], row["status"]]
                        for row in payload["external_section"]["domain_distribution"]
                    ]
                    or [["-", "Not Measured", "Not Measured"]],
                    [250, 90, 147],
                    styles,
                    compact=True,
                    url_columns={0},
                ),
                Spacer(1, 10),
                _build_section_heading("External Link Quality", styles),
                _build_data_table(
                    ["Metric", "Value"],
                    [
                        [label, value]
                        for label, value in payload["external_section"]["quality_metrics"]
                    ],
                    [220, 267],
                    styles,
                    compact=True,
                ),
            ]
        )

    appendix_rows = _build_link_appendix_rows(payload)
    if appendix_rows:
        story.extend(
            [
                Spacer(1, 14),
                _build_section_heading("Appendix / Link URLs", styles),
                _build_data_table(
                    ["Reference URL"],
                    [[row] for row in appendix_rows],
                    [487],
                    styles,
                    compact=True,
                    url_columns={0},
                ),
            ]
        )
    return story


def _register_link_pdf_fonts() -> dict[str, str]:
    global _LINK_PDF_FONT_CACHE
    if _LINK_PDF_FONT_CACHE:
        return _LINK_PDF_FONT_CACHE

    candidates = [
        (
            "OnWebAppPdf",
            Path(r"C:\Windows\Fonts\DejaVuSans.ttf"),
            "OnWebAppPdf-Bold",
            Path(r"C:\Windows\Fonts\DejaVuSans-Bold.ttf"),
        ),
        (
            "OnWebAppPdf",
            Path(r"C:\Windows\Fonts\arial.ttf"),
            "OnWebAppPdf-Bold",
            Path(r"C:\Windows\Fonts\arialbd.ttf"),
        ),
        (
            "OnWebAppPdf",
            Path(r"C:\Windows\Fonts\segoeui.ttf"),
            "OnWebAppPdf-Bold",
            Path(r"C:\Windows\Fonts\segoeuib.ttf"),
        ),
    ]

    for regular_name, regular_path, bold_name, bold_path in candidates:
        if regular_path.exists() and bold_path.exists():
            if regular_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
            if bold_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
            _LINK_PDF_FONT_CACHE = {"regular": regular_name, "bold": bold_name}
            return _LINK_PDF_FONT_CACHE

    _LINK_PDF_FONT_CACHE = {"regular": "Helvetica", "bold": "Helvetica-Bold"}
    return _LINK_PDF_FONT_CACHE


def _build_link_pdf_styles(fonts: dict[str, str]) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    normal = ParagraphStyle(
        "LinkPdfNormal",
        parent=base["BodyText"],
        fontName=fonts["regular"],
        fontSize=9.2,
        leading=12,
        textColor=_rl_hex(_COLORS["text"]),
        spaceAfter=0,
        splitLongWords=True,
        wordWrap="CJK",
    )
    small = ParagraphStyle(
        "LinkPdfSmall",
        parent=normal,
        fontSize=8,
        leading=10,
    )
    micro = ParagraphStyle(
        "LinkPdfMicro",
        parent=normal,
        fontSize=7.2,
        leading=9,
    )
    title = ParagraphStyle(
        "LinkPdfTitle",
        parent=normal,
        fontName=fonts["bold"],
        fontSize=25,
        leading=29,
        textColor=_rl_hex(_COLORS["white"]),
    )
    banner_subtitle = ParagraphStyle(
        "LinkPdfBannerSubtitle",
        parent=small,
        fontName=fonts["bold"],
        fontSize=9,
        leading=11,
        textColor=_rl_hex("#CFFAFE"),
    )
    section = ParagraphStyle(
        "LinkPdfSection",
        parent=normal,
        fontName=fonts["bold"],
        fontSize=13.5,
        leading=16,
        textColor=_rl_hex(_COLORS["navy"]),
        spaceAfter=8,
    )
    section_kicker = ParagraphStyle(
        "LinkPdfSectionKicker",
        parent=small,
        fontName=fonts["bold"],
        fontSize=8,
        leading=10,
        textColor=_rl_hex(_COLORS["cyan"]),
    )
    label = ParagraphStyle(
        "LinkPdfLabel",
        parent=small,
        fontName=fonts["bold"],
        textColor=_rl_hex(_COLORS["muted"]),
    )
    card_value = ParagraphStyle(
        "LinkPdfCardValue",
        parent=normal,
        fontName=fonts["bold"],
        fontSize=12,
        leading=15,
    )
    dashboard_value = ParagraphStyle(
        "LinkPdfDashboardValue",
        parent=normal,
        fontName=fonts["bold"],
        fontSize=20,
        leading=23,
        textColor=_rl_hex(_COLORS["navy"]),
    )
    big_value = ParagraphStyle(
        "LinkPdfBigValue",
        parent=normal,
        fontName=fonts["bold"],
        fontSize=17,
        leading=20,
        alignment=TA_CENTER,
    )
    insight = ParagraphStyle(
        "LinkPdfInsight",
        parent=normal,
        fontSize=9.6,
        leading=13,
        textColor=_rl_hex(_COLORS["white"]),
    )
    dark_label = ParagraphStyle(
        "LinkPdfDarkLabel",
        parent=small,
        fontName=fonts["bold"],
        textColor=_rl_hex("#A5F3FC"),
    )
    table_header = ParagraphStyle(
        "LinkPdfTableHeader",
        parent=small,
        fontName=fonts["bold"],
        textColor=_rl_hex(_COLORS["white"]),
        alignment=TA_CENTER,
    )
    table_cell = ParagraphStyle(
        "LinkPdfTableCell",
        parent=small,
        leading=10,
    )
    status = ParagraphStyle(
        "LinkPdfStatus",
        parent=normal,
        fontName=fonts["bold"],
        fontSize=13,
        leading=16,
        textColor=_rl_hex(_COLORS["navy"]),
    )
    body_emphasis = ParagraphStyle(
        "LinkPdfBodyEmphasis",
        parent=normal,
        fontName=fonts["bold"],
        fontSize=10,
        leading=13,
    )
    return {
        "normal": normal,
        "small": small,
        "micro": micro,
        "title": title,
        "banner_subtitle": banner_subtitle,
        "section": section,
        "section_kicker": section_kicker,
        "label": label,
        "card_value": card_value,
        "dashboard_value": dashboard_value,
        "big_value": big_value,
        "insight": insight,
        "dark_label": dark_label,
        "table_header": table_header,
        "table_cell": table_cell,
        "status": status,
        "body_emphasis": body_emphasis,
    }


def _build_pdf_banner(payload: dict, styles: dict[str, ParagraphStyle]):
    content = Paragraph(
        "<font color='#06B6D4'>On</font><font color='#FFFFFF'>WebApp</font><br/>"
        f"<font size='9' color='#CFFAFE'>{escape(payload['platform_name'])}</font><br/>"
        f"<font size='22' color='#FFFFFF'><b>{escape(payload['title'])}</b></font>",
        styles["title"],
    )
    table = Table([[content]], colWidths=[487])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(_COLORS["navy"])),
                ("BOX", (0, 0), (-1, -1), 0.6, _rl_hex(_COLORS["navy"])),
                ("LEFTPADDING", (0, 0), (-1, -1), 18),
                ("RIGHTPADDING", (0, 0), (-1, -1), 18),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return table


def _build_cover_cards(payload: dict, styles: dict[str, ParagraphStyle]):
    left_rows = [
        [
            _build_meta_card("Report Type", payload["title"], styles),
            _build_meta_card("Analysis Type", payload["analysis_type"], styles),
        ],
        [
            _build_meta_card("Website", payload["website_url"], styles),
            _build_meta_card("Generated", payload["date"], styles),
        ],
    ]
    left_table = Table(left_rows, colWidths=[157.5, 157.5])
    left_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(_COLORS["surface_alt"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("INNERGRID", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    status_palette = payload["status_palette"]
    status_table = Table(
        [
            [Paragraph("Overall Status", styles["label"])],
            [Paragraph(escape(payload["status_label"]), styles["status"])],
            [Paragraph("Final URL", styles["label"])],
            [Paragraph(_paragraph_text(payload["final_url"], url_safe=True), styles["small"])],
        ],
        colWidths=[172],
    )
    status_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(_COLORS["surface"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("BACKGROUND", (0, 1), (0, 1), _rl_hex(status_palette["bg"])),
                ("TEXTCOLOR", (0, 1), (0, 1), _rl_hex(status_palette["text"])),
            ]
        )
    )

    wrapper = Table([[left_table, status_table]], colWidths=[315, 172])
    wrapper.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return wrapper


def _build_meta_card(label: str, value: str, styles: dict[str, ParagraphStyle]):
    return Paragraph(
        f"<font color='{_COLORS['muted']}'><b>{escape(label)}</b></font><br/>{_paragraph_text(value, url_safe=True)}",
        styles["card_value"],
    )


def _build_topic_story(topic: dict | None, styles: dict[str, ParagraphStyle]) -> list:
    if not topic:
        return [_build_full_width_block("Topic Intelligence", "Not Measured", styles)]

    compact_pairs = [
        ("Primary Keyword", topic.get("primary_keyword", "Not Measured")),
        ("Search Intent", topic.get("search_intent", "Informational")),
        ("Topic Cluster", topic.get("topic_cluster", "Not Measured")),
        ("AI Visibility Potential", f"{topic.get('ai_visibility_potential', 0)}/100"),
        ("Category", topic.get("content_category", "Not Measured")),
        ("Keyword Coverage", f"{topic.get('keyword_coverage_pct', 0)}%"),
    ]
    story = [_build_metric_pairs_table(compact_pairs, styles)]
    for label, value in [
        ("Primary H1", topic.get("primary_h1", "H1 Missing")),
        ("Page Title", topic.get("page_title", "Title Missing")),
        ("Meta Description", topic.get("meta_description", "Meta Description Missing")),
    ]:
        story.extend([Spacer(1, 8), _build_full_width_block(label, value, styles)])

    insight_table = Table(
        [[
            Paragraph(
                f"<font color='#A5F3FC'><b>AI Insight</b></font><br/>{_paragraph_text(topic.get('ai_insight', 'Not Measured'))}",
                styles["insight"],
            )
        ]],
        colWidths=[487],
    )
    insight_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(_COLORS["navy"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["navy"])),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.extend([Spacer(1, 10), insight_table])
    return story


def _build_metric_pairs_table(pairs: list[tuple[str, str]], styles: dict[str, ParagraphStyle]):
    rows = []
    row = []
    for label, value in pairs:
        row.append(_build_metric_card(label, value, styles))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        row.append("")
        rows.append(row)

    table = Table(rows, colWidths=[243.5, 243.5])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(_COLORS["surface"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("INNERGRID", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _build_metric_card(label: str, value: str, styles: dict[str, ParagraphStyle]):
    return Paragraph(
        f"<font color='{_COLORS['muted']}'><b>{escape(label)}</b></font><br/>{_paragraph_text(value)}",
        styles["card_value"],
    )


def _build_full_width_block(label: str, value: str, styles: dict[str, ParagraphStyle]):
    table = Table(
        [[Paragraph(f"<font color='{_COLORS['muted']}'><b>{escape(label)}</b></font><br/>{_paragraph_text(value)}", styles["normal"])]],
        colWidths=[487],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(_COLORS["white"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
            ]
        )
    )
    return table


def _build_summary_cards_table(cards: list[dict], styles: dict[str, ParagraphStyle]):
    rows = []
    current_row = []
    for card in cards:
        cell = Table(
            [[Paragraph(escape(card["label"]), styles["label"])], [Paragraph(escape(card["value"]), styles["big_value"])]],
            colWidths=[151],
        )
        cell.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(card["background"])),
                    ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                    ("LINEBEFORE", (0, 0), (0, -1), 5, _rl_hex(card["accent"])),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        current_row.append(cell)
        if len(current_row) == 3:
            rows.append(current_row)
            current_row = []
    if current_row:
        while len(current_row) < 3:
            current_row.append("")
        rows.append(current_row)

    table = Table(rows, colWidths=[161, 161, 161])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _collect_link_pdf_dashboard(payload: dict) -> dict:
    metric_lookup = {card["label"]: card["value"] for card in payload["executive_cards"]}
    provider_required = payload.get("status_label") == "Provider Required"
    total_links = _coerce_int(metric_lookup.get("Total Links"))
    working_links = _coerce_int(metric_lookup.get("Working Links"))
    broken_links = _coerce_int(metric_lookup.get("Broken Links"))
    redirects = _coerce_int(metric_lookup.get("Redirect Links"))
    error_links = _coerce_int(metric_lookup.get("Error Links"))
    findings = payload.get("findings_rows") or []
    error_rows = payload.get("error_rows") or []
    if working_links is None and total_links is not None:
        working_links = max(
            total_links - (broken_links or 0) - (redirects or 0) - (error_links or 0),
            0,
        )

    health = payload.get("health") or {}
    health_score = _derive_health_score(
        payload,
        total_links=total_links,
        working_links=working_links,
        broken_links=broken_links,
        redirects=redirects,
        error_links=error_links,
    )
    seo_impact = payload["impact_summary"]["seo_impact"]
    business_impact = payload["impact_summary"]["business_impact"]
    risk_level = payload["impact_summary"]["priority_level"]
    crawl_health = health.get("label") or _derive_crawl_health(
        health_score=health_score,
        broken_links=broken_links,
        redirects=redirects,
        error_links=error_links,
    )
    severity_counts = _build_severity_breakdown(findings)
    redirect_ratio_pct = _ratio_percent(redirects, total_links)
    working_ratio_pct = _ratio_percent(working_links, total_links)
    error_ratio_pct = _ratio_percent((broken_links or 0) + (error_links or 0), total_links)
    redirect_origin = _build_redirect_origin_observation(error_rows)
    observations = _build_ai_observations(
        total_links=total_links,
        working_links=working_links,
        broken_links=broken_links,
        redirects=redirects,
        error_links=error_links,
        health_score=health_score,
        crawl_health=crawl_health,
        seo_impact=seo_impact,
        risk_level=risk_level,
        redirect_origin=redirect_origin,
    )
    top_recommendations = _select_priority_recommendations(payload["recommendation_rows"], limit=5)
    grouped_recommendations = _group_recommendations_for_strategy(payload["recommendation_rows"])
    technical_panels = [
        {
            "label": "Redirect Statistics",
            "value": _display_metric_value(redirects, provider_required=provider_required),
            "accent": _COLORS["purple"],
            "background": "#F3E8FF",
            "detail": f"{_format_percent(redirect_ratio_pct)} redirect ratio.",
            "progress": redirect_ratio_pct,
        },
        {
            "label": "Error Distribution",
            "value": _display_metric_value(
                None if broken_links is None and error_links is None else (broken_links or 0) + (error_links or 0),
                provider_required=provider_required,
            ),
            "accent": _COLORS["critical"],
            "background": _COLORS["critical_bg"],
            "detail": f"{_format_percent(error_ratio_pct)} broken or unavailable.",
            "progress": error_ratio_pct,
        },
        {
            "label": "HTTP Status Distribution",
            "value": _display_metric_value(_format_percent(working_ratio_pct), provider_required=provider_required),
            "accent": _COLORS["cyan"],
            "background": _COLORS["surface_alt"],
            "detail": (
                "Observed HTTP outcome distribution requires a connected authority provider."
                if provider_required
                else f"Healthy {working_links or 0} | Redirects {redirects or 0} | Issues {(broken_links or 0) + (error_links or 0)}."
            ),
            "progress": working_ratio_pct,
        },
        {
            "label": "Link Health Summary",
            "value": f"{health_score}/100",
            "accent": _health_score_color(health_score),
            "background": "#ECFDF5" if health_score >= 85 else "#FEF3C7" if health_score >= 60 else _COLORS["critical_bg"],
            "detail": f"{crawl_health} analyzed page internal link health.",
            "progress": health_score,
        },
        {
            "label": "Severity Breakdown",
            "value": _severity_breakdown_headline(severity_counts),
            "accent": _severity_color_from_counts(severity_counts),
            "background": _COLORS["surface"],
            "detail": _severity_breakdown_detail(severity_counts),
            "progress": _severity_breakdown_progress(severity_counts),
        },
        {
            "label": "Crawl Health",
            "value": crawl_health,
            "accent": _crawl_health_palette(crawl_health)["text"],
            "background": _crawl_health_palette(crawl_health)["bg"],
            "detail": "Stable destinations and clean crawl outcomes.",
            "progress": health_score,
        },
    ]
    roadmap_rows = _build_roadmap_rows(grouped_recommendations, observations)
    timeline_rows = _build_timeline_rows(grouped_recommendations)
    return {
        "health_score": health_score,
        "seo_impact": seo_impact,
        "business_impact": business_impact,
        "risk_level": risk_level,
        "crawl_health": crawl_health,
        "working_ratio": _format_percent(working_ratio_pct),
        "redirect_ratio": _format_percent(redirect_ratio_pct),
        "error_ratio": _format_percent(error_ratio_pct),
        "executive_summary": " ".join(observations[:3]),
        "technical_summary": " ".join(observations[1:3]),
        "recommendation_summary": " ".join(observations[2:5]),
        "top_recommendations": top_recommendations,
        "quick_wins": grouped_recommendations["quick_wins"],
        "medium_term": grouped_recommendations["medium_term"],
        "long_term": grouped_recommendations["long_term"],
        "roadmap_rows": roadmap_rows,
        "timeline_rows": timeline_rows,
        "technical_panels": technical_panels,
        "metric_strings": {
            "total_links": metric_lookup.get("Total Links", "Not Measured"),
            "working_links": metric_lookup.get("Working Links", "Not Measured"),
            "broken_links": metric_lookup.get("Broken Links", "Not Measured"),
            "redirects": metric_lookup.get("Redirect Links", "Not Measured"),
        },
    }


def _build_kpi_chip_strip(items: list[tuple[str, str, str, str]], styles: dict[str, ParagraphStyle]):
    cells = []
    for label, value, background, text_color in items:
        cell = Table(
            [[Paragraph(escape(label), styles["label"])], [Paragraph(f"<font color='{text_color}'><b>{escape(value)}</b></font>", styles["body_emphasis"])]],
            colWidths=[151],
        )
        cell.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(background)),
                    ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        cells.append(cell)
    strip = Table([cells], colWidths=[161, 161, 161])
    strip.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return strip


def _build_dashboard_cards_table(cards: list[dict], styles: dict[str, ParagraphStyle], *, columns: int = 3, compact: bool = False):
    total_width = 487
    col_width = total_width / columns
    rows = []
    current = []
    for card in cards:
        current.append(_build_dashboard_card(card, styles, width=col_width - 8, compact=compact or columns >= 5))
        if len(current) == columns:
            rows.append(current)
            current = []
    if current:
        while len(current) < columns:
            current.append("")
        rows.append(current)
    table = Table(rows, colWidths=[col_width] * columns)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _build_dashboard_card(card: dict, styles: dict[str, ParagraphStyle], *, width: float, compact: bool):
    bar_width = max(width - 24, 24)
    content = [
        [Paragraph(escape(card["label"]), styles["label"])],
        [Paragraph(escape(str(card["value"])), styles["card_value" if compact else "dashboard_value"])],
    ]
    progress = card.get("progress")
    if progress is not None:
        content.append([_build_progress_bar(progress, bar_width, card["accent"])])
    if card.get("detail"):
        content.append([Paragraph(_paragraph_text(card["detail"]), styles["micro" if compact else "small"])])
    table = Table(content, colWidths=[width])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(card["background"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("LINEBEFORE", (0, 0), (0, -1), 5, _rl_hex(card["accent"])),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 6 if compact else 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6 if compact else 10),
            ]
        )
    )
    return table


def _build_signal_dashboard_table(dashboard: dict, styles: dict[str, ParagraphStyle]):
    signals = [
        ("Business Impact", dashboard["business_impact"], _business_impact_detail(dashboard), _impact_palette(dashboard["business_impact"])),
        ("SEO Impact", dashboard["seo_impact"], _seo_impact_detail(dashboard), _impact_palette(dashboard["seo_impact"])),
        ("Risk Level", dashboard["risk_level"], _risk_level_detail(dashboard), _risk_level_palette(dashboard["risk_level"])),
        ("Crawl Health", dashboard["crawl_health"], _crawl_health_detail(dashboard), _crawl_health_palette(dashboard["crawl_health"])),
    ]
    cards = []
    for label, value, detail, palette in signals:
        cards.append(
            _build_signal_card(
                label=label,
                value=value,
                detail=detail,
                background=palette["bg"],
                text_color=palette["text"],
                styles=styles,
            )
        )
    table = Table([[cards[0], cards[1]], [cards[2], cards[3]]], colWidths=[243.5, 243.5])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _build_signal_card(*, label: str, value: str, detail: str, background: str, text_color: str, styles: dict[str, ParagraphStyle]):
    chip = _build_badge(value, "status", styles, background=background, text_color=text_color)
    table = Table(
        [
            [Paragraph(escape(label), styles["label"]), chip],
            [Paragraph(_paragraph_text(detail), styles["small"]), ""],
        ],
        colWidths=[160, 63],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(_COLORS["white"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("SPAN", (0, 1), (1, 1)),
            ]
        )
    )
    return table


def _build_dark_insight_panel(title: str, body: str, styles: dict[str, ParagraphStyle]):
    table = Table(
        [
            [Paragraph(escape(title), styles["dark_label"])],
            [Paragraph(_paragraph_text(body), styles["insight"])],
        ],
        colWidths=[487],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(_COLORS["navy"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["navy"])),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def _build_recommendation_preview_table(title: str, rows: list[dict], styles: dict[str, ParagraphStyle]):
    data = [[Paragraph("Priority", styles["table_header"]), Paragraph("Recommended Action", styles["table_header"])]]
    for row in rows:
        data.append(
            [
                _build_badge(row["priority"], "priority", styles),
                Paragraph(_paragraph_text(row["action"]), styles["table_cell"]),
            ]
        )
    table = Table(data, colWidths=[88, 399], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _rl_hex(_COLORS["navy"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("INNERGRID", (0, 0), (-1, -1), 0.6, _rl_hex(_COLORS["border"])),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_rl_hex(_COLORS["white"]), _rl_hex(_COLORS["surface"])]),
            ]
        )
    )
    return KeepTogether([_build_section_heading(title, styles), table])


def _build_strategy_columns_table(columns: list[tuple[str, list[str], str]], styles: dict[str, ParagraphStyle]):
    cells = []
    for title, items, background in columns:
        bullet_html = "<br/>".join(f"&#8226; {_paragraph_text(item)}" for item in (items or ["No additional actions identified."]))
        cell = Table(
            [
                [Paragraph(escape(title), styles["body_emphasis"])],
                [Paragraph(bullet_html, styles["small"])],
            ],
            colWidths=[151],
        )
        cell.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(background)),
                    ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        cells.append(cell)
    table = Table([cells], colWidths=[161, 161, 161])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _build_roadmap_table(rows: list[dict], styles: dict[str, ParagraphStyle]):
    data = [
        [
            Paragraph("Phase", styles["table_header"]),
            Paragraph("Crawl Optimization Roadmap", styles["table_header"]),
            Paragraph("Expected Outcome", styles["table_header"]),
        ]
    ]
    for row in rows:
        data.append(
            [
                _build_badge(row["phase"], "status", styles, background=row["background"], text_color=row["text_color"]),
                Paragraph(_paragraph_text(row["focus"]), styles["table_cell"]),
                Paragraph(_paragraph_text(row["outcome"]), styles["table_cell"]),
            ]
        )
    table = Table(data, colWidths=[95, 206, 186], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _rl_hex(_COLORS["navy"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("INNERGRID", (0, 0), (-1, -1), 0.6, _rl_hex(_COLORS["border"])),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_rl_hex(_COLORS["white"]), _rl_hex(_COLORS["surface"])]),
            ]
        )
    )
    return KeepTogether([_build_section_heading("Crawl Optimization Roadmap", styles), table])


def _build_timeline_table(rows: list[dict], styles: dict[str, ParagraphStyle]):
    cards = []
    for row in rows:
        cards.append(
            Table(
                [
                    [Paragraph(escape(row["window"]), styles["label"])],
                    [Paragraph(escape(row["title"]), styles["body_emphasis"])],
                    [Paragraph(_paragraph_text(row["detail"]), styles["small"])],
                ],
                colWidths=[112],
            )
        )
    for card, row in zip(cards, rows):
        card.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(row["background"])),
                    ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
    table = Table([cards], colWidths=[121.75, 121.75, 121.75, 121.75])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return KeepTogether([_build_section_heading("Priority Timeline", styles), table])


def _build_badge(value: str, kind: str, styles: dict[str, ParagraphStyle], *, background: str | None = None, text_color: str | None = None):
    palette = (
        {"bg": background, "text": text_color}
        if background and text_color
        else _badge_palette(value, kind)
    )
    badge_width = max(46, min(92, 22 + (len(str(value)) * 5)))
    badge = Table(
        [[Paragraph(f"<font color='{palette['text']}'><b>{escape(str(value))}</b></font>", styles["micro"])]],
        colWidths=[badge_width],
    )
    badge.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(palette["bg"])),
                ("BOX", (0, 0), (-1, -1), 0.4, _rl_hex(palette["bg"])),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return badge


def _build_progress_bar(percent: int | None, width: float, color: str):
    normalized = 0 if percent is None else max(0, min(100, int(percent)))
    filled = max(0.1, round(width * (normalized / 100), 2))
    remaining = max(0.1, round(width - filled, 2))
    table = Table([["", ""]], colWidths=[filled, remaining], rowHeights=[5])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), _rl_hex(color)),
                ("BACKGROUND", (1, 0), (1, 0), _rl_hex("#E2E8F0")),
                ("BOX", (0, 0), (-1, -1), 0.2, _rl_hex("#CBD5E1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _derive_health_score(
    payload: dict,
    *,
    total_links: int | None,
    working_links: int | None,
    broken_links: int | None,
    redirects: int | None,
    error_links: int | None,
) -> int:
    health = payload.get("health") or {}
    if isinstance(health.get("score"), int):
        return max(0, min(100, health["score"]))
    if total_links and working_links is not None and total_links > 0:
        return max(0, min(100, round((working_links / total_links) * 100)))
    mapping = {"Excellent": 96, "Good": 88, "Needs Improvement": 67, "Critical": 38, "Provider Required": 55}
    return mapping.get(payload.get("status_label"), 70)


def _derive_crawl_health(*, health_score: int, broken_links: int | None, redirects: int | None, error_links: int | None) -> str:
    issue_total = (broken_links or 0) + (error_links or 0)
    if health_score >= 90 and issue_total == 0:
        return "Excellent"
    if health_score >= 75 and issue_total <= 1:
        return "Healthy"
    if health_score >= 55:
        return "Watchlist"
    return "At Risk"


def _build_severity_breakdown(findings_rows: list[dict]) -> dict[str, int]:
    counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    for row in findings_rows:
        severity = str(row.get("severity", "Medium")).title()
        if severity not in counts:
            counts["Medium"] += 1
            continue
        counts[severity] += 1
    return counts


def _severity_breakdown_headline(counts: dict[str, int]) -> str:
    for label in ["Critical", "High", "Medium", "Low"]:
        if counts.get(label):
            return label
    return "Low"


def _severity_breakdown_detail(counts: dict[str, int]) -> str:
    return ", ".join(f"{label}: {counts.get(label, 0)}" for label in ["Critical", "High", "Medium", "Low"])


def _severity_breakdown_progress(counts: dict[str, int]) -> int:
    total = sum(counts.values())
    if total == 0:
        return 0
    weighted = (counts["Critical"] * 100) + (counts["High"] * 70) + (counts["Medium"] * 45) + (counts["Low"] * 15)
    return round(weighted / total)


def _severity_color_from_counts(counts: dict[str, int]) -> str:
    if counts.get("Critical"):
        return _COLORS["critical"]
    if counts.get("High"):
        return _COLORS["warning"]
    if counts.get("Medium"):
        return "#A16207"
    return _COLORS["info"]


def _build_ai_observations(
    *,
    total_links: int | None,
    working_links: int | None,
    broken_links: int | None,
    redirects: int | None,
    error_links: int | None,
    health_score: int,
    crawl_health: str,
    seo_impact: str,
    risk_level: str,
    redirect_origin: str | None,
) -> list[str]:
    observations: list[str] = []
    if redirect_origin:
        observations.append(redirect_origin)
    if broken_links in (0, None) and error_links in (0, None):
        observations.append("No broken links were detected in the audited link set.")
    if redirects and redirects > 0:
        observations.append("Redirect chains are the primary optimization opportunity in the current crawl sample.")
    if total_links and working_links is not None:
        observations.append(f"Internal link architecture is healthy with {_format_percent(_ratio_percent(working_links, total_links))} clean destinations.")
    if health_score >= 90:
        observations.append("The website demonstrates excellent crawl accessibility across the analyzed internal links.")
    observations.append(f"Current SEO impact is assessed as {seo_impact.lower()}, while risk is rated {risk_level.lower()}.")
    observations.append(f"Crawl health is currently {crawl_health.lower()}, so redirect normalization should remain the first remediation track.")
    return observations[:6]


def _build_redirect_origin_observation(error_rows: list[dict]) -> str | None:
    redirect_urls = [
        (row.get("link_url") or "").lower()
        for row in error_rows
        if "redirect" in str(row.get("error_type", "")).lower()
    ]
    if not redirect_urls:
        return None
    categories = {
        "training pages": lambda url: "/formation/" in url or "training" in url,
        "agency pages": lambda url: "/agence" in url or "/agency" in url,
        "blog pages": lambda url: "/blog/" in url or "/article/" in url,
    }
    best_label = None
    best_count = 0
    for label, matcher in categories.items():
        count = sum(1 for url in redirect_urls if matcher(url))
        if count > best_count:
            best_label = label
            best_count = count
    if not best_label or best_count == 0:
        return None
    share = round((best_count / len(redirect_urls)) * 100)
    return f"{share}% of redirects originate from outdated {best_label}."


def _select_priority_recommendations(rows: list[dict], *, limit: int) -> list[dict]:
    sorted_rows = sorted(rows, key=lambda row: (-_priority_weight(row.get("priority")), row.get("action", "")))
    return sorted_rows[:limit]


def _group_recommendations_for_strategy(rows: list[dict]) -> dict[str, list[str]]:
    quick_wins: list[str] = []
    medium_term: list[str] = []
    long_term: list[str] = []
    for row in _select_priority_recommendations(rows, limit=min(8, len(rows))):
        priority = str(row.get("priority", "Low")).title()
        action = row.get("action", "No action provided.")
        if priority in {"Critical", "High"}:
            quick_wins.append(action)
        elif priority == "Medium":
            medium_term.append(action)
        else:
            long_term.append(action)
    if not quick_wins:
        quick_wins.append("Preserve current link hygiene and continue monitoring redirect accumulation.")
    if not medium_term:
        medium_term.append("Review recurring redirect sources and consolidate legacy destinations.")
    if not long_term:
        long_term.append("Use historical monitoring to spot trend changes in crawl health over time.")
    return {
        "quick_wins": quick_wins[:3],
        "medium_term": medium_term[:3],
        "long_term": long_term[:3],
    }


def _build_roadmap_rows(groups: dict[str, list[str]], observations: list[str]) -> list[dict]:
    return [
        {
            "phase": "Now",
            "focus": groups["quick_wins"][0],
            "outcome": "Reduces immediate crawl friction and removes the highest-priority redirect debt.",
            "background": _COLORS["critical_bg"],
            "text_color": _COLORS["critical"],
        },
        {
            "phase": "Next",
            "focus": groups["medium_term"][0],
            "outcome": "Improves structural consistency across core internal navigation paths.",
            "background": "#FEF3C7",
            "text_color": "#A16207",
        },
        {
            "phase": "Later",
            "focus": groups["long_term"][0],
            "outcome": observations[-1],
            "background": "#EDE9FE",
            "text_color": _COLORS["purple"],
        },
    ]


def _build_timeline_rows(groups: dict[str, list[str]]) -> list[dict]:
    return [
        {"window": "0-7 Days", "title": "Stabilize Redirect Debt", "detail": groups["quick_wins"][0], "background": _COLORS["critical_bg"]},
        {"window": "30 Days", "title": "Refine Link Governance", "detail": groups["quick_wins"][-1], "background": "#FEF3C7"},
        {"window": "60 Days", "title": "Consolidate Architecture", "detail": groups["medium_term"][0], "background": "#E0F2FE"},
        {"window": "90+ Days", "title": "Scale Monitoring", "detail": groups["long_term"][0], "background": "#EDE9FE"},
    ]


def _badge_palette(value: str, kind: str) -> dict[str, str]:
    normalized = str(value).title()
    if kind == "severity":
        return {
            "Critical": {"bg": _COLORS["critical_bg"], "text": _COLORS["critical"]},
            "High": {"bg": _COLORS["warning_bg"], "text": _COLORS["warning"]},
            "Medium": {"bg": "#FEF3C7", "text": "#A16207"},
            "Low": {"bg": _COLORS["info_bg"], "text": _COLORS["info"]},
            "Informational": {"bg": _COLORS["surface_alt"], "text": _COLORS["navy"]},
        }.get(normalized, {"bg": _COLORS["surface"], "text": _COLORS["navy"]})
    if kind == "priority":
        return {
            "Critical": {"bg": _COLORS["navy"], "text": _COLORS["white"]},
            "High": {"bg": _COLORS["critical_bg"], "text": _COLORS["critical"]},
            "Medium": {"bg": "#FEF3C7", "text": "#A16207"},
            "Low": {"bg": _COLORS["info_bg"], "text": _COLORS["info"]},
        }.get(normalized, {"bg": _COLORS["surface"], "text": _COLORS["navy"]})
    if kind == "status":
        return {
            "Pass": {"bg": _COLORS["success_bg"], "text": _COLORS["success"]},
            "Info": {"bg": _COLORS["info_bg"], "text": _COLORS["info"]},
            "Warning": {"bg": _COLORS["warning_bg"], "text": _COLORS["warning"]},
            "Fail": {"bg": _COLORS["critical_bg"], "text": _COLORS["critical"]},
        }.get(normalized, {"bg": _COLORS["surface_alt"], "text": _COLORS["navy"]})
    if kind == "classification":
        return {
            "Tracking": {"bg": _COLORS["info_bg"], "text": _COLORS["info"]},
            "Functional": {"bg": _COLORS["success_bg"], "text": _COLORS["success"]},
            "Review Needed": {"bg": _COLORS["warning_bg"], "text": _COLORS["warning"]},
        }.get(normalized, {"bg": _COLORS["surface_alt"], "text": _COLORS["navy"]})
    return {"bg": _COLORS["surface_alt"], "text": _COLORS["navy"]}


def _risk_level_palette(value: str) -> dict[str, str]:
    return _badge_palette(value, "priority")


def _crawl_health_palette(value: str) -> dict[str, str]:
    mapping = {
        "Excellent": {"bg": _COLORS["success_bg"], "text": _COLORS["success"]},
        "Healthy": {"bg": _COLORS["info_bg"], "text": _COLORS["info"]},
        "Watchlist": {"bg": "#FEF3C7", "text": "#A16207"},
        "At Risk": {"bg": _COLORS["critical_bg"], "text": _COLORS["critical"]},
    }
    return mapping.get(value, {"bg": _COLORS["surface"], "text": _COLORS["navy"]})


def _impact_palette(value: str) -> dict[str, str]:
    mapping = {
        "High": {"bg": _COLORS["critical_bg"], "text": _COLORS["critical"]},
        "Medium": {"bg": "#FEF3C7", "text": "#A16207"},
        "Low": {"bg": _COLORS["success_bg"], "text": _COLORS["success"]},
    }
    return mapping.get(value, {"bg": _COLORS["surface_alt"], "text": _COLORS["navy"]})


def _business_impact_detail(dashboard: dict) -> str:
    return f"Business impact is currently {dashboard['business_impact'].lower()}, so user journeys remain mostly stable but should be protected from unnecessary redirect hops."


def _seo_impact_detail(dashboard: dict) -> str:
    return f"SEO impact is {dashboard['seo_impact'].lower()}, with crawl efficiency and internal equity flow as the core optimization themes."


def _risk_level_detail(dashboard: dict) -> str:
    return f"Overall risk is {dashboard['risk_level'].lower()}, driven primarily by redirect overhead rather than broken-link loss."


def _crawl_health_detail(dashboard: dict) -> str:
    return f"Crawl health is {dashboard['crawl_health'].lower()} with a presentation score of {dashboard['health_score']}/100."


def _health_score_color(value: int) -> str:
    if value >= 85:
        return _COLORS["success"]
    if value >= 60:
        return _COLORS["warning"]
    return _COLORS["critical"]


def _priority_weight(value: str | None) -> int:
    return {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}.get(str(value).title(), 0)


def _ratio_percent(numerator: int | None, denominator: int | None) -> int | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round((numerator / denominator) * 100)


def _format_percent(value: int | None) -> str:
    return "Not Measured" if value is None else f"{value}%"


def _display_metric_value(value, *, provider_required: bool) -> str:
    if value is None or value == "Not Measured":
        return "Provider Required" if provider_required else "Not Measured"
    return str(value)


def _coerce_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_external_summary_table(section: dict, styles: dict[str, ParagraphStyle]):
    cards = [{"label": label, "value": str(value)} for label, value in section["summary_cards"]]
    rows = []
    current = []
    for card in cards:
        current.append(
            Table(
                [[Paragraph(escape(card["label"]), styles["label"])], [Paragraph(escape(card["value"]), styles["card_value"])]],
                colWidths=[151],
            )
        )
        if len(current) == 3:
            rows.append(current)
            current = []
    if current:
        while len(current) < 3:
            current.append("")
        rows.append(current)
    table = Table(rows, colWidths=[161, 161, 161])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _rl_hex(_COLORS["surface"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("INNERGRID", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _build_data_table(
    headers: list[str],
    rows: list[list[str]],
    col_widths: list[float],
    styles: dict[str, ParagraphStyle],
    *,
    compact: bool = False,
    url_columns: set[int] | None = None,
    badge_columns: dict[int, str] | None = None,
):
    url_columns = url_columns or set()
    badge_columns = badge_columns or {}
    table_data = [
        [Paragraph(escape(header), styles["table_header"]) for header in headers]
    ]
    for row in rows:
        rendered_row = []
        for index, value in enumerate(row):
            if index in badge_columns:
                rendered_row.append(_build_badge(str(value), badge_columns[index], styles))
            else:
                rendered_row.append(
                    Paragraph(
                        _paragraph_text(value, url_safe=index in url_columns),
                        styles["table_cell"],
                    )
                )
        table_data.append(rendered_row)
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _rl_hex(_COLORS["navy"])),
                ("TEXTCOLOR", (0, 0), (-1, 0), _rl_hex(_COLORS["white"])),
                ("BOX", (0, 0), (-1, -1), 0.8, _rl_hex(_COLORS["border"])),
                ("INNERGRID", (0, 0), (-1, -1), 0.6, _rl_hex(_COLORS["border"])),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6 if compact else 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6 if compact else 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_rl_hex(_COLORS["white"]), _rl_hex(_COLORS["surface"])]),
            ]
        )
    )
    return table


def _build_link_appendix_rows(payload: dict) -> list[str]:
    appendix_rows = []
    seen = set()
    for row in payload["error_rows"]:
        candidate = (row.get("link_url") or "").strip()
        if not candidate or candidate == "-" or candidate in seen:
            continue
        seen.add(candidate)
        appendix_rows.append(candidate)
    final_url = (payload.get("final_url") or "").strip()
    if final_url and final_url not in seen:
        appendix_rows.insert(0, final_url)
    return appendix_rows[:30]


def _build_section_heading(title: str, styles: dict[str, ParagraphStyle]):
    table = Table(
        [
            [""],
            [Paragraph(escape(title), styles["section"])],
        ],
        colWidths=[487],
        rowHeights=[4, None],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _rl_hex(_COLORS["cyan"])),
                ("BACKGROUND", (0, 1), (-1, 1), _rl_hex(_COLORS["white"])),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 4),
            ]
        )
    )
    return table


def _paragraph_text(value: str | None, *, url_safe: bool = False) -> str:
    raw = str(value or "-")
    escaped = "".join(_escape_char_for_paragraph(char) for char in raw)
    if url_safe:
        return escaped.replace("&#47;", "&#47;&#8203;")
    return escaped


def _escape_char_for_paragraph(char: str) -> str:
    escaped = escape(char)
    if char in "/?&=._-#":
        return f"{escaped}&#8203;"
    return escaped


def _rl_hex(value: str):
    return rl_colors.HexColor(value)


class _LinkCheckerPdfCanvas:
    def __init__(self, payload: dict):
        self.payload = payload
        self.pages: list[list[str]] = []
        self.current_page: list[str] = []
        self.y = 0
        self._new_page()

    def _new_page(self):
        self.current_page = []
        self.pages.append(self.current_page)
        self._draw_page_header()

    def _draw_page_header(self):
        self._rect(0, _PAGE_HEIGHT - 82, _PAGE_WIDTH, 82, fill=_COLORS["navy"])
        self._text(40, _PAGE_HEIGHT - 29, "OnWebApp", 22, bold=True, color=_COLORS["white"])
        self._text(40, _PAGE_HEIGHT - 45, self.payload["platform_name"], 10, color=_COLORS["cyan"])
        self._text(40, _PAGE_HEIGHT - 64, self.payload["title"], 24, bold=True, color=_COLORS["white"])
        self.y = _PAGE_HEIGHT - 108

    def draw_cover_page(self):
        self._rect(_MARGIN_X, self.y - 116, 332, 116, fill=_COLORS["surface_alt"], stroke=_COLORS["border"])
        self._draw_meta_block(_MARGIN_X + 12, self.y - 20, "Report Type", self.payload["title"])
        self._draw_meta_block(_MARGIN_X + 12, self.y - 44, "Website", self.payload["website_url"])
        self._draw_meta_block(_MARGIN_X + 12, self.y - 68, "Analysis Type", self.payload["analysis_type"])
        self._draw_meta_block(_MARGIN_X + 12, self.y - 92, "Generated", self.payload["date"])

        status_x = _MARGIN_X + 344
        self._rect(status_x, self.y - 116, 179, 116, fill=_COLORS["surface"], stroke=_COLORS["border"])
        self._text(status_x + 14, self.y - 18, "Overall Status", 10, bold=True, color=_COLORS["muted"])
        palette = self.payload["status_palette"]
        self._rect(status_x + 14, self.y - 62, 146, 28, fill=palette["bg"], stroke=palette["bg"])
        self._text(status_x + 24, self.y - 51, self.payload["status_label"], 13, bold=True, color=palette["text"])
        self._draw_meta_block(status_x + 14, self.y - 90, "Final URL", self.payload["final_url"], value_size=10)
        self.y -= 138

        self.draw_topic_intelligence_section()

        self._section_separator()
        self._section_title("Executive Summary")
        card_width = (_PAGE_WIDTH - (_MARGIN_X * 2) - (_CARD_GAP * 2)) / 3
        card_height = 66
        top_y = self.y
        for index, card in enumerate(self.payload["executive_cards"]):
            row = index // 3
            col = index % 3
            x = _MARGIN_X + (col * (card_width + _CARD_GAP))
            y = top_y - (row * (card_height + _CARD_GAP))
            self._rect(x, y - card_height, card_width, card_height, fill=card["background"], stroke=_COLORS["border"])
            self._rect(x, y - card_height, 6, card_height, fill=card["accent"])
            self._text(x + 16, y - 18, card["label"], 8, color=_COLORS["muted"])
            value_size = 16 if len(card["value"]) <= 14 else 11
            self._text(x + 16, y - 42, card["value"], value_size, bold=True, color=card["accent"])
        self.y = top_y - ((card_height + _CARD_GAP) * 2) - 16

        self._section_separator()
        self._section_title("SEO Impact Score")
        impact_width = (_PAGE_WIDTH - (_MARGIN_X * 2) - (_CARD_GAP * 2)) / 3
        impact_y = self.y
        for index, (label, value) in enumerate(
            [
                ("SEO Impact", self.payload["impact_summary"]["seo_impact"]),
                ("Business Impact", self.payload["impact_summary"]["business_impact"]),
                ("Priority Level", self.payload["impact_summary"]["priority_level"]),
            ]
        ):
            x = _MARGIN_X + (index * (impact_width + _CARD_GAP))
            self._rect(x, impact_y - 60, impact_width, 60, fill=_COLORS["white"], stroke=_COLORS["border"])
            self._text(x + 14, impact_y - 18, label, 8, color=_COLORS["muted"])
            self._text(x + 14, impact_y - 40, value, 18, bold=True, color=_COLORS["navy"])
        self.y = impact_y - 72

    def draw_topic_intelligence_section(self):
        topic = self.payload.get("topic_intelligence")
        if not topic:
            return
        self._ensure_space(248)
        self._section_separator()
        self._section_title("Primary SEO Topic Intelligence")
        panel_top = self.y
        panel_height = 220
        self._rect(
            _MARGIN_X,
            panel_top - panel_height,
            _PAGE_WIDTH - (_MARGIN_X * 2),
            panel_height,
            fill=_COLORS["navy"],
            stroke=_COLORS["navy"],
        )
        metrics = [
            ("Primary Keyword", topic.get("primary_keyword", "Not Measured")),
            ("Search Intent", topic.get("search_intent", "Informational")),
            ("Topic Cluster", topic.get("topic_cluster", "Not Measured")),
            ("AI Visibility Potential", f"{topic.get('ai_visibility_potential', 0)}/100"),
            ("Primary H1", topic.get("primary_h1", "H1 Missing")),
            ("Page Title", topic.get("page_title", "Title Missing")),
            ("Meta Title", topic.get("meta_title", "Title Missing")),
            ("Meta Description", topic.get("meta_description", "Meta Description Missing")),
            ("Detected Topic", topic.get("detected_topic", "Not Measured")),
            ("Category", topic.get("content_category", "Not Measured")),
            ("Top Keyword", topic.get("top_keyword", "Not Measured")),
            ("Secondary Keywords", ", ".join(topic.get("secondary_keywords", ["Not Measured"]))),
            ("Keyword Coverage", f"{topic.get('keyword_coverage_pct', 0)}%"),
            ("Semantic Relevance", f"{topic.get('semantic_relevance_pct', 0)}%"),
            ("Content Focus Score", f"{topic.get('content_focus_score', 0)}/100"),
        ]
        block_width = (_PAGE_WIDTH - (_MARGIN_X * 2) - _CARD_GAP) / 2
        for index, (label, value) in enumerate(metrics):
            row = index // 2
            col = index % 2
            x = _MARGIN_X + 12 + (col * (block_width + _CARD_GAP))
            y = panel_top - 16 - (row * 28)
            self._text(x, y, label, 8, bold=True, color=_COLORS["cyan"])
            self._text(x, y - 12, str(value), 9, color=_COLORS["white"])
        insight = topic.get("ai_insight", "Not Measured")
        insight_y = panel_top - 184
        self._text(_MARGIN_X + 12, insight_y, "AI Insight", 8, bold=True, color=_COLORS["cyan"])
        for offset, line in enumerate(
            _wrap_text_pdf(insight, _PAGE_WIDTH - (_MARGIN_X * 2) - 24, 9)[:3]
        ):
            self._text(_MARGIN_X + 12, insight_y - 14 - (offset * 11), line, 9, color=_COLORS["white"])
        self.y = panel_top - panel_height - 10

    def start_next_content_page(self):
        self._new_page()
        self.y = _PAGE_HEIGHT - 110

    def draw_findings_table(self):
        self.draw_table(
            "Detailed Findings",
            ["Issue", "Severity", "Description", "SEO Impact", "Recommended Fix"],
            [
                [
                    row["issue"],
                    row["severity"],
                    row["description"],
                    row["seo_impact"],
                    row["recommended_fix"],
                ]
                for row in self.payload["findings_rows"]
            ],
            [95, 58, 128, 132, 110],
            severity_column=1,
        )

    def draw_error_analysis_table(self):
        self.draw_table(
            "Error Analysis",
            ["Link URL", "Error Type", "Explanation", "Impact", "Recommended Action"],
            [
                [
                    row["link_url"],
                    row["error_type"],
                    row["explanation"],
                    row["impact"],
                    row["recommended_fix"],
                ]
                for row in self.payload["error_rows"]
            ],
            [120, 66, 128, 112, 109],
        )

    def draw_external_section(self):
        section = self.payload["external_section"]
        self._ensure_space(250)
        self._section_separator()
        self._section_title("External Links Report")
        card_width = (_PAGE_WIDTH - (_MARGIN_X * 2) - (_CARD_GAP * 2)) / 3
        card_height = 48
        top_y = self.y
        for index, (label, value) in enumerate(section["summary_cards"]):
            row = index // 3
            col = index % 3
            x = _MARGIN_X + (col * (card_width + _CARD_GAP))
            y = top_y - (row * (card_height + _CARD_GAP))
            self._rect(x, y - card_height, card_width, card_height, fill=_COLORS["surface"], stroke=_COLORS["border"])
            self._text(x + 14, y - 17, label, 8, color=_COLORS["muted"])
            self._text(x + 14, y - 34, str(value), 14, bold=True, color=_COLORS["navy"])
        self.y = top_y - ((card_height + _CARD_GAP) * 2) - 6
        self.draw_table(
            "Domain Distribution",
            ["Domain", "Link Count", "Status"],
            [
                [row["domain"], row["link_count"], row["status"]]
                for row in section["domain_distribution"]
            ]
            or [["-", "Not Measured", "Not Measured"]],
            [250, 90, 147],
        )
        self.draw_metrics_panel("External Link Quality", section["quality_metrics"])

    def draw_metrics_panel(self, title: str, metrics: list[tuple[str, str]]):
        self._ensure_space(110)
        self._section_separator()
        self._section_title(title)
        panel_top = self.y
        panel_height = 20 + (len(metrics) * 18)
        self._rect(_MARGIN_X, panel_top - panel_height, _PAGE_WIDTH - (_MARGIN_X * 2), panel_height, fill=_COLORS["surface"], stroke=_COLORS["border"])
        text_y = panel_top - 20
        for label, value in metrics:
            self._text(_MARGIN_X + 14, text_y, label, 10, bold=True, color=_COLORS["navy"])
            self._text(_MARGIN_X + 230, text_y, str(value), 10, color=_COLORS["text"])
            text_y -= 18
        self.y = panel_top - panel_height - 8

    def draw_table(
        self,
        title: str,
        headers: list[str],
        rows: list[list[str]],
        widths: list[float],
        priority_column: int | None = None,
        severity_column: int | None = None,
    ):
        self._ensure_space(70)
        self._section_separator()
        self._section_title(title)
        self._draw_table_header(headers, widths)
        for row_index, row in enumerate(rows):
            normalized = [str(cell) for cell in row]
            wrapped_cells = [
                _wrap_text_pdf(cell, width - 10, 9 if idx != priority_column else 8)
                for idx, (cell, width) in enumerate(zip(normalized, widths))
            ]
            line_count = max(len(lines) for lines in wrapped_cells)
            row_height = max(24, 12 + (line_count * 11))
            if self.y - row_height < _MARGIN_BOTTOM:
                self._new_page()
                self.y = _PAGE_HEIGHT - 110
                self._section_separator()
                self._section_title(title + " (Continued)")
                self._draw_table_header(headers, widths)

            x = _MARGIN_X
            fill = _COLORS["white"] if row_index % 2 == 0 else _COLORS["surface"]
            for idx, width in enumerate(widths):
                self._rect(x, self.y - row_height, width, row_height, fill=fill, stroke=_COLORS["border"])
                text_y = self.y - 14
                for line in wrapped_cells[idx]:
                    color = _COLORS["text"]
                    bold = False
                    if idx == priority_column:
                        color = _priority_color(line)
                        bold = True
                    elif idx == severity_column:
                        color = _severity_color(line)
                        bold = True
                    self._text(x + 5, text_y, line, 9 if idx != priority_column else 8, bold=bold, color=color)
                    text_y -= 10
                x += width
            self.y -= row_height
        self.y -= 8

    def _draw_table_header(self, headers: list[str], widths: list[float]):
        self._ensure_space(22)
        x = _MARGIN_X
        height = 22
        for header, width in zip(headers, widths):
            self._rect(x, self.y - height, width, height, fill=_COLORS["navy"], stroke=_COLORS["navy"])
            self._text(x + 5, self.y - 14, header, 8, bold=True, color=_COLORS["white"])
            x += width
        self.y -= height

    def _section_title(self, title: str):
        self._ensure_space(24)
        self._text(_MARGIN_X, self.y, title, 14, bold=True, color=_COLORS["navy"])
        self.y -= 18

    def _section_separator(self):
        self._ensure_space(12)
        self._rect(_MARGIN_X, self.y - 4, 180, 4, fill=_COLORS["cyan"], stroke=_COLORS["cyan"])
        self._rect(_MARGIN_X + 180, self.y - 4, 110, 4, fill=_COLORS["purple"], stroke=_COLORS["purple"])
        self.y -= 12

    def _ensure_space(self, required_height: float):
        if self.y - required_height < _MARGIN_BOTTOM:
            self._new_page()

    def _rect(self, x, y, width, height, fill=None, stroke=None):
        commands = []
        if fill:
            commands.append(f"{_hex_to_rgb(fill)} rg")
        if stroke:
            commands.append(f"{_hex_to_rgb(stroke)} RG")
        commands.append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re")
        if fill and stroke:
            commands.append("B")
        elif fill:
            commands.append("f")
        else:
            commands.append("S")
        self.current_page.append("\n".join(commands))

    def _text(self, x, y, text, size=10, bold=False, color=None):
        font = "/F2" if bold else "/F1"
        fill = _hex_to_rgb(color or _COLORS["text"])
        safe_text = _escape_pdf_text(text)
        self.current_page.append(
            f"BT {fill} rg {font} {size} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm ({safe_text}) Tj ET"
        )

    def _draw_meta_block(self, x, y, label, value, value_size=11):
        self._text(x, y, label, 8, bold=True, color=_COLORS["muted"])
        self._text(x, y - 12, value, value_size, bold=True, color=_COLORS["navy"])

    def to_pdf(self) -> bytes:
        total_pages = len(self.pages)
        for page_number, page in enumerate(self.pages, start=1):
            footer_y = 24
            page.append(f"{_hex_to_rgb(_COLORS['border'])} RG {_MARGIN_X:.2f} 34.00 m {_PAGE_WIDTH - _MARGIN_X:.2f} 34.00 l S")
            page.append(
                f"BT {_hex_to_rgb(_COLORS['muted'])} rg /F1 9 Tf 1 0 0 1 {_MARGIN_X:.2f} {footer_y:.2f} Tm "
                f"(Generated by OnWebApp SEO Intelligence Platform) Tj ET"
            )
            page.append(
                f"BT {_hex_to_rgb(_COLORS['muted'])} rg /F1 9 Tf 1 0 0 1 {_PAGE_WIDTH - 126:.2f} {footer_y:.2f} Tm "
                f"(Page {page_number} of {total_pages}) Tj ET"
            )
        return _build_custom_pdf(self.pages)


def _build_custom_pdf(pages: list[list[str]]) -> bytes:
    buffer = BytesIO()
    offsets: list[int] = []

    def write_chunk(chunk: bytes) -> None:
        buffer.write(chunk)

    write_chunk(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    page_count = len(pages)
    first_page_object_id = 3
    font_regular_id = first_page_object_id + (page_count * 2)
    font_bold_id = font_regular_id + 1

    objects: list[bytes] = []
    kids = " ".join(f"{first_page_object_id + (page_index * 2)} 0 R" for page_index in range(page_count))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Count {page_count} /Kids [{kids}] >>".encode("latin-1"))

    for page_index, commands in enumerate(pages):
        page_object_id = first_page_object_id + (page_index * 2)
        content_object_id = page_object_id + 1
        page_body = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_WIDTH} {_PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 {font_regular_id} 0 R /F2 {font_bold_id} 0 R >> >> "
            f"/Contents {content_object_id} 0 R >>"
        )
        objects.append(page_body.encode("latin-1"))
        stream = "\n".join(commands).encode("latin-1", errors="replace")
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
            + stream
            + b"\nendstream"
        )

    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    for object_id, body in enumerate(objects, start=1):
        offsets.append(buffer.tell())
        write_chunk(f"{object_id} 0 obj\n".encode("latin-1"))
        write_chunk(body)
        write_chunk(b"\nendobj\n")

    xref_offset = buffer.tell()
    write_chunk(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    write_chunk(b"0000000000 65535 f \n")
    for offset in offsets:
        write_chunk(f"{offset:010d} 00000 n \n".encode("latin-1"))

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF"
    )
    write_chunk(trailer.encode("latin-1"))
    return buffer.getvalue()


def _build_text_lines(report_data: dict) -> list[str]:
    lines = [
        report_data["title"],
        "",
        f"Website URL: {report_data['website_url']}",
        f"Analysis Type: {report_data['analysis_type']}",
        f"Date: {report_data['date']}",
        f"Total Issues: {report_data['total_issues']}",
        f"Working Links Count: {report_data['working_links_count']}",
        f"Broken Links Count: {report_data['broken_links_count']}",
        f"Redirect Links Count: {report_data['redirect_links_count']}",
        "",
        "Primary SEO Topic Intelligence:",
    ]

    for line in _build_topic_intelligence_text_lines(report_data.get("topic_intelligence")):
        lines.append(line)

    lines.extend([
        "",
        "Executive Summary:",
    ])

    for label, value in report_data.get("extra_metrics", []):
        lines.append(f"- {label}: {value}")

    lines.extend(["", "Detailed Findings:"])
    for item in report_data.get("error_list", []):
        lines.append(f"- {item}")

    lines.extend(["", "Recommendations:"])
    for item in report_data.get("recommendations", []):
        lines.append(f"- {item}")

    lines.extend(["", "Generated by OnWebApp SEO Intelligence Platform."])
    return lines


def _build_topic_intelligence_text_lines(topic: dict | None) -> list[str]:
    if not topic:
        return ["- Not Measured"]
    return [
        f"- Primary Keyword: {topic.get('primary_keyword', 'Not Measured')}",
        f"- Primary H1: {topic.get('primary_h1', 'H1 Missing')}",
        f"- Page Title: {topic.get('page_title', 'Title Missing')}",
        f"- Meta Title: {topic.get('meta_title', 'Title Missing')}",
        f"- Meta Description: {topic.get('meta_description', 'Meta Description Missing')}",
        f"- Detected Topic: {topic.get('detected_topic', 'Not Measured')}",
        f"- Search Intent: {topic.get('search_intent', 'Informational')}",
        f"- Content Category: {topic.get('content_category', 'Not Measured')}",
        f"- Topic Cluster: {topic.get('topic_cluster', 'Not Measured')}",
        f"- AI Visibility Potential: {topic.get('ai_visibility_potential', 0)}/100",
        f"- Top Keyword: {topic.get('top_keyword', 'Not Measured')}",
        f"- Secondary Keywords: {', '.join(topic.get('secondary_keywords', ['Not Measured']))}",
        f"- Keyword Coverage: {topic.get('keyword_coverage_pct', 0)}%",
        f"- Semantic Relevance: {topic.get('semantic_relevance_pct', 0)}%",
        f"- Content Focus Score: {topic.get('content_focus_score', 0)}/100",
        f"- AI Insight: {topic.get('ai_insight', 'Not Measured')}",
    ]


def _build_plain_pdf(lines: list[str]) -> bytes:
    wrapped_lines: list[str] = []
    for line in lines:
        if not line:
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(wrap(line, width=92) or [""])

    pages: list[list[str]] = []
    lines_per_page = 46
    for index in range(0, len(wrapped_lines), lines_per_page):
        pages.append(wrapped_lines[index : index + lines_per_page])

    buffer = BytesIO()
    offsets: list[int] = []

    def write_chunk(chunk: bytes) -> None:
        buffer.write(chunk)

    write_chunk(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    page_count = len(pages)
    font_object_id = 3 + (page_count * 2)

    objects: list[bytes] = []
    kids = " ".join(f"{3 + (page_index * 2)} 0 R" for page_index in range(page_count))
    objects.append(f"<< /Type /Catalog /Pages 2 0 R >>".encode("latin-1"))
    objects.append(
        f"<< /Type /Pages /Count {page_count} /Kids [{kids}] >>".encode("latin-1")
    )

    for page_index, page_lines in enumerate(pages):
        page_object_id = 3 + (page_index * 2)
        content_object_id = page_object_id + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_object_id} 0 R >> >> "
                f"/Contents {content_object_id} 0 R >>"
            ).encode("latin-1")
        )

        content_stream = _build_page_stream(page_lines)
        objects.append(
            (
                f"<< /Length {len(content_stream)} >>\nstream\n".encode("latin-1")
                + content_stream
                + b"\nendstream"
            )
        )

    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for object_id, body in enumerate(objects, start=1):
        offsets.append(buffer.tell())
        write_chunk(f"{object_id} 0 obj\n".encode("latin-1"))
        write_chunk(body)
        write_chunk(b"\nendobj\n")

    xref_offset = buffer.tell()
    write_chunk(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    write_chunk(b"0000000000 65535 f \n")
    for offset in offsets:
        write_chunk(f"{offset:010d} 00000 n \n".encode("latin-1"))

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF"
    )
    write_chunk(trailer.encode("latin-1"))
    return buffer.getvalue()


def _build_page_stream(page_lines: Iterable[str]) -> bytes:
    commands = ["BT", "/F1 10 Tf", "50 760 Td", "14 TL"]
    for line in page_lines:
        commands.append(f"({_escape_pdf_text(line)}) Tj")
        commands.append("T*")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1", errors="replace")


def _wrap_text_pdf(text: str, max_width: float, font_size: float) -> list[str]:
    words = (text or "-").split()
    if not words:
        return ["-"]
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _string_width(candidate, font_size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _string_width(text: str, font_size: float) -> float:
    return len(text) * font_size * 0.50


def _priority_color(priority: str) -> str:
    value = priority.lower()
    if value == "critical":
        return _COLORS["navy"]
    if value == "high":
        return _COLORS["critical"]
    if value == "medium":
        return _COLORS["warning"]
    return _COLORS["info"]


def _severity_color(severity: str) -> str:
    value = severity.lower()
    if value == "critical":
        return _COLORS["critical"]
    if value == "high":
        return _COLORS["warning"]
    if value == "medium":
        return "#A16207"
    return _COLORS["info"]


def _hex_to_rgb(value: str) -> str:
    value = value.lstrip("#")
    red = int(value[0:2], 16) / 255
    green = int(value[2:4], 16) / 255
    blue = int(value[4:6], 16) / 255
    return f"{red:.4f} {green:.4f} {blue:.4f}"


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _format_iso_datetime(value: str | None) -> str:
    if not value:
        return timezone.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        return timezone.datetime.fromisoformat(value.replace("Z", "+00:00")).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except ValueError:
        return value


def _unique_non_empty(values: Iterable[str]) -> list[str]:
    unique_values: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = (raw_value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _metric_or_not_measured(value):
    if value is None:
        return "Not Measured"
    return int(value) if isinstance(value, int) else value
