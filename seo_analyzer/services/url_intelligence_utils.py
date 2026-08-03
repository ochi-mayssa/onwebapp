import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


TRACKING_PARAMETERS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "dclid",
    "gbraid",
    "wbraid",
    "gad_source",
    "gad_campaignid",
    "fbclid",
    "msclkid",
    "srsltid",
}

FUNCTIONAL_PARAMETER_HINTS = {
    "id",
    "page",
    "p",
    "lang",
    "locale",
    "sort",
    "order",
    "filter",
    "filters",
    "q",
    "query",
    "search",
    "category",
    "tag",
    "view",
    "variant",
    "color",
    "size",
}

SPECIAL_CHARACTER_PATTERN = re.compile(r"[^a-z0-9/\-_.%]")
LONG_NUMERIC_PATTERN = re.compile(r"\d{4,}")
RANDOM_TOKEN_PATTERN = re.compile(r"[a-z]*\d[a-z\d]{5,}", re.IGNORECASE)
FILE_EXTENSION_PATTERN = re.compile(r"\.[a-z0-9]{1,5}$", re.IGNORECASE)
GENERIC_DEPTH_SEGMENTS = {
    "archive",
    "archives",
    "page",
    "pages",
    "default",
    "view",
    "index",
    "item",
    "items",
    "listing",
    "list",
}


def safe_normalize_url(url):
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or parsed.path
    path = parsed.path if parsed.netloc else ""
    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, parsed.fragment))


def normalize_comparison_url(url):
    parsed = urlparse(safe_normalize_url(url))
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    netloc = parsed.netloc.lower()
    return urlunparse((parsed.scheme.lower(), netloc, path, "", parsed.query, ""))


def strip_tracking_parameters(url):
    parsed = urlparse(safe_normalize_url(url))
    filtered_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower().strip() not in TRACKING_PARAMETERS
    ]
    filtered_query = urlencode(filtered_pairs, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, filtered_query, ""))


def tracking_only_query(parameters_payload):
    return (
        bool(parameters_payload.get("all"))
        and bool(parameters_payload.get("tracking"))
        and not parameters_payload.get("functional")
        and not parameters_payload.get("unnecessary")
    )


def split_domain_parts(netloc):
    host = netloc.lower().split("@")[-1].split(":")[0]
    parts = [part for part in host.split(".") if part]
    if len(parts) >= 3:
        return ".".join(parts[:-2]), ".".join(parts[-2:])
    if len(parts) >= 2:
        return "", ".".join(parts[-2:])
    return "", host


def extract_url_components(url):
    parsed = urlparse(safe_normalize_url(url))
    path = parsed.path or "/"
    segments = [segment for segment in path.split("/") if segment]
    slug = segments[-1] if segments else ""
    subdomain, domain = split_domain_parts(parsed.netloc)
    return {
        "protocol": parsed.scheme.lower(),
        "domain": domain,
        "subdomain": subdomain,
        "path": path,
        "slug": slug,
        "segments": segments,
        "depth": len(segments),
        "trailing_slash": path.endswith("/") and path != "/",
        "query": parsed.query,
        "fragment": parsed.fragment,
        "netloc": parsed.netloc.lower(),
    }


def slug_tokens(slug):
    cleaned = re.sub(r"[%_]+", "-", slug.lower())
    return [token for token in re.split(r"[^a-z0-9]+", cleaned) if token]


def strip_slug_extension(slug):
    return FILE_EXTENSION_PATTERN.sub("", slug or "")


