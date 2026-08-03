import time
from collections import Counter
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.utils import timezone

from .url_intelligence_recommender import build_ai_recommendations, detect_url_issues
from .url_intelligence_scoring import calculate_url_health_scores
from .url_intelligence_utils import (
    analyze_depth_structure,
    analyze_numeric_slug,
    build_optimized_url,
    classify_keyword_match,
    classify_query_parameters,
    dynamic_url_detected,
    extract_url_components,
    normalize_comparison_url,
    safe_normalize_url,
    slug_tokens,
    special_character_count,
    strip_tracking_parameters,
    tracking_only_query,
)
from .utils import build_http_session, build_redirect_chain, classify_request_error


HTTP_RESPONSE_CLASSIFICATIONS = {
    401: {
        "status": "auth_required",
        "label": "Authentication Required",
        "explanation": "The page requires authentication or authorization.",
    },
    403: {
        "status": "access_restricted",
        "label": "Access Restricted",
        "explanation": "The analyzer received HTTP 403 and could not fully access the page. This may be caused by bot protection, firewall rules, CDN/WAF security, authentication, or request filtering. This result does not confirm that search engines receive the same response.",
    },
    404: {
        "status": "not_found",
        "label": "Not Found",
        "explanation": "The URL returned HTTP 404 and was not found.",
    },
    410: {
        "status": "gone",
        "label": "Gone",
        "explanation": "The URL returned HTTP 410 and appears to be permanently gone.",
    },
    429: {
        "status": "rate_limited",
        "label": "Rate Limited",
        "explanation": "The analyzer was temporarily rate-limited and could not reliably inspect the page.",
    },
}


def classify_http_response(status_code, request_failed):
    if request_failed or status_code is None:
        return {
            "status": "request_failed",
            "label": "Request Failed",
            "explanation": "The analyzer could not complete the request and could not verify page accessibility.",
        }
    if 200 <= status_code < 300:
        return {
            "status": "accessible",
            "label": "Accessible",
            "explanation": "The analyzer accessed the page successfully.",
        }
    if 300 <= status_code < 400:
        return {
            "status": "redirect",
            "label": "Redirect",
            "explanation": "The request resolved through a redirect response.",
        }
    if status_code in HTTP_RESPONSE_CLASSIFICATIONS:
        return HTTP_RESPONSE_CLASSIFICATIONS[status_code]
    if 500 <= status_code < 600:
        return {
            "status": "server_error",
            "label": "Server Error",
            "explanation": "The server returned a 5xx response and the page could not be reliably inspected.",
        }
    return {
        "status": "http_error",
        "label": "HTTP Error",
        "explanation": "The request returned an unexpected HTTP error response.",
    }


def analyze_url_intelligence_task(task):
    if task.started_at is None:
        task.started_at = timezone.now()
    task.status = "running"
    task.save(update_fields=["status", "started_at"])

    try:
        report = analyze_url(task.url, target_keyword=task.target_keyword)
        task.status = "completed"
        task.completed_at = report["completed_at"]
        task.error_message = ""
        task.save(update_fields=["status", "completed_at", "error_message"])
        return report
    except Exception as exc:  # pragma: no cover - defensive task state update
        task.status = "failed"
        task.completed_at = timezone.now()
        task.error_message = str(exc)
        task.save(update_fields=["status", "completed_at", "error_message"])
        raise


