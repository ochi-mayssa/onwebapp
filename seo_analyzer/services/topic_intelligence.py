from __future__ import annotations

from collections import Counter
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .utils import clean_text, normalize_url

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "best",
    "by",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "their",
    "this",
    "to",
    "with",
    "your",
}

GENERIC_TERMS = {
    "home",
    "page",
    "welcome",
    "official",
    "site",
    "online",
    "website",
    "untitled",
    "example",
}

INTENT_PATTERNS = {
    "Transactional": [
        "buy",
        "pricing",
        "price",
        "order",
        "subscribe",
        "book",
        "checkout",
        "sale",
        "shop",
        "request demo",
        "start trial",
    ],
    "Commercial": [
        "best",
        "top",
        "review",
        "reviews",
        "compare",
        "comparison",
        "vs",
        "alternative",
        "software",
        "platform",
        "service",
        "agency",
        "tool",
    ],
    "Navigational": [
        "login",
        "sign in",
        "dashboard",
        "official site",
        "contact",
        "about us",
        "account",
    ],
    "Informational": [
        "how to",
        "what is",
        "why",
        "guide",
        "tutorial",
        "tips",
        "learn",
        "definition",
        "checklist",
    ],
}

CLUSTER_RULES = {
    "seo": "SEO & Search Visibility",
    "search": "SEO & Search Visibility",
    "backlink": "Off-Page SEO & Authority",
    "link": "Technical SEO & Link Architecture",
    "sitemap": "Technical SEO & Crawlability",
    "crawl": "Technical SEO & Crawlability",
    "audit": "SEO Auditing & Monitoring",
    "ai": "AI Search & SEO Intelligence",
    "content": "Content Strategy & Topical Authority",
    "blog": "Content Marketing",
    "product": "Product Discovery & Ecommerce",
    "shop": "Product Discovery & Ecommerce",
    "pricing": "Commercial Conversion Pages",
    "service": "Service Acquisition Pages",
    "login": "Brand Navigation & Account Access",
}

TECHNICAL_CATEGORY_CONFIG = {
    "Discovery": {
        "icon": "Compass",
        "description": "Measures whether search engines can discover key URLs through sitemaps and internal pathways.",
        "business_impact": "Weak discovery reduces how many revenue-driving pages can enter the index.",
        "recommended_action": "Improve XML sitemap coverage and reinforce internal linking to priority pages.",
    },
    "Crawlability": {
        "icon": "Route",
        "description": "Assesses whether bots can access pages efficiently without blockers or broken pathways.",
        "business_impact": "Poor crawlability wastes crawl budget and slows content refresh in search.",
        "recommended_action": "Resolve robots, redirect, and broken-path issues that slow crawler access.",
    },
    "Indexability": {
        "icon": "Database",
        "description": "Evaluates whether pages send consistent canonical and indexation signals.",
        "business_impact": "Conflicting indexation rules can remove ranking pages from search entirely.",
        "recommended_action": "Fix noindex, canonical, and duplicate signal conflicts on priority pages.",
    },
    "Rendering": {
        "icon": "Layout",
        "description": "Reviews how clearly the page communicates topic relevance through headings and metadata.",
        "business_impact": "Weak rendering signals make it harder for search systems to interpret page purpose.",
        "recommended_action": "Strengthen titles, H1/H2 hierarchy, and content context for the target topic.",
    },
    "Performance": {
        "icon": "Zap",
        "description": "Tracks speed and page weight factors that influence crawl efficiency and user satisfaction.",
        "business_impact": "Slow pages reduce conversions and can suppress visibility on competitive SERPs.",
        "recommended_action": "Reduce response time, trim heavy assets, and optimize server delivery.",
    },
    "Security": {
        "icon": "Shield",
        "description": "Confirms whether the page is served securely over HTTPS.",
        "business_impact": "Security warnings damage trust and can reduce both rankings and conversions.",
        "recommended_action": "Enforce HTTPS everywhere and resolve certificate issues immediately.",
    },
    "Structured Data": {
        "icon": "Code",
        "description": "Prepared for schema-quality validation and rich-result readiness scoring.",
        "business_impact": "Schema gaps limit the page's ability to earn enhanced SERP features.",
        "recommended_action": "Plan schema markup for Organization, WebPage, Article, Product, or FAQ entities.",
    },
}

PRIORITY_STYLE = {
    "Critical": {
        "badge_class": "bg-danger-subtle text-danger border border-danger-subtle",
        "card_class": "border-danger",
    },
    "High": {
        "badge_class": "bg-warning-subtle text-warning border border-warning-subtle",
        "card_class": "border-warning",
    },
    "Medium": {
        "badge_class": "bg-primary-subtle text-primary border border-primary-subtle",
        "card_class": "border-primary",
    },
    "Low": {
        "badge_class": "bg-success-subtle text-success border border-success-subtle",
        "card_class": "border-success",
    },
}


def build_topic_intelligence(
    *,
    url: str,
    page_title: str = "",
    meta_title: str = "",
    meta_description: str = "",
    h1: str = "",
    h2: str = "",
    content_text: str = "",
    word_count: int | None = None,
    h2_count: int | None = None,
    result=None,
    issues=None,
    technical_snapshot: dict | None = None,
) -> dict:
    normalized_url = normalize_url(url)
    page_title = clean_text(page_title or "")
    meta_title = clean_text(meta_title or page_title or "")
    meta_description = clean_text(meta_description or "")
    h1 = clean_text(h1 or "")
    h2 = clean_text(h2 or "")
    content_text = clean_text(content_text or "")

    sections = {
        "url": normalized_url,
        "h1": h1,
        "h2": h2,
        "title": page_title,
        "meta_title": meta_title,
        "meta_description": meta_description,
        "content": content_text[:7000],
    }
    weighted_candidates = _extract_weighted_candidates(sections)
    primary_keyword = weighted_candidates[0] if weighted_candidates else _keyword_from_url(normalized_url)
    secondary_keywords = _secondary_keywords(weighted_candidates, primary_keyword)
    long_tail_keywords = _long_tail_keywords(weighted_candidates, primary_keyword)
    supporting_keywords = _supporting_keywords(weighted_candidates, primary_keyword, secondary_keywords)
    semantic_keywords = _semantic_keywords(primary_keyword, secondary_keywords, long_tail_keywords)
    topic = _detected_topic(primary_keyword, page_title, h1)
    intent_profile = _detect_search_intent_profile(sections, normalized_url)
    intent = intent_profile["label"]
    category = _detect_content_category(normalized_url, sections, intent)
    cluster = _detect_topic_cluster(primary_keyword, secondary_keywords + semantic_keywords, category)
    keyword_coverage = _keyword_coverage(primary_keyword, sections)
    semantic_relevance = _semantic_relevance(primary_keyword, secondary_keywords + semantic_keywords, sections)
    keyword_alignment = _keyword_alignment(primary_keyword, sections)
    focus_score = _content_focus_score(sections, keyword_coverage, semantic_relevance, word_count)
    readability = _readability_score(content_text, word_count)
    heading_structure = _heading_structure_score(h1, h2_count, h2)
    topical_authority = _topical_authority_score(
        word_count=word_count,
        semantic_relevance=semantic_relevance,
        long_tail_keywords=long_tail_keywords,
        h2_count=h2_count,
    )
    ai_visibility = _ai_visibility_score(
        sections=sections,
        keyword_coverage=keyword_coverage,
        semantic_relevance=semantic_relevance,
        focus_score=focus_score,
        word_count=word_count,
        intent=intent,
    )
    keyword_density = _keyword_density(primary_keyword, sections["content"])
    keyword_placement = _keyword_placement(primary_keyword, sections)
    missing_keywords = _missing_keywords(semantic_keywords + supporting_keywords, sections)
    keyword_opportunity_score = _keyword_opportunity_score(
        keyword_coverage=keyword_coverage,
        semantic_relevance=semantic_relevance,
        keyword_alignment=keyword_alignment,
        missing_keywords=missing_keywords,
    )
    target_audience = _detect_target_audience(
        intent=intent,
        category=category,
        primary_keyword=primary_keyword,
        topic_cluster=cluster,
    )

    content_quality = {
        "content_focus_score": focus_score,
        "keyword_alignment_pct": keyword_alignment,
        "semantic_coverage_pct": semantic_relevance,
        "topical_authority_pct": topical_authority,
        "content_readability_pct": readability,
        "heading_structure_pct": heading_structure,
        "word_count": word_count or len(_tokenize(sections["content"])),
    }
    technical_seo_intelligence = _build_technical_seo_intelligence(
        result=result,
        issues=issues,
        sections=sections,
        h2_count=h2_count,
        content_quality=content_quality,
        technical_snapshot=technical_snapshot or {},
    )
    action_priority = _build_action_priority(
        issues=issues,
        primary_keyword=primary_keyword,
        intent=intent,
        content_quality=content_quality,
        technical_seo_intelligence=technical_seo_intelligence,
        missing_keywords=missing_keywords,
        has_missing_h1=not bool(h1),
    )
    executive_summary = _build_executive_summary(
        primary_keyword=primary_keyword,
        intent_profile=intent_profile,
        topic=topic,
        ai_visibility=ai_visibility,
        overall_health_score=getattr(result, "health_score", None),
        action_priority=action_priority,
        issues=issues,
    )
    ai_insight = _build_ai_insight(
        primary_keyword=primary_keyword,
        intent=intent,
        cluster=cluster,
        focus_score=focus_score,
        category=category,
        semantic_relevance=semantic_relevance,
        technical_seo_intelligence=technical_seo_intelligence,
        action_priority=action_priority,
    )
    visual_dashboard_cards = _build_visual_dashboard_cards(
        result=result,
        ai_visibility=ai_visibility,
        keyword_coverage=keyword_coverage,
        content_quality=content_quality,
        technical_seo_intelligence=technical_seo_intelligence,
    )
    competitor_mode = _build_competitor_mode_placeholder(primary_keyword, cluster)

    keyword_intelligence = {
        "primary_keyword": primary_keyword,
        "secondary_keywords": secondary_keywords,
        "supporting_keywords": supporting_keywords,
        "long_tail_keywords": long_tail_keywords,
        "semantic_keywords": semantic_keywords,
        "keyword_density_pct": keyword_density,
        "keyword_placement": keyword_placement,
        "missing_keywords": missing_keywords,
        "keyword_opportunity_score": keyword_opportunity_score,
    }

    return {
        "primary_keyword": primary_keyword,
        "primary_h1": h1 or "H1 Missing",
        "primary_h2": h2 or "H2 Not Measured",
        "page_title": page_title or "Title Missing",
        "meta_title": meta_title or "Title Missing",
        "meta_description": meta_description or "Meta Description Missing",
        "detected_topic": topic,
        "search_intent": intent,
        "search_intent_confidence_pct": intent_profile["confidence_pct"],
        "intent_signal_summary": intent_profile["summary"],
        "content_category": category,
        "topic_cluster": cluster,
        "target_audience": target_audience,
        "ai_visibility_potential": ai_visibility,
        "top_keyword": primary_keyword,
        "secondary_keywords": secondary_keywords,
        "long_tail_keywords": long_tail_keywords,
        "semantic_keywords": semantic_keywords,
        "supporting_keywords": supporting_keywords,
        "keyword_coverage_pct": keyword_coverage,
        "semantic_relevance_pct": semantic_relevance,
        "content_focus_score": focus_score,
        "keyword_intelligence": keyword_intelligence,
        "content_quality": content_quality,
        "technical_seo_intelligence": technical_seo_intelligence,
        "action_priority": action_priority,
        "executive_summary": executive_summary,
        "top_ai_recommendations": executive_summary["top_ai_recommendations"],
        "top_critical_issues": executive_summary["top_critical_issues"],
        "ai_insight": ai_insight,
        "ai_seo_insights": {
            "executive_ai_summary": ai_insight,
            "opportunity_statement": _build_opportunity_statement(keyword_intelligence, content_quality),
        },
        "visual_dashboard_cards": visual_dashboard_cards,
        "competitor_mode": competitor_mode,
        "intent_badge_class": _intent_badge_class(intent),
        "visibility_badge_class": _visibility_badge_class(ai_visibility),
        "has_missing_h1": not bool(h1),
    }


