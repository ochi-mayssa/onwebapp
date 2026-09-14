from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
from datetime import datetime, timezone
import logging
from time import perf_counter
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .backlink_engine import BacklinkAnalyzer
from .topic_intelligence import build_topic_intelligence, build_topic_intelligence_from_html
from .utils import (
    build_redirect_chain,
    classify_request_error,
    clean_text,
    extract_domain,
    normalize_url,
)

BACKLINK_FALLBACK_MESSAGE = (
    "Backlink data requires Moz, Ahrefs, Semrush, or Google Search Console integration."
)
logger = logging.getLogger(__name__)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
MAX_LINKS_PER_REPORT = 100
LINK_CHECK_MAX_WORKERS = 20
LINK_CHECK_TIMEOUT = 3
LINK_CHECK_MAX_REDIRECTS = 3

ANALYSIS_LABELS = {
    "internal": "Internal Links",
    "external": "External Links",
    "backlinks": "Backlink Intelligence",
}

STATUS_LABELS = {
    "working": "Working",
    "broken": "Broken",
    "redirect": "Redirect",
    "error": "Error",
}


def analyze_links(url: str, analysis_type: str) -> dict[str, Any]:
    normalized_url = normalize_url(url)
    if analysis_type == "backlinks":
        return _analyze_backlinks(normalized_url)
    return _analyze_page_links(normalized_url, analysis_type)


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _base_payload(url: str, analysis_type: str) -> dict[str, Any]:
    normalized_url = normalize_url(url)
    return {
        "url": normalized_url,
        "domain": extract_domain(normalized_url),
        "final_url": normalized_url,
        "analysis_type": analysis_type,
        "analysis_type_label": ANALYSIS_LABELS[analysis_type],
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "error_type": "",
        "message": "",
        "summary": {
            "total_links": 0,
            "working_links_count": 0,
            "broken_links_count": 0,
            "redirect_links_count": 0,
            "error_links_count": 0,
            "total_issues": 0,
        },
        "metrics_available": True,
        "provider_required": False,
        "supported_providers": [],
        "links": [],
        "error_links": [],
        "unavailable_details": [],
        "fallback_message": "",
        "recommendations": [],
        "status_badge": {
            "label": "Needs Improvement",
            "class": "bg-warning-subtle text-warning border border-warning-subtle",
        },
        "external_insights": {},
        "topic_intelligence": None,
    }


def _error_payload(payload: dict[str, Any], error_type: str, message: str) -> dict[str, Any]:
    payload["status"] = "error"
    payload["error_type"] = error_type
    payload["message"] = message
    payload["summary"]["error_links_count"] = 1
    payload["summary"]["total_issues"] = 1
    payload["unavailable_details"] = [message]
    payload["recommendations"] = [
        "Resolve the website access issue and rerun the selected link analysis."
    ]
    payload["status_badge"] = _build_status_badge(payload["summary"])
    return payload


def _mark_summary_not_available(payload: dict[str, Any]) -> None:
    payload["metrics_available"] = False
    payload["summary"] = {
        "total_links": None,
        "working_links_count": None,
        "broken_links_count": None,
        "redirect_links_count": None,
        "error_links_count": None,
        "total_issues": 0,
    }


def _provider_required_payload(payload: dict[str, Any], detail: str) -> dict[str, Any]:
    payload["status"] = "error"
    payload["provider_required"] = True
    payload["error_type"] = "Provider Required"
    payload["message"] = (
        "Backlink data is not available because no backlink provider is currently connected."
    )
    payload["fallback_message"] = BACKLINK_FALLBACK_MESSAGE
    payload["supported_providers"] = [
        "Google Search Console",
        "Moz",
        "Ahrefs",
        "Semrush",
    ]
    payload["unavailable_details"] = [detail]
    payload["recommendations"] = [
        "Backlink analysis requires external authority data that cannot be discovered through website crawling alone.",
        "Connect one of the supported providers to access Referring Domains, Backlinks, Anchor Text Distribution, Domain Authority, and Link Quality Metrics.",
    ]
    payload["status_badge"] = {
        "label": "Provider Required",
        "class": "bg-warning-subtle text-warning border border-warning-subtle",
    }
    _mark_summary_not_available(payload)
    return payload


