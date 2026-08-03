import logging
import time
from decimal import Decimal
from urllib.parse import urlparse
from django.db.models import Avg, F
from django.utils import timezone
from ..models import SEOResult, SEOIssue
from .utils import check_https_validity
from .recommender import get_recommendation


logger = logging.getLogger(__name__)
_ANALYSIS_TIMING_REPORTS: dict[int, dict] = {}


def pop_analysis_timing_report(task_id: int) -> dict | None:
    return _ANALYSIS_TIMING_REPORTS.pop(task_id, None)


def resolve_https_status(task, crawl_data):
    """Prefer the crawler's real root-page response over helper probes."""
    root_page = crawl_data.get("root_page")
    if root_page and root_page.final_url and root_page.status_code:
        return urlparse(root_page.final_url).scheme == "https"
    return check_https_validity(task.domain)


def calculate_technical_score(task, page_audits, https_valid=None):
    """Calculate Technical SEO score"""
    page_audits = list(page_audits)
    total = Decimal("0.00")
    max_score = Decimal("100.00")

    # HTTPS Valid (20 points)
    if https_valid is None:
        https_valid = check_https_validity(task.domain)
    if https_valid:
        total += Decimal("20.00")

    # Robots.txt Accessible (10 points)
    first_page = page_audits[0] if page_audits else None
    if first_page and first_page.has_robots:
        total += Decimal("10.00")

    # Sitemap Accessible (15 points)
    if first_page and first_page.has_sitemap:
        total += Decimal("15.00")

    # Canonical Tags (20 points)
    valid_canonical_count = sum(
        1
        for page in page_audits
        if page.has_canonical and page.canonical_url == page.final_url
    )
    total_pages = len(page_audits) or 1
    valid_canonical_pct = valid_canonical_count / total_pages
    if valid_canonical_pct >= 0.9:
        total += Decimal("20.00")
    elif valid_canonical_pct >= 0.5:
        total += Decimal("10.00")

    # Noindex Pages (10 points, reverse)
    noindex_count = sum(1 for page in page_audits if page.is_noindex)
    if noindex_count == 0:
        total += Decimal("10.00")

    # Broken Links (25 points) - MVP simplified
    total += Decimal("25.00")

    return min(total, max_score)


def calculate_on_page_score(page_audits):
    """Calculate On-Page SEO score"""
    page_audits = list(page_audits)
    total = Decimal("0.00")
    total_pages = len(page_audits) or 1

    # Title Tags (25 points)
    valid_title_count = sum(
        1
        for page in page_audits
        if page.title_tag_length is not None and 30 <= page.title_tag_length <= 60
    )
    valid_title_pct = valid_title_count / total_pages
    if valid_title_pct >= 0.9:
        total += Decimal("25.00")
    elif valid_title_pct >= 0.5:
        total += Decimal("12.00")

    # Meta Descriptions (20 points)
    valid_meta_count = sum(
        1
        for page in page_audits
        if page.meta_description_length is not None and 50 <= page.meta_description_length <= 320
    )
    valid_meta_pct = valid_meta_count / total_pages
    if valid_meta_pct >= 0.9:
        total += Decimal("20.00")
    elif valid_meta_pct >= 0.5:
        total += Decimal("10.00")

    # Single H1 (20 points)
    single_h1_count = sum(1 for page in page_audits if page.h1_count == 1)
    single_h1_pct = single_h1_count / total_pages
    if single_h1_pct >= 0.95:
        total += Decimal("20.00")
    elif single_h1_pct >= 0.7:
        total += Decimal("10.00")

    # Image Alt Text (20 points)
    total_images = sum(p.images_count for p in page_audits)
    total_missing_alt = sum(p.images_missing_alt for p in page_audits)
    if total_images == 0:
        avg_alt_pct = 1.0
    else:
        avg_alt_pct = 1 - (total_missing_alt / total_images)
    if avg_alt_pct >= 0.9:
        total += Decimal("20.00")
    elif avg_alt_pct >= 0.5:
        total += Decimal("10.00")

    # Word Count (15 points)
    valid_word_count = sum(
        1 for page in page_audits if page.word_count is not None and page.word_count >= 300
    )
    valid_word_pct = valid_word_count / total_pages
    if valid_word_pct >= 0.8:
        total += Decimal("15.00")
    elif valid_word_pct >= 0.4:
        total += Decimal("7.00")

    return min(total, Decimal("100.00"))