def analyze_numeric_slug(slug):
    base_slug = strip_slug_extension(slug.lower())
    tokens = slug_tokens(base_slug)
    if not tokens:
        return {
            "numeric_id_prefix_detected": False,
            "numeric_heavy_slug": False,
            "numeric_token_ratio": 0,
            "digit_ratio": 0,
        }

    numeric_tokens = [token for token in tokens if token.isdigit()]
    alpha_tokens = [token for token in tokens if re.search(r"[a-z]", token)]
    digit_count = sum(char.isdigit() for char in base_slug)
    alnum_count = sum(char.isalnum() for char in base_slug)
    numeric_token_ratio = len(numeric_tokens) / len(tokens)
    digit_ratio = digit_count / alnum_count if alnum_count else 0
    first_token = tokens[0]
    numeric_id_prefix_detected = (
        first_token.isdigit()
        and len(first_token) >= 3
        and len(alpha_tokens) >= 2
    )
    numeric_only_slug = bool(tokens) and all(token.isdigit() for token in tokens)
    meaningful_numeric_suffix = (
        len(numeric_tokens) == 1
        and len(alpha_tokens) >= 1
        and tokens[-1].isdigit()
        and len(tokens[-1]) <= 4
        and not first_token.isdigit()
    )
    numeric_tokens_after_prefix = (
        [token for token in tokens[1:] if token.isdigit()]
        if numeric_id_prefix_detected
        else numeric_tokens
    )
    long_numeric_token_detected = any(len(token) >= 4 for token in numeric_tokens_after_prefix)
    dense_numeric_suffixes = (
        len(numeric_tokens_after_prefix) >= 2
        and sum(len(token) for token in numeric_tokens_after_prefix) >= 4
    )
    numeric_heavy_slug = (
        not meaningful_numeric_suffix
        and (
            numeric_only_slug
            or long_numeric_token_detected
            or (digit_count >= 6 and digit_ratio >= 0.45 and not numeric_id_prefix_detected)
            or dense_numeric_suffixes
            or (numeric_token_ratio >= 0.5 and len(alpha_tokens) <= 1 and digit_count >= 4)
        )
    )

    return {
        "numeric_id_prefix_detected": numeric_id_prefix_detected,
        "numeric_heavy_slug": numeric_heavy_slug,
        "numeric_token_ratio": round(numeric_token_ratio, 2),
        "digit_ratio": round(digit_ratio, 2),
    }


def analyze_depth_structure(segments):
    normalized_segments = [strip_slug_extension(segment.lower()) for segment in segments if segment]
    depth = len(normalized_segments)
    repeated_segments = len(normalized_segments) - len(set(normalized_segments))
    numeric_only_count = sum(segment.isdigit() for segment in normalized_segments)
    generic_count = sum(segment in GENERIC_DEPTH_SEGMENTS for segment in normalized_segments)
    single_char_count = sum(len(segment) == 1 for segment in normalized_segments)
    short_code_count = sum(len(segment) == 2 and segment.isalpha() for segment in normalized_segments)
    meaningful_segments = sum(
        1
        for segment in normalized_segments
        if len(segment) >= 3 and segment not in GENERIC_DEPTH_SEGMENTS and not segment.isdigit()
    )
    logical_hierarchy = (
        depth <= 4
        and repeated_segments == 0
        and numeric_only_count == 0
        and generic_count == 0
        and single_char_count == 0
    ) or (
        depth >= 5
        and repeated_segments == 0
        and numeric_only_count <= 1
        and generic_count == 0
        and single_char_count == 0
        and meaningful_segments >= max(3, depth - 1)
    ) or (
        depth == 4
        and repeated_segments == 0
        and numeric_only_count == 0
        and generic_count <= 1
        and single_char_count == 0
        and short_code_count <= 2
        and meaningful_segments >= 2
    )

    if depth <= 2:
        classification = "shallow"
        status = "PASS"
        issue_detected = False
        finding = f"Depth {depth} is shallow."
    elif logical_hierarchy:
        classification = "deep_but_logical" if depth >= 4 else "moderate"
        status = "PASS" if depth == 3 else "INFO"
        issue_detected = False
        finding = f"Depth {depth} reflects a logical hierarchical path structure."
    elif depth >= 7 or single_char_count >= 3 or numeric_only_count >= 3 or (generic_count + repeated_segments) >= 3:
        classification = "excessive"
        status = "WARNING"
        issue_detected = True
        finding = f"Depth {depth} appears excessive because the path includes weak, repeated, or generated segments."
    elif depth >= 5 or numeric_only_count >= 2 or generic_count >= 2 or repeated_segments >= 1:
        classification = "potentially_excessive"
        status = "WARNING"
        issue_detected = True
        finding = f"Depth {depth} may be deeper than necessary for this path structure."
    else:
        classification = "moderate"
        status = "INFO"
        issue_detected = False
        finding = f"Depth {depth} is moderate and does not indicate a clear structural problem."

    return {
        "classification": classification,
        "status": status,
        "issue_detected": issue_detected,
        "finding": finding,
        "segments": normalized_segments,
        "repeated_segments": repeated_segments,
        "numeric_only_count": numeric_only_count,
        "generic_count": generic_count,
        "single_char_count": single_char_count,
        "meaningful_segments": meaningful_segments,
    }


