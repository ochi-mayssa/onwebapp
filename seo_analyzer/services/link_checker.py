from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
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

# Constants
BACKLINK_FALLBACK_MESSAGE = (
    "Backlink data requires Moz, Ahrefs, Semrush, or Google Search Console integration."
)
logger = logging.getLogger(__name__)

# Performance-optimized constants
MAX_LINKS_PER_REPORT = 15
LINK_CHECK_MAX_WORKERS = 30
LINK_CHECK_TIMEOUT = (0.3, 0.8)
LINK_CHECK_MAX_REDIRECTS = 2
HTML_DOWNLOAD_TIMEOUT = (1.5, 3.0)
BATCH_SIZE = 50
CONNECTION_POOL_SIZE = 50
MAX_HTML_SIZE = 1024 * 1024  # 1MB

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

# Global session pool
_session_pool = None


def analyze_links(url: str, analysis_type: str) -> dict[str, Any]:
    """Main entry point for link analysis with optimized performance."""
    normalized_url = normalize_url(url)
    if analysis_type == "backlinks":
        return _analyze_backlinks_optimized(normalized_url)
    return _analyze_page_links_optimized(normalized_url, analysis_type)


def _get_session_pool() -> requests.Session:
    """Get or create a shared session pool with connection reuse."""
    global _session_pool
    if _session_pool is None:
        _session_pool = requests.Session()
        adapter = HTTPAdapter(
            max_retries=0,
            pool_connections=CONNECTION_POOL_SIZE,
            pool_maxsize=CONNECTION_POOL_SIZE,
            pool_block=False,
        )
        _session_pool.mount("http://", adapter)
        _session_pool.mount("https://", adapter)
    return _session_pool


def _base_payload(url: str, analysis_type: str) -> dict[str, Any]:
    """Create base payload structure."""
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
        "performance_log": {},
    }


def _error_payload(payload: dict[str, Any], error_type: str, message: str) -> dict[str, Any]:
    """Create error payload with proper structure."""
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


def _provider_required_payload(payload: dict[str, Any], detail: str) -> dict[str, Any]:
    """Create provider required payload."""
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


def _mark_summary_not_available(payload: dict[str, Any]) -> None:
    """Mark summary as not available."""
    payload["metrics_available"] = False
    payload["summary"] = {
        "total_links": None,
        "working_links_count": None,
        "broken_links_count": None,
        "redirect_links_count": None,
        "error_links_count": None,
        "total_issues": 0,
    }


def _analyze_page_links_optimized(url: str, analysis_type: str) -> dict[str, Any]:
    """Optimized page link analysis with parallel processing."""
    payload = _base_payload(url, analysis_type)
    session = _get_session_pool()
    started_at = perf_counter()

    # Download HTML with optimized timeout
    try:
        response = _download_html_fast(session, url)
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
    
    # Build topic intelligence
    payload["topic_intelligence"] = build_topic_intelligence_from_html(final_url, response.content)
    
    # Extract links quickly from HTML
    candidate_links, collection_stats = _collect_candidate_links_fast(
        response.content,
        response.url,
        final_url,
        base_domain,
        analysis_type,
    )
    
    # Batch check links in parallel
    if candidate_links:
        status_cache = _run_fast_link_checks_optimized(
            [candidate["link_url"] for candidate in candidate_links]
        )
    else:
        status_cache = {}

    # Build link rows with status
    discovered_links = [
        _build_checked_link_row(candidate, status_cache.get(candidate["link_url"], (None, "error", "Not checked")), analysis_type)
        for candidate in candidate_links
    ]

    # Populate payload
    payload["links"] = discovered_links
    payload["summary"] = _build_summary(discovered_links)
    
    # Build analysis-specific data
    if analysis_type == "internal":
        payload["error_links"] = [link for link in discovered_links if link["status"] in {"broken", "error"}]
        payload["health"] = build_internal_link_health(payload["summary"])
        payload["findings"] = build_internal_link_findings(payload["summary"], payload["links"])
        payload["recommendations"] = _build_page_link_recommendations_optimized(
            analysis_type,
            payload["summary"],
            payload["links"],
        )
        payload["status_badge"] = _build_status_badge_from_health(payload["health"])
    else:
        payload["error_links"] = [link for link in discovered_links if link["status"] != "working"]
        if analysis_type == "external":
            payload["external_insights"] = _build_external_insights_fast(discovered_links)
        payload["recommendations"] = _build_page_link_recommendations_optimized(
            analysis_type,
            payload["summary"],
            payload["links"],
            payload.get("external_insights"),
        )
        payload["status_badge"] = _build_status_badge(payload["summary"])

    if not discovered_links:
        payload["message"] = "No Links Found"

    # Performance logging
    payload["performance_log"] = _build_performance_log(
        analysis_type=analysis_type,
        total_links_found=collection_stats["total_links_found"],
        unique_urls_checked=len(status_cache),
        duplicate_urls_skipped=collection_stats["duplicate_urls_skipped"],
        total_time_seconds=perf_counter() - started_at,
    )
    _log_performance(payload["performance_log"])
    
    return payload