def analyze_url(url, *, target_keyword=""):
    normalized_input = safe_normalize_url(url)
    original_components = extract_url_components(normalized_input)
    request_url = urlparse(normalized_input)._replace(fragment="").geturl()
    session = build_http_session()
    response = None
    response_time = None
    request_failed = False
    error_type = ""
    error_message = ""
    started = time.perf_counter()

    try:
        response = session.get(
            request_url,
            timeout=6,
            allow_redirects=True,
        )
        response_time = round(time.perf_counter() - started, 3)
    except requests.RequestException as exc:
        response_time = round(time.perf_counter() - started, 3)
        request_failed = True
        error_type, error_message = classify_request_error(exc)

    final_url = response.url if response is not None else request_url
    redirect_chain = build_redirect_chain(request_url, response) if response is not None else [request_url]
    redirect_count = max(0, len(redirect_chain) - 1)
    analyzed_url = final_url or normalized_input
    parsed_components = extract_url_components(analyzed_url)
    status_code = response.status_code if response is not None else None
    http_access = classify_http_response(status_code, request_failed)
    parameters_payload = classify_query_parameters(analyzed_url)
    keyword_match_status, keyword_match_pct, matched_keywords = classify_keyword_match(
        parsed_components["slug"],
        target_keyword,
    )

    html_content = ""
    canonical_url = ""
    meta_robots = ""
    x_robots_tag = ""
    canonical_status = "unknown"
    canonical_matches = False
    canonical_to_clean_url = False

    if response is not None:
        x_robots_tag = response.headers.get("X-Robots-Tag", "").strip()
        content_type = response.headers.get("Content-Type", "")
        can_evaluate_html = 200 <= response.status_code < 300 and "html" in content_type.lower()
        if can_evaluate_html:
            html_content = response.text
            soup = BeautifulSoup(html_content, "html.parser")
            canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value.lower())
            if canonical_tag and canonical_tag.get("href"):
                canonical_url = urljoin(response.url, canonical_tag.get("href").strip())
            meta_robots_tag = soup.find("meta", attrs={"name": lambda value: value and value.lower() == "robots"})
            if meta_robots_tag and meta_robots_tag.get("content"):
                meta_robots = meta_robots_tag.get("content").strip()
    else:
        can_evaluate_html = False

    final_normalized = normalize_comparison_url(analyzed_url)
    final_clean_normalized = normalize_comparison_url(strip_tracking_parameters(analyzed_url))
    if canonical_url:
        canonical_normalized = normalize_comparison_url(canonical_url)
        canonical_clean_normalized = normalize_comparison_url(strip_tracking_parameters(canonical_url))
        canonical_matches = canonical_normalized == final_normalized
        canonical_to_clean_url = (
            canonical_clean_normalized == final_clean_normalized
            and canonical_normalized != final_normalized
            and tracking_only_query(parameters_payload)
        )
        if canonical_matches:
            canonical_status = "self"
        elif canonical_to_clean_url:
            canonical_status = "other"
        elif redirect_count > 0 and canonical_normalized == normalize_comparison_url(normalized_input):
            canonical_status = "conflict"
        else:
            canonical_status = "other"
    elif html_content and can_evaluate_html:
        canonical_status = "missing"
    elif http_access["status"] in {"auth_required", "access_restricted", "rate_limited"}:
        canonical_status = "not_evaluated"
    elif not can_evaluate_html:
        canonical_status = "not_evaluated"

    robots_directives = " ".join(filter(None, [meta_robots.lower(), x_robots_tag.lower()]))
    if request_failed:
        indexability_status = "error"
    elif status_code == 401:
        indexability_status = "not_evaluated_auth_required"
    elif status_code == 403:
        indexability_status = "not_evaluated_access_restricted"
    elif status_code == 429:
        indexability_status = "not_evaluated_rate_limited"
    elif status_code == 404:
        indexability_status = "not_found"
    elif status_code == 410:
        indexability_status = "gone"
    elif status_code and 500 <= status_code < 600:
        indexability_status = "server_error"
    elif "noindex" in robots_directives or "none" in robots_directives:
        indexability_status = "noindex"
    elif redirect_count > 0:
        indexability_status = "redirected"
    elif response is not None and 200 <= response.status_code < 300:
        indexability_status = "indexable"
    else:
        indexability_status = "unknown"

    decoded_path = unquote(parsed_components["path"])
    slug_words = slug_tokens(parsed_components["slug"])
    numeric_slug_analysis = analyze_numeric_slug(parsed_components["slug"])
    depth_analysis = analyze_depth_structure(parsed_components["segments"])
    is_root_homepage = parsed_components["depth"] == 0 and parsed_components["path"] in {"", "/"}
    if is_root_homepage:
        slug_clarity = "not_applicable"
    elif not parsed_components["slug"]:
        slug_clarity = "weak"
    elif len(slug_words) >= 2 and not any(char.isupper() for char in decoded_path) and "_" not in decoded_path:
        slug_clarity = "strong"
    elif slug_words:
        slug_clarity = "fair"
    else:
        slug_clarity = "weak"

    if is_root_homepage and target_keyword:
        keyword_match_status = "not_applicable"
        keyword_match_pct = 0
        matched_keywords = []

    if (
        len(decoded_path) > 90
        or "_" in decoded_path
        or any(char.isupper() for char in decoded_path)
        or depth_analysis["issue_detected"]
        or dynamic_url_detected(analyzed_url)
    ):
        url_readability = "poor"
    elif parsed_components["query"] or len(decoded_path) > 50:
        url_readability = "average"
    else:
        url_readability = "good"

    structure_payload = {
        "protocol": parsed_components["protocol"],
        "domain": parsed_components["domain"],
        "subdomain": parsed_components["subdomain"] or "None",
        "path": parsed_components["path"] or "/",
        "slug": parsed_components["slug"] or "None",
        "parameters": parameters_payload["all"],
        "fragment": original_components["fragment"] or "None",
        "url_readability": url_readability,
        "slug_clarity": slug_clarity,
        "keyword_match_pct": keyword_match_pct,
        "matched_keywords": matched_keywords,
        "is_root_homepage": is_root_homepage,
        "depth_classification": depth_analysis["classification"],
        "depth_status": depth_analysis["status"],
        "depth_finding": depth_analysis["finding"],
        "numeric_id_prefix_detected": numeric_slug_analysis["numeric_id_prefix_detected"],
        "numeric_heavy_slug": numeric_slug_analysis["numeric_heavy_slug"],
        "numeric_token_ratio": numeric_slug_analysis["numeric_token_ratio"],
        "digit_ratio": numeric_slug_analysis["digit_ratio"],
        "canonical_to_clean_url": canonical_to_clean_url,
    }

    analysis = {
        "input_url": url,
        "original_url": normalized_input,
        "analyzed_url": analyzed_url,
        "final_url": final_url,
        "http_status_code": status_code,
        "access_status": http_access["status"],
        "access_status_label": http_access["label"],
        "access_status_explanation": http_access["explanation"],
        "response_time": response_time,
        "https_status": urlparse(analyzed_url).scheme.lower() == "https",
        "redirect_detected": redirect_count > 0,
        "redirect_count": redirect_count,
        "redirect_chain": redirect_chain,
        "protocol": parsed_components["protocol"],
        "domain": parsed_components["domain"],
        "subdomain": parsed_components["subdomain"],
        "path": parsed_components["path"],
        "slug": parsed_components["slug"],
        "is_root_homepage": is_root_homepage,
        "fragment_value": original_components["fragment"],
        "url_length": len(analyzed_url),
        "url_depth": parsed_components["depth"],
        "depth_segments": parsed_components["segments"],
        "depth_classification": depth_analysis["classification"],
        "depth_status": depth_analysis["status"],
        "depth_finding": depth_analysis["finding"],
        "depth_issue_detected": depth_analysis["issue_detected"],
        "depth_evidence": " / ".join(parsed_components["segments"]) if parsed_components["segments"] else "/",
        "trailing_slash": parsed_components["trailing_slash"],
        "has_uppercase": any(char.isupper() for char in decoded_path),
        "has_underscores": "_" in decoded_path,
        "hyphen_count": decoded_path.count("-"),
        "special_character_count": special_character_count(decoded_path),
        "encoded_space_detected": "%20" in parsed_components["path"].lower() or " " in parsed_components["path"],
        "numeric_id_prefix_detected": numeric_slug_analysis["numeric_id_prefix_detected"],
        "numeric_slug_detected": numeric_slug_analysis["numeric_heavy_slug"],
        "query_params_count": len(parameters_payload["all"]),
        "tracking_params_count": len(parameters_payload["tracking"]),
        "functional_params_count": len(parameters_payload["functional"]),
        "unnecessary_params_count": len(parameters_payload["unnecessary"]),
        "tracking_only_query": tracking_only_query(parameters_payload),
        "has_fragment": bool(original_components["fragment"]),
        "dynamic_url_detected": dynamic_url_detected(analyzed_url),
        "canonical_url": canonical_url,
        "canonical_status": canonical_status,
        "canonical_matches": canonical_matches,
        "canonical_to_clean_url": canonical_to_clean_url,
        "canonical_evaluated": can_evaluate_html,
        "meta_robots": meta_robots,
        "x_robots_tag": x_robots_tag,
        "indexability_status": indexability_status,
        "keyword_match_status": keyword_match_status,
        "target_keyword": target_keyword,
        "parameters_payload": parameters_payload,
        "structure_payload": structure_payload,
        "url_readability": url_readability,
        "slug_clarity": slug_clarity,
        "request_failed": request_failed,
        "error_type": error_type,
        "error_message": error_message,
    }

    scores = calculate_url_health_scores(analysis)
    analysis.update(scores)

    issues = detect_url_issues(analysis)
    severity_counts = Counter(issue["severity"] for issue in issues)
    optimized_url_payload = build_optimized_url(normalized_input, parameters_payload, analysis)
    recommendations = build_ai_recommendations(issues, optimized_url_payload)
    quality_checks = build_quality_checks(analysis)

    analysis.update(
        {
            "issues": issues,
            "quality_checks": quality_checks,
            "recommendations": recommendations,
            "optimized_url_payload": optimized_url_payload,
            "critical_issues": severity_counts.get("critical", 0),
            "high_issues": severity_counts.get("high", 0),
            "medium_issues": severity_counts.get("medium", 0),
            "low_issues": severity_counts.get("low", 0),
            "informational_issues": severity_counts.get("informational", 0),
            "total_issues": len(issues),
            "completed_at": timezone.now(),
        }
    )
    return analysis