def calculate_performance_score(page_audits):
    """Calculate Performance score"""
    page_audits = list(page_audits)
    total = Decimal("0.00")
    total_pages = len(page_audits) or 1

    # Average Response Time (30 points)
    response_times = [page.response_time for page in page_audits if page.response_time is not None]
    avg_rt = (sum(response_times) / len(response_times)) if response_times else 10
    if avg_rt <= 1:
        total += Decimal("30.00")
    elif avg_rt <= 2:
        total += Decimal("20.00")
    elif avg_rt <= 3:
        total += Decimal("10.00")

    # Average Page Size (35 points)
    page_sizes = [page.page_size for page in page_audits if page.page_size is not None]
    avg_ps = (sum(page_sizes) / len(page_sizes)) if page_sizes else 5_000_000
    if avg_ps <= 500_000:
        total += Decimal("35.00")
    elif avg_ps <= 1_000_000:
        total += Decimal("20.00")
    elif avg_ps <= 2_000_000:
        total += Decimal("10.00")

    # No Large Pages (35 points)
    large_page_count = sum(
        1 for page in page_audits if page.page_size is not None and page.page_size >= 2_000_000
    )
    large_page_pct = large_page_count / total_pages
    if large_page_pct == 0:
        total += Decimal("35.00")
    elif large_page_pct <= 0.1:
        total += Decimal("20.00")
    elif large_page_pct <= 0.2:
        total += Decimal("10.00")

    return min(total, Decimal("100.00"))


def calculate_discovery_score(task, page_audits, sitemap_entries):
    """Calculate Discovery score"""
    page_audits = list(page_audits)
    total = Decimal("0.00")
    total_pages = len(page_audits) or 1

    # Sitemap Entries Found (40 points)
    crawled_final_urls = set(p.final_url for p in page_audits if p.final_url)
    sitemap_urls = set(u for u in sitemap_entries if "sitemap" not in u.lower())
    if len(sitemap_urls) == 0:
        total += Decimal("20.00")
    else:
        found_in_sitemap = len(crawled_final_urls & sitemap_urls)
        sitemap_found_pct = found_in_sitemap / len(sitemap_urls)
        if sitemap_found_pct >= 0.8:
            total += Decimal("40.00")
        elif sitemap_found_pct >= 0.4:
            total += Decimal("20.00")

    # Orphan Pages (35 points) - MVP simplified
    total += Decimal("35.00")

    # Internal Links per Page (25 points)
    avg_links = sum(p.internal_links_count for p in page_audits) / total_pages
    if avg_links >= 3:
        total += Decimal("25.00")
    elif avg_links >= 1:
        total += Decimal("12.00")

    return min(total, Decimal("100.00"))


def calculate_ai_opportunity_score(health_score, issues):
    """Calculate AI Opportunity Score"""
    easy_fix_names = {
        "Missing Title Tag",
        "Missing Meta Description",
        "Missing H1 Tag",
        "Missing Canonical Tag",
    }
    if hasattr(issues, "filter"):
        easy_fix_count = issues.filter(name__in=list(easy_fix_names)).count()
    else:
        easy_fix_count = sum(1 for issue in issues if issue.name in easy_fix_names)
    score = Decimal("100.00") - (health_score * Decimal("0.5")) + (Decimal(easy_fix_count) * Decimal("5.00"))
    return max(min(score, Decimal("100.00")), Decimal("0.00"))


