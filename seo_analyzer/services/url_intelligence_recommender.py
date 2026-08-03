ISSUE_LIBRARY = {
    "http": {
        "name": "Non-HTTPS URL",
        "severity": "high",
        "category": "technical",
        "seo_impact": "Non-secure URLs weaken trust and can limit ranking competitiveness.",
        "business_impact": "Visitors may hesitate to engage or convert on non-secure pages.",
        "recommended_fix": "Serve the URL over HTTPS and update internal references to the secure version.",
    },
    "redirect": {
        "name": "Redirect Detected",
        "severity": "medium",
        "category": "technical",
        "seo_impact": "Redirect hops add latency and can dilute canonical clarity.",
        "business_impact": "Users and crawlers reach the destination with extra friction.",
        "recommended_fix": "Link directly to the final URL wherever possible.",
    },
    "uppercase": {
        "name": "Uppercase Characters Detected",
        "severity": "medium",
        "category": "structure",
        "seo_impact": "Mixed-case URLs can create inconsistent variants on some servers.",
        "business_impact": "Inconsistent URLs are harder to maintain and share reliably.",
        "recommended_fix": "Use lowercase URLs consistently.",
    },
    "underscores": {
        "name": "Underscores Detected",
        "severity": "medium",
        "category": "structure",
        "seo_impact": "Underscores are less readable than hyphens in search-facing URLs.",
        "business_impact": "Users scan descriptive hyphenated URLs more easily.",
        "recommended_fix": "Replace underscores with hyphens in the URL slug.",
    },
    "length": {
        "name": "URL Too Long",
        "severity": "medium",
        "category": "structure",
        "seo_impact": "Long URLs are harder to read and can be truncated in search results.",
        "business_impact": "Complex URLs reduce clarity for visitors and stakeholders.",
        "recommended_fix": "Shorten the path and remove unnecessary elements while preserving intent.",
    },
    "depth": {
        "name": "Deep URL Structure",
        "severity": "medium",
        "category": "structure",
        "seo_impact": "Deep URL paths can signal unnecessary complexity and weaker topical focus.",
        "business_impact": "Complex hierarchies are harder to govern during content updates.",
        "recommended_fix": "Flatten the URL structure where possible.",
    },
    "tracking": {
        "name": "Tracking Parameters Detected",
        "severity": "informational",
        "category": "seo",
        "seo_impact": "Tracking parameters can create noisy URL variants if reused in internal linking.",
        "business_impact": "Analytics links may circulate as non-canonical public URLs.",
        "recommended_fix": "Use the clean canonical URL for internal links and public navigation. Keep tracking parameters only where campaign attribution is required.",
    },
    "unnecessary_params": {
        "name": "Potentially Unnecessary Parameters",
        "severity": "medium",
        "category": "seo",
        "seo_impact": "Unnecessary parameters create complexity and can fragment crawl signals.",
        "business_impact": "Parameter-heavy URLs are harder to maintain and QA.",
        "recommended_fix": "Review non-essential parameters and remove them only after developer validation.",
    },
    "dynamic": {
        "name": "Dynamic URL Pattern Detected",
        "severity": "medium",
        "category": "seo",
        "seo_impact": "Dynamic URL patterns are less readable and often less stable for search.",
        "business_impact": "Dynamic URLs can complicate analytics, QA, and content governance.",
        "recommended_fix": "Prefer clean, descriptive, static-looking URLs when feasible.",
    },
    "numeric_slug": {
        "name": "Numeric-Heavy Slug Detected",
        "severity": "medium",
        "category": "structure",
        "seo_impact": "Numeric-heavy slugs usually communicate little topical relevance.",
        "business_impact": "Opaque URLs reduce trust and are harder for teams to audit.",
        "recommended_fix": "Replace ID-heavy slugs with descriptive words where feasible.",
    },
    "numeric_id_prefix": {
        "name": "Numeric ID Prefix Detected",
        "severity": "low",
        "category": "structure",
        "seo_impact": "The URL contains a numeric identifier before a descriptive slug. This is not necessarily harmful, but it can make the URL longer and less readable.",
        "business_impact": "Numeric prefixes reduce readability and can complicate governance for content teams.",
        "recommended_fix": "If the numeric ID is not required by the CMS or routing system, consider removing it. Validate routing before making changes.",
    },
    "canonical_missing": {
        "name": "Canonical Missing",
        "severity": "medium",
        "category": "canonical",
        "seo_impact": "Missing canonicals can reduce clarity when alternate URL variants exist.",
        "business_impact": "Search signals may fragment across duplicate paths or parameters.",
        "recommended_fix": "Add a self-referencing canonical if this URL is the preferred version.",
    },
    "canonical_other": {
        "name": "Canonical Points to Another URL",
        "severity": "low",
        "category": "canonical",
        "seo_impact": "Search engines may consolidate signals to a different preferred URL.",
        "business_impact": "Teams may misinterpret which URL is intended to rank.",
        "recommended_fix": "Confirm the canonical target is intentional and consistent with the URL strategy.",
    },
    "canonical_conflict": {
        "name": "Canonical Conflict",
        "severity": "high",
        "category": "canonical",
        "seo_impact": "Conflicting canonical signals can undermine index selection and ranking stability.",
        "business_impact": "Important URLs may not rank as intended.",
        "recommended_fix": "Align canonical tags with the preferred final indexable URL.",
    },
    "noindex": {
        "name": "URL Is Not Indexable",
        "severity": "high",
        "category": "indexability",
        "seo_impact": "Non-indexable URLs cannot reliably earn organic visibility.",
        "business_impact": "Pages intended to generate traffic may remain invisible in search.",
        "recommended_fix": "Remove the noindex/blocking directive if search visibility is desired.",
    },
    "auth_required": {
        "name": "Authentication Required",
        "severity": "medium",
        "category": "technical",
        "seo_impact": "The analyzer could not fully inspect the page because authentication is required. If search engines face the same restriction, discovery may be limited.",
        "business_impact": "Protected content may be intentionally restricted, but public SEO validation remains incomplete.",
        "recommended_fix": "Confirm whether the URL is intentionally protected and verify separately whether search engine access is expected.",
    },
    "access_restricted": {
        "name": "Access Restricted",
        "severity": "high",
        "category": "technical",
        "seo_impact": "If search engine crawlers receive the same 403 response, crawling and indexing may be affected. This analyzer result alone does not confirm that Googlebot is blocked.",
        "business_impact": "Security rules may be preventing independent validation and could affect discoverability if legitimate crawlers are also restricted.",
        "recommended_fix": "Review CDN, WAF, firewall, bot-protection, and server access rules. Verify separately whether legitimate search engine crawlers can access the URL.",
    },
    "rate_limited": {
        "name": "Rate Limited",
        "severity": "medium",
        "category": "technical",
        "seo_impact": "Temporary rate limiting prevented the analyzer from fully inspecting the page. Persistent crawler throttling can affect crawl efficiency.",
        "business_impact": "Monitoring and third-party validation can become unreliable during rate limiting.",
        "recommended_fix": "Review rate-limiting rules and confirm that legitimate crawlers and monitoring requests are allowed appropriate access.",
    },
    "not_found": {
        "name": "URL Not Found",
        "severity": "critical",
        "category": "technical",
        "seo_impact": "A 404 response prevents the URL from being indexed as a live page.",
        "business_impact": "Users and campaigns may land on a missing destination.",
        "recommended_fix": "Restore the page if it should exist, or redirect it appropriately if it has permanently moved.",
    },
    "gone": {
        "name": "URL Permanently Gone",
        "severity": "high",
        "category": "technical",
        "seo_impact": "A 410 response signals that the URL has been intentionally removed and should not remain in search results.",
        "business_impact": "Legacy references may continue sending users to a retired destination.",
        "recommended_fix": "Confirm the removal is intentional and redirect or update references if a replacement page exists.",
    },
    "server_error": {
        "name": "Server Error",
        "severity": "critical",
        "category": "technical",
        "seo_impact": "Server-side failures can block crawling and destabilize indexing if they persist.",
        "business_impact": "Visitors and bots may be unable to access the page during outages.",
        "recommended_fix": "Investigate the server-side failure and restore a stable successful response.",
    },
    "error": {
        "name": "URL Returned an Error Status",
        "severity": "critical",
        "category": "technical",
        "seo_impact": "Error responses prevent crawling and indexing for the requested URL.",
        "business_impact": "Users and campaigns may land on a failing page.",
        "recommended_fix": "Resolve the server or destination issue and return a stable final response.",
    },
    "keyword_missing": {
        "name": "Target Keyword Missing from URL",
        "severity": "low",
        "category": "keyword",
        "seo_impact": "A missing descriptive keyword can reduce topical clarity in the URL.",
        "business_impact": "The URL may be less intuitive for users and stakeholders.",
        "recommended_fix": "Consider including the target keyword in the slug if it fits naturally.",
    },
}