def _analyze_page_links(url: str, analysis_type: str) -> dict[str, Any]:
    payload = _base_payload(url, analysis_type)
    session = _build_session()
    started_at = perf_counter()

    try:
        response = session.get(url, timeout=15, allow_redirects=True)
    except requests.RequestException as exc:
        error_type, message = classify_request_error(exc)
        return _error_payload(payload, error_type, message)

    if response.status_code >= 400:
        return _error_payload(
            payload,
            "HTTP Error",
            f"The website returned HTTP status {response.status_code}.",
        )

    content_type = response.headers.get("Content-Type", "")
    if "html" not in content_type.lower():
        return _error_payload(
            payload,
            "HTTP Error",
            "The website did not return an HTML page that can be analyzed.",
        )

    final_url = normalize_url(response.url)
    base_domain = extract_domain(final_url)
    payload["final_url"] = final_url
    payload["domain"] = base_domain
    payload["topic_intelligence"] = build_topic_intelligence_from_html(final_url, response.content)
    candidate_links, collection_stats = _collect_candidate_links(
        response.content,
        response.url,
        final_url,
        base_domain,
        analysis_type,
    )
    status_cache = _run_fast_link_checks(
        [candidate["link_url"] for candidate in candidate_links],
        analysis_type=analysis_type,
    )
    discovered_links = [
        _build_checked_link_row(candidate, status_cache[candidate["link_url"]], analysis_type)
        for candidate in candidate_links
    ]

    payload["links"] = discovered_links
    payload["summary"] = _build_summary(discovered_links)
    payload["error_links"] = [link for link in discovered_links if link["status"] != "working"]
    if analysis_type == "external":
        payload["external_insights"] = _build_external_insights(discovered_links)
    payload["recommendations"] = _build_page_link_recommendations(
        analysis_type,
        payload["summary"],
        payload["links"],
        payload.get("external_insights"),
    )
    payload["status_badge"] = _build_status_badge(payload["summary"])
    if not discovered_links:
        payload["message"] = "No Links Found"
    payload["performance_log"] = _build_performance_log(
        analysis_type=analysis_type,
        total_links_found=collection_stats["total_links_found"],
        unique_urls_checked=len(status_cache),
        duplicate_urls_skipped=collection_stats["duplicate_urls_skipped"],
        total_time_seconds=perf_counter() - started_at,
    )
    _log_performance(payload["performance_log"])
    return payload


def _analyze_backlinks(url: str) -> dict[str, Any]:
    payload = _base_payload(url, "backlinks")
    domain = extract_domain(url)
    payload["topic_intelligence"] = build_topic_intelligence(
        url=url,
        page_title=domain.replace(".", " "),
        meta_title=domain.replace(".", " "),
        h1="Backlink Intelligence",
        meta_description="Backlink visibility and authority intelligence for the analyzed domain.",
    )

    try:
        analyzer = BacklinkAnalyzer(api_provider="moz")
    except ValueError:
        return _provider_required_payload(
            payload,
            "No supported backlink provider is currently connected.",
        )

    try:
        report = analyzer.analyze_domain(domain)
    except Exception:
        return _provider_required_payload(
            payload,
            "The configured backlink provider could not return backlink data.",
        )

    backlink_rows: list[dict[str, Any]] = []
    for backlink in report.get("backlinks", [])[:MAX_LINKS_PER_REPORT]:
        verified = analyzer.verify_backlink_status(backlink.copy())
        status_key, status_detail = _map_backlink_status(
            verified.get("verification_status", ""),
            verified.get("http_status"),
        )
        backlink_rows.append(
            {
                "source_domain": verified.get("referring_domain")
                or extract_domain(verified.get("source_url", "")),
                "source_url": verified.get("source_url", ""),
                "target_url": verified.get("target_url") or url,
                "anchor_text": verified.get("anchor_text") or "-",
                "link_type": "DoFollow" if verified.get("is_dofollow") else "NoFollow",
                "domain_authority": verified.get("domain_authority"),
                "http_status_code": verified.get("http_status"),
                "status": status_key,
                "status_label": STATUS_LABELS[status_key],
                "status_detail": status_detail,
            }
        )

    payload["links"] = backlink_rows
    payload["summary"] = _build_summary(backlink_rows)
    payload["error_links"] = [link for link in backlink_rows if link["status"] != "working"]
    payload["recommendations"] = _build_backlink_recommendations(
        payload["summary"],
        payload["fallback_message"],
        backlink_rows,
    )
    payload["status_badge"] = _build_status_badge(payload["summary"])
    return payload