def classify_query_parameters(url):
    parsed = urlparse(safe_normalize_url(url))
    parameter_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    tracking = []
    functional = []
    unnecessary = []
    for key, value in parameter_pairs:
        normalized_key = key.lower().strip()
        normalized_value = value.strip()
        item = {
            "key": key,
            "value": value,
            "reason": "",
        }
        if normalized_key in TRACKING_PARAMETERS:
            item["reason"] = "Known tracking parameter"
            tracking.append(item)
        elif normalized_key in FUNCTIONAL_PARAMETER_HINTS:
            item["reason"] = "Common functional parameter"
            functional.append(item)
        elif not normalized_value:
            item["reason"] = "Empty parameter value"
            unnecessary.append(item)
        elif LONG_NUMERIC_PATTERN.search(normalized_value) or RANDOM_TOKEN_PATTERN.search(normalized_value):
            item["reason"] = "Token-like value requires developer validation"
            unnecessary.append(item)
        else:
            item["reason"] = "Potentially unnecessary parameter"
            unnecessary.append(item)
    return {
        "all": [{"key": key, "value": value} for key, value in parameter_pairs],
        "tracking": tracking,
        "functional": functional,
        "unnecessary": unnecessary,
    }


def classify_keyword_match(slug, target_keyword):
    if not target_keyword:
        return "not_provided", 0, []
    keyword_tokens = [token for token in re.split(r"[^a-z0-9]+", target_keyword.lower()) if token]
    if not keyword_tokens:
        return "not_provided", 0, []
    tokens = slug_tokens(slug)
    matches = [token for token in keyword_tokens if token in tokens]
    if len(matches) == len(keyword_tokens):
        return "yes", 100, matches
    if matches:
        return "partial", round((len(matches) / len(keyword_tokens)) * 100), matches
    return "no", 0, []


def special_character_count(path):
    if not path:
        return 0
    return len(SPECIAL_CHARACTER_PATTERN.findall(path.lower()))


def dynamic_url_detected(url):
    parsed = urlparse(safe_normalize_url(url))
    lowered_path = parsed.path.lower()
    dynamic_markers = [".php", ".aspx", ".jsp"]
    if any(marker in lowered_path for marker in dynamic_markers):
        return True

    parameters_payload = classify_query_parameters(url)
    if not parsed.query:
        return False
    if tracking_only_query(parameters_payload):
        return False
    return bool(parameters_payload.get("functional") or parameters_payload.get("unnecessary"))