def _download_html_fast(session: requests.Session, url: str) -> requests.Response:
    """Fast HTML download with streaming and limited content."""
    return session.get(
        url, 
        timeout=HTML_DOWNLOAD_TIMEOUT, 
        allow_redirects=True,
        stream=True,
        headers={
            'Accept-Encoding': 'gzip, deflate',
            'Cache-Control': 'no-cache',
            'User-Agent': 'Mozilla/5.0 (compatible; LinkChecker/1.0)'
        }
    )


def _collect_candidate_links_fast(
    html: bytes | str,
    source_url: str,
    final_url: str,
    base_domain: str,
    analysis_type: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Optimized link extraction with size limits."""
    candidate_links: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    total_links_found = 0
    duplicate_urls_skipped = 0
    
    # Limit HTML size for parsing
    if isinstance(html, bytes) and len(html) > MAX_HTML_SIZE:
        html_content = html[:MAX_HTML_SIZE]
    else:
        html_content = html
    
    # Parse HTML - use html.parser for speed
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Extract links in one pass
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue

        absolute_url = normalize_url(urljoin(source_url, href))
        if not absolute_url:
            continue
            
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
        
        # Get and clean anchor text
        anchor_text = anchor.get_text(" ", strip=True)
        if not anchor_text:
            anchor_text = "-"
        elif len(anchor_text) > 100:
            anchor_text = anchor_text[:97] + "..."
            
        candidate = {
            "link_url": absolute_url,
            "anchor_text": anchor_text,
            "source_page": final_url,
        }
        if analysis_type == "external":
            candidate["external_domain"] = target_domain
        candidate_links.append(candidate)
        
        if len(candidate_links) >= MAX_LINKS_PER_REPORT:
            break

    # Clean up
    soup.decompose()
    
    return candidate_links, {
        "total_links_found": total_links_found,
        "duplicate_urls_skipped": duplicate_urls_skipped,
    }


def _run_fast_link_checks_optimized(urls: list[str]) -> dict[str, tuple[int | None, str, str | dict[str, Any]]]:
    """Highly optimized parallel link checking with batching."""
    if not urls:
        return {}
    
    # Deduplicate URLs
    unique_urls = list(dict.fromkeys(normalize_url(url) for url in urls))
    cache: dict[str, tuple[int | None, str, str | dict[str, Any]]] = {}
    
    # Process in batches
    for i in range(0, len(unique_urls), BATCH_SIZE):
        batch = unique_urls[i:i + BATCH_SIZE]
        batch_cache = _check_urls_batch_optimized(batch)
        cache.update(batch_cache)
    
    return cache


def _check_urls_batch_optimized(urls: list[str]) -> dict[str, tuple[int | None, str, str | dict[str, Any]]]:
    """Check a batch of URLs with optimized connection pooling."""
    if not urls:
        return {}
    
    session = _get_session_pool()
    cache: dict[str, tuple[int | None, str, str | dict[str, Any]]] = {}
    
    max_workers = min(LINK_CHECK_MAX_WORKERS, len(urls))
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(_check_single_url_fast, session, url): url 
            for url in urls
        }
        
        # Process with overall timeout
        try:
            for future in as_completed(future_to_url, timeout=2.0):
                url = future_to_url[future]
                try:
                    cache[url] = future.result(timeout=0.5)
                except (TimeoutError, Exception):
                    cache[url] = (None, "error", "Timeout or error during check")
        except TimeoutError:
            # Cancel remaining futures
            for future in future_to_url:
                future.cancel()
            # Mark remaining as timeout
            for url in urls:
                if url not in cache:
                    cache[url] = (None, "error", "Batch timeout")
    
    return cache


def _check_single_url_fast(session: requests.Session, url: str) -> tuple[int | None, str, str | dict[str, Any]]:
    """Ultra-fast single URL check with minimal overhead."""
    # Try HEAD first
    try:
        response = session.head(
            url,
            timeout=(0.2, 0.5),
            allow_redirects=False,
            headers={'Accept-Encoding': 'gzip, deflate'}
        )
        status_code = response.status_code
        
        if 200 <= status_code < 300:
            return status_code, "working", {
                "message": "OK", 
                "redirect_count": 0, 
                "redirect_chain": [url], 
                "final_url": url
            }
        elif 300 <= status_code < 400:
            final_url = normalize_url(response.headers.get("Location", "")) or url
            if _is_authentication_redirect_url(final_url):
                message = f"Authentication Required: redirected to {final_url}"
            else:
                message = f"Redirected to {final_url}"
            return status_code, "redirect", {
                "message": message,
                "redirect_count": 1,
                "redirect_chain": [url, final_url],
                "final_url": final_url,
            }
        elif 400 <= status_code < 600:
            return status_code, "broken", {
                "message": f"Broken ({status_code})",
                "redirect_count": 0,
                "redirect_chain": [url],
                "final_url": url,
            }
        else:
            return status_code, "error", {
                "message": f"Unknown status ({status_code})",
                "redirect_count": 0,
                "redirect_chain": [url],
                "final_url": url,
            }
            
    except requests.RequestException:
        # Fallback to GET if HEAD fails
        try:
            response = session.get(
                url,
                timeout=(0.3, 0.6),
                allow_redirects=False,
                stream=True,
                headers={'Accept-Encoding': 'gzip, deflate'}
            )
            # Close immediately to avoid reading body
            response.close()
            status_code = response.status_code
            
            if 200 <= status_code < 300:
                return status_code, "working", {
                    "message": "OK",
                    "redirect_count": 0,
                    "redirect_chain": [url],
                    "final_url": url,
                }
            elif 300 <= status_code < 400:
                final_url = normalize_url(response.headers.get("Location", "")) or url
                if _is_authentication_redirect_url(final_url):
                    message = f"Authentication Required: redirected to {final_url}"
                else:
                    message = f"Redirected to {final_url}"
                return status_code, "redirect", {
                    "message": message,
                    "redirect_count": 1,
                    "redirect_chain": [url, final_url],
                    "final_url": final_url,
                }
            elif 400 <= status_code < 600:
                return status_code, "broken", {
                    "message": f"Broken ({status_code})",
                    "redirect_count": 0,
                    "redirect_chain": [url],
                    "final_url": url,
                }
            else:
                return status_code, "error", {
                    "message": f"Unknown status ({status_code})",
                    "redirect_count": 0,
                    "redirect_chain": [url],
                    "final_url": url,
                }
                
        except requests.RequestException as exc:
            error_type, message = classify_request_error(exc)
            return None, "error", f"{error_type}: {message}"
    
    return None, "error", "Unknown error"


def _is_authentication_redirect_url(url: str) -> bool:
    """Check if URL is an authentication page."""
    path = urlparse(url).path.lower().strip("/")
    auth_paths = {
        "accounts/login",
        "users/login",
        "login",
        "signin",
        "sign-in",
        "auth/login",
        "auth",
        "account",
        "authenticate",
    }
    return path in auth_paths or any(p in path for p in auth_paths)


def _build_checked_link_row(
    candidate: dict[str, Any],
    status_result: tuple[int | None, str, str | dict[str, Any]],
    analysis_type: str,
) -> dict[str, Any]:
    """Build complete link row with status information."""
    status_code, status_key, status_detail = status_result
    
    link_data = {
        "link_url": candidate["link_url"],
        "anchor_text": candidate["anchor_text"],
        "source_page": candidate["source_page"],
        "http_status_code": status_code,
        "status": status_key,
        "status_label": STATUS_LABELS.get(status_key, status_key.title()),
        "status_detail": status_detail if isinstance(status_detail, str) else status_detail.get("message", str(status_detail)),
        "final_link_url": candidate["link_url"],
        "redirect_count": 0,
        "redirect_chain": [candidate["link_url"]],
    }
    
    if analysis_type == "external":
        link_data["external_domain"] = candidate["external_domain"]

    if isinstance(status_detail, dict):
        link_data["status_detail"] = status_detail.get("message", "OK")
        link_data["final_link_url"] = status_detail.get("final_url", candidate["link_url"])
        link_data["redirect_count"] = status_detail.get("redirect_count", 0)
        link_data["redirect_chain"] = status_detail.get("redirect_chain", [candidate["link_url"]])
    
    return link_data


def _build_summary(links: list[dict[str, Any]]) -> dict[str, int]:
    """Build summary statistics from links."""
    counts = Counter(link["status"] for link in links)
    broken = counts.get("broken", 0)
    redirect = counts.get("redirect", 0)
    error = counts.get("error", 0)
    return {
        "total_links": len(links),
        "working_links_count": counts.get("working", 0),
        "broken_links_count": broken,
        "redirect_links_count": redirect,
        "error_links_count": error,
        "total_issues": broken + redirect + error,
    }


def _build_page_link_recommendations_optimized(
    analysis_type: str,
    summary: dict[str, int],
    links: list[dict[str, Any]],
    external_insights: dict[str, Any] | None = None,
) -> list[Any]:
    """Optimized recommendations with early returns."""
    total_links = summary.get("total_links", 0)
    
    if total_links == 0:
        if analysis_type == "internal":
            return [_build_internal_recommendation(
                "No internal links found on this page.",
                priority="Low",
                difficulty="Easy",
                estimated_gain="+0 SEO Score",
                business_impact="No internal navigation paths to validate.",
                estimated_time="5 minutes",
                confidence="High",
            )]
        return [f"No {analysis_type} links found for analysis."]
    
    if analysis_type == "internal":
        return build_internal_link_recommendations(summary, links)
    
    # External links recommendations
    broken_count = summary.get("broken_links_count", 0)
    redirect_count = summary.get("redirect_links_count", 0)
    error_count = summary.get("error_links_count", 0)
    
    recommendations = []
    
    if broken_count:
        recommendations.append(
            f"Fix {broken_count} broken external links to maintain user trust and SEO."
        )
    if redirect_count:
        recommendations.append(
            f"Update {redirect_count} redirecting external links to their final destinations."
        )
    if error_count:
        recommendations.append(
            f"Investigate {error_count} external links with connection errors."
        )
    if not recommendations:
        recommendations.append("All external links are currently accessible.")
    
    # Add security insights
    if external_insights:
        security = external_insights.get("security_analysis", {})
        if security.get("http_external_links", 0) > 0:
            recommendations.append(
                f"Update {security['http_external_links']} HTTP external links to HTTPS where possible."
            )
    
    return recommendations


def _build_external_insights_fast(links: list[dict[str, Any]]) -> dict[str, Any]:
    """Fast external insights building with Counter optimization."""
    if not links:
        return {
            "overview_metrics": {"total_external_links": 0},
            "domain_distribution": [],
            "security_analysis": {
                "https_external_links": 0, 
                "http_external_links": 0,
                "potentially_unsafe_links": 0
            },
            "quality_section": {
                "authority_available": "Not Available",
                "domain_diversity": "Low",
                "link_distribution": "Balanced"
            }
        }
    
    # Use Counter for faster aggregation
    domain_counter = Counter()
    status_counter = Counter()
    https_count = 0
    
    for link in links:
        domain = link.get("external_domain") or extract_domain(link.get("link_url", ""))
        if domain:
            domain_counter[domain] += 1
        status_counter[link.get("status", "error")] += 1
        
        if str(link.get("link_url", "")).lower().startswith("https://"):
            https_count += 1
    
    total_links = len(links)
    http_count = total_links - https_count
    unique_domains = len(domain_counter)
    
    # Build domain distribution (top 10)
    domain_distribution = []
    for domain, count in domain_counter.most_common(10):
        domain_distribution.append({
            "domain": domain,
            "link_count": count,
            "status": "Healthy" if domain not in [l.get("external_domain") for l in links if l.get("status") in ["broken", "error"]] else "Needs Attention"
        })
    
    # Determine diversity
    if unique_domains >= 5:
        diversity = "Strong"
    elif unique_domains >= 2:
        diversity = "Moderate"
    else:
        diversity = "Low"
    
    # Determine distribution
    top_domain_share = max(domain_counter.values(), default=0) / total_links if total_links > 0 else 0
    if top_domain_share >= 0.7:
        distribution = "Highly Concentrated"
    elif top_domain_share >= 0.4:
        distribution = "Balanced"
    else:
        distribution = "Well Distributed"
    
    return {
        "overview_metrics": {
            "total_external_links": total_links,
            "unique_external_domains": unique_domains,
            "working_external_links": status_counter.get("working", 0),
            "broken_external_links": status_counter.get("broken", 0),
            "redirecting_external_links": status_counter.get("redirect", 0),
        },
        "domain_distribution": domain_distribution,
        "security_analysis": {
            "https_external_links": https_count,
            "http_external_links": http_count,
            "potentially_unsafe_links": http_count,
        },
        "quality_section": {
            "authority_available": "Available" if any(link.get("domain_authority") for link in links) else "Not Available",
            "domain_diversity": diversity,
            "link_distribution": distribution,
        }
    }


def _analyze_backlinks_optimized(url: str) -> dict[str, Any]:
    """Optimized backlink analysis with timeout protection."""
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

    # Add timeout protection for backlink analysis
    try:
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError("Backlink analysis timed out")
        
        # Set timeout (5 seconds)
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(5)
        
        try:
            report = analyzer.analyze_domain(domain)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
            
    except (TimeoutError, Exception) as e:
        return _provider_required_payload(
            payload,
            f"The configured backlink provider could not return backlink data: {str(e)}",
        )

    # Process backlinks
    backlink_rows = []
    for backlink in report.get("backlinks", [])[:MAX_LINKS_PER_REPORT]:
        # Quick verification
        verified = _verify_backlink_fast(backlink)
        status_key, status_detail = _map_backlink_status(
            verified.get("verification_status", ""),
            verified.get("http_status"),
        )
        backlink_rows.append({
            "source_domain": verified.get("referring_domain") or extract_domain(verified.get("source_url", "")),
            "source_url": verified.get("source_url", ""),
            "target_url": verified.get("target_url") or url,
            "anchor_text": verified.get("anchor_text") or "-",
            "link_type": "DoFollow" if verified.get("is_dofollow") else "NoFollow",
            "domain_authority": verified.get("domain_authority"),
            "http_status_code": verified.get("http_status"),
            "status": status_key,
            "status_label": STATUS_LABELS.get(status_key, status_key.title()),
            "status_detail": status_detail,
        })

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


def _verify_backlink_fast(backlink: dict[str, Any]) -> dict[str, Any]:
    """Fast backlink verification with minimal checks."""
    url = backlink.get("source_url", "")
    if not url:
        return backlink
    
    try:
        session = _get_session_pool()
        response = session.head(url, timeout=(0.3, 0.5), allow_redirects=False)
        backlink["http_status"] = response.status_code
        if 200 <= response.status_code < 300:
            backlink["verification_status"] = "active"
        elif 300 <= response.status_code < 400:
            backlink["verification_status"] = "redirect"
        elif 400 <= response.status_code < 600:
            backlink["verification_status"] = "dead"
        else:
            backlink["verification_status"] = "unknown"
    except Exception:
        backlink["verification_status"] = "unverified"
    
    return backlink


def _map_backlink_status(verification_status: str, http_status: int | None) -> tuple[str, str]:
    """Map backlink status to standard status keys."""
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


def _build_backlink_recommendations(
    summary: dict[str, int],
    fallback_message: str,
    backlinks: list[dict[str, Any]],
) -> list[str]:
    """Build backlink-specific recommendations."""
    if fallback_message:
        return [
            "Backlink analysis requires external authority data that cannot be discovered through website crawling alone.",
            "Connect one of the supported providers to access Referring Domains, Backlinks, Anchor Text Distribution, Domain Authority, and Link Quality Metrics.",
        ]

    recommendations = []
    if not backlinks:
        recommendations.append(
            "No backlinks were returned by the provider. Verify the domain, provider coverage, and subscription limits."
        )
    if summary.get("broken_links_count", 0):
        recommendations.append(
            "Review broken backlinks and recover high-value referring pages where possible."
        )
    if summary.get("redirect_links_count", 0):
        recommendations.append(
            "Update redirected backlink targets when the provider exposes destination changes."
        )
    if summary.get("working_links_count", 0):
        recommendations.append(
            "Prioritize the strongest working backlinks for outreach replication and authority-building campaigns."
        )
    if not recommendations:
        recommendations.append(
            "Backlink data is available and currently healthy. Continue monitoring link quality and referring domain authority."
        )
    return recommendations


def build_internal_link_health(summary: dict[str, Any]) -> dict[str, Any]:
    """Build health score for internal links."""
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

    # Calculate score with weighted penalties
    score = 100 - (broken_links * 8) - (error_links * 5) - (redirect_links * 2)
    score = max(0, min(100, score))

    if score >= 90:
        label, grade, severity = "Excellent", "A", "success"
    elif score >= 75:
        label, grade, severity = "Good", "B", "success"
    elif score >= 50:
        label, grade, severity = "Needs Attention", "C", "warning"
    else:
        label, grade, severity = "Critical", "D", "danger"

    reasons = []
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
    """Build findings for internal links."""
    broken_links = int(summary.get("broken_links_count") or 0)
    error_links = int(summary.get("error_links_count") or 0)
    redirect_links = int(summary.get("redirect_links_count") or 0)
    redirect_chains = sum(1 for link in links if int(link.get("redirect_count") or 0) > 1)
    empty_anchor_text = sum(
        1
        for link in links
        if not str(link.get("anchor_text") or "").strip() or str(link.get("anchor_text")).strip() == "-"
    )

    findings = []
    
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
    """Build recommendations for internal links."""
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

    recommendations = []
    
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
    """Build internal finding structure."""
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
    """Build internal recommendation structure."""
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
    """Build status badge from health data."""
    if not health:
        return {
            "label": "Needs Improvement",
            "class": "bg-warning-subtle text-warning border border-warning-subtle",
        }
    
    label = health.get("label", "Needs Attention")
    severity = health.get("severity", "warning")
    
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
    """Build status badge from summary."""
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


def _build_performance_log(
    *,
    analysis_type: str,
    total_links_found: int,
    unique_urls_checked: int,
    duplicate_urls_skipped: int,
    total_time_seconds: float,
) -> dict[str, Any]:
    """Build performance log."""
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
    """Log performance metrics."""
    logger.info(
        "link_checker_performance analysis_type=%s total_links_found=%s unique_urls_checked=%s duplicate_urls_skipped=%s total_time_seconds=%s average_time_per_checked_url=%s",
        performance_log["analysis_type"],
        performance_log["total_links_found"],
        performance_log["unique_urls_checked"],
        performance_log["duplicate_urls_skipped"],
        performance_log["total_time_seconds"],
        performance_log["average_time_per_checked_url"],
    )