def _collect_candidate_links(
    html: bytes | str,
    source_url: str,
    final_url: str,
    base_domain: str,
    analysis_type: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    candidate_links: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    total_links_found = 0
    duplicate_urls_skipped = 0

    for anchor in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue

        absolute_url = normalize_url(urljoin(source_url, href))
        target_domain = extract_domain(absolute_url)
        is_internal = target_domain == base_domain

        if analysis_type == "internal" and not is_internal:
            continue
        if analysis_type == "external" and is_internal:
            continue

        total_links_found += 1
        if absolute_url in seen_urls:
            duplicate_urls_skipped += 1
            continue

        seen_urls.add(absolute_url)
        candidate = {
            "link_url": absolute_url,
            "anchor_text": clean_text(anchor.get_text(" ", strip=True)) or "-",
            "source_page": final_url,
        }
        if analysis_type == "external":
            candidate["external_domain"] = target_domain
        candidate_links.append(candidate)
        if len(candidate_links) >= MAX_LINKS_PER_REPORT:
            break

    return candidate_links, {
        "total_links_found": total_links_found,
        "duplicate_urls_skipped": duplicate_urls_skipped,
    }


def _run_fast_link_checks(urls: list[str], *, analysis_type: str) -> dict[str, tuple[int | None, str, str | dict[str, Any]]]:
    cache: dict[str, tuple[int | None, str, str | dict[str, Any]]] = {}
    unique_urls: list[str] = []

    for url in urls:
        normalized = normalize_url(url)
        if normalized in cache:
            continue
        cache[normalized] = (None, "error", "Unprocessed")
        unique_urls.append(normalized)

    if not unique_urls:
        return cache

    max_workers = min(LINK_CHECK_MAX_WORKERS, len(unique_urls))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_check_url_status_with_session, checked_url): checked_url
            for checked_url in unique_urls
        }
        for future in as_completed(future_map):
            checked_url = future_map[future]
            try:
                cache[checked_url] = future.result()
            except Exception as exc:  # pragma: no cover - defensive guard
                error_type, message = classify_request_error(exc)
                cache[checked_url] = (None, "error", f"{error_type}: {message}")

    return cache


def _check_url_status_with_session(url: str) -> tuple[int | None, str, str | dict[str, Any]]:
    session = _build_session()
    session.max_redirects = LINK_CHECK_MAX_REDIRECTS
    return _check_url_status(session, url)