def build_optimized_url(url, parameters_payload, analysis):
    parsed = urlparse(safe_normalize_url(url))
    original_path = parsed.path or "/"
    clean_path = original_path.lower().replace("_", "-").replace("%20", "-").replace(" ", "-")
    base_path = clean_path
    requires_validation_reasons = []
    original_segments = [segment for segment in original_path.split("/") if segment]

    actionable_structural_findings = any(
        [
            analysis.get("has_uppercase"),
            analysis.get("has_underscores"),
            analysis.get("encoded_space_detected"),
            analysis.get("numeric_id_prefix_detected"),
            analysis.get("numeric_slug_detected"),
            analysis.get("url_length", 0) > 75,
            analysis.get("depth_issue_detected"),
        ]
    )

    if analysis.get("numeric_id_prefix_detected"):
        base_path = re.sub(r"/(\d+)-", "/", base_path, count=1)
        requires_validation_reasons.append("The numeric ID prefix may be required by the current routing or CMS.")

    extension_match = FILE_EXTENSION_PATTERN.search(base_path)
    if extension_match and (
        analysis.get("numeric_id_prefix_detected")
        or analysis.get("numeric_slug_detected")
        or analysis.get("url_length", 0) > 75
    ):
        base_path = FILE_EXTENSION_PATTERN.sub("", base_path)
        requires_validation_reasons.append("The file extension may be required by the current routing system.")

    clean_path = base_path
    clean_path = re.sub(r"[^a-z0-9/\-.]+", "-", clean_path)
    clean_path = re.sub(r"-{2,}", "-", clean_path)
    clean_path = re.sub(r"/{2,}", "/", clean_path)
    if clean_path and clean_path != "/" and not clean_path.endswith("/"):
        clean_path = f"{clean_path}/"

    functional_pairs = [(item["key"], item["value"]) for item in parameters_payload.get("functional", [])]
    review_needed_pairs = [(item["key"], item["value"]) for item in parameters_payload.get("unnecessary", [])]
    preserved_pairs = functional_pairs + review_needed_pairs
    preserved_query = urlencode(preserved_pairs, doseq=True)
    if functional_pairs:
        requires_validation_reasons.append("Functional parameters may be required by the backend or application state.")
    if review_needed_pairs:
        review_needed_keys = ", ".join(item["key"] for item in parameters_payload.get("unnecessary", []))
        requires_validation_reasons.append(
            f'The purpose of these parameters could not be confidently determined: {review_needed_keys}.'
        )

    if analysis.get("depth_issue_detected"):
        flattened_segments = []
        for segment in original_segments:
            normalized = strip_slug_extension(segment.lower())
            if normalized.isdigit() or normalized in GENERIC_DEPTH_SEGMENTS:
                continue
            if flattened_segments and normalized == strip_slug_extension(flattened_segments[-1].lower()):
                continue
            flattened_segments.append(normalized)

        if len(flattened_segments) >= 3:
            flattened_segments = [flattened_segments[0], flattened_segments[-1]]
        elif len(flattened_segments) == 0 and original_segments:
            flattened_segments = [original_segments[0].lower(), original_segments[-1].lower()]

        proposed_path = "/" + "/".join(flattened_segments) + "/" if flattened_segments else "/"
        if proposed_path != "/":
            clean_path = proposed_path
        requires_validation_reasons.append(
            "Flattening this path may affect routing, breadcrumbs, and content hierarchy."
        )

    suggested_url = urlunparse(
        (
            "https" if parsed.scheme.lower() != "https" else parsed.scheme.lower(),
            parsed.netloc.lower(),
            clean_path or "/",
            "",
            preserved_query,
            "",
        )
    )

    current_normalized = normalize_comparison_url(url)
    suggested_normalized = normalize_comparison_url(suggested_url)
    current_without_tracking = normalize_comparison_url(strip_tracking_parameters(url))
    suggested_without_tracking = normalize_comparison_url(strip_tracking_parameters(suggested_url))

    if review_needed_pairs and current_normalized == suggested_normalized:
        return {
            "current_url": url,
            "suggested_url": "",
            "status": "developer_validation_required",
            "message": "The purpose of one or more URL parameters could not be confidently determined. Validate their functional impact before removing them from the URL.",
            "requires_validation": True,
            "validation_notes": requires_validation_reasons,
            "migration_warning": "",
        }

    if current_normalized == suggested_normalized:
        return {
            "current_url": url,
            "suggested_url": "",
            "status": "no_change",
            "message": "No structural URL change is necessary.",
            "requires_validation": False,
            "migration_warning": "",
        }

    if (
        parameters_payload.get("tracking")
        and current_without_tracking == suggested_normalized
        and current_normalized != suggested_normalized
    ):
        return {
            "current_url": url,
            "suggested_url": suggested_url,
            "status": "clean_url",
            "message": "Use the clean canonical URL for internal linking and public navigation. Tracking parameters may remain in campaign links where attribution is required.",
            "requires_validation": False,
            "validation_notes": [],
            "migration_warning": "",
        }

    requires_validation = bool(requires_validation_reasons)
    message = (
        "Validate redirects and routing before changing the live URL."
        if requires_validation
        else "Safe optimization suggestion based on the analyzed URL structure."
    )
    return {
        "current_url": url,
        "suggested_url": suggested_url,
        "status": "requires_validation" if requires_validation else "safe",
        "message": message,
        "requires_validation": requires_validation,
        "validation_notes": requires_validation_reasons,
        "migration_warning": (
            "Changing an existing indexed URL requires a permanent 301 redirect from the old URL to the new URL."
            if analysis.get("indexability_status") in {"indexable", "redirected"}
            else ""
        ),
    }
