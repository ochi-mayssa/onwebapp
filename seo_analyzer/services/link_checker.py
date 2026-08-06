from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
from datetime import datetime, timezone
import logging
from threading import Thread
from time import perf_counter
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
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
MAX_LINKS_PER_REPORT = 15
LINK_CHECK_MAX_WORKERS = 15
LINK_CHECK_TIMEOUT = (0.5, 1.0)
LINK_CHECK_MAX_REDIRECTS = 2
HTML_DOWNLOAD_TIMEOUT = (2, 5)

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
    adapter = HTTPAdapter(
        max_retries=0,
        pool_connections=10,
        pool_maxsize=20,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
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
        "findings": [],
        "health": None,
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
    if payload.get("analysis_type") == "internal":
        payload["health"] = build_internal_link_health(payload["summary"])
        payload["findings"] = build_internal_link_findings(payload["summary"], payload.get("links", []))
        payload["recommendations"] = [
            _build_internal_recommendation(
                "Resolve the website access issue and rerun the analyzed page internal links audit.",
                priority="High",
                difficulty="Easy",
                estimated_gain="+10 SEO Score",
                business_impact="Restores access to the analyzed page so internal link validation can complete.",
                estimated_time="10 minutes",
                confidence="High",
            )
        ]
        payload["status_badge"] = _build_status_badge_from_health(payload["health"])
    else:
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


def _download_html(session: requests.Session, url: str, total_timeout: float = 8.0) -> requests.Response:
    result: list[requests.Response | Exception] = []

    def _do_download():
        try:
            result.append(session.get(url, timeout=(2, 5), allow_redirects=True))
        except Exception as exc:
            result.append(exc)

    worker = Thread(target=_do_download, daemon=True)
    worker.start()
    worker.join(timeout=total_timeout)

    if worker.is_alive():
        raise requests.Timeout(
            f"Page download exceeded {total_timeout}s total timeout."
        )
    if not result:
        raise requests.ConnectionError("Page download produced no result.")
    if isinstance(result[0], Exception):
        raise result[0]
    return result[0]


def _analyze_page_links(url: str, analysis_type: str) -> dict[str, Any]:
    payload = _base_payload(url, analysis_type)
    session = _build_session()
    started_at = perf_counter()

    try:
        response = _download_html(session, url, total_timeout=8.0)
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
    if analysis_type == "internal":
        payload["error_links"] = [
            link for link in discovered_links if link["status"] in {"broken", "error"}
        ]
    else:
        payload["error_links"] = [link for link in discovered_links if link["status"] != "working"]
    if analysis_type == "external":
        payload["external_insights"] = _build_external_insights(discovered_links)
    if analysis_type == "internal":
        payload["health"] = build_internal_link_health(payload["summary"])
        payload["findings"] = build_internal_link_findings(payload["summary"], payload["links"])
        payload["recommendations"] = _build_page_link_recommendations(
            analysis_type,
            payload["summary"],
            payload["links"],
            payload.get("external_insights"),
        )
        payload["status_badge"] = _build_status_badge_from_health(payload["health"])
    else:
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

    session = _build_session()
    max_workers = min(LINK_CHECK_MAX_WORKERS, len(unique_urls))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_check_url_status, session, checked_url): checked_url
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


def _check_url_status(session: requests.Session, url: str) -> tuple[int | None, str, str | dict[str, Any]]:
    result: list[tuple[int | None, str, str | dict[str, Any]] | Exception] = []

    def _do_check():
        try:
            result.append(_check_url_status_inner(session, url))
        except Exception as exc:
            result.append(exc)

    worker = Thread(target=_do_check, daemon=True)
    worker.start()
    worker.join(timeout=3.0)

    if worker.is_alive():
        return None, "error", "Timeout: link check exceeded 3s"
    if not result:
        return None, "error", "Link check produced no result"
    if isinstance(result[0], Exception):
        error_type, message = classify_request_error(result[0])
        return None, "error", f"{error_type}: {message}"
    return result[0]