def _check_url_status(session: requests.Session, url: str) -> tuple[int | None, str, str | dict[str, Any]]:
    try:
        response = session.head(url, timeout=LINK_CHECK_TIMEOUT, allow_redirects=True)
        if _should_fallback_to_get(response):
            response = session.get(
                url,
                timeout=LINK_CHECK_TIMEOUT,
                allow_redirects=True,
                stream=True,
            )
        status_code = response.status_code
        redirect_chain = build_redirect_chain(url, response)
        redirect_count = max(len(redirect_chain) - 1, 0)
        final_url = normalize_url(response.url)
    except requests.RequestException as exc:
        try:
            response = session.get(
                url,
                timeout=LINK_CHECK_TIMEOUT,
                allow_redirects=True,
                stream=True,
            )
            status_code = response.status_code
            redirect_chain = build_redirect_chain(url, response)
            redirect_count = max(len(redirect_chain) - 1, 0)
            final_url = normalize_url(response.url)
        except requests.RequestException as fallback_exc:
            error_type, message = classify_request_error(fallback_exc)
            return None, "error", f"{error_type}: {message}"

    detail = {
        "message": "OK",
        "redirect_count": redirect_count,
        "redirect_chain": redirect_chain,
        "final_url": final_url,
    }
    if redirect_count > 0:
        detail["message"] = f"Redirected {redirect_count} time(s) to {final_url}"
        return status_code, "redirect", detail
    if 200 <= status_code < 300:
        return status_code, "working", detail
    if status_code in {404, 410}:
        detail["message"] = f"Broken ({status_code})"
        return status_code, "broken", detail
    detail["message"] = f"Status {status_code}"
    return status_code, "error", detail


def _should_fallback_to_get(response: requests.Response) -> bool:
    return response.status_code in {403, 405, 429, 500, 501, 502, 503}


def _build_checked_link_row(
    candidate: dict[str, Any],
    status_result: tuple[int | None, str, str | dict[str, Any]],
    analysis_type: str,
) -> dict[str, Any]:
    status_code, status_key, status_detail = status_result
    link_data = {
        "link_url": candidate["link_url"],
        "anchor_text": candidate["anchor_text"],
        "source_page": candidate["source_page"],
        "http_status_code": status_code,
        "status": status_key,
        "status_label": STATUS_LABELS[status_key],
        "status_detail": status_detail,
        "final_link_url": candidate["link_url"],
        "redirect_count": 0,
        "redirect_chain": [candidate["link_url"]],
    }
    if analysis_type == "external":
        link_data["external_domain"] = candidate["external_domain"]

    if isinstance(status_detail, dict):
        link_data["status_detail"] = status_detail["message"]
        link_data["final_link_url"] = status_detail["final_url"]
        link_data["redirect_count"] = status_detail["redirect_count"]
        link_data["redirect_chain"] = status_detail["redirect_chain"]
    return link_data


def _build_performance_log(
    *,
    analysis_type: str,
    total_links_found: int,
    unique_urls_checked: int,
    duplicate_urls_skipped: int,
    total_time_seconds: float,
) -> dict[str, Any]:
    average_time = total_time_seconds / unique_urls_checked if unique_urls_checked else 0.0
    return {
        "analysis_type": analysis_type,
        "total_links_found": total_links_found,
        "unique_urls_checked": unique_urls_checked,
        "duplicate_urls_skipped": duplicate_urls_skipped,
        "total_time_seconds": round(total_time_seconds, 3),
        "average_time_per_checked_url": round(average_time, 3),
    }


def _log_performance(performance_log: dict[str, Any]) -> None:
    logger.info(
        "link_checker_performance analysis_type=%s total_links_found=%s unique_urls_checked=%s duplicate_urls_skipped=%s total_time_seconds=%s average_time_per_checked_url=%s",
        performance_log["analysis_type"],
        performance_log["total_links_found"],
        performance_log["unique_urls_checked"],
        performance_log["duplicate_urls_skipped"],
        performance_log["total_time_seconds"],
        performance_log["average_time_per_checked_url"],
    )


def _map_backlink_status(verification_status: str, http_status: int | None) -> tuple[str, str]:
    status_text = (verification_status or "").lower()
    if "active" in status_text or http_status == 200:
        return "working", verification_status or "Active"
    if "redirect" in status_text or (http_status is not None and 300 <= http_status < 400):
        return "redirect", verification_status or f"Redirect ({http_status})"
    if "dead" in status_text or http_status in {404, 410}:
        return "broken", verification_status or f"Broken ({http_status})"
    if "status" in status_text and http_status is not None and 200 <= http_status < 300:
        return "working", verification_status
    return "error", verification_status or "Provider verification unavailable"


