from decimal import Decimal, ROUND_HALF_UP


def _decimal_score(value):
    bounded = max(0, min(100, value))
    return Decimal(str(bounded)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def score_to_label(score):
    if score is None:
        return "Not Evaluated"
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Good"
    if score >= 50:
        return "Needs Improvement"
    return "Critical"


def calculate_url_health_scores(analysis):
    structure = 100
    if analysis["url_length"] > 75:
        structure -= min(25, (analysis["url_length"] - 75) // 3 + 8)
    if analysis.get("depth_issue_detected"):
        depth_penalty = {
            "potentially_excessive": 10,
            "excessive": 18,
        }.get(analysis.get("depth_classification"), 8)
        structure -= depth_penalty
    if analysis["has_uppercase"]:
        structure -= 10
    if analysis["has_underscores"]:
        structure -= 10
    if analysis["special_character_count"] > 0:
        structure -= min(12, analysis["special_character_count"] * 2)
    if analysis["encoded_space_detected"]:
        structure -= 8
    if analysis.get("numeric_id_prefix_detected"):
        structure -= 8
    if analysis["numeric_slug_detected"]:
        structure -= 12
    technical = 100
    status_code = analysis.get("http_status_code") or 0
    if analysis.get("request_failed"):
        technical -= 65
    elif status_code in {401, 403}:
        technical -= 35
    elif status_code == 429:
        technical -= 28
    elif status_code in {404, 410}:
        technical -= 65
    elif 500 <= status_code < 600:
        technical -= 65
    elif status_code >= 300:
        technical -= 15
    if not analysis["https_status"]:
        technical -= 20
    if analysis["redirect_count"] > 0:
        technical -= min(15, analysis["redirect_count"] * 5)

    canonical_status = analysis["canonical_status"]
    if canonical_status == "other" and analysis.get("canonical_to_clean_url"):
        canonical = 100
    else:
        canonical = {
            "self": 100,
            "missing": 70,
            "other": 70,
            "conflict": 35,
            "not_evaluated": 50,
            "unknown": 60,
        }.get(canonical_status, 60)

    indexability_status = analysis["indexability_status"]
    indexability = {
        "indexable": 100,
        "unknown": 65,
        "redirected": 60,
        "blocked": 35,
        "noindex": 20,
        "not_evaluated_auth_required": 50,
        "not_evaluated_access_restricted": 50,
        "not_evaluated_rate_limited": 50,
        "not_found": 10,
        "gone": 10,
        "server_error": 25,
        "error": 10,
    }.get(indexability_status, 65)

    seo = 100
    if analysis["tracking_params_count"] > 0:
        seo -= min(12, analysis["tracking_params_count"] * 4)
    if analysis["unnecessary_params_count"] > 0:
        seo -= min(12, analysis["unnecessary_params_count"] * 4)
    if analysis["dynamic_url_detected"]:
        seo -= 12
    if analysis["url_readability"] == "poor":
        seo -= 18
    elif analysis["url_readability"] == "average":
        seo -= 8
    if not analysis.get("is_root_homepage"):
        if analysis["slug_clarity"] == "weak":
            seo -= 15
        elif analysis["slug_clarity"] == "fair":
            seo -= 6

    keyword_status = analysis["keyword_match_status"]
    if keyword_status == "yes":
        keyword = 100
    elif keyword_status == "partial":
        keyword = 65
    elif keyword_status == "no":
        keyword = 30
    else:
        keyword = None

    structure_score = _decimal_score(structure)
    technical_score = _decimal_score(technical)
    canonical_score = _decimal_score(canonical)
    indexability_score = _decimal_score(indexability)
    seo_score = _decimal_score(seo)
    keyword_score = _decimal_score(keyword) if keyword is not None else None

    if keyword_score is None:
        weighted_components = [
            (structure_score, Decimal("0.28")),
            (technical_score, Decimal("0.28")),
            (canonical_score, Decimal("0.16")),
            (indexability_score, Decimal("0.16")),
            (seo_score, Decimal("0.12")),
        ]
    else:
        weighted_components = [
            (structure_score, Decimal("0.25")),
            (technical_score, Decimal("0.25")),
            (canonical_score, Decimal("0.15")),
            (indexability_score, Decimal("0.15")),
            (seo_score, Decimal("0.10")),
            (keyword_score, Decimal("0.10")),
        ]

    not_evaluated_statuses = {
        "canonical": analysis["canonical_status"] == "not_evaluated",
        "indexability": analysis["indexability_status"] in {
            "not_evaluated_auth_required",
            "not_evaluated_access_restricted",
            "not_evaluated_rate_limited",
        },
    }
    applicable_components = []
    for index, (score, weight) in enumerate(weighted_components):
        if index == 2 and not_evaluated_statuses["canonical"]:
            continue
        if index == 3 and not_evaluated_statuses["indexability"]:
            continue
        applicable_components.append((score, weight))

    total_weight = sum(weight for _, weight in applicable_components)
    health_value = sum(score * weight for score, weight in applicable_components) / total_weight

    health_score = _decimal_score(health_value)

    return {
        "health_score": health_score,
        "structure_score": structure_score,
        "technical_score": technical_score,
        "canonical_score": canonical_score,
        "indexability_score": indexability_score,
        "seo_friendliness_score": seo_score,
        "keyword_relevance_score": keyword_score,
        "health_label": score_to_label(health_score),
    }