def _check_url_status_inner(session: requests.Session, url: str) -> tuple[int | None, str, str | dict[str, Any]]:
    try:
        head_response = session.head(
            url,
            timeout=(0.3, 1.0),
            allow_redirects=False,
        )
        status_code = head_response.status_code
        final_url = normalize_url(head_response.headers.get("Location", "") or url) if 300 <= status_code < 400 else url
        redirect_count = 1 if 300 <= status_code < 400 else 0
        redirect_chain = [url, final_url] if redirect_count else [url]
    except requests.RequestException:
        try:
            response = session.get(
                url,
                timeout=(0.3, 1.0),
                allow_redirects=False,
                stream=True,
            )
            status_code = response.status_code
            final_url = normalize_url(response.headers.get("Location", "") or url) if 300 <= status_code < 400 else url
            redirect_count = 1 if 300 <= status_code < 400 else 0
            redirect_chain = [url, final_url] if redirect_count else [url]
        except requests.RequestException as exc:
            error_type, message = classify_request_error(exc)
            return None, "error", f"{error_type}: {message}"

    detail = {
        "message": "OK",
        "redirect_count": redirect_count,
        "redirect_chain": redirect_chain,
        "final_url": final_url,
    }
    if 300 <= status_code < 400:
        if _is_authentication_redirect_url(final_url):
            detail["message"] = f"Authentication Required: redirected to {final_url}"
        else:
            detail["message"] = f"Redirected to {final_url}"
        return status_code, "redirect", detail
    if 200 <= status_code < 300:
        return status_code, "working", detail
    if 400 <= status_code < 600:
        detail["message"] = f"Broken ({status_code})"
        return status_code, "broken", detail
    detail["message"] = f"Unknown status ({status_code})"
    return status_code, "error", detail


def _is_authentication_redirect_url(url: str) -> bool:
    path = urlparse(url).path.lower().strip("/")
    auth_paths = {
        "accounts/login",
        "users/login",
        "login",
        "signin",
        "sign-in",
        "auth/login",
    }
    return path in auth_paths


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
) -> list[Any]:
    if analysis_type == "internal":
        return build_internal_link_recommendations(summary, links)
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


def build_internal_link_health(summary: dict[str, Any]) -> dict[str, Any]:
    total_links = int(summary.get("total_links") or 0)
    broken_links = int(summary.get("broken_links_count") or 0)
    error_links = int(summary.get("error_links_count") or 0)
    redirect_links = int(summary.get("redirect_links_count") or 0)

    if total_links <= 0:
        return {
            "score": 0,
            "label": "Critical",
            "grade": "D",
            "severity": "danger",
            "reason": "No internal links were discovered on the analyzed page.",
        }

    score = 100 - (broken_links * 8) - (error_links * 5) - (redirect_links * 2)
    score = max(0, min(100, score))

    if score >= 90:
        label = "Excellent"
        grade = "A"
        severity = "success"
    elif score >= 75:
        label = "Good"
        grade = "B"
        severity = "success"
    elif score >= 50:
        label = "Needs Attention"
        grade = "C"
        severity = "warning"
    else:
        label = "Critical"
        grade = "D"
        severity = "danger"

    reasons: list[str] = []
    if broken_links:
        reasons.append(f"{broken_links} broken internal link(s) reduce crawl reliability.")
    if error_links:
        reasons.append(f"{error_links} timeout or request error(s) prevent stable validation.")
    if redirect_links:
        reasons.append(f"{redirect_links} redirected link(s) add unnecessary hops.")
    if not reasons:
        reasons.append("All analyzed internal links resolve directly without redirects or errors.")

    return {
        "score": score,
        "label": label,
        "grade": grade,
        "severity": severity,
        "reason": " ".join(reasons),
    }