def detect_issues(task, page_audits, crawl_data):
    """Detect all SEO issues"""
    issues = []
    root_page = crawl_data.get("root_page")

    # Audit-wide issues
    # 1. Missing HTTPS Certificate
    https_valid = resolve_https_status(task, crawl_data)
    if not https_valid:
        issues.append({
            "name": "Missing HTTPS Certificate",
            "severity": "critical",
            "category": "general",
            "page_audit": None,
            "description": "Domain does not have a valid HTTPS certificate.",
        })

    # 2. Missing Robots.txt
    if not crawl_data.get("has_robots", False):
        issues.append({
            "name": "Missing Robots.txt",
            "severity": "medium",
            "category": "technical",
            "page_audit": None,
            "description": "Website does not have a robots.txt file.",
        })

    # 3. Missing XML Sitemap
    if not crawl_data.get("has_sitemap", False):
        issues.append({
            "name": "Missing XML Sitemap",
            "severity": "high",
            "category": "discovery",
            "page_audit": None,
            "description": "Website does not have an XML sitemap.",
        })

    # 4. Homepage Not Returning 200 OK
    if root_page and root_page.status_code != 200:
        issues.append({
            "name": "Homepage Not Returning 200 OK",
            "severity": "critical",
            "category": "general",
            "page_audit": root_page,
            "description": f"Homepage returned status code {root_page.status_code}.",
        })

    # Page-specific issues
    for page in page_audits:
        # 5. Missing Title Tag
        if not page.title_tag or page.title_tag.strip() == "":
            issues.append({
                "name": "Missing Title Tag",
                "severity": "high",
                "category": "on-page",
                "page_audit": page,
                "description": f"Page {page.final_url} is missing a title tag.",
            })
        else:
            # 6. Title Tag Too Short
            if page.title_tag_length and page.title_tag_length < 30:
                issues.append({
                    "name": "Title Tag Too Short (<30 chars)",
                    "severity": "medium",
                    "category": "on-page",
                    "page_audit": page,
                    "description": f"Title tag is {page.title_tag_length} characters long (should be 30-60).",
                })
            # 7. Title Tag Too Long
            if page.title_tag_length and page.title_tag_length > 60:
                issues.append({
                    "name": "Title Tag Too Long (>60 chars)",
                    "severity": "medium",
                    "category": "on-page",
                    "page_audit": page,
                    "description": f"Title tag is {page.title_tag_length} characters long (should be 30-60).",
                })

        # 8. Missing Meta Description
        if not page.meta_description or page.meta_description.strip() == "":
            issues.append({
                "name": "Missing Meta Description",
                "severity": "medium",
                "category": "on-page",
                "page_audit": page,
                "description": f"Page {page.final_url} is missing a meta description.",
            })
        else:
            # 9. Meta Too Short
            if page.meta_description_length and page.meta_description_length <50:
                issues.append({
                    "name": "Meta Description Too Short (<50 chars)",
                    "severity": "low",
                    "category": "on-page",
                    "page_audit": page,
                    "description": f"Meta description is {page.meta_description_length} characters long (should be 50-320).",
                })
            # 10. Meta Too Long
            if page.meta_description_length and page.meta_description_length >320:
                issues.append({
                    "name": "Meta Description Too Long (>320 chars)",
                    "severity": "low",
                    "category": "on-page",
                    "page_audit": page,
                    "description": f"Meta description is {page.meta_description_length} characters long (should be 50-320).",
                })

        # 11. Missing H1 Tag
        if page.h1_count ==0:
            issues.append({
                "name": "Missing H1 Tag",
                "severity": "high",
                "category": "on-page",
                "page_audit": page,
                "description": f"Page {page.final_url} is missing an H1 tag.",
            })
        # 12. Multiple H1 Tags
        if page.h1_count >1:
            issues.append({
                "name": "Multiple H1 Tags",
                "severity": "medium",
                "category": "on-page",
                "page_audit": page,
                "description": f"Page {page.final_url} has {page.h1_count} H1 tags (should have exactly 1).",
            })

        # 13. Missing Canonical Tag
        if not page.has_canonical:
            issues.append({
                "name": "Missing Canonical Tag",
                "severity": "high",
                "category": "technical",
                "page_audit": page,
                "description": f"Page {page.final_url} is missing a canonical tag.",
            })
        # 14. Canonical Mismatch
        elif page.canonical_url and page.final_url and page.canonical_url != page.final_url:
            issues.append({
                "name": "Canonical Tag Mismatch",
                "severity": "critical",
                "category": "technical",
                "page_audit": page,
                "description": f"Canonical tag points to {page.canonical_url} but page is at {page.final_url}.",
            })

        # 15. Noindex Tag Present
        if page.is_noindex:
            issues.append({
                "name": "Noindex Tag Present",
                "severity": "critical",
                "category": "indexability",
                "page_audit": page,
                "description": f"Page {page.final_url} has a noindex tag.",
            })

        # 16. Slow Response Time
        if page.response_time and page.response_time >3:
            issues.append({
                "name": "Slow Response Time (>3s)",
                "severity": "medium",
                "category": "performance",
                "page_audit": page,
                "description": f"Page {page.final_url} has a response time of {page.response_time:.2f} seconds.",
            })

        # 17. Large Page Size
        if page.page_size and page.page_size > 2_000_000:
            issues.append({
                "name": "Large Page Size (>2MB)",
                "severity": "low",
                "category": "performance",
                "page_audit": page,
                "description": f"Page {page.final_url} has a size of {page.page_size / 1_000_000:.2f} MB.",
            })

        # 18. Thin Content
        if page.word_count and page.word_count < 300:
            issues.append({
                "name": "Thin Content (<300 words)",
                "severity": "medium",
                "category": "on-page",
                "page_audit": page,
                "description": f"Page {page.final_url} has only {page.word_count} words (should be ≥300).",
            })

        # 19. Missing Image Alt Text
        if page.images_count > 0 and page.images_missing_alt >0:
            issues.append({
                "name": "Missing Image Alt Text",
                "severity": "medium",
                "category": "on-page",
                "page_audit": page,
                "description": f"Page {page.final_url} has {page.images_missing_alt} images with missing alt text.",
            })
    return issues