EXPECTED_SEO_IMPROVEMENTS = {
    "Canonical Missing": "Clearer preferred-URL signals and improved consolidation of duplicate content variants.",
    "Canonical Conflict": "Clearer preferred-URL signals and reduced risk of duplicate or conflicting indexing signals.",
    "Canonical Points to Another URL": "Improved canonical consistency and clearer search engine understanding of the preferred URL.",
    "URL Too Long": "Improved URL readability, usability, and maintainability.",
    "Numeric-Heavy Slug Detected": "Improved topical clarity, readability, and semantic relevance of the URL.",
    "Numeric ID Prefix Detected": "Improved URL readability and cleaner topical focus if the identifier is not required.",
    "Deep URL Structure": "Improved crawl efficiency and a clearer, more maintainable URL hierarchy.",
    "Uppercase Characters Detected": "Improved URL consistency and reduced risk of duplicate URL variants.",
    "Underscores Detected": "Improved URL readability and clearer word separation.",
    "Tracking Parameters Detected": "Cleaner URL variants and reduced duplicate crawling and indexing signals.",
    "Potentially Unnecessary Parameters": "Cleaner crawl paths and reduced risk of unnecessary URL duplication.",
    "Dynamic URL Pattern Detected": "Cleaner crawl paths and improved URL stability for search engines and users.",
    "Access Restricted": "Improved crawl accessibility if legitimate search engine crawlers are currently being blocked.",
    "Authentication Required": "Clearer validation of crawler accessibility if search engine access is intended for this URL.",
    "Rate Limited": "Improved crawl accessibility and more reliable technical validation when temporary throttling is resolved.",
    "URL Not Found": "Restored crawlability and preservation of user and link equity signals when the URL is correctly restored or redirected.",
    "URL Permanently Gone": "Clearer search engine handling of intentionally removed content and reduced wasted crawl activity.",
    "Server Error": "Improved crawl reliability, page availability, and indexing stability.",
    "URL Returned an Error Status": "Improved technical SEO consistency after resolving the detected issue.",
    "Redirect Detected": "Improved crawl efficiency and faster access to the final destination.",
    "Redirect Chain": "Reduced crawl hops, improved crawl efficiency, and faster URL resolution.",
    "Redirect Loop": "Restored URL accessibility and reliable crawling.",
    "URL Is Not Indexable": "Improved eligibility for crawling and indexing once the blocking condition is resolved.",
    "Target Keyword Missing from URL": "Improved semantic alignment between the URL and the target search topic.",
    "Non-HTTPS URL": "Improved crawl trust, technical consistency, and user confidence with a secure canonical URL.",
    "URL structure optimization opportunity": "Improved URL clarity and stronger long-term crawl and governance consistency after validating the structural change.",
}