def build_topic_intelligence_from_html(url: str, html: bytes | str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.title.string if soup.title and soup.title.string else ""
    meta_description_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = meta_description_tag.get("content", "") if meta_description_tag else ""
    auth_topic = None
    content_root = _primary_content_root(soup)
    h1_tag = content_root.find("h1") if content_root else soup.find("h1")
    h1 = h1_tag.get_text(" ", strip=True) if h1_tag else ""
    h2_tags = [
        heading.get_text(" ", strip=True)
        for heading in (content_root.find_all("h2") if content_root else soup.find_all("h2"))[:4]
    ]
    content_text = _extract_primary_content_text(soup)
    if _is_authentication_page(url, title_tag, h1, meta_description, content_text):
        auth_topic = _authentication_topic_label(url, title_tag, h1, meta_description, content_text)
        if not h1:
            h1 = auth_topic
        if not title_tag:
            title_tag = auth_topic
        if not meta_description:
            meta_description = f"{auth_topic} page"
        content_text = " ".join(
            part for part in [auth_topic, h1, title_tag, meta_description, content_text] if part
        )
    words = [word for word in content_text.split() if word]
    intelligence = build_topic_intelligence(
        url=url,
        page_title=title_tag,
        meta_title=title_tag,
        meta_description=meta_description,
        h1=h1,
        h2=" | ".join(h2_tags),
        content_text=content_text,
        word_count=len(words),
        h2_count=len(h2_tags),
    )
    if auth_topic:
        intelligence["primary_keyword"] = auth_topic
        intelligence["top_keyword"] = auth_topic
        intelligence["detected_topic"] = auth_topic
    return intelligence


def _primary_content_root(soup: BeautifulSoup):
    return (
        soup.find("main")
        or soup.find(attrs={"role": "main"})
        or soup.find("article")
        or soup.find(id=re.compile(r"content|main", re.I))
        or soup.find(class_=re.compile(r"content|main", re.I))
    )


def _extract_primary_content_text(soup: BeautifulSoup) -> str:
    content_root = _primary_content_root(soup)
    if content_root:
        return clean_text(content_root.get_text(" ", strip=True))

    body = soup.body or soup
    for tag in body.find_all(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
        tag.decompose()
    for node in body.find_all(_is_boilerplate_container):
        node.decompose()
    return clean_text(body.get_text(" ", strip=True))


def _is_boilerplate_container(tag) -> bool:
    if not getattr(tag, "attrs", None):
        return False
    signals = " ".join(
        str(value)
        for value in [
            tag.get("id", ""),
            " ".join(tag.get("class", [])) if isinstance(tag.get("class"), list) else tag.get("class", ""),
            tag.get("aria-label", ""),
            tag.get("role", ""),
        ]
        if value
    ).lower()
    return any(
        token in signals
        for token in [
            "footer",
            "navbar",
            "navigation",
            "newsletter",
            "subscribe",
            "signup",
            "sign-up",
            "cta",
            "call-to-action",
            "cookie",
            "breadcrumb",
            "promo",
            "banner",
        ]
    )


def _is_authentication_page(
    url: str,
    page_title: str,
    h1: str,
    meta_description: str,
    content_text: str,
) -> bool:
    path = urlparse(url).path.lower()
    if any(
        token in path
        for token in ["/login", "/signin", "/sign-in", "/accounts/login", "/users/login", "/auth/"]
    ):
        return True
    combined = " ".join([page_title, h1, meta_description, content_text[:300]]).lower()
    return any(
        token in combined
        for token in [
            " login ",
            " log in ",
            "signin",
            "sign in",
            "sign-in",
            "authentication",
            "authenticate",
            "account access",
        ]
    )


def _authentication_topic_label(
    url: str,
    page_title: str,
    h1: str,
    meta_description: str,
    content_text: str,
) -> str:
    combined = " ".join([h1, page_title, meta_description, content_text[:300], _keyword_from_url(url)]).lower()
    if any(token in combined for token in ["sign in", "sign-in", "signin"]):
        return "Sign In"
    if any(token in combined for token in ["authentication", "authenticate"]):
        return "Authentication"
    if any(token in combined for token in ["account access", "account login"]):
        return "Account Access"
    return "Login"


def build_topic_intelligence_from_url(url: str) -> dict:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    normalized_url = normalize_url(url)
    try:
        response = session.get(normalized_url, timeout=12, allow_redirects=True)
        if response.status_code >= 400 or "html" not in response.headers.get("Content-Type", "").lower():
            raise requests.RequestException("The page did not return analyzable HTML.")
        return build_topic_intelligence_from_html(response.url, response.content)
    except requests.RequestException:
        return build_topic_intelligence(url=normalized_url)


def build_topic_intelligence_from_page_audit(page_audit, fallback_url: str, *, result=None, issues=None) -> dict:
    return build_topic_intelligence(
        url=getattr(page_audit, "final_url", None) or getattr(page_audit, "url", None) or fallback_url,
        page_title=getattr(page_audit, "title_tag", "") or "",
        meta_title=getattr(page_audit, "title_tag", "") or "",
        meta_description=getattr(page_audit, "meta_description", "") or "",
        h1=getattr(page_audit, "h1_text", "") or "",
        h2="H2 headings not stored in crawl model" if getattr(page_audit, "h2_count", 0) else "",
        content_text=" ".join(
            part
            for part in [
                getattr(page_audit, "title_tag", "") or "",
                getattr(page_audit, "meta_description", "") or "",
                getattr(page_audit, "h1_text", "") or "",
            ]
            if part
        ),
        word_count=getattr(page_audit, "word_count", None),
        h2_count=getattr(page_audit, "h2_count", None),
        result=result,
        issues=issues,
        technical_snapshot={
            "has_robots": getattr(page_audit, "has_robots", False),
            "has_sitemap": getattr(page_audit, "has_sitemap", False),
            "status_code": getattr(page_audit, "status_code", None),
            "response_time": getattr(page_audit, "response_time", None),
        },
    )


def _analyze_image_intelligence(all_images, target_keyword):
    images_found = all_images
    missing_alt = []
    duplicate_alt = []
    missing_caption = []
    missing_title = []
    broken_images = []
    lazy_loaded = []
    unsupported_formats = []
    
    supported_formats = {"jpg", "jpeg", "png", "gif", "webp", "svg", "avif"}
    alt_texts_seen = {}
    
    for img in images_found:
        alt = img.get("alt", "").strip()
        title = img.get("title", "").strip()
        caption = img.get("caption", "").strip()
        loading = img.get("loading", "")
        src = img.get("src", "")
        
        if not alt:
            missing_alt.append(img)
        else:
            if alt in alt_texts_seen:
                duplicate_alt.append(img)
                duplicate_alt.append(alt_texts_seen[alt])
            else:
                alt_texts_seen[alt] = img
        
        if not title:
            missing_title.append(img)
        if not caption:
            missing_caption.append(img)
        if loading == "lazy":
            lazy_loaded.append(img)
        
        ext = src.split(".")[-1].lower().split("?")[0]
        if ext not in supported_formats and src:
            unsupported_formats.append(img)
    
    total = len(images_found)
    issues = len(missing_alt) + len(missing_caption) + len(duplicate_alt) / 2
    health_score = max(0, int(100 - (issues / max(total, 1)) * 40))
    
    keyword_match_score = 0
    for img in images_found:
        alt = img.get("alt", "").lower()
        title = img.get("title", "").lower()
        if target_keyword.lower() in alt or target_keyword.lower() in title:
            keyword_match_score += 10
    keyword_match_score = min(100, keyword_match_score)
    
    # Build reasoning for scores
    score_reasoning = []
    if missing_alt:
        score_reasoning.append(f"Missing alt text on {len(missing_alt)} images")
    if duplicate_alt:
        score_reasoning.append(f"Duplicate alt text on {len(duplicate_alt)//2} images")
    if missing_caption:
        score_reasoning.append(f"Missing captions on {len(missing_caption)} images")
    if missing_title:
        score_reasoning.append(f"Missing titles on {len(missing_title)} images")
    if unsupported_formats:
        score_reasoning.append(f"Unsupported image formats on {len(unsupported_formats)} images")
    if keyword_match_score < 50:
        score_reasoning.append(f"Low keyword alignment with '{target_keyword}'")
    
    return {
        "images_found": len(images_found),
        "images_indexed": len(images_found) - len(missing_alt) if images_found else 0,
        "missing_images": [],
        "broken_images": broken_images,
        "missing_alt": missing_alt,
        "duplicate_alt": duplicate_alt,
        "large_images": [],
        "missing_caption": missing_caption,
        "missing_license": [],
        "lazy_loaded": lazy_loaded,
        "unsupported_formats": unsupported_formats,
        "image_seo_score": health_score,
        "image_visibility_score": min(100, health_score + keyword_match_score),
        "image_discovery_score": min(100, health_score + 20),
        "keyword_match_score": keyword_match_score,
        "score_reasoning": score_reasoning if score_reasoning else ["All key image SEO elements are present and optimized"],
        # AI Interpretation
        "ai_image_interpretation": {
            "detected_objects": [],  # Placeholder for future OCR/AI
            "detected_scene": "",
            "detected_product": "",
            "detected_logo": "",
            "detected_brand": "",
            "detected_topic": target_keyword,
            "marketing_category": "",
            "image_confidence": 0,
            "suggested_alt": f"{target_keyword} - {len(missing_alt)} images need descriptive alt text",
            "suggested_caption": "",
            "suggested_filename": "",
            "image_marketing_relevance": keyword_match_score
        }
    }


def _analyze_video_intelligence(all_videos, has_video_schema, target_keyword, page_text=""):
    missing_thumbnails = []
    missing_titles = []
    missing_descriptions = []
    missing_durations = []
    missing_upload_dates = []
    missing_keyword_in_content = False
    
    for video in all_videos:
        if not video.get("poster"):
            missing_thumbnails.append(video)
    
    total = len(all_videos)
    issues = len(missing_thumbnails) + (0 if has_video_schema else total)
    video_seo_score = max(0, int(100 - (issues / max(total, 1)) * 60))
    rich_result_eligible = has_video_schema and len(missing_thumbnails) == 0
    
    # Check keyword match in page text
    keyword_match = 0
    if target_keyword and target_keyword.lower() in page_text.lower():
        keyword_match = 100
    else:
        keyword_match = 0
        missing_keyword_in_content = True
    
    # Build detailed reasoning
    score_reasoning = []
    if not has_video_schema:
        score_reasoning.append("Missing VideoObject schema markup")
    if missing_thumbnails:
        score_reasoning.append(f"Missing thumbnail on {len(missing_thumbnails)} videos")
    if missing_titles:
        score_reasoning.append(f"Missing titles on {len(missing_titles)} videos")
    if missing_upload_dates:
        score_reasoning.append(f"Missing upload dates on {len(missing_upload_dates)} videos")
    if missing_keyword_in_content:
        score_reasoning.append(f"Missing keyword alignment with '{target_keyword}'")
    
    # Calculate marketing relevance
    marketing_relevance = keyword_match
    marketing_relevance_label = "High" if marketing_relevance > 70 else "Medium" if marketing_relevance > 30 else "Low"
    
    return {
        "videos_found": len(all_videos),
        "videos_indexed": len(all_videos) if has_video_schema else 0,
        "video_sitemap_present": False,
        "missing_video_sitemap": [],
        "missing_thumbnails": missing_thumbnails,
        "missing_titles": missing_titles,
        "missing_descriptions": missing_descriptions,
        "missing_durations": missing_durations,
        "missing_upload_dates": missing_upload_dates,
        "missing_schema": [] if has_video_schema else all_videos,
        "videoobject_schema": has_video_schema,
        "rich_result_eligible": rich_result_eligible,
        "video_seo_score": video_seo_score,
        "video_discovery_score": min(100, video_seo_score + (20 if rich_result_eligible else 0)),
        "keyword_match_score": keyword_match,
        "marketing_relevance": marketing_relevance_label,
        "score_reasoning": score_reasoning if score_reasoning else ["All key video SEO elements are present and optimized"],
        # Detailed video analysis
        "video_details": [
            {
                "title": video.get("title", "Untitled"),
                "description": video.get("description", ""),
                "src": video.get("src", ""),
                "page_url": video.get("page_url", "")
            } for video in all_videos
        ],
        # AI Interpretation
        "ai_video_interpretation": {
            "detected_topic": target_keyword,
            "detected_category": "",
            "target_audience": "",
            "marketing_intent": "",
            "keyword_match": keyword_match,
            "thumbnail_quality": 0,
            "thumbnail_ctr_prediction": 0,
            "video_discoverability": video_seo_score,
            "suggested_title": "",
            "suggested_description": "",
            "suggested_thumbnail_text": "",
            "suggested_filename": ""
        }
    }


# Industry detection keywords
INDUSTRY_KEYWORDS = {
    "Entertainment": ["movie", "film", "music", "song", "video", "youtube", "entertainment", "game", "gaming", "tv", "show"],
    "Technology": ["software", "tech", "computer", "code", "programming", "ai", "digital", "app", "website"],
    "Digital Marketing": ["marketing", "seo", "ppc", "advertising", "social media", "content marketing", "lead generation", "analytics", "campaign"],
    "Finance": ["finance", "banking", "investment", "money", "stock", "loan", "credit", "budget"],
    "Healthcare": ["health", "medical", "doctor", "hospital", "medicine", "wellness", "fitness"],
    "Education": ["education", "school", "university", "course", "learning", "teach", "student"]
}

def _detect_industry(page_text, detected_topic):
    page_text_lower = page_text.lower()
    detected_topic_lower = detected_topic.lower() if detected_topic else ""
    
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in page_text_lower or keyword in detected_topic_lower:
                return industry
    return "General"

def _detect_audience(page_text, search_intent):
    intent_lower = search_intent.lower() if search_intent else ""
    if "transactional" in intent_lower or "commercial" in intent_lower:
        return "Potential Customers"
    elif "informational" in intent_lower:
        return "Information Seekers"
    return "General Audience"

def _analyze_text_intelligence(topic_intel, target_keyword, page_text=""):
    detected_topic = topic_intel.get("primary_keyword", "")
    # Calculate topic match based on keyword overlap
    topic_match = 0
    if target_keyword and detected_topic:
        target_tokens = set(target_keyword.lower().split())
        detected_tokens = set(detected_topic.lower().split())
        overlap = len(target_tokens & detected_tokens)
        total = len(target_tokens | detected_tokens)
        if total > 0:
            topic_match = int((overlap / total) * 100)
    
    # Calculate semantic match
    semantic_match = topic_intel.get("semantic_relevance_pct", 0)
    
    # Calculate intent match
    intent_match = 50  # Default
    detected_intent = topic_intel.get("search_intent", "").lower()
    # Simple intent mapping
    if "informational" in detected_intent:
        intent_match = 70
    elif "commercial" in detected_intent:
        intent_match = 80
    elif "transactional" in detected_intent:
        intent_match = 90
    
    # Industry match
    detected_industry = _detect_industry(page_text, detected_topic)
    target_industry = _detect_industry(target_keyword, target_keyword)
    industry_match = 100 if detected_industry == target_industry else 0
    
    # Audience match
    detected_audience = _detect_audience(page_text, detected_intent)
    audience_match = 50  # Default, can be enhanced later
    
    # Marketing relevance label
    if topic_match > 70:
        marketing_relevance = "High"
    elif topic_match > 30:
        marketing_relevance = "Medium"
    elif topic_match > 10:
        marketing_relevance = "Low"
    else:
        marketing_relevance = "Very Low"
    
    # Calculate marketing readiness score
    marketing_readiness = int((topic_match * 0.4) + (semantic_match * 0.2) + (intent_match * 0.2) + (industry_match * 0.1) + (audience_match * 0.1))
    
    # AI conclusion
    if topic_match > 70:
        ai_conclusion = f"The detected content has strong alignment with the target keyword '{target_keyword}'. This content is well-positioned for marketing and SEO optimization."
    elif topic_match > 30:
        ai_conclusion = f"The detected content has some alignment with the target keyword '{target_keyword}', but can be optimized to improve relevance."
    else:
        ai_conclusion = f"The detected content is unrelated to the requested keyword '{target_keyword}'. Google identifies this as '{detected_topic or 'general content'}'. Optimizing this page for '{target_keyword}' would not produce meaningful SEO value."
    
    return {
        "primary_keyword": topic_intel.get("primary_keyword", target_keyword),
        "secondary_keywords": topic_intel.get("secondary_keywords", []),
        "long_tail_keywords": topic_intel.get("long_tail_keywords", []),
        "semantic_keywords": topic_intel.get("semantic_keywords", []),
        "topic_cluster": topic_intel.get("topic_cluster", ""),
        "entities": [],
        "search_intent": topic_intel.get("search_intent", ""),
        "target_audience": detected_audience,
        "content_category": topic_intel.get("content_category", ""),
        "marketing_funnel_stage": "",
        "keyword_coverage": topic_intel.get("keyword_coverage_pct", 0),
        "semantic_coverage": topic_intel.get("semantic_relevance_pct", 0),
        "topic_authority": topic_intel.get("content_focus_score", 0),
        # New content alignment metrics
        "content_alignment": {
            "detected_topic": detected_topic,
            "detected_content_type": "Web Page",
            "detected_industry": detected_industry,
            "detected_audience": detected_audience,
            "target_keyword": target_keyword,
            "topic_match": topic_match,
            "semantic_match": semantic_match,
            "intent_match": intent_match,
            "industry_match": industry_match,
            "audience_match": audience_match,
            "final_alignment_score": int((topic_match + semantic_match + intent_match + industry_match + audience_match) / 5),
            "marketing_relevance": marketing_relevance,
            "marketing_readiness_score": marketing_readiness,
            "ai_conclusion": ai_conclusion
        }
    }


def _analyze_google_discovery(xml_found, image_score, video_score, mobile_score, keyword_score):
    discovery_score = min(100, (
        (20 if xml_found else 0) +
        (image_score * 0.25) +
        (video_score * 0.25) +
        (mobile_score * 0.25) +
        (keyword_score * 0.25)
    ))
    
    stages = []
    
    # XML Sitemap stage
    stages.append({
        "name": "Canonical & Sitemap",
        "status": "PASS" if xml_found else "FAIL",
        "explanation": "XML sitemap detected, helping Google discover all your pages" if xml_found else "Missing XML sitemap - add one to improve page discovery"
    })
    
    # VideoObject schema
    stages.append({
        "name": "VideoObject Schema",
        "status": "PASS" if video_score > 80 else "WARNING",
        "explanation": "Video schema is properly implemented" if video_score > 80 else "Missing or incomplete VideoObject schema - add it to enable rich results"
    })
    
    # Rendering
    stages.append({
        "name": "Rendering",
        "status": "PASS" if mobile_score > 80 else "WARNING",
        "explanation": "Page renders well on mobile devices" if mobile_score > 80 else "Needs mobile optimization - check viewport and responsive design"
    })
    
    # Rich Results
    rich_result_status = "PASS" if (video_score > 80 and image_score > 80) else "FAIL"
    stages.append({
        "name": "Rich Results",
        "status": rich_result_status,
        "explanation": "Eligible for rich results in Google SERPs" if rich_result_status == "PASS" else "Missing thumbnail resolution or schema markup for rich results"
    })
    
    return {
        "discovery_score": int(discovery_score),
        "blocked_stage": None,
        "index_stage": "Good" if xml_found else "Needs Sitemap",
        "rendering_stage": "Good" if mobile_score > 80 else "Needs Mobile Optimization",
        "rich_result_stage": "Eligible" if video_score > 80 else "Needs Video Schema",
        "stages": stages
    }


def _analyze_digital_marketing_intelligence(text_intel, image_intel, video_intel, target_keyword):
    content_alignment = text_intel.get("content_alignment", {})
    detected_topic = content_alignment.get("detected_topic", "")
    marketing_relevance = content_alignment.get("marketing_relevance", "Low")
    topic_match = content_alignment.get("topic_match", 0)
    
    primary_keyword = text_intel.get("primary_keyword", target_keyword)
    secondary_keywords = text_intel.get("secondary_keywords", [])
    long_tail_keywords = text_intel.get("long_tail_keywords", [])
    
    target_keyword_lower = target_keyword.lower() if target_keyword else ""
    
    # Generate content ideas based on target keyword's industry
    suggested_content_ideas = []
    if "digital marketing" in target_keyword_lower:
        suggested_content_ideas = [
            "SEO Strategy",
            "PPC Campaigns",
            "Content Marketing",
            "Social Media Marketing",
            "Lead Generation",
            "Analytics"
        ]
    elif "entertainment" in target_keyword_lower or "music" in target_keyword_lower or "video" in target_keyword_lower:
        suggested_content_ideas = [
            "Video Production Tips",
            "Content Creation",
            "Audience Engagement",
            "Monetization Strategies",
            "Social Media Growth"
        ]
    elif "technology" in target_keyword_lower or "software" in target_keyword_lower:
        suggested_content_ideas = [
            "Product Reviews",
            "Software Tutorials",
            "Tech Trends",
            "Development Guides",
            "User Experience Tips"
        ]
    else:
        # Generic but target-specific ideas
        suggested_content_ideas = [
            f"Complete Guide to {target_keyword}",
            f"Top 10 {target_keyword} Tips",
            f"{target_keyword} Best Practices",
            f"How to Get Started with {target_keyword}",
            f"Common {target_keyword} Mistakes to Avoid"
        ]
    
    # Contextual AI conclusion for marketing
    if marketing_relevance == "Very Low":
        marketing_ai_conclusion = f"The analyzed content is unrelated to the requested marketing topic '{target_keyword}'. This content is best suited for topics related to '{detected_topic or 'its current focus'}', not '{target_keyword}'."
    elif marketing_relevance == "Low":
        marketing_ai_conclusion = f"The analyzed content has limited relevance to '{target_keyword}'. Consider creating new content specifically tailored to this keyword for better results."
    else:
        marketing_ai_conclusion = f"The analyzed content aligns well with '{target_keyword}'. This content can be optimized and used as a foundation for marketing campaigns."
    
    return {
        "primary_marketing_keyword": primary_keyword,
        "supporting_keywords": secondary_keywords,
        "keyword_gaps": [f"Content missing focus on {target_keyword}"] if marketing_relevance == "Very Low" else [],
        "content_opportunities": [
            f"Create more content around {target_keyword}",
            f"Optimize existing content for better alignment",
            f"Add supporting media (images/videos) about {target_keyword}"
        ],
        "search_intent": text_intel.get("search_intent", ""),
        "competition_estimate": "Medium",
        "suggested_landing_page": f"/{target_keyword.replace(' ', '-')}",
        "suggested_cta": "Get Started" if marketing_relevance in ["High", "Medium"] else "Learn More",
        "suggested_content_ideas": suggested_content_ideas,
        "marketing_ai_conclusion": marketing_ai_conclusion,
        "suggested_meta_title": f"{target_keyword} | Comprehensive Guide" if marketing_relevance in ["High", "Medium"] else "",
        "suggested_meta_description": f"Learn everything about {target_keyword}. Complete guide with tips, examples, and best practices." if marketing_relevance in ["High", "Medium"] else "",
        "suggested_faq": [
            f"What is {target_keyword}?",
            f"Why is {target_keyword} important?",
            f"How to get started with {target_keyword}?"
        ] if marketing_relevance in ["High", "Medium"] else [],
        "suggested_linkedin_post": f"📊 Just published our latest guide on {target_keyword}! Check out key insights and best practices. #Marketing #SEO #{target_keyword.replace(' ', '')}" if marketing_relevance in ["High", "Medium"] else "",
        "suggested_facebook_caption": f"Want to master {target_keyword}? We've got you covered! Read our complete guide here." if marketing_relevance in ["High", "Medium"] else "",
        "suggested_instagram_caption": f"✨ New post alert! Discover everything you need to know about {target_keyword} 🔥 #Marketing #GrowthHacks" if marketing_relevance in ["High", "Medium"] else "",
        "suggested_internal_links": [
            "Related blog post on content strategy",
            "SEO best practices guide"
        ] if marketing_relevance in ["High", "Medium"] else [],
        "suggested_content_cluster": [primary_keyword, *secondary_keywords[:3]] if marketing_relevance in ["High", "Medium"] else [],
        "suggested_conversion_goal": "Increase leads by 20%" if marketing_relevance in ["High", "Medium"] else "",
        "suggested_campaign": f"Q4 {target_keyword} Awareness Campaign" if marketing_relevance in ["High", "Medium"] else ""
    }





def build_sitemap_intelligence_report(url: str, target_keyword: str | None = None, sitemap_url: str | None = None) -> dict:
    normalized_url = normalize_url(url)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    
    # Step 1: XML Sitemap Discovery
    robots_url = urljoin(normalized_url, "/robots.txt")
    sitemap_candidates = [sitemap_url] if sitemap_url else [
        urljoin(normalized_url, "/sitemap.xml"),
        urljoin(normalized_url, "/sitemap_index.xml"),
    ]
    
    robots_status = "Not Measured"
    discovered_sitemap = None
    sitemap_status = "Not Measured"
    sitemap_urls_list = []
    broken_sitemap_urls = []
    noindex_sitemap_urls = []
    redirected_sitemap_urls = []
    
    try:
        response = session.get(robots_url, timeout=8, allow_redirects=True)
        robots_status = "Available" if response.status_code == 200 else f"HTTP {response.status_code}"
    except requests.RequestException:
        robots_status = "Unavailable"
    
    for candidate_url in sitemap_candidates:
        if not candidate_url:
            continue
        try:
            response = session.get(candidate_url, timeout=8, allow_redirects=True)
            if response.status_code == 200:
                discovered_sitemap = candidate_url
                sitemap_status = "Available"
                # Parse sitemap
                from xml.etree import ElementTree as ET
                try:
                    root = ET.fromstring(response.content)
                    # Handle sitemap index
                    if root.tag.endswith("sitemapindex"):
                        for sitemap in root.findall(".//{*}sitemap"):
                            loc = sitemap.find("{*}loc")
                            if loc is not None and loc.text:
                                sitemap_urls_list.append(loc.text)
                    else:
                        for url_entry in root.findall(".//{*}url"):
                            loc = url_entry.find("{*}loc")
                            if loc is not None and loc.text:
                                sitemap_urls_list.append(loc.text)
                except Exception:
                    pass
                break
        except requests.RequestException:
            continue
    if sitemap_status == "Not Measured":
        sitemap_status = "Unavailable"
    
    # Step 2: Analyze pages for media, text, mobile, etc.
    all_images = []
    all_videos = []
    has_any_video_schema = False
    mobile_pages = []
    viewport_issues = []
    keyword_in_page_text = []
    has_html_sitemap = False
    has_hreflang = []
    
    # Check some pages from sitemap (or homepage)
    pages_to_check = sitemap_urls_list[:5] if sitemap_urls_list else [normalized_url]
    
    for page_url in pages_to_check:
        try:
            response = session.get(page_url, timeout=8, allow_redirects=True)
            if response.status_code >= 400:
                broken_sitemap_urls.append(page_url)
                continue
            if response.status_code in (301, 302, 303, 307, 308):
                redirected_sitemap_urls.append(page_url)
            
            # Check for noindex
            soup = BeautifulSoup(response.content, "html.parser")
            noindex_meta = soup.find("meta", attrs={"name": "robots", "content": lambda x: x and "noindex" in x.lower()})
            if noindex_meta:
                noindex_sitemap_urls.append(page_url)
            
            # Check for mobile signals
            viewport_meta = soup.find("meta", attrs={"name": "viewport"})
            if not viewport_meta:
                viewport_issues.append(page_url)
            mobile_pages.append(page_url)
            
            # Check for HTML sitemap
            if "sitemap" in soup.get_text(" ").lower():
                has_html_sitemap = True
            
            # Check for hreflang
            for link in soup.find_all("link", rel="alternate"):
                if link.has_attr("hreflang"):
                    has_hreflang.append({
                        "hreflang": link.get("hreflang"),
                        "href": link.get("href")
                    })
            
            # Extract images and videos with the new crawler-like logic
            img_tags = soup.find_all("img")
            for img in img_tags:
                src = img.get("src", "")
                absolute_src = urljoin(page_url, src) if src else ""
                alt = img.get("alt", "").strip()
                title = img.get("title", "").strip()
                caption = ""
                parent_figure = img.find_parent("figure")
                if parent_figure:
                    figcaption = parent_figure.find("figcaption")
                    if figcaption:
                        caption = clean_text(figcaption.get_text())
                loading_attr = img.get("loading", "")
                all_images.append({
                    "src": absolute_src,
                    "alt": alt,
                    "title": title,
                    "caption": caption,
                    "loading": loading_attr,
                    "width": img.get("width", ""),
                    "height": img.get("height", ""),
                    "page_url": page_url
                })
            
            # Extract videos
            video_tags = soup.find_all("video")
            for video in video_tags:
                src = video.get("src", "")
                poster = video.get("poster", "")
                all_videos.append({
                    "type": "native",
                    "src": urljoin(page_url, src) if src else "",
                    "poster": urljoin(page_url, poster) if poster else "",
                    "page_url": page_url
                })
            
            iframe_tags = soup.find_all("iframe", src=True)
            for iframe in iframe_tags:
                src = iframe["src"]
                if "youtube.com" in src or "youtu.be" in src or "vimeo.com" in src:
                    all_videos.append({
                        "type": "iframe",
                        "src": src,
                        "page_url": page_url
                    })
            
            # Check for VideoObject schema
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    import json
                    schema_data = json.loads(script.string)
                    if isinstance(schema_data, list):
                        for item in schema_data:
                            if item.get("@type") == "VideoObject":
                                has_any_video_schema = True
                    elif schema_data.get("@type") == "VideoObject":
                        has_any_video_schema = True
                except:
                    continue
            
            # Check keyword in page text
            page_text = soup.get_text(" ", strip=True).lower()
            if target_keyword and target_keyword.lower() in page_text:
                keyword_in_page_text.append(page_url)
                
        except requests.RequestException:
            continue
    
    # Capture main page text
    main_page_text = ""
    try:
        main_response = session.get(normalized_url, timeout=8, allow_redirects=True)
        if main_response.status_code == 200:
            main_soup = BeautifulSoup(main_response.content, "html.parser")
            main_page_text = main_soup.get_text(" ", strip=True)
    except requests.RequestException:
        pass
    
    # Calculate mobile health score
    mobile_health_score = 0
    if mobile_pages:
        total = len(mobile_pages)
        viewport_issues_count = len(viewport_issues)
        mobile_health_score = max(0, 100 - (viewport_issues_count / total) * 50)
    
    # Build topic intelligence
    topic_intelligence = build_topic_intelligence_from_url(normalized_url)
    topic_intelligence["technical_seo_intelligence"] = _build_technical_seo_intelligence(
        result=None,
        issues=[],
        sections={"url": normalized_url, "h1": "", "h2": "", "title": "", "meta_title": "", "meta_description": "", "content": ""},
        h2_count=0,
        content_quality=topic_intelligence["content_quality"],
        technical_snapshot={
            "robots_status": robots_status,
            "sitemap_status": sitemap_status,
        },
    )
    
    # Set default target keyword if not provided
    used_target_keyword = target_keyword or topic_intelligence.get("primary_keyword", "your primary keyword")
    
    # Analyze all modules
    image_intel = _analyze_image_intelligence(all_images, used_target_keyword)
    video_intel = _analyze_video_intelligence(all_videos, has_any_video_schema, used_target_keyword, main_page_text)
    text_intel = _analyze_text_intelligence(topic_intelligence, used_target_keyword, main_page_text)
    google_discovery = _analyze_google_discovery(
        discovered_sitemap is not None,
        image_intel.get("image_seo_score", 0),
        video_intel.get("video_seo_score", 0),
        mobile_health_score,
        text_intel.get("keyword_coverage", 0)
    )
    digital_marketing = _analyze_digital_marketing_intelligence(text_intel, image_intel, video_intel, used_target_keyword)
    
    # Generate AI Recommendations with contextual explanations (Phase 4)
    content_alignment = text_intel.get("content_alignment", {})
    marketing_relevance = content_alignment.get("marketing_relevance", "Low")
    
    recommendations = {
        "Critical": [],
        "High": [],
        "Medium": [],
        "Low": []
    }
    
    if discovered_sitemap is None:
        recommendations["Critical"].append({
            "issue": "Missing XML Sitemap",
            "explanation": "An XML sitemap helps Google discover all pages on your site, which is essential for SEO",
            "seo_impact": "High - limits page discovery",
            "business_impact": "Medium - potential missed traffic",
            "recommended_action": "Create and submit an XML sitemap to Google Search Console",
            "expected_improvement": "Increased page indexing"
        })
    if image_intel.get("missing_alt", []):
        recommendations["Critical"].append({
            "issue": f"Missing alt text on {len(image_intel.get('missing_alt', []))} images",
            "explanation": "Alt text helps search engines understand images and improves accessibility for visually impaired users",
            "seo_impact": "High - reduces image search visibility",
            "business_impact": "Medium - potential missed image traffic",
            "recommended_action": f"Add descriptive alt text to {len(image_intel.get('missing_alt', []))} images",
            "expected_improvement": "Better image SEO and accessibility"
        })
    if not has_any_video_schema and all_videos:
        recommendations["High"].append({
            "issue": "Missing VideoObject Schema",
            "explanation": "Video schema enables rich results in Google SERPs, which can significantly improve CTR",
            "seo_impact": "Medium - no video rich results",
            "business_impact": "Medium - lower CTR on video content",
            "recommended_action": "Add VideoObject schema markup to embedded videos",
            "expected_improvement": "Potential rich results in Google"
        })
    if viewport_issues:
        recommendations["High"].append({
            "issue": f"Missing viewport meta tag on {len(viewport_issues)} pages",
            "explanation": "Viewport tag is required for mobile-friendly design, which is a Google ranking factor",
            "seo_impact": "High - mobile usability issues",
            "business_impact": "High - poor mobile user experience",
            "recommended_action": f"Add viewport meta tags to {len(viewport_issues)} pages",
            "expected_improvement": "Better mobile rankings and UX"
        })
    
    # Only add these recommendations if content is relevant
    if marketing_relevance in ["High", "Medium"]:
        if not (image_intel.get("keyword_match_score", 0) > 50):
            recommendations["Medium"].append({
                "issue": "Low keyword alignment in images",
                "explanation": f"Images don't contain '{used_target_keyword}' in alt text or metadata, which reduces their relevance for this keyword",
                "seo_impact": "Medium - reduces image relevance",
                "business_impact": "Low",
                "recommended_action": f"Incorporate '{used_target_keyword}' into image alt text and file names",
                "expected_improvement": "Better image SEO for target keyword"
            })
        if image_intel.get("lazy_loaded", []):
            recommendations["Low"].append({
                "issue": "Lazy loaded images",
                "explanation": "Above-the-fold images should load immediately to improve perceived page speed",
                "seo_impact": "Low",
                "business_impact": "Low",
                "recommended_action": "Disable lazy loading for critical above-the-fold images",
                "expected_improvement": "Faster perceived load time"
            })
    else:
        # Add contextual recommendation about content relevance
        recommendations["Critical"].append({
            "issue": "Content Misalignment with Target Keyword",
            "explanation": content_alignment.get("ai_conclusion", "The analyzed content is not relevant to the target keyword"),
            "seo_impact": "Very High - content will not rank for the target keyword",
            "business_impact": "High - no marketing value for this keyword",
            "recommended_action": f"Create new content specifically tailored to '{used_target_keyword}' or choose a different target keyword",
            "expected_improvement": "Relevant content that can actually rank and drive traffic"
        })
    
    # Enhanced Executive Summary (Phase 4)
    content_alignment = text_intel.get("content_alignment", {})
    
    # Calculate overall score from modules that have scores
    scores = []
    if image_intel.get("image_seo_score") is not None:
        scores.append(image_intel.get("image_seo_score"))
    if video_intel.get("video_seo_score") is not None:
        scores.append(video_intel.get("video_seo_score"))
    if mobile_health_score is not None:
        scores.append(mobile_health_score)
    if google_discovery.get("discovery_score") is not None:
        scores.append(google_discovery.get("discovery_score"))
    
    overall_score = None
    if scores:
        overall_score = int(sum(scores) / len(scores))
    
    # Calculate business opportunity
    topic_match = content_alignment.get("topic_match", 0)
    if topic_match > 70:
        business_opportunity = "High Opportunity"
    elif topic_match > 30:
        business_opportunity = "Medium Opportunity"
    elif topic_match > 10:
        business_opportunity = "Low Opportunity"
    else:
        business_opportunity = "Not Relevant"
    
    # Calculate overall SEO readiness
    seo_readiness = None
    if google_discovery.get("discovery_score") is not None:
        seo_readiness = google_discovery.get("discovery_score")
    
    # Calculate overall marketing readiness (as a score now)
    marketing_readiness = content_alignment.get("marketing_readiness_score", 0)
    
    executive_summary = {
        "total_images": len(all_images),
        "total_videos": len(all_videos),
        "media_pages_checked": len(pages_to_check),
        "overall_score": overall_score,  # Can be None for N/A display
        "top_priority_issues": [rec for rec in recommendations["Critical"] + recommendations["High"]],
        
        # Phase 4 fields
        "detected_content_type": content_alignment.get("detected_content_type", "Web Page"),
        "detected_industry": content_alignment.get("detected_industry", "General"),
        "detected_audience": content_alignment.get("detected_audience", "General Audience"),
        "target_keyword": used_target_keyword,
        "topic_match": content_alignment.get("topic_match", 0),
        "marketing_relevance": content_alignment.get("marketing_relevance", "Low"),
        "overall_seo_readiness": seo_readiness,
        "overall_marketing_readiness": marketing_readiness,  # Now a numerical score
        "business_opportunity": business_opportunity,
        
        # Keep existing fields for backward compatibility
        "overall_business_impact": business_opportunity,
        "overall_seo_impact": "Good" if (seo_readiness or 0) > 70 else "Needs Work",
        "overall_google_discovery_readiness": "Ready" if (google_discovery.get("discovery_score", 0)) > 80 else "Needs Optimization",
        "critical_findings": [rec["issue"] for rec in recommendations["Critical"]],
        "highest_priority_actions": [rec["recommended_action"] for rec in recommendations["Critical"]],
        "business_risks": [
            "Potential missed traffic from missing sitemap" if discovered_sitemap is None else "",
            "Poor mobile UX affecting conversions" if viewport_issues else ""
        ],
        "marketing_risks": [
            "Content misalignment with target keyword" if content_alignment.get("marketing_relevance", "Low") in ["Low", "Very Low"] else ""
        ]
    }
    
    # Merge the topic intelligence recommendations
    topic_intelligence["executive_summary"]["top_ai_recommendations"] = [
        *recommendations["Critical"],
        *recommendations["High"],
        *recommendations["Medium"],
        *recommendations["Low"],
    ]
    topic_intelligence["top_ai_recommendations"] = topic_intelligence["executive_summary"]["top_ai_recommendations"]
    
    return {
        "url": normalized_url,
        "target_keyword": used_target_keyword,
        "topic_intelligence": topic_intelligence,
        "executive_summary": executive_summary,
        "robots_status": robots_status,
        "sitemap_status": sitemap_status,
        "discovered_sitemap": discovered_sitemap,
        "checked_endpoints": [robots_url, *sitemap_candidates],
        "recommendations": recommendations,  # Add full recommendations dict
        
        # XML Sitemap
        "xml_sitemap": {
            "found": discovered_sitemap is not None,
            "valid": discovered_sitemap is not None,
            "urls_found": len(sitemap_urls_list),
            "broken_urls": broken_sitemap_urls,
            "noindex_urls": noindex_sitemap_urls,
            "redirected_urls": redirected_sitemap_urls,
            "discovered_sitemap": discovered_sitemap,
            "robots_status": robots_status
        },
        
        # Image Intelligence
        "image_intelligence": image_intel,
        
        # Video Intelligence
        "video_intelligence": video_intel,
        
        # Text Intelligence
        "text_intelligence": text_intel,
        
        # Text / Visual Content Signals (keeping for backward compatibility)
        "text_visual_signals": {
            "keyword_in_image_signals": image_intel.get("keyword_match_score", 0) > 0,
            "keyword_in_video_signals": [],
            "keyword_in_page_text": list(set(keyword_in_page_text)),
            "keyword_coverage_score": text_intel.get("keyword_coverage", 0),
            "visual_relevance_score": image_intel.get("keyword_match_score", 0)
        },
        
        # Mobile Signals
        "mobile_signals": {
            "mobile_pages": mobile_pages,
            "viewport_issues": viewport_issues,
            "blocked_resources": [],
            "health_score": int(mobile_health_score)
        },
        
        # Google Discovery
        "google_discovery": google_discovery,
        "google_discovery_score": google_discovery.get("discovery_score", 0),
        
        # Digital Marketing Intelligence
        "digital_marketing_intelligence": digital_marketing,
        
        # AI Recommendations
        "recommendations": recommendations
    }


def _extract_weighted_candidates(sections: dict[str, str]) -> list[str]:
    weights = {
        "h1": 6,
        "h2": 4,
        "title": 5,
        "meta_title": 4,
        "meta_description": 2,
        "content": 1,
    }
    scores: Counter[str] = Counter()
    for section_name, text in sections.items():
        if section_name == "url":
            text = urlparse(text).path.replace("-", " ").replace("_", " ")
        tokens = _tokenize(text)
        for size in (4, 3, 2, 1):
            for index in range(0, len(tokens) - size + 1):
                phrase_tokens = tokens[index : index + size]
                if all(token in STOPWORDS for token in phrase_tokens):
                    continue
                if phrase_tokens[-1] in STOPWORDS:
                    continue
                phrase = " ".join(phrase_tokens).strip()
                if not phrase or phrase in GENERIC_TERMS:
                    continue
                if any(token in GENERIC_TERMS for token in phrase_tokens):
                    continue
                scores[phrase] += weights.get(section_name, 1) + max(size - 1, 0)
    ranked = sorted(scores.items(), key=lambda item: (-item[1], -len(item[0].split()), item[0]))
    return [phrase.title() for phrase, _score in ranked[:18]]


def _secondary_keywords(weighted_candidates: list[str], primary_keyword: str) -> list[str]:
    primary_terms = set(primary_keyword.lower().split())
    secondary = []
    for candidate in weighted_candidates[1:]:
        candidate_terms = set(candidate.lower().split())
        if candidate_terms <= primary_terms:
            continue
        secondary.append(candidate)
        if len(secondary) >= 4:
            break
    return secondary or ["Not Measured"]


def _supporting_keywords(weighted_candidates: list[str], primary_keyword: str, secondary_keywords: list[str]) -> list[str]:
    excluded = {primary_keyword, *secondary_keywords}
    supporting = []
    for candidate in weighted_candidates:
        if candidate in excluded or len(candidate.split()) > 2:
            continue
        supporting.append(candidate)
        if len(supporting) >= 4:
            break
    return supporting or secondary_keywords[:2] or ["Not Measured"]


def _long_tail_keywords(weighted_candidates: list[str], primary_keyword: str) -> list[str]:
    primary_terms = set(primary_keyword.lower().split())
    long_tail = []
    for candidate in weighted_candidates:
        tokens = candidate.lower().split()
        if len(tokens) < 3:
            continue
        if set(tokens) <= primary_terms:
            continue
        long_tail.append(candidate)
        if len(long_tail) >= 3:
            break
    return long_tail or ["Not Measured"]


def _semantic_keywords(primary_keyword: str, secondary_keywords: list[str], long_tail_keywords: list[str]) -> list[str]:
    semantic = []
    pool = [primary_keyword, *secondary_keywords, *long_tail_keywords]
    for phrase in pool:
        for token in phrase.lower().split():
            if token in STOPWORDS or token in GENERIC_TERMS or len(token) < 4:
                continue
            label = token.title()
            if label not in semantic:
                semantic.append(label)
        if len(semantic) >= 5:
            break
    return semantic or ["Not Measured"]


def _detected_topic(primary_keyword: str, page_title: str, h1: str) -> str:
    if primary_keyword and primary_keyword != "General Topic":
        return primary_keyword
    for value in [h1, page_title]:
        if value:
            return value[:80]
    return "General Topic"


def _detect_search_intent_profile(sections: dict[str, str], url: str) -> dict:
    combined = " ".join(value.lower() for value in sections.values() if value)
    path = urlparse(url).path.lower()
    scores = {label: 0 for label in [*INTENT_PATTERNS.keys(), "Mixed Intent"]}
    for label, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if pattern in combined or pattern in path:
                scores[label] += 1
    if path in {"", "/"} and scores["Navigational"] == 0:
        scores["Navigational"] += 1

    ranked = sorted(
        ((label, score) for label, score in scores.items() if label != "Mixed Intent"),
        key=lambda item: (-item[1], item[0]),
    )
    primary_label, primary_score = ranked[0]
    secondary_label, secondary_score = ranked[1]
    if primary_score == 0:
        primary_label, primary_score = "Informational", 1
    if primary_score > 0 and secondary_score > 0 and primary_score - secondary_score <= 1:
        label = "Mixed Intent"
        confidence = min(94, 58 + (primary_score * 9))
        summary = f"Signals indicate both {primary_label.lower()} and {secondary_label.lower()} demand patterns."
    else:
        label = primary_label
        confidence = min(98, 60 + (primary_score * 10) + max(primary_score - secondary_score, 0) * 4)
        summary = f"Strongest signals come from on-page messaging and URL structure for {label.lower()} intent."
    return {
        "label": label,
        "confidence_pct": confidence,
        "primary_signal": primary_label,
        "secondary_signal": secondary_label,
        "summary": summary,
    }


def _detect_content_category(url: str, sections: dict[str, str], intent: str) -> str:
    path = urlparse(url).path.lower()
    combined = " ".join(value.lower() for value in sections.values() if value)
    if path in {"", "/"}:
        return "Homepage"
    if any(token in path or token in combined for token in ["blog", "guide", "how to", "tutorial", "learn"]):
        return "Guide / Article"
    if any(token in path or token in combined for token in ["pricing", "product", "shop", "buy", "checkout"]):
        return "Product / Transaction Page"
    if any(token in path or token in combined for token in ["service", "agency", "solution", "platform", "software"]):
        return "Service / Solution Page"
    if any(token in path or token in combined for token in ["compare", "vs", "alternative", "review"]):
        return "Comparison Page"
    if intent == "Navigational":
        return "Brand / Navigation Page"
    return "Landing Page"


def _detect_topic_cluster(primary_keyword: str, secondary_keywords: list[str], category: str) -> str:
    haystack = " ".join([primary_keyword, *secondary_keywords, category]).lower()
    for token, cluster in CLUSTER_RULES.items():
        if token in haystack:
            return cluster
    return f"{category} Cluster"


def _keyword_coverage(primary_keyword: str, sections: dict[str, str]) -> int:
    if not primary_keyword or primary_keyword == "General Topic":
        return 28
    keyword = primary_keyword.lower()
    hits = 0
    max_hits = 0
    for section_name, text in sections.items():
        if section_name == "url":
            text = urlparse(text).path.replace("-", " ")
        weight = 2 if section_name in {"h1", "h2", "title", "meta_title"} else 1
        max_hits += weight
        if keyword in text.lower():
            hits += weight
        elif set(keyword.split()) & set(_tokenize(text)):
            hits += 1
    return min(100, max(18, int((hits / max_hits) * 100))) if max_hits else 0


def _semantic_relevance(primary_keyword: str, secondary_keywords: list[str], sections: dict[str, str]) -> int:
    combined_tokens = set(_tokenize(" ".join(value for key, value in sections.items() if key != "url")))
    terms = set(primary_keyword.lower().split())
    for keyword in secondary_keywords:
        terms.update(keyword.lower().split())
    terms = {term for term in terms if term not in STOPWORDS}
    if not terms:
        return 35
    overlap = len(terms & combined_tokens)
    return min(100, max(20, int((overlap / len(terms)) * 100)))


def _keyword_alignment(primary_keyword: str, sections: dict[str, str]) -> int:
    alignment = 0
    placements = _keyword_placement(primary_keyword, sections)
    alignment += len(placements) * 16
    if sections["meta_description"]:
        alignment += 10
    if sections["content"]:
        alignment += 20
    return max(22, min(100, alignment))


def _content_focus_score(
    sections: dict[str, str],
    keyword_coverage: int,
    semantic_relevance: int,
    word_count: int | None,
) -> int:
    signal_score = 0
    if sections["h1"]:
        signal_score += 20
    if sections["title"]:
        signal_score += 20
    if sections["meta_description"]:
        signal_score += 15
    if sections["h2"]:
        signal_score += 10
    if word_count and word_count >= 300:
        signal_score += 15
    return min(100, int((signal_score + keyword_coverage + semantic_relevance) / 1.8))


def _readability_score(content_text: str, word_count: int | None) -> int:
    text = content_text or ""
    tokens = _tokenize(text)
    if not tokens:
        return 38
    sentence_count = max(1, len([part for part in re.split(r"[.!?]+", text) if part.strip()]))
    avg_sentence_length = len(tokens) / sentence_count
    avg_word_length = sum(len(token) for token in tokens) / len(tokens)
    score = 88
    if avg_sentence_length > 28:
        score -= 18
    elif avg_sentence_length > 22:
        score -= 10
    if avg_word_length > 6.5:
        score -= 8
    elif avg_word_length > 5.8:
        score -= 4
    if word_count and word_count < 180:
        score -= 8
    return max(25, min(100, int(score)))


def _heading_structure_score(h1: str, h2_count: int | None, h2: str) -> int:
    score = 52
    if h1:
        score += 24
    else:
        score -= 14
    if h2_count and h2_count > 0:
        score += 16
    elif h2:
        score += 10
    else:
        score -= 6
    return max(25, min(100, score))


def _topical_authority_score(
    *,
    word_count: int | None,
    semantic_relevance: int,
    long_tail_keywords: list[str],
    h2_count: int | None,
) -> int:
    score = 35
    if word_count:
        if word_count >= 1200:
            score += 24
        elif word_count >= 700:
            score += 18
        elif word_count >= 300:
            score += 10
    score += round(semantic_relevance * 0.28)
    if long_tail_keywords and long_tail_keywords[0] != "Not Measured":
        score += min(12, len(long_tail_keywords) * 4)
    if h2_count:
        score += min(8, h2_count * 2)
    return max(20, min(100, score))


def _ai_visibility_score(
    *,
    sections: dict[str, str],
    keyword_coverage: int,
    semantic_relevance: int,
    focus_score: int,
    word_count: int | None,
    intent: str,
) -> int:
    score = 42
    if sections["h1"]:
        score += 12
    else:
        score -= 10
    if sections["title"]:
        score += 8
    if sections["meta_description"]:
        score += 6
    if sections["h2"]:
        score += 4
    if word_count:
        if word_count >= 900:
            score += 12
        elif word_count >= 500:
            score += 8
        elif word_count >= 300:
            score += 4
        else:
            score -= 4
    score += round(keyword_coverage * 0.12)
    score += round(semantic_relevance * 0.10)
    score += round(focus_score * 0.10)
    if intent in {"Commercial", "Transactional"}:
        score += 4
    elif intent == "Mixed Intent":
        score += 2
    return max(18, min(100, score))


def _keyword_density(primary_keyword: str, content_text: str) -> float:
    if not primary_keyword or primary_keyword == "General Topic":
        return 0.0
    content_lower = content_text.lower()
    tokens = _tokenize(content_text)
    if not tokens:
        return 0.0
    matches = content_lower.count(primary_keyword.lower())
    density = (matches * len(primary_keyword.split())) / max(len(tokens), 1) * 100
    return round(min(density, 100.0), 2)


def _keyword_placement(primary_keyword: str, sections: dict[str, str]) -> list[str]:
    placements = []
    keyword = primary_keyword.lower()
    checks = {
        "URL": urlparse(sections["url"]).path.replace("-", " ").replace("_", " "),
        "Title": sections["title"],
        "Meta Title": sections["meta_title"],
        "Meta Description": sections["meta_description"],
        "H1": sections["h1"],
        "H2": sections["h2"],
        "Main Content": sections["content"],
    }
    for label, text in checks.items():
        if keyword and keyword in text.lower():
            placements.append(label)
    return placements or ["Main Content"]


def _missing_keywords(candidates: list[str], sections: dict[str, str]) -> list[str]:
    normalized_sections = " ".join(value.lower() for key, value in sections.items() if key != "url")
    missing = []
    for candidate in candidates:
        if candidate == "Not Measured":
            continue
        if candidate.lower() not in normalized_sections:
            missing.append(candidate)
        if len(missing) >= 4:
            break
    return missing or ["No major supporting gaps detected"]


def _keyword_opportunity_score(
    *,
    keyword_coverage: int,
    semantic_relevance: int,
    keyword_alignment: int,
    missing_keywords: list[str],
) -> int:
    score = int((keyword_coverage + semantic_relevance + keyword_alignment) / 3)
    if missing_keywords and missing_keywords[0] != "No major supporting gaps detected":
        score -= min(18, len(missing_keywords) * 4)
    return max(22, min(100, score))


def _detect_target_audience(intent: str, category: str, primary_keyword: str, topic_cluster: str) -> str:
    keyword = primary_keyword.lower()
    if intent == "Transactional":
        return "High-intent buyers evaluating conversion-ready offers"
    if intent == "Commercial":
        return "Decision-makers comparing tools, services, or providers"
    if intent == "Navigational":
        return "Existing users or branded visitors looking for a known destination"
    if "guide" in category.lower() or intent == "Informational":
        return "Researchers, marketers, and teams seeking educational guidance"
    if "service" in category.lower():
        return "Prospects evaluating a provider in the " + topic_cluster.lower()
    if "product" in keyword:
        return "Product-aware visitors with buying intent"
    return "Broad search audiences aligned with the page topic"


def _build_technical_seo_intelligence(
    *,
    result,
    issues,
    sections: dict[str, str],
    h2_count: int | None,
    content_quality: dict,
    technical_snapshot: dict,
) -> list[dict]:
    issue_list = list(issues or [])
    categories = {
        "Discovery": _related_issues(issue_list, categories={"discovery"}, names={"Missing XML Sitemap"}),
        "Crawlability": _related_issues(
            issue_list,
            categories={"technical", "discovery", "general"},
            names={"Missing Robots.txt", "Homepage Not Returning 200 OK"},
        ),
        "Indexability": _related_issues(
            issue_list,
            categories={"indexability", "technical"},
            names={"Noindex Tag Present", "Canonical Tag Mismatch", "Missing Canonical Tag"},
        ),
        "Rendering": _related_issues(
            issue_list,
            categories={"on-page"},
            names={
                "Missing Title Tag",
                "Title Tag Too Short (<30 chars)",
                "Title Tag Too Long (>60 chars)",
                "Missing Meta Description",
                "Meta Description Too Short (<50 chars)",
                "Meta Description Too Long (>320 chars)",
                "Missing H1 Tag",
                "Multiple H1 Tags",
                "Thin Content (<300 words)",
            },
        ),
        "Performance": _related_issues(
            issue_list,
            categories={"performance"},
            names={"Slow Response Time (>3s)", "Large Page Size (>2MB)"},
        ),
        "Security": _related_issues(
            issue_list,
            categories={"general"},
            names={"Missing HTTPS Certificate"},
        ),
        "Structured Data": [],
    }

    health_entries = []
    for label, related in categories.items():
        score = _technical_category_score(
            label=label,
            result=result,
            related_issues=related,
            sections=sections,
            h2_count=h2_count,
            content_quality=content_quality,
            technical_snapshot=technical_snapshot,
        )
        highest_priority = _highest_priority_label(related) if related else ("Medium" if label == "Structured Data" else "Low")
        actions = _top_actions_from_issues(related)
        if label == "Structured Data" and not related:
            actions = [TECHNICAL_CATEGORY_CONFIG[label]["recommended_action"]]
        health_entries.append(
            {
                "label": label,
                "health_score": score if isinstance(score, int) else None,
                "health_score_display": score if isinstance(score, str) else f"{score}/100",
                "badge_class": _category_badge_class(score if isinstance(score, int) else None),
                "problems_found": len(related) if label != "Structured Data" else ("Not Measured" if not related else len(related)),
                "business_impact": TECHNICAL_CATEGORY_CONFIG[label]["business_impact"],
                "priority": highest_priority,
                "priority_badge_class": PRIORITY_STYLE[highest_priority]["badge_class"],
                "recommended_action": actions[0] if actions else TECHNICAL_CATEGORY_CONFIG[label]["recommended_action"],
                "why_it_matters": TECHNICAL_CATEGORY_CONFIG[label]["description"],
            }
        )
    return health_entries


def _technical_category_score(
    *,
    label: str,
    result,
    related_issues: list,
    sections: dict[str, str],
    h2_count: int | None,
    content_quality: dict,
    technical_snapshot: dict,
):
    if label == "Structured Data" and not related_issues:
        return "Not Measured"
    if label == "Discovery":
        base = _as_int(getattr(result, "discovery_score", None), default=62)
        if technical_snapshot.get("has_sitemap") is False:
            base -= 14
        if technical_snapshot.get("sitemap_status") == "Unavailable":
            base -= 12
    elif label == "Crawlability":
        technical = _as_int(getattr(result, "technical_score", None), default=64)
        discovery = _as_int(getattr(result, "discovery_score", None), default=62)
        base = int((technical + discovery) / 2)
        if technical_snapshot.get("has_robots") is False:
            base -= 8
        status_code = technical_snapshot.get("status_code")
        if status_code and status_code >= 400:
            base -= 18
    elif label == "Indexability":
        technical = _as_int(getattr(result, "technical_score", None), default=65)
        on_page = _as_int(getattr(result, "on_page_score", None), default=60)
        base = int((technical + on_page) / 2)
    elif label == "Rendering":
        base = _as_int(getattr(result, "on_page_score", None), default=58)
        if not sections["h1"]:
            base -= 10
        if not sections["meta_description"]:
            base -= 8
        if not h2_count:
            base -= 4
    elif label == "Performance":
        base = _as_int(getattr(result, "performance_score", None), default=55)
        response_time = technical_snapshot.get("response_time")
        if response_time and response_time > 3:
            base -= 8
    elif label == "Security":
        https_status = getattr(result, "https_status", None)
        if https_status is True:
            base = 92
        elif https_status is False:
            base = 32
        else:
            base = 60
    else:
        base = 58
    penalty = sum(_issue_penalty(issue) for issue in related_issues)
    return max(18, min(100, base - penalty))


def _build_action_priority(
    *,
    issues,
    primary_keyword: str,
    intent: str,
    content_quality: dict,
    technical_seo_intelligence: list[dict],
    missing_keywords: list[str],
    has_missing_h1: bool,
) -> dict[str, list[dict]]:
    issue_list = list(issues or [])
    priority_buckets = {label: [] for label in PRIORITY_STYLE}
    seen_actions = set()

    for issue in issue_list:
        priority_label = _normalize_priority(_issue_attr(issue, "priority") or _issue_attr(issue, "severity") or "medium")
        action = clean_text(_issue_attr(issue, "recommended_fix") or _issue_attr(issue, "name") or "Review issue")
        if not action or action in seen_actions:
            continue
        seen_actions.add(action)
        difficulty, time_estimate = _difficulty_and_time_for_issue(action, priority_label)
        priority_buckets[priority_label].append(
            {
                "action": action,
                "seo_impact": clean_text(_issue_attr(issue, "seo_impact") or "Improves ranking signals and crawl efficiency."),
                "business_impact": clean_text(_issue_attr(issue, "business_impact") or "Supports stronger visibility and conversion performance."),
                "estimated_difficulty": difficulty,
                "estimated_time": time_estimate,
                "why_it_matters": clean_text(_issue_attr(issue, "description") or "This issue weakens the page's ability to rank consistently."),
                "badge_class": PRIORITY_STYLE[priority_label]["badge_class"],
            }
        )

    if not any(priority_buckets.values()):
        fallback_items = _fallback_priority_actions(
            primary_keyword=primary_keyword,
            intent=intent,
            content_quality=content_quality,
            technical_seo_intelligence=technical_seo_intelligence,
            missing_keywords=missing_keywords,
            has_missing_h1=has_missing_h1,
        )
        for label, items in fallback_items.items():
            priority_buckets[label].extend(items)

    return priority_buckets


def _fallback_priority_actions(
    *,
    primary_keyword: str,
    intent: str,
    content_quality: dict,
    technical_seo_intelligence: list[dict],
    missing_keywords: list[str],
    has_missing_h1: bool,
) -> dict[str, list[dict]]:
    actions = {label: [] for label in PRIORITY_STYLE}
    if has_missing_h1:
        actions["Critical"].append(
            _action_item(
                "Create a keyword-aligned H1 for the primary topic.",
                "Clarifies topic focus for search engines and users.",
                "Improves message clarity on the highest-visibility screen area.",
                "Easy",
                "30-60 minutes",
            )
        )
    if content_quality["semantic_coverage_pct"] < 65:
        missing = ", ".join(missing_keywords[:3]) if missing_keywords else "supporting subtopics"
        actions["High"].append(
            _action_item(
                f"Expand content to cover missing semantic themes such as {missing}.",
                "Builds stronger topical breadth around the target keyword.",
                "Improves organic discoverability for non-branded supporting queries.",
                "Medium",
                "2-4 hours",
            )
        )
    for category in technical_seo_intelligence:
        if category["priority"] in {"Critical", "High"} and category["recommended_action"]:
            actions[category["priority"]].append(
                _action_item(
                    category["recommended_action"],
                    category["why_it_matters"],
                    category["business_impact"],
                    "Medium" if category["priority"] == "High" else "High",
                    "2-8 hours" if category["priority"] == "High" else "1-2 days",
                )
            )
            break
    actions["Medium"].append(
        _action_item(
            f"Strengthen keyword placement for the {primary_keyword} theme across title, metadata, and supporting headings.",
            "Reinforces intent matching and keyword alignment.",
            "Improves click-through potential on competitive SERPs.",
            "Easy",
            "1-2 hours",
        )
    )
    actions["Low"].append(
        _action_item(
            f"Prepare competitor benchmarking for {intent.lower()} SERPs in the {primary_keyword} space.",
            "Creates a roadmap for future gap analysis.",
            "Helps prioritize investments against market leaders.",
            "Medium",
            "Planned / Future",
        )
    )
    return actions


def _build_executive_summary(
    *,
    primary_keyword: str,
    intent_profile: dict,
    topic: str,
    ai_visibility: int,
    overall_health_score,
    action_priority: dict[str, list[dict]],
    issues,
) -> dict:
    top_critical = [
        clean_text(_issue_attr(issue, "name") or "Critical issue")
        for issue in list(issues or [])
        if _normalize_priority(_issue_attr(issue, "severity") or "medium") == "Critical"
    ][:3]
    if not top_critical:
        top_critical = ["No critical ranking blockers detected in the current crawl."]

    recommendations = []
    for label in ["Critical", "High", "Medium", "Low"]:
        for item in action_priority[label]:
            recommendations.append(item["action"])
            if len(recommendations) >= 3:
                break
        if len(recommendations) >= 3:
            break
    if not recommendations:
        recommendations = ["Continue monitoring this page as new content and templates are released."]

    return {
        "primary_keyword": primary_keyword,
        "search_intent": intent_profile["label"],
        "search_intent_confidence_pct": intent_profile["confidence_pct"],
        "detected_topic": topic,
        "ai_visibility_potential": ai_visibility,
        "overall_health_score": _as_int(overall_health_score, default=None),
        "top_critical_issues": top_critical,
        "top_ai_recommendations": recommendations,
    }


def _build_ai_insight(
    *,
    primary_keyword: str,
    intent: str,
    cluster: str,
    focus_score: int,
    category: str,
    semantic_relevance: int,
    technical_seo_intelligence: list[dict],
    action_priority: dict[str, list[dict]],
) -> str:
    focus_label = "strong" if focus_score >= 75 else "moderate" if focus_score >= 50 else "limited"
    semantic_label = "strong" if semantic_relevance >= 75 else "partial" if semantic_relevance >= 50 else "weak"
    weakest_category = min(
        (entry for entry in technical_seo_intelligence if entry["health_score"] is not None),
        key=lambda entry: entry["health_score"],
        default=None,
    )
    next_best_action = None
    for label in ["Critical", "High", "Medium", "Low"]:
        if action_priority[label]:
            next_best_action = action_priority[label][0]["action"]
            break
    weakest_label = weakest_category["label"] if weakest_category else "technical SEO"
    return (
        f'This page targets the keyword "{primary_keyword}" with {intent.lower()} intent. '
        f"It sits in the {cluster} topic cluster and behaves like a {category.lower()}. "
        f"Topical focus is {focus_label}, but semantic coverage is {semantic_label}. "
        f"The main execution gap is currently {weakest_label.lower()}, so prioritizing {next_best_action or 'the top recommended fix'} "
        f"should improve both ranking resilience and business visibility."
    )


def _build_visual_dashboard_cards(
    *,
    result,
    ai_visibility: int,
    keyword_coverage: int,
    content_quality: dict,
    technical_seo_intelligence: list[dict],
) -> list[dict]:
    technical_scores = [
        entry["health_score"] for entry in technical_seo_intelligence if isinstance(entry["health_score"], int)
    ]
    technical_average = int(sum(technical_scores) / len(technical_scores)) if technical_scores else 0
    security_entry = next((entry for entry in technical_seo_intelligence if entry["label"] == "Security"), None)
    performance_entry = next((entry for entry in technical_seo_intelligence if entry["label"] == "Performance"), None)
    return [
        _dashboard_card("Health Score", _as_int(getattr(result, "health_score", None), default=0), "success", "Overall SEO stability across the audited website."),
        _dashboard_card("Visibility Score", ai_visibility, "primary", "Estimated readiness for organic and AI-assisted discovery."),
        _dashboard_card("AI Opportunity Score", _as_int(getattr(result, "ai_opportunity_score", None), default=0), "warning", "Headroom for fast-win improvements with ranking upside."),
        _dashboard_card("Keyword Coverage", keyword_coverage, "info", "Measures how clearly the page targets its primary topic."),
        _dashboard_card("Content Quality", int((content_quality["content_focus_score"] + content_quality["semantic_coverage_pct"]) / 2), "primary", "Reflects focus, readability, and topical completeness."),
        _dashboard_card("Technical SEO", technical_average, "warning", "Shows how well crawl, indexation, and performance systems support visibility."),
        _dashboard_card(
            "Security",
            security_entry["health_score"] if security_entry and security_entry["health_score"] is not None else "Not Measured",
            "success",
            "Secure delivery protects trust and avoids ranking drag.",
        ),
        _dashboard_card(
            "Performance",
            performance_entry["health_score"] if performance_entry and performance_entry["health_score"] is not None else "Not Measured",
            "danger",
            "Performance influences crawl efficiency, UX, and conversion rates.",
        ),
    ]


def _build_competitor_mode_placeholder(primary_keyword: str, topic_cluster: str) -> dict:
    cards = []
    for title, description in [
        ("Compare Against Competitor", "Benchmark this page against a competing URL targeting the same search demand."),
        ("Keyword Gap", "Identify missing target terms competitors cover more effectively."),
        ("Content Gap", "Highlight subtopics, questions, and sections absent from the current page."),
        ("Authority Gap", "Compare authority, trust, and link strength against market leaders."),
    ]:
        cards.append(
            {
                "title": title,
                "status": "Prepared",
                "description": description,
                "badge_class": "bg-secondary-subtle text-secondary border border-secondary-subtle",
            }
        )
    return {
        "headline": f"Competitor Mode is prepared for future {primary_keyword} benchmarking.",
        "subheadline": f"Architecture is in place for {topic_cluster.lower()} comparisons without connecting APIs yet.",
        "cards": cards,
    }


def _build_opportunity_statement(keyword_intelligence: dict, content_quality: dict) -> str:
    missing_keywords = keyword_intelligence["missing_keywords"]
    if missing_keywords and missing_keywords[0] != "No major supporting gaps detected":
        missing = ", ".join(missing_keywords[:3])
        return f"Opportunity exists to expand coverage around {missing} to improve semantic breadth."
    if content_quality["topical_authority_pct"] < 60:
        return "Opportunity exists to deepen the content with richer sections, proof points, and supporting subtopics."
    return "Opportunity is strongest in ongoing optimization and competitor benchmarking rather than emergency fixes."


def _dashboard_card(title: str, value, color: str, explanation: str) -> dict:
    return {
        "title": title,
        "value": value,
        "color": color,
        "explanation": explanation,
    }


def _related_issues(issues: list, *, categories: set[str], names: set[str]) -> list:
    related = []
    for issue in issues:
        issue_category = (_issue_attr(issue, "category") or "").lower()
        issue_name = clean_text(_issue_attr(issue, "name") or "")
        if issue_category in categories or issue_name in names:
            related.append(issue)
    return related


def _top_actions_from_issues(issues: list) -> list[str]:
    actions = []
    seen = set()
    for issue in issues:
        action = clean_text(_issue_attr(issue, "recommended_fix") or _issue_attr(issue, "name") or "")
        if not action or action in seen:
            continue
        seen.add(action)
        actions.append(action)
        if len(actions) >= 2:
            break
    return actions


def _highest_priority_label(issues: list) -> str:
    if any(_normalize_priority(_issue_attr(issue, "severity") or "medium") == "Critical" for issue in issues):
        return "Critical"
    if any(_normalize_priority(_issue_attr(issue, "severity") or "medium") == "High" for issue in issues):
        return "High"
    if any(_normalize_priority(_issue_attr(issue, "severity") or "medium") == "Medium" for issue in issues):
        return "Medium"
    return "Low"


def _issue_penalty(issue) -> int:
    severity = _normalize_priority(_issue_attr(issue, "severity") or "medium")
    penalty = {"Critical": 16, "High": 10, "Medium": 6, "Low": 3}
    return penalty[severity]


def _normalize_priority(value: str) -> str:
    lowered = (value or "").strip().lower()
    mapping = {
        "critical": "Critical",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
    }
    return mapping.get(lowered, "Medium")


def _difficulty_and_time_for_issue(action: str, priority_label: str) -> tuple[str, str]:
    action_lower = action.lower()
    if any(token in action_lower for token in ["title", "meta description", "h1", "heading"]):
        return "Easy", "30-90 minutes"
    if any(token in action_lower for token in ["canonical", "robots", "sitemap", "redirect"]):
        return "Medium", "1-4 hours"
    if any(token in action_lower for token in ["https", "certificate", "performance", "response time", "page size"]):
        return "High", "1-3 days"
    defaults = {
        "Critical": ("High", "1-2 days"),
        "High": ("Medium", "2-6 hours"),
        "Medium": ("Easy", "1-3 hours"),
        "Low": ("Easy", "Under 1 hour"),
    }
    return defaults[priority_label]


def _action_item(action: str, seo_impact: str, business_impact: str, difficulty: str, time_estimate: str) -> dict:
    return {
        "action": action,
        "seo_impact": seo_impact,
        "business_impact": business_impact,
        "estimated_difficulty": difficulty,
        "estimated_time": time_estimate,
        "why_it_matters": seo_impact,
        "badge_class": "bg-primary-subtle text-primary border border-primary-subtle",
    }


def _issue_attr(issue, field: str):
    if isinstance(issue, dict):
        return issue.get(field)
    return getattr(issue, field, None)


def _as_int(value, default: int | None) -> int | None:
    if value is None:
        return default
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _keyword_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return "Homepage Brand Query"
    candidate = path.split("/")[-1].replace("-", " ").replace("_", " ").strip()
    return clean_text(candidate).title() or "General Topic"


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2]


def _intent_badge_class(intent: str) -> str:
    mapping = {
        "Informational": "bg-info-subtle text-info border border-info-subtle",
        "Commercial": "bg-primary-subtle text-primary border border-primary-subtle",
        "Transactional": "bg-warning-subtle text-warning border border-warning-subtle",
        "Navigational": "bg-secondary-subtle text-secondary border border-secondary-subtle",
        "Mixed Intent": "bg-purple text-white border",
    }
    return mapping.get(intent, "bg-light text-dark border")


def _visibility_badge_class(score: int) -> str:
    if score >= 80:
        return "bg-success-subtle text-success border border-success-subtle"
    if score >= 60:
        return "bg-primary-subtle text-primary border border-primary-subtle"
    if score >= 40:
        return "bg-warning-subtle text-warning border border-warning-subtle"
    return "bg-danger-subtle text-danger border border-danger-subtle"


def _category_badge_class(score: int | None) -> str:
    if score is None:
        return "bg-secondary-subtle text-secondary border border-secondary-subtle"
    if score >= 80:
        return "bg-success-subtle text-success border border-success-subtle"
    if score >= 60:
        return "bg-primary-subtle text-primary border border-primary-subtle"
    if score >= 40:
        return "bg-warning-subtle text-warning border border-warning-subtle"
    return "bg-danger-subtle text-danger border border-danger-subtle"