def analyze(task, crawl_data):
    """Run full SEO analysis"""
    if not crawl_data.get("crawl_succeeded", True) or not crawl_data.get("root_page"):
        return None

    analysis_started_at = time.perf_counter()
    page_audits = list(task.page_audits.all())
    timing_report = {
        "crawl_time": float(crawl_data.get("performance_report", {}).get("total_execution_time", 0.0)),
        "parsing_time": float(crawl_data.get("performance_report", {}).get("stage_timings", {}).get("parse_html", 0.0)),
        "seo_analysis_time": 0.0,
        "ai_analysis_time": 0.0,
        "topic_intelligence_time": 0.0,
        "ai_recommendations_time": 0.0,
        "report_generation_time": 0.0,
    }

    https_probe_started_at = time.perf_counter()
    https_probe_status = check_https_validity(task.domain)
    timing_report["https_probe_time"] = round(time.perf_counter() - https_probe_started_at, 4)

    https_resolution_started_at = time.perf_counter()
    https_status = resolve_https_status(task, crawl_data)
    timing_report["https_resolution_time"] = round(time.perf_counter() - https_resolution_started_at, 4)

    seo_stage_started_at = time.perf_counter()
    technical_score = calculate_technical_score(task, page_audits, https_valid=https_probe_status)
    on_page_score = calculate_on_page_score(page_audits)
    performance_score = calculate_performance_score(page_audits)
    discovery_score = calculate_discovery_score(task, page_audits, crawl_data.get("sitemap_entries", set()))
    root_page = crawl_data.get("root_page")
    if root_page and root_page.status_code == 200:
        general_score = Decimal("100.00")
    else:
        general_score = Decimal("50.00")
    health_score = (
        (general_score * Decimal("0.05")) +
        (technical_score * Decimal("0.35")) +
        (on_page_score * Decimal("0.30")) +
        (performance_score * Decimal("0.15")) +
        (discovery_score * Decimal("0.15"))
    ).quantize(Decimal("0.00"))
    timing_report["seo_analysis_time"] = round(time.perf_counter() - seo_stage_started_at, 4)

    issue_stage_started_at = time.perf_counter()
    detected_issues = detect_issues(task, page_audits, crawl_data)
    issue_objects = []
    recommendation_started_at = time.perf_counter()
    for issue_data in detected_issues:
        rec = get_recommendation(issue_data["name"])
        issue_obj = SEOIssue(
            task=task,
            page_audit=issue_data["page_audit"],
            name=issue_data["name"],
            severity=issue_data["severity"],
            category=issue_data["category"],
            description=issue_data["description"],
            seo_impact=rec["seo_impact"],
            business_impact=rec["business_impact"],
            recommended_fix=rec["recommended_fix"],
            priority=rec["priority"],
        )
        issue_objects.append(issue_obj)
    timing_report["ai_recommendations_time"] = round(time.perf_counter() - recommendation_started_at, 4)
    SEOIssue.objects.bulk_create(issue_objects)
    timing_report["issue_detection_time"] = round(time.perf_counter() - issue_stage_started_at, 4)

    critical = sum(1 for issue in issue_objects if issue.severity == "critical")
    high = sum(1 for issue in issue_objects if issue.severity == "high")
    medium = sum(1 for issue in issue_objects if issue.severity == "medium")
    low = sum(1 for issue in issue_objects if issue.severity == "low")
    total = len(issue_objects)

    ai_stage_started_at = time.perf_counter()
    ai_opportunity_score = calculate_ai_opportunity_score(health_score, issue_objects)
    timing_report["ai_analysis_time"] = round(time.perf_counter() - ai_stage_started_at, 4)

    pages_crawled = len(page_audits)
    internal_links_count = sum(p.internal_links_count for p in page_audits)
    broken_internal_links_count = sum(p.broken_internal_links_count for p in page_audits)
    sitemap_entries_found = len(crawl_data.get("sitemap_entries", set()))
    orphan_pages_count = 0
    redirect_count = 0

    report_stage_started_at = time.perf_counter()
    from ..models import SEOHistoricalReport
    SEOHistoricalReport.objects.create(
        user=task.user,
        domain=task.domain,
        health_score=health_score,
        technical_score=technical_score,
        on_page_score=on_page_score,
        performance_score=performance_score,
    )

    result, created = SEOResult.objects.get_or_create(
        task=task,
        defaults={
            "final_url": root_page.final_url if root_page else task.url,
            "https_status": https_status,
            "main_status_code": root_page.status_code if root_page else 404,
            "main_response_time": root_page.response_time if root_page else 0,
            "health_score": health_score,
            "technical_score": technical_score.quantize(Decimal("0.00")),
            "on_page_score": on_page_score.quantize(Decimal("0.00")),
            "performance_score": performance_score.quantize(Decimal("0.00")),
            "discovery_score": discovery_score.quantize(Decimal("0.00")),
            "ai_opportunity_score": ai_opportunity_score.quantize(Decimal("0.00")),
            "critical_issues": critical,
            "high_issues": high,
            "medium_issues": medium,
            "low_issues": low,
            "total_issues": total,
            "pages_crawled": pages_crawled,
            "internal_links_count": internal_links_count,
            "broken_internal_links_count": broken_internal_links_count,
            "sitemap_entries_found": sitemap_entries_found,
            "orphan_pages_count": orphan_pages_count,
            "redirect_count": redirect_count,
        },
    )
    timing_report["report_generation_time"] = round(time.perf_counter() - report_stage_started_at, 4)

    timing_report["total_execution_time"] = round(
        crawl_data.get("performance_report", {}).get("total_execution_time", 0.0)
        + (time.perf_counter() - analysis_started_at),
        4,
    )
    timing_report["analysis_only_time"] = round(time.perf_counter() - analysis_started_at, 4)
    timing_report["pages_crawled"] = pages_crawled
    timing_report["requests_performed"] = crawl_data.get("performance_report", {}).get("requests_performed", 0)
    timing_report["cached_requests_reused"] = crawl_data.get("performance_report", {}).get("cached_requests_reused", 0)
    timing_report["stage_breakdown"] = crawl_data.get("performance_report", {}).get("stage_timings", {})
    _ANALYSIS_TIMING_REPORTS[task.id] = timing_report.copy()

    logger.info(
        "Website SEO analysis timing report for %s: total=%ss crawl=%ss parsing=%ss seo=%ss ai=%ss recommendations=%ss report=%ss pages=%s requests=%s cache_hits=%s stage_breakdown=%s",
        task.url,
        timing_report["total_execution_time"],
        timing_report["crawl_time"],
        timing_report["parsing_time"],
        timing_report["seo_analysis_time"],
        timing_report["ai_analysis_time"],
        timing_report["ai_recommendations_time"],
        timing_report["report_generation_time"],
        timing_report["pages_crawled"],
        timing_report["requests_performed"],
        timing_report["cached_requests_reused"],
        timing_report["stage_breakdown"],
    )
    return result