def _build_summary(links: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(link["status"] for link in links)
    broken = counts["broken"]
    redirect = counts["redirect"]
    error = counts["error"]
    return {
        "total_links": len(links),
        "working_links_count": counts["working"],
        "broken_links_count": broken,
        "redirect_links_count": redirect,
        "error_links_count": error,
        "total_issues": broken + redirect + error,
    }


def _build_page_link_recommendations(
    analysis_type: str,
    summary: dict[str, int],
    links: list[dict[str, Any]],
    external_insights: dict[str, Any] | None = None,
) -> list[str]:
    if summary["total_links"] == 0:
        return [f"No links found for the selected {ANALYSIS_LABELS[analysis_type].lower()} analysis."]

    broken_count = summary["broken_links_count"]
    redirect_count = summary["redirect_links_count"]
    error_count = summary["error_links_count"]

    if broken_count == 0 and redirect_count == 0 and error_count == 0:
        if analysis_type == "internal":
            return [
                "Internal linking structure is healthy.",
                "No broken internal links detected.",
                "No redirect chains detected.",
                "Internal navigation appears accessible to users and crawlers.",
                "Continue monitoring link health regularly.",
            ]
        recommendations = [
            f"{ANALYSIS_LABELS[analysis_type]} are healthy.",
            "No broken links detected.",
            "No redirect chains detected.",
            "Link destinations appear accessible to users and crawlers.",
            "Continue monitoring link health regularly.",
        ]
        if analysis_type == "external" and external_insights:
            http_links = external_insights.get("security_analysis", {}).get(
                "http_external_links", 0
            )
            if http_links == 0:
                recommendations.append(
                    "All measured external links use HTTPS, which supports safer outbound navigation."
                )
        return recommendations

    recommendations: list[str] = []
    if broken_count:
        recommendations.append(
            f"Fix {broken_count} broken {ANALYSIS_LABELS[analysis_type].lower()} to remove dead-end user journeys."
        )
        recommendations.append(
            "Update or remove broken URLs so visitors and crawlers can reach the intended destination."
        )
    if redirect_count:
        recommendations.append(
            "Replace redirecting URLs with their final destination to improve crawl efficiency and page speed."
        )
    if error_count:
        recommendations.append(
            "Review links returning unexpected HTTP errors and verify whether they are blocked, rate-limited, or removed."
        )
    if analysis_type == "external" and external_insights:
        security_analysis = external_insights.get("security_analysis", {})
        http_links = security_analysis.get("http_external_links", 0)
        potentially_unsafe = security_analysis.get("potentially_unsafe_links", 0)
        quality_section = external_insights.get("quality_section", {})
        if http_links:
            recommendations.append(
                f"Replace {http_links} HTTP external links with HTTPS destinations where available to reduce trust and security risk."
            )
        if potentially_unsafe and potentially_unsafe != http_links:
            recommendations.append(
                "Review potentially unsafe external destinations and remove sources that no longer meet trust requirements."
            )
        if quality_section.get("domain_diversity") == "Low":
            recommendations.append(
                "Diversify outbound references across more external domains to reduce reliance on a narrow source set."
            )
        if quality_section.get("link_distribution") == "Highly Concentrated":
            recommendations.append(
                "Redistribute external citations more evenly across trusted domains instead of concentrating most links on a single source."
            )
    return recommendations


def _build_status_badge(summary: dict[str, int]) -> dict[str, str]:
    total_links = summary.get("total_links", 0) or 0
    broken_count = summary.get("broken_links_count", 0) or 0
    redirect_count = summary.get("redirect_links_count", 0) or 0
    error_count = summary.get("error_links_count", 0) or 0
    issue_weight = (broken_count * 3) + (error_count * 3) + redirect_count

    if total_links == 0:
        return {
            "label": "Needs Improvement",
            "class": "bg-warning-subtle text-warning border border-warning-subtle",
        }
    if issue_weight == 0:
        return {
            "label": "Excellent",
            "class": "bg-success-subtle text-success border border-success-subtle",
        }
    if broken_count == 0 and error_count == 0:
        return {
            "label": "Good",
            "class": "bg-primary-subtle text-primary border border-primary-subtle",
        }
    if issue_weight <= 5:
        return {
            "label": "Needs Improvement",
            "class": "bg-warning-subtle text-warning border border-warning-subtle",
        }
    return {
        "label": "Critical",
        "class": "bg-danger-subtle text-danger border border-danger-subtle",
    }


def _build_backlink_recommendations(
    summary: dict[str, int],
    fallback_message: str,
    backlinks: list[dict[str, Any]],
) -> list[str]:
    if fallback_message:
        return [
            "Backlink analysis requires external authority data that cannot be discovered through website crawling alone.",
            "Connect one of the supported providers to access Referring Domains, Backlinks, Anchor Text Distribution, Domain Authority, and Link Quality Metrics.",
        ]

    recommendations: list[str] = []
    if not backlinks:
        recommendations.append(
            "No backlinks were returned by the provider. Verify the domain, provider coverage, and subscription limits."
        )
    if summary["broken_links_count"]:
        recommendations.append(
            "Review broken backlinks and recover high-value referring pages where possible."
        )
    if summary["redirect_links_count"]:
        recommendations.append(
            "Update redirected backlink targets when the provider exposes destination changes."
        )
    if summary["working_links_count"]:
        recommendations.append(
            "Prioritize the strongest working backlinks for outreach replication and authority-building campaigns."
        )
    if not recommendations:
        recommendations.append(
            "Backlink data is available and currently healthy. Continue monitoring link quality and referring domain authority."
        )
    return recommendations


def _build_external_insights(links: list[dict[str, Any]]) -> dict[str, Any]:
    total_links = len(links)
    domain_counter: Counter[str] = Counter()
    domain_statuses: defaultdict[str, list[str]] = defaultdict(list)
    https_links = 0
    http_links = 0

    for link in links:
        domain = link.get("external_domain") or extract_domain(link.get("link_url", ""))
        if domain:
            domain_counter[domain] += 1
            domain_statuses[domain].append(link.get("status", "error"))
        if str(link.get("link_url", "")).lower().startswith("https://"):
            https_links += 1
        else:
            http_links += 1

    domain_distribution = []
    for domain, count in domain_counter.most_common():
        statuses = domain_statuses.get(domain, [])
        if "broken" in statuses or "error" in statuses:
            status = "Needs Attention"
        elif "redirect" in statuses:
            status = "Redirecting"
        else:
            status = "Healthy"
        domain_distribution.append(
            {
                "domain": domain,
                "link_count": count,
                "status": status,
            }
        )

    unique_domains = len(domain_counter)
    top_domain_share = 0.0
    if total_links:
        top_domain_share = max(domain_counter.values(), default=0) / total_links

    if unique_domains >= 5:
        domain_diversity = "Strong"
    elif unique_domains >= 2:
        domain_diversity = "Moderate"
    else:
        domain_diversity = "Low"

    if top_domain_share >= 0.7:
        link_distribution = "Highly Concentrated"
    elif top_domain_share >= 0.4:
        link_distribution = "Balanced"
    else:
        link_distribution = "Well Distributed"

    authority_available = "Not Available"
    if any(link.get("domain_authority") is not None for link in links):
        authority_available = "Available"

    return {
        "overview_metrics": {
            "total_external_links": total_links,
            "unique_external_domains": unique_domains,
            "working_external_links": sum(
                1 for link in links if link.get("status") == "working"
            ),
            "broken_external_links": sum(
                1 for link in links if link.get("status") == "broken"
            ),
            "redirecting_external_links": sum(
                1 for link in links if link.get("status") == "redirect"
            ),
        },
        "domain_distribution": domain_distribution,
        "security_analysis": {
            "https_external_links": https_links,
            "http_external_links": http_links,
            "potentially_unsafe_links": http_links,
        },
        "quality_section": {
            "authority_available": authority_available,
            "domain_diversity": domain_diversity,
            "link_distribution": link_distribution,
        },
    }