def build_quality_checks(analysis):
    checks = []

    def add(label, status, finding):
        checks.append({"label": label, "status": status, "finding": finding})

    add(
        "HTTPS",
        "PASS" if analysis["https_status"] else "FAIL",
        "Secure HTTPS protocol" if analysis["https_status"] else "URL is not served over HTTPS.",
    )
    add(
        "HTTP Status",
        (
            "PASS"
            if analysis["access_status"] == "accessible"
            else ("WARNING" if analysis["access_status"] in {"auth_required", "access_restricted", "rate_limited", "redirect"} else "FAIL")
        ),
        (
            f"HTTP {analysis.get('http_status_code') or 'Unavailable'} - {analysis['access_status_label']}."
            if analysis.get("http_status_code")
            else analysis["access_status_explanation"]
        ),
    )
    add(
        "URL Length",
        "PASS" if analysis["url_length"] <= 75 else "WARNING",
        f"URL length is {analysis['url_length']} characters.",
    )
    add(
        "URL Depth",
        analysis["depth_status"],
        analysis["depth_finding"],
    )
    add(
        "Uppercase",
        "WARNING" if analysis["has_uppercase"] else "PASS",
        "Uppercase characters detected." if analysis["has_uppercase"] else "Lowercase usage is consistent.",
    )
    add(
        "Underscores",
        "WARNING" if analysis["has_underscores"] else "PASS",
        "Use hyphens instead of underscores." if analysis["has_underscores"] else "No underscores detected.",
    )
    add(
        "Fragment",
        "INFO" if analysis["has_fragment"] else "PASS",
        (
            f'Fragment identifier "#{analysis["fragment_value"]}" detected. URL fragments are generally used for client-side or in-page navigation.'
            if analysis["has_fragment"]
            else "No URL fragment detected."
        ),
    )
    if analysis.get("numeric_id_prefix_detected"):
        add(
            "Numeric ID Prefix",
            "INFO",
            "The slug begins with a numeric identifier before descriptive text.",
        )
    elif analysis["numeric_slug_detected"]:
        add(
            "Numeric Slug Pattern",
            "WARNING",
            "Numbers represent a substantial portion of the slug.",
        )
    add(
        "Tracking Parameters",
        "INFO" if analysis["tracking_params_count"] else "PASS",
        (
            f"{analysis['tracking_params_count']} tracking parameter(s) detected."
            if analysis["tracking_params_count"]
            else "No tracking parameters detected."
        ),
    )
    add(
        "Canonical",
        (
            "PASS"
            if analysis["canonical_status"] == "self"
            or (analysis["canonical_status"] == "other" and analysis.get("canonical_to_clean_url"))
            else ("WARNING" if analysis["canonical_status"] in {"missing", "other"} else ("FAIL" if analysis["canonical_status"] == "conflict" else "INFO"))
        ),
        {
            "self": "Self-referencing canonical detected.",
            "other": (
                "The tracking URL canonicalizes to the clean preferred URL. This is generally expected behavior for tracking variants."
                if analysis.get("canonical_to_clean_url")
                else "Canonical points to another URL."
            ),
            "missing": "Canonical tag is missing.",
            "conflict": "Canonical conflicts with the final resolved URL.",
            "not_evaluated": "The canonical tag could not be evaluated because the page HTML was not accessible to the analyzer.",
            "unknown": "Canonical status could not be confirmed.",
        }.get(analysis["canonical_status"], "Canonical status unknown."),
    )
    indexability_messages = {
        "not_evaluated_auth_required": "The analyzer could not verify indexability because the page requires authentication or authorization.",
        "not_evaluated_access_restricted": "The analyzer could not verify indexability because the server restricted access to the request.",
        "not_evaluated_rate_limited": "The analyzer could not verify indexability because the request was rate-limited.",
        "not_found": "URL classification: Not Indexable - Not Found.",
        "gone": "URL classification: Not Indexable - Gone.",
        "server_error": "URL classification: Temporarily Unavailable - Server Error.",
        "error": "URL classification: Error.",
    }
    indexability_label = analysis["indexability_status"].replace("_", " ").title()
    add(
        "Indexability",
        (
            "PASS"
            if analysis["indexability_status"] == "indexable"
            else ("FAIL" if analysis["indexability_status"] in {"error", "noindex", "not_found", "gone", "server_error"} else "INFO")
        ),
        indexability_messages.get(analysis["indexability_status"], f"URL classification: {indexability_label}."),
    )
    if analysis["target_keyword"]:
        if analysis.get("is_root_homepage"):
            add(
                "Target Keyword",
                "INFO",
                "Keyword path matching is not evaluated for a root homepage URL with no slug.",
            )
        else:
            add(
                "Target Keyword",
                "PASS" if analysis["keyword_match_status"] == "yes" else ("WARNING" if analysis["keyword_match_status"] == "partial" else "INFO"),
                f"Keyword in URL: {analysis['keyword_match_status'].title()}.",
            )
    return checks