def build_internal_link_findings(summary: dict[str, Any], links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    broken_links = int(summary.get("broken_links_count") or 0)
    error_links = int(summary.get("error_links_count") or 0)
    redirect_links = int(summary.get("redirect_links_count") or 0)
    redirect_chains = sum(1 for link in links if int(link.get("redirect_count") or 0) > 1)
    empty_anchor_text = sum(
        1
        for link in links
        if not str(link.get("anchor_text") or "").strip() or str(link.get("anchor_text")).strip() == "-"
    )

    findings: list[dict[str, Any]] = []
    if broken_links > 0:
        findings.append(
            _build_internal_finding(
                issue="Broken Internal Links",
                severity="High",
                affected_count=broken_links,
                description="Broken destinations interrupt navigation and stop users or crawlers from reaching the intended page.",
                business_impact="Visitors can hit dead ends before reaching important content or conversion paths.",
                seo_impact="Broken internal references interrupt crawl flow and weaken internal discovery signals.",
                recommended_fix="Repair invalid destinations or replace them with valid internal URLs.",
                estimated_time="25 minutes" if broken_links <= 5 else "60 minutes",
                confidence="High",
            )
        )
    if error_links > 0:
        findings.append(
            _build_internal_finding(
                issue="Timeout / Error Links",
                severity="High",
                affected_count=error_links,
                description="Some internal destinations could not be validated because they timed out or returned request-level errors.",
                business_impact="Unstable links create unreliable navigation and reduce trust in critical user journeys.",
                seo_impact="Crawlers may fail to consistently reach the affected destinations during repeated audits.",
                recommended_fix="Review the affected destinations for timeout, SSL, DNS, or connection failures and stabilize the response path.",
                estimated_time="20 minutes" if error_links <= 3 else "45 minutes",
                confidence="High",
            )
        )
    if redirect_links > 0:
        findings.append(
            _build_internal_finding(
                issue="Redirected Internal Links",
                severity="Medium" if redirect_links < 5 else "High",
                affected_count=redirect_links,
                description="Some internal links resolve successfully only after one or more redirects.",
                business_impact="Users and crawlers need extra hops before reaching the final content destination.",
                seo_impact="Redirected internal links reduce crawl efficiency and dilute clean path signaling.",
                recommended_fix="Update internal links so they point directly to the final canonical destination.",
                estimated_time="15 minutes" if redirect_links < 5 else "35 minutes",
                confidence="High",
            )
        )
    if redirect_chains > 0:
        findings.append(
            _build_internal_finding(
                issue="Too Many Redirects",
                severity="Critical",
                affected_count=redirect_chains,
                description="Multi-hop redirect chains were detected in the analyzed page internal links set.",
                business_impact="Longer redirect paths slow user journeys and increase the risk of navigation abandonment.",
                seo_impact="Redirect chains waste crawl budget and weaken direct signal transfer to final pages.",
                recommended_fix="Replace chained destinations with direct final targets and remove intermediate hops.",
                estimated_time="20 minutes" if redirect_chains <= 3 else "45 minutes",
                confidence="High",
            )
        )
    if empty_anchor_text > 0:
        findings.append(
            _build_internal_finding(
                issue="Empty Anchor Text",
                severity="Low",
                affected_count=empty_anchor_text,
                description="Some internal links use empty or placeholder anchor text on the analyzed page.",
                business_impact="Users receive weaker context about where a link leads.",
                seo_impact="Low-context anchors reduce semantic clarity for crawlers and internal relevance signals.",
                recommended_fix="Replace empty or placeholder anchors with descriptive link text.",
                estimated_time="15 minutes",
                confidence="Medium",
            )
        )

    if findings:
        return findings

    return [
        _build_internal_finding(
            issue="No Issues",
            severity="Low",
            affected_count=0,
            description="The analyzed page internal links report does not currently show broken links, timeout errors, or redirect issues.",
            business_impact="Current navigation paths appear stable for users on the analyzed page.",
            seo_impact="Internal crawl paths currently appear clean and consistent for the analyzed page.",
            recommended_fix="Maintain the current internal linking quality and continue monitoring.",
            estimated_time="Ongoing monitoring",
            confidence="High",
        )
    ]


def build_internal_link_recommendations(summary: dict[str, Any], links: list[dict[str, Any]]) -> list[dict[str, str]]:
    if int(summary.get("total_links") or 0) == 0:
        return [
            _build_internal_recommendation(
                "No links found for the selected internal links analysis.",
                priority="Low",
                difficulty="Easy",
                estimated_gain="+0 SEO Score",
                business_impact="No internal destinations were available to validate on the analyzed page.",
                estimated_time="10 minutes",
                confidence="High",
            )
        ]

    broken_count = int(summary.get("broken_links_count") or 0)
    redirect_count = int(summary.get("redirect_links_count") or 0)
    error_count = int(summary.get("error_links_count") or 0)

    if broken_count == 0 and redirect_count == 0 and error_count == 0:
        return [
            _build_internal_recommendation(
                "Internal linking structure is healthy.",
                priority="Low",
                difficulty="Easy",
                estimated_gain="+3 SEO Score",
                business_impact="The analyzed page already provides stable internal navigation.",
                estimated_time="Ongoing monitoring",
                confidence="High",
            ),
            _build_internal_recommendation(
                "No broken internal links detected.",
                priority="Low",
                difficulty="Easy",
                estimated_gain="+0 SEO Score",
                business_impact="Visitors are not being sent to invalid destinations from the analyzed page.",
                estimated_time="Ongoing monitoring",
                confidence="High",
            ),
            _build_internal_recommendation(
                "No redirect chains detected.",
                priority="Low",
                difficulty="Easy",
                estimated_gain="+0 SEO Score",
                business_impact="Users and crawlers currently reach destinations without multi-hop friction.",
                estimated_time="Ongoing monitoring",
                confidence="High",
            ),
            _build_internal_recommendation(
                "Internal navigation appears accessible to users and crawlers.",
                priority="Low",
                difficulty="Easy",
                estimated_gain="+2 SEO Score",
                business_impact="The analyzed page supports predictable navigation paths.",
                estimated_time="Ongoing monitoring",
                confidence="Medium",
            ),
            _build_internal_recommendation(
                "Continue monitoring link health regularly.",
                priority="Low",
                difficulty="Easy",
                estimated_gain="+2 SEO Score",
                business_impact="Regular monitoring helps catch regressions before they affect users or search discovery.",
                estimated_time="15 minutes",
                confidence="High",
            ),
        ]

    recommendations: list[dict[str, str]] = []
    if broken_count:
        recommendations.append(
            _build_internal_recommendation(
                f"Fix {broken_count} broken internal links to remove dead-end user journeys.",
                priority="High",
                difficulty="Easy",
                estimated_gain="+18 SEO Score",
                business_impact="Broken destinations can interrupt important user and conversion paths on the analyzed page.",
                estimated_time="25 minutes" if broken_count <= 5 else "60 minutes",
                confidence="High",
            )
        )
        recommendations.append(
            _build_internal_recommendation(
                "Update or remove broken URLs so visitors and crawlers can reach the intended destination.",
                priority="High",
                difficulty="Medium",
                estimated_gain="+14 SEO Score",
                business_impact="Repairing invalid URLs improves navigation reliability and reduces user frustration.",
                estimated_time="30 minutes" if broken_count <= 5 else "75 minutes",
                confidence="High",
            )
        )
    if redirect_count:
        recommendations.append(
            _build_internal_recommendation(
                "Replace redirecting URLs with their final destination to improve crawl efficiency and page speed.",
                priority="Medium",
                difficulty="Easy",
                estimated_gain="+10 SEO Score",
                business_impact="Direct links reduce latency before users reach the final page.",
                estimated_time="15 minutes" if redirect_count < 5 else "35 minutes",
                confidence="High",
            )
        )
    if error_count:
        recommendations.append(
            _build_internal_recommendation(
                "Review links returning unexpected HTTP errors and verify whether they are blocked, rate-limited, or removed.",
                priority="Medium",
                difficulty="Medium",
                estimated_gain="+12 SEO Score",
                business_impact="Resolving unstable destinations improves confidence in the analyzed page navigation path.",
                estimated_time="20 minutes" if error_count <= 3 else "45 minutes",
                confidence="High",
            )
        )

    empty_anchor_count = sum(
        1
        for link in links
        if not str(link.get("anchor_text") or "").strip() or str(link.get("anchor_text")).strip() == "-"
    )
    if empty_anchor_count:
        recommendations.append(
            _build_internal_recommendation(
                "Replace empty anchor text with descriptive labels so each internal destination communicates clear intent.",
                priority="Low",
                difficulty="Easy",
                estimated_gain="+6 SEO Score",
                business_impact="Clear anchors improve navigation comprehension and editorial quality.",
                estimated_time="15 minutes",
                confidence="Medium",
            )
        )

    return recommendations


def _build_internal_finding(
    *,
    issue: str,
    severity: str,
    affected_count: int,
    description: str,
    business_impact: str,
    seo_impact: str,
    recommended_fix: str,
    estimated_time: str,
    confidence: str,
) -> dict[str, Any]:
    severity_title = severity.title()
    css_class = "finding-info"
    icon = "bi-info-circle-fill"
    if severity_title == "Critical":
        css_class = "finding-critical"
        icon = "bi-exclamation-octagon-fill"
    elif severity_title == "High":
        css_class = "finding-warning"
        icon = "bi-exclamation-triangle-fill"
    elif severity_title == "Medium":
        css_class = "finding-info"
        icon = "bi-arrow-repeat"
    elif severity_title == "Low":
        css_class = "finding-info"
        icon = "bi-shield-check"

    return {
        "issue": issue,
        "severity": severity_title,
        "affected_count": affected_count,
        "description": description,
        "business_impact": business_impact,
        "seo_impact": seo_impact,
        "recommended_fix": recommended_fix,
        "estimated_time": estimated_time,
        "confidence": confidence,
        "css_class": css_class,
        "icon": icon,
    }


def _build_internal_recommendation(
    text: str,
    *,
    priority: str,
    difficulty: str,
    estimated_gain: str,
    business_impact: str,
    estimated_time: str,
    confidence: str,
) -> dict[str, str]:
    return {
        "text": text,
        "priority": priority,
        "difficulty": difficulty,
        "estimated_gain": estimated_gain,
        "business_impact": business_impact,
        "estimated_time": estimated_time,
        "confidence": confidence,
    }


def _build_status_badge_from_health(health: dict[str, Any] | None) -> dict[str, str]:
    label = (health or {}).get("label", "Needs Attention")
    severity = (health or {}).get("severity", "warning")
    if severity == "success":
        text_class = "text-success"
        border_class = "border-success-subtle"
        bg_class = "bg-success-subtle"
        if label == "Good":
            text_class = "text-primary"
            border_class = "border-primary-subtle"
            bg_class = "bg-primary-subtle"
        return {
            "label": label,
            "class": f"{bg_class} {text_class} border {border_class}",
        }
    if severity == "danger":
        return {
            "label": label,
            "class": "bg-danger-subtle text-danger border border-danger-subtle",
        }
    return {
        "label": label,
        "class": "bg-warning-subtle text-warning border border-warning-subtle",
    }


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