DEFAULT_EXPECTED_SEO_IMPROVEMENT = (
    "Improved technical SEO consistency after resolving the detected issue."
)


def get_expected_seo_improvement(problem_name):
    return EXPECTED_SEO_IMPROVEMENTS.get(problem_name, DEFAULT_EXPECTED_SEO_IMPROVEMENT)


def detect_url_issues(analysis):
    issues = []

    def add(issue_key, evidence, **overrides):
        template = ISSUE_LIBRARY[issue_key]
        issues.append(
            {
                "name": template["name"],
                "severity": template["severity"],
                "category": template["category"],
                "evidence": evidence,
                "description": template["name"],
                "seo_impact": overrides.get("seo_impact", template["seo_impact"]),
                "business_impact": overrides.get("business_impact", template["business_impact"]),
                "recommended_fix": overrides.get("recommended_fix", template["recommended_fix"]),
            }
        )

    status_code = analysis.get("http_status_code") or 0
    if analysis.get("request_failed"):
        add("error", f"HTTP status {status_code or 'unavailable'}")
    elif status_code == 401:
        add("auth_required", "HTTP 401")
    elif status_code == 403:
        add("access_restricted", "HTTP 403")
    elif status_code == 429:
        add("rate_limited", "HTTP 429")
    elif status_code == 404:
        add("not_found", "HTTP 404")
    elif status_code == 410:
        add("gone", "HTTP 410")
    elif status_code and 500 <= status_code < 600:
        add("server_error", f"HTTP {status_code}")
    elif status_code >= 400:
        add("error", f"HTTP status {status_code or 'unavailable'}")
    if not analysis["https_status"]:
        add("http", analysis["analyzed_url"])
    if analysis["redirect_count"] > 0:
        add("redirect", f"{analysis['redirect_count']} redirect(s) to {analysis['final_url']}")
    if analysis["has_uppercase"]:
        add("uppercase", analysis["path"] or analysis["analyzed_url"])
    if analysis["has_underscores"]:
        add("underscores", analysis["path"] or analysis["analyzed_url"])
    if analysis["url_length"] > 75:
        if analysis.get("tracking_only_query"):
            add(
                "length",
                f"Length: {analysis['url_length']} characters",
                recommended_fix="The base URL is already concise. The excessive length is primarily caused by tracking parameters. Use the clean URL for internal linking and public navigation while retaining tracking parameters only where campaign attribution is required.",
            )
        else:
            add("length", f"Length: {analysis['url_length']} characters")
    if analysis.get("depth_issue_detected"):
        add(
            "depth",
            f"Depth: {analysis['url_depth']} | Segments: {analysis.get('depth_evidence', analysis['path'] or analysis['analyzed_url'])}",
        )
    if analysis["tracking_params_count"] > 0:
        add("tracking", ", ".join(item["key"] for item in analysis["parameters_payload"]["tracking"]))
    if analysis["unnecessary_params_count"] > 0:
        add(
            "unnecessary_params",
            ", ".join(item["key"] for item in analysis["parameters_payload"]["unnecessary"]),
        )
    if analysis["dynamic_url_detected"]:
        add("dynamic", analysis["analyzed_url"])
    if analysis.get("numeric_id_prefix_detected"):
        add("numeric_id_prefix", analysis["slug"] or analysis["analyzed_url"])
    if analysis["numeric_slug_detected"]:
        add("numeric_slug", analysis["slug"] or analysis["analyzed_url"])

    canonical_status = analysis["canonical_status"]
    if canonical_status == "missing":
        add("canonical_missing", "No canonical tag found")
    elif canonical_status == "other" and not analysis.get("canonical_to_clean_url"):
        add("canonical_other", analysis.get("canonical_url") or "Canonical points elsewhere")
    elif canonical_status == "conflict":
        add("canonical_conflict", analysis.get("canonical_url") or "Canonical mismatch")

    indexability_status = analysis["indexability_status"]
    if indexability_status == "noindex":
        robots_value = analysis.get("meta_robots") or analysis.get("x_robots_tag") or indexability_status
        add("noindex", robots_value)

    if analysis["keyword_match_status"] == "no":
        add("keyword_missing", analysis["target_keyword"])

    return issues


def build_ai_recommendations(issues, optimized_url_payload):
    recommendations = []
    for issue in issues:
        recommendations.append(
            {
                "priority": issue["severity"].title(),
                "problem": issue["name"],
                "why_it_matters": issue["seo_impact"],
                "recommended_action": issue["recommended_fix"],
                "expected_seo_improvement": get_expected_seo_improvement(issue["name"]),
            }
        )

    if optimized_url_payload.get("status") in {"safe", "requires_validation"}:
        recommendations.append(
            {
                "priority": "Medium" if optimized_url_payload["status"] == "safe" else "High",
                "problem": "URL structure optimization opportunity",
                "why_it_matters": "A cleaner URL can improve readability, canonical consistency, and long-term governance.",
                "recommended_action": optimized_url_payload["message"],
                "expected_seo_improvement": get_expected_seo_improvement(
                    "URL structure optimization opportunity"
                ),
            }
        )
    return recommendations
