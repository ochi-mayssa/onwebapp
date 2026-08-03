
import logging
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup, FeatureNotFound

from .utils import (
    DEFAULT_REQUEST_TIMEOUT,
    build_http_session,
    classify_request_exception,
    clean_text,
    normalize_url,
)

logger = logging.getLogger(__name__)
_HTML_PARSER = "lxml"


def perform_free_website_pre_check(url: str):
    """
    Perform a FREE, basic website pre-check (only 1 page, no crawling).
    Returns a dictionary with results.
    """
    results = {
        "url": url,
        "final_url": None,
        "status_code": None,
        "https_status": None,
        "redirect_count": 0,
        "response_time": None,
        "page_size": None,
        "checks": [],
        "critical_issues": 0,
        "warnings": 0,
        "passed": 0,
        "health_score": 0,
        "status_label": "Critical",
        "error": None,
        "error_type": None,
        "html_available": False,
    }

    session = build_http_session()
    normalized_url = normalize_url(url)

    try:
        start_time = time.perf_counter()
        response = session.get(
            normalized_url,
            timeout=DEFAULT_REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        elapsed = time.perf_counter() - start_time

        results["final_url"] = normalize_url(response.url)
        results["status_code"] = response.status_code
        results["https_status"] = urlparse(results["final_url"]).scheme == "https"
        results["redirect_count"] = len(response.history)
        results["response_time"] = elapsed
        results["page_size"] = len(response.content)

        # 1. Website Accessibility Check
        if 200 <= response.status_code < 300:
            results["checks"].append({
                "name": "Website Accessibility",
                "status": "PASS",
                "finding": f"Website is accessible (HTTP {response.status_code})",
            })
            results["passed"] += 1
        elif 300 <= response.status_code < 400:
            results["checks"].append({
                "name": "Website Accessibility",
                "status": "WARNING",
                "finding": f"Website redirects (HTTP {response.status_code})",
            })
            results["warnings"] += 1
        elif response.status_code == 403:
            results["checks"].append({
                "name": "Website Accessibility",
                "status": "WARNING",
                "finding": "The website returned HTTP 403 and restricted automated access.",
            })
            results["warnings"] += 1
        elif response.status_code == 404:
            results["checks"].append({
                "name": "Website Accessibility",
                "status": "FAIL",
                "finding": "Website not found (HTTP 404)",
            })
            results["critical_issues"] += 1
        elif response.status_code == 429:
            results["checks"].append({
                "name": "Website Accessibility",
                "status": "WARNING",
                "finding": "Website rate limited the request (HTTP 429)",
            })
            results["warnings"] += 1
        elif 500 <= response.status_code < 600:
            results["checks"].append({
                "name": "Website Accessibility",
                "status": "FAIL",
                "finding": f"Website server error (HTTP {response.status_code})",
            })
            results["critical_issues"] += 1
        else:
            results["checks"].append({
                "name": "Website Accessibility",
                "status": "FAIL",
                "finding": f"Website returned error (HTTP {response.status_code})",
            })
            results["critical_issues"] += 1

        # 2. HTTPS Check
        if results["https_status"]:
            results["checks"].append({
                "name": "HTTPS",
                "status": "PASS",
                "finding": "Secure HTTPS connection detected",
            })
            results["passed"] += 1
        else:
            results["checks"].append({
                "name": "HTTPS",
                "status": "FAIL",
                "finding": "No HTTPS connection",
            })
            results["critical_issues"] += 1

        # Check if we have HTML content to analyze
        has_html_content = (
            (200 <= response.status_code < 400 or response.content)
            and "text/html" in (response.headers.get("Content-Type") or "")
        )
        if has_html_content:
            results["html_available"] = True
            try:
                soup = BeautifulSoup(response.content, _HTML_PARSER)
            except FeatureNotFound:
                soup = BeautifulSoup(response.content, "html.parser")

            # 3. Page Title Presence
            title_tag = soup.title
            if title_tag and title_tag.string and clean_text(title_tag.string):
                results["checks"].append({
                    "name": "Page Title",
                    "status": "PASS",
                    "finding": "Page title detected",
                })
                results["passed"] += 1
            else:
                results["checks"].append({
                    "name": "Page Title",
                    "status": "WARNING",
                    "finding": "Page title missing or empty",
                })
                results["warnings"] += 1

            # 4. Meta Description Presence
            meta_desc_tag = soup.find("meta", attrs={"name": "description"})
            if meta_desc_tag and meta_desc_tag.get("content") and clean_text(meta_desc_tag["content"]):
                results["checks"].append({
                    "name": "Meta Description",
                    "status": "PASS",
                    "finding": "Meta description detected",
                })
                results["passed"] += 1
            else:
                results["checks"].append({
                    "name": "Meta Description",
                    "status": "WARNING",
                    "finding": "Meta description missing or empty",
                })
                results["warnings"] += 1

            # 5. H1 Presence
            h1_tags = soup.find_all("h1")
            h1_count = len(h1_tags)
            if h1_count == 1 and clean_text(h1_tags[0].get_text()):
                results["checks"].append({
                    "name": "H1 Heading",
                    "status": "PASS",
                    "finding": "Single H1 heading detected",
                })
                results["passed"] += 1
            elif h1_count == 0:
                results["checks"].append({
                    "name": "H1 Heading",
                    "status": "WARNING",
                    "finding": "No H1 heading detected",
                })
                results["warnings"] += 1
            else:
                results["checks"].append({
                    "name": "H1 Heading",
                    "status": "WARNING",
                    "finding": f"Multiple H1 headings ({h1_count}) detected",
                })
                results["warnings"] += 1

            # 6. Canonical Presence
            canonical_tag = soup.find("link", attrs={"rel": "canonical"})
            if canonical_tag and canonical_tag.get("href"):
                results["checks"].append({
                    "name": "Canonical Tag",
                    "status": "PASS",
                    "finding": "Canonical tag detected",
                })
                results["passed"] += 1
            else:
                results["checks"].append({
                    "name": "Canonical Tag",
                    "status": "WARNING",
                    "finding": "Canonical tag missing",
                })
                results["warnings"] += 1

            # 7. Robots Meta Tag Check
            meta_robots_tag = soup.find("meta", attrs={"name": "robots"})
            is_noindex = False
            if meta_robots_tag:
                content = meta_robots_tag.get("content", "").lower()
                is_noindex = "noindex" in content
            if is_noindex:
                results["checks"].append({
                    "name": "Robots Meta Tag",
                    "status": "FAIL",
                    "finding": "Page has noindex tag (not indexable)",
                })
                results["critical_issues"] += 1
            else:
                results["checks"].append({
                    "name": "Robots Meta Tag",
                    "status": "PASS",
                    "finding": "No noindex tag detected (page is indexable)",
                })
                results["passed"] += 1

        else:
            # HTML not available, mark HTML-dependent checks as NOT EVALUATED
            results["checks"].extend([
                {
                    "name": "Page Title",
                    "status": "NOT EVALUATED",
                    "finding": "HTML content not available",
                },
                {
                    "name": "Meta Description",
                    "status": "NOT EVALUATED",
                    "finding": "HTML content not available",
                },
                {
                    "name": "H1 Heading",
                    "status": "NOT EVALUATED",
                    "finding": "HTML content not available",
                },
                {
                    "name": "Canonical Tag",
                    "status": "NOT EVALUATED",
                    "finding": "HTML content not available",
                },
                {
                    "name": "Robots Meta Tag",
                    "status": "NOT EVALUATED",
                    "finding": "HTML content not available",
                },
            ])

    except Exception as e:
        error_type, error_msg = classify_request_exception(e)
        results["error"] = str(e)
        results["error_type"] = error_type
        results["checks"].append({
            "name": "Website Accessibility",
            "status": "FAIL",
            "finding": f"Error accessing website: {error_msg}",
        })
        results["critical_issues"] += 1
        # Mark all other checks as NOT EVALUATED
        results["checks"].extend([
            {
                "name": "HTTPS",
                "status": "NOT EVALUATED",
                "finding": "Website not accessible",
            },
            {
                "name": "Page Title",
                "status": "NOT EVALUATED",
                "finding": "Website not accessible",
            },
            {
                "name": "Meta Description",
                "status": "NOT EVALUATED",
                "finding": "Website not accessible",
            },
            {
                "name": "H1 Heading",
                "status": "NOT EVALUATED",
                "finding": "Website not accessible",
            },
            {
                "name": "Canonical Tag",
                "status": "NOT EVALUATED",
                "finding": "Website not accessible",
            },
            {
                "name": "Robots Meta Tag",
                "status": "NOT EVALUATED",
                "finding": "Website not accessible",
            },
        ])

    # Calculate Health Score
    # Scoring logic:
    # - PASS: +10 points
    # - WARNING: +5 points
    # - FAIL: 0 points
    # - NOT EVALUATED: excluded from denominator
    max_score = 0
    current_score = 0

    for check in results["checks"]:
        if check["status"] == "PASS":
            max_score += 10
            current_score += 10
        elif check["status"] == "WARNING":
            max_score += 10
            current_score += 5
        elif check["status"] == "FAIL":
            max_score += 10
            current_score += 0

    if max_score > 0:
        results["health_score"] = int(round((current_score / max_score) * 100))
    else:
        results["health_score"] = 0

    # Determine Status Label
    if results["health_score"] >= 90:
        results["status_label"] = "Excellent"
    elif results["health_score"] >= 75:
        results["status_label"] = "Good"
    elif results["health_score"] >= 50:
        results["status_label"] = "Needs Improvement"
    else:
        results["status_label"] = "Critical"

    return results

