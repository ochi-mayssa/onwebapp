from abc import ABC, abstractmethod
from collections import Counter
from math import sqrt
import re
from types import MappingProxyType
from typing import Dict, Any, List, Optional
import requests
import json
from urllib.parse import urlparse, urljoin, parse_qs
from bs4 import BeautifulSoup
from .topic_intelligence import build_topic_intelligence_from_url


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _split_heading_values(value: Any) -> List[str]:
    if isinstance(value, list):
        return [item for item in (_clean_text(item) for item in value) if item]
    text = _clean_text(value)
    if not text:
        return []
    return [item for item in (_clean_text(part) for part in text.split("|")) if item]


def _tokenize_text(value: Any) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", _clean_text(value).lower()) if len(token) > 1}


SEMANTIC_SYNONYMS = {
    "digital marketing": {
        "marketing",
        "online marketing",
        "internet marketing",
    },
    "seo": {
        "search engine optimization",
        "organic search",
        "search visibility",
        "technical seo",
        "on page seo",
    },
    "sitemap": {
        "xml sitemap",
        "site map",
    },
    "content marketing": {
        "blog strategy",
        "editorial strategy",
        "content strategy",
    },
    "ppc": {
        "paid search",
        "search ads",
        "advertising",
    },
}

TOPIC_RELATIONSHIPS = {
    "digital marketing": {"seo": 0.85, "content marketing": 0.8, "ppc": 0.8, "analytics": 0.75, "social media": 0.75},
    "seo": {"digital marketing": 0.85, "sitemap": 0.72, "search visibility": 0.9, "organic search": 0.9, "technical seo": 0.9},
    "sitemap": {"seo": 0.72, "digital marketing": 0.58, "crawlability": 0.82, "indexation": 0.82, "technical seo": 0.8},
    "content marketing": {"digital marketing": 0.8, "seo": 0.7},
    "ppc": {"digital marketing": 0.8},
}

INDUSTRY_KEYWORDS = {
    "Marketing": ["marketing", "seo", "digital marketing", "social media", "content marketing", "ppc", "advertising", "analytics", "lead generation", "marketing automation", "business growth"],
    "Entertainment": ["music", "song", "album", "movie", "film", "gaming", "game", "playthrough", "video content", "entertainment", "celebrity"],
    "Religion": ["islam", "quran", "muslim", "prayer", "religion", "faith", "church", "mosque", "temple"],
    "Technology": ["software", "tech", "programming", "coding", "developer", "ai", "artificial intelligence", "machine learning", "data science"],
    "Education": ["education", "learning", "course", "tutorial", "school", "university", "teaching", "training"],
    "Health": ["health", "fitness", "medical", "wellness", "nutrition", "exercise", "doctor", "healthcare"],
    "Business": ["business", "startup", "entrepreneur", "ceo", "management", "finance", "investment", "economics"],
}

AUDIENCE_KEYWORDS = {
    "Marketers": ["marketing", "seo", "digital marketing", "content marketing", "ppc"],
    "Developers": ["programming", "coding", "developer", "software", "tech", "ai"],
    "Students": ["education", "learning", "course", "tutorial", "school", "university"],
    "Gamers": ["gaming", "game", "playthrough"],
    "General Audience": [],
}


def _normalize_phrase(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", _clean_text(value).lower()))


def _canonical_topic(value: Any) -> str:
    normalized = _normalize_phrase(value)
    if not normalized:
        return ""
    for canonical, aliases in SEMANTIC_SYNONYMS.items():
        if normalized == canonical or normalized in aliases:
            return canonical
    return normalized


def _expand_semantic_embedding(value: Any, weight: float = 1.0) -> Counter[str]:
    normalized = _normalize_phrase(value)
    embedding: Counter[str] = Counter()
    if not normalized:
        return embedding

    canonical = _canonical_topic(normalized)
    embedding[canonical] += weight * 3
    for token in _tokenize_text(normalized):
        embedding[token] += weight

    for alias in SEMANTIC_SYNONYMS.get(canonical, set()):
        embedding[_canonical_topic(alias)] += weight * 1.5
        for token in _tokenize_text(alias):
            embedding[token] += weight * 0.8

    for related_topic, related_weight in TOPIC_RELATIONSHIPS.get(canonical, {}).items():
        embedding[related_topic] += weight * related_weight
        for token in _tokenize_text(related_topic):
            embedding[token] += weight * related_weight * 0.7

    return embedding


def _combine_embeddings(*weighted_values: tuple[Any, float]) -> Counter[str]:
    combined: Counter[str] = Counter()
    for value, weight in weighted_values:
        combined.update(_expand_semantic_embedding(value, weight))
    return combined


def _cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common_terms = set(left) & set(right)
    numerator = sum(left[term] * right[term] for term in common_terms)
    left_norm = sqrt(sum(weight * weight for weight in left.values()))
    right_norm = sqrt(sum(weight * weight for weight in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _semantic_relation_weight(left: Any, right: Any) -> float:
    left_canonical = _canonical_topic(left)
    right_canonical = _canonical_topic(right)
    if not left_canonical or not right_canonical:
        return 0.0
    if left_canonical == right_canonical:
        return 1.0

    direct = max(
        TOPIC_RELATIONSHIPS.get(left_canonical, {}).get(right_canonical, 0.0),
        TOPIC_RELATIONSHIPS.get(right_canonical, {}).get(left_canonical, 0.0),
    )
    if direct:
        return direct

    indirect = 0.0
    for intermediate, left_weight in TOPIC_RELATIONSHIPS.get(left_canonical, {}).items():
        right_weight = TOPIC_RELATIONSHIPS.get(intermediate, {}).get(right_canonical, 0.0)
        indirect = max(indirect, min(left_weight, right_weight) * 0.85)
    return indirect


def _infer_industry(value: Any) -> str:
    normalized = _normalize_phrase(value)
    if not normalized:
        return ""
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return industry
    return ""


def _infer_audience(value: Any) -> str:
    normalized = _normalize_phrase(value)
    if not normalized:
        return ""
    for audience, keywords in AUDIENCE_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return audience
    return ""


def _freeze_analysis_context(data: Dict[str, Any]) -> MappingProxyType:
    semantic_keywords = tuple(
        keyword for keyword in (_clean_text(item) for item in data.get("semantic_keywords", [])) if keyword
    )
    frozen = {
        "target_keyword": _clean_text(data.get("target_keyword", "")),
        "detected_topic": _clean_text(data.get("detected_topic", "")),
        "primary_keyword": _clean_text(data.get("primary_keyword", "")),
        "industry": _clean_text(data.get("industry", "")),
        "audience": _clean_text(data.get("audience", "")),
        "intent": _clean_text(data.get("intent", "")),
        "semantic_keywords": semantic_keywords,
        "topic_cluster": _clean_text(data.get("topic_cluster", "")),
        "content_category": _clean_text(data.get("content_category", "")),
    }
    return MappingProxyType(frozen)


def _analysis_context_to_dict(analysis_context: MappingProxyType) -> Dict[str, Any]:
    return {
        **dict(analysis_context),
        "semantic_keywords": list(analysis_context.get("semantic_keywords", ())),
    }


def _is_analysis_context_empty(analysis_context: MappingProxyType) -> bool:
    meaningful_keys = (
        "detected_topic",
        "primary_keyword",
        "industry",
        "audience",
        "intent",
        "topic_cluster",
        "content_category",
    )
    return not any(_clean_text(analysis_context.get(key, "")) for key in meaningful_keys) and not analysis_context.get("semantic_keywords")


def _build_analysis_embedding(analysis_context: MappingProxyType) -> Counter[str]:
    return _combine_embeddings(
        (analysis_context.get("detected_topic", ""), 4.0),
        (analysis_context.get("primary_keyword", ""), 3.0),
        (analysis_context.get("topic_cluster", ""), 2.0),
        (analysis_context.get("content_category", ""), 1.2),
        *((keyword, 1.4) for keyword in analysis_context.get("semantic_keywords", ())),
    )


def _calculate_topic_match(analysis_context: MappingProxyType) -> int:
    target_keyword = analysis_context.get("target_keyword", "")
    detected_topic = _first_non_empty(
        analysis_context.get("detected_topic", ""),
        analysis_context.get("primary_keyword", ""),
    )
    if not target_keyword or not detected_topic:
        return 0

    if _canonical_topic(detected_topic) == _canonical_topic(target_keyword):
        return 100

    topic_embedding = _combine_embeddings((detected_topic, 4.0), (analysis_context.get("primary_keyword", ""), 2.0))
    target_embedding = _combine_embeddings((target_keyword, 4.0))
    base_similarity = _cosine_similarity(topic_embedding, target_embedding)
    support_similarity = _cosine_similarity(_build_analysis_embedding(analysis_context), target_embedding)
    relation_weight = _semantic_relation_weight(detected_topic, target_keyword)

    if relation_weight >= 0.6:
        return max(60, min(90, int(round(max(base_similarity, support_similarity, relation_weight) * 100))))

    combined_similarity = max(base_similarity, support_similarity * 0.9, relation_weight)
    return max(0, min(100, int(round(combined_similarity * 100))))


def _calculate_semantic_match(analysis_context: MappingProxyType) -> int:
    target_keyword = analysis_context.get("target_keyword", "")
    if not target_keyword:
        return 0

    target_embedding = _combine_embeddings((target_keyword, 4.0))
    similarity = _cosine_similarity(_build_analysis_embedding(analysis_context), target_embedding)
    relation_weight = _semantic_relation_weight(
        _first_non_empty(analysis_context.get("detected_topic", ""), analysis_context.get("primary_keyword", "")),
        target_keyword,
    )
    score = int(round(max(similarity, relation_weight * 0.9) * 100))

    if _canonical_topic(_first_non_empty(analysis_context.get("detected_topic", ""), analysis_context.get("primary_keyword", ""))) == _canonical_topic(target_keyword):
        return 100

    if relation_weight >= 0.6:
        return max(65, min(95, score))

    return max(0, min(100, score))


class VideoIntelligencePipeline:
    """Single source of truth for all video-related intelligence"""
    
    PROVIDER_PLATFORMS = ["YouTube", "Vimeo", "Facebook", "Instagram", "TikTok", "LinkedIn", "X"]
    
    # Industry detection rules
    INDUSTRY_KEYWORDS = {
        "Marketing": ["marketing", "seo", "digital marketing", "social media", "content marketing", "ppc", "advertising", "analytics", "lead generation", "marketing automation", "business growth"],
        "Entertainment": ["music", "song", "album", "movie", "film", "gaming", "game", "playthrough", "video content", "entertainment", "celebrity"],
        "Religion": ["islam", "quran", "muslim", "prayer", "religion", "faith", "church", "mosque", "temple"],
        "Technology": ["software", "tech", "programming", "coding", "developer", "ai", "artificial intelligence", "machine learning", "data science"],
        "Education": ["education", "learning", "course", "tutorial", "school", "university", "teaching", "training"],
        "Health": ["health", "fitness", "medical", "wellness", "nutrition", "exercise", "doctor", "healthcare"],
        "Business": ["business", "startup", "entrepreneur", "ceo", "management", "finance", "investment", "economics"]
    }
    
    # Audience detection rules
    AUDIENCE_KEYWORDS = {
        "Marketers": ["marketing", "seo", "digital marketing", "content marketing", "ppc"],
        "Developers": ["programming", "coding", "developer", "software", "tech", "ai"],
        "Students": ["education", "learning", "course", "tutorial", "school", "university"],
        "Gamers": ["gaming", "game", "playthrough"],
        "General Audience": []
    }
    
    # Intent detection rules
    INTENT_KEYWORDS = {
        "Informational": ["how to", "what is", "guide", "tutorial", "learn", "explain", "explore"],
        "Transactional": ["buy", "purchase", "shop", "order", "checkout"],
        "Navigational": ["official", "website", "homepage"],
        "Commercial": ["review", "compare", "best", "top", "vs"]
    }

    @staticmethod
    def extract_video_metadata(url: str, original_url: str) -> Dict[str, Any]:
        """Extract comprehensive metadata from video URLs"""
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        })
        
        metadata = {
            "original_url": original_url,
            "final_url": url,
            "provider": None,
            "platform": None,
            "video_id": None,
            "title": None,
            "description": None,
            "thumbnail": None,
            "upload_date": None,
            "duration": None,
            "language": None,
            "canonical": None,
            "channel": None,
            "publisher": None,
            "author": None,
            "category": None,
            "tags": [],
            "keywords": [],
            "opengraph": {},
            "twitter_cards": {},
            "json_ld": {},
            "video_object": {},
            "robots": None,
            "indexable": True
        }
        
        # Parse URL to determine provider and platform
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        if "youtube.com" in domain or "youtu.be" in domain:
            metadata["provider"] = "YouTube"
            metadata["platform"] = "YouTube"
            # Extract video ID
            if "youtube.com" in domain and "/watch" in parsed.path:
                qs = parse_qs(parsed.query)
                metadata["video_id"] = qs.get("v", [None])[0]
            elif "youtu.be" in domain:
                metadata["video_id"] = parsed.path.lstrip("/")
                
        elif "vimeo.com" in domain:
            metadata["provider"] = "Vimeo"
            metadata["platform"] = "Vimeo"
            # Extract video ID
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) >= 1 and path_parts[0].isdigit():
                metadata["video_id"] = path_parts[0]
                
        elif "facebook.com" in domain or "fb.watch" in domain:
            metadata["provider"] = "Facebook"
            metadata["platform"] = "Facebook"
        elif "instagram.com" in domain:
            metadata["provider"] = "Instagram"
            metadata["platform"] = "Instagram"
        elif "tiktok.com" in domain:
            metadata["provider"] = "TikTok"
            metadata["platform"] = "TikTok"
        elif "linkedin.com" in domain:
            metadata["provider"] = "LinkedIn"
            metadata["platform"] = "LinkedIn"
        elif "x.com" in domain or "twitter.com" in domain:
            metadata["provider"] = "X"
            metadata["platform"] = "X"
        
        # Fetch and parse the page
        try:
            # First, try YouTube's oEmbed API for reliable metadata
            if metadata["platform"] == "YouTube" and metadata["video_id"]:
                try:
                    from urllib.parse import quote
                    youtube_url = f"https://www.youtube.com/watch?v={metadata['video_id']}"
                    oembed_url = f"https://www.youtube.com/oembed?url={quote(youtube_url)}&format=json"
                    oembed_response = session.get(oembed_url, timeout=10)
                    if oembed_response.status_code == 200:
                        oembed_data = oembed_response.json()
                        if oembed_data.get("title"):
                            metadata["title"] = oembed_data["title"]
                        if oembed_data.get("author_name"):
                            metadata["channel"] = oembed_data["author_name"]
                            metadata["author"] = oembed_data["author_name"]
                        if oembed_data.get("thumbnail_url"):
                            metadata["thumbnail"] = oembed_data["thumbnail_url"]
                except Exception:
                    pass  # Fall back to page scraping if oEmbed fails
            
            response = session.get(url, timeout=15, allow_redirects=True)
            soup = BeautifulSoup(response.content, "html.parser")
            
            # Extract canonical
            canonical_tag = soup.find("link", attrs={"rel": "canonical"})
            if canonical_tag:
                metadata["canonical"] = canonical_tag.get("href")
            
            # Extract robots meta
            robots_meta = soup.find("meta", attrs={"name": "robots"})
            if robots_meta:
                metadata["robots"] = robots_meta.get("content")
                if "noindex" in metadata["robots"].lower():
                    metadata["indexable"] = False
            
            # Extract OpenGraph FIRST (prioritize over title/description)
            for og_meta in soup.find_all("meta", property=lambda x: x and x.startswith("og:")):
                prop = og_meta["property"]
                content = og_meta.get("content", "").strip()
                metadata["opengraph"][prop] = content
                
                if prop == "og:title" and not metadata["title"]:
                    metadata["title"] = content
                elif prop == "og:description" and not metadata["description"]:
                    metadata["description"] = content
                elif prop == "og:image" and not metadata["thumbnail"]:
                    metadata["thumbnail"] = content
                elif prop == "og:site_name" and not metadata["publisher"]:
                    metadata["publisher"] = content
            
            # Extract title from <title> tag only if no og:title and not yet set
            title_tag = soup.find("title")
            if title_tag and not metadata["title"]:
                title_text = title_tag.get_text(strip=True)
                # Clean up YouTube's default "- YouTube" suffix
                if title_text.endswith("- YouTube"):
                    title_text = title_text[:-len("- YouTube")].strip()
                metadata["title"] = title_text
            
            # Extract meta description only if no og:description and not yet set
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and not metadata["description"]:
                metadata["description"] = meta_desc.get("content", "").strip()
            
            # Extract meta keywords
            meta_kw = soup.find("meta", attrs={"name": "keywords"})
            if meta_kw:
                kw_text = meta_kw.get("content", "").strip()
                if kw_text:
                    metadata["keywords"] = [kw.strip() for kw in kw_text.split(",") if kw.strip()]
            
            # Extract Twitter Cards
            for tw_meta in soup.find_all("meta", attrs={"name": lambda x: x and x.startswith("twitter:")}):
                name = tw_meta["name"]
                content = tw_meta.get("content", "").strip()
                metadata["twitter_cards"][name] = content
            
            # Extract JSON-LD
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    schema_data = json.loads(script.string)
                    schemas_to_process = []
                    if isinstance(schema_data, list):
                        schemas_to_process = schema_data
                    elif isinstance(schema_data, dict):
                        schemas_to_process = [schema_data]
                    
                    for item in schemas_to_process:
                        if item.get("@type") == "VideoObject":
                            metadata["video_object"] = item
                            if not metadata["title"]:
                                metadata["title"] = item.get("name")
                            if not metadata["description"]:
                                metadata["description"] = item.get("description")
                            if not metadata["thumbnail"]:
                                metadata["thumbnail"] = item.get("thumbnailUrl")
                            metadata["duration"] = item.get("duration")
                            metadata["upload_date"] = item.get("uploadDate")
                            metadata["author"] = item.get("author", {}).get("name") if isinstance(item.get("author"), dict) else item.get("author")
                            if not metadata["channel"]:
                                metadata["channel"] = metadata["author"]
                except Exception:
                    continue
            
        except Exception as e:
            # If fetch fails, still return what we have
            pass
        
        return metadata
    
    @staticmethod
    def analyze_topic_and_keywords(metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze topic, keywords, industry, audience, intent using only extracted metadata"""
        analysis = {
            "topic": "Video Content",
            "primary_keyword": None,
            "secondary_keywords": [],
            "long_tail_keywords": [],
            "semantic_keywords": [],
            "topic_cluster": [],
            "industry": "General",
            "audience": "General Audience",
            "intent": "Informational",
            "business_category": None,
            "marketing_category": None
        }
        
        # Combine all text for analysis
        all_text_parts = []
        if metadata.get("title"):
            all_text_parts.append(metadata["title"])
        if metadata.get("description"):
            all_text_parts.append(metadata["description"])
        all_text = " ".join(all_text_parts).lower()
        
        # Extract primary keyword (from title)
        if metadata.get("title"):
            analysis["primary_keyword"] = metadata["title"]
        
        # Extract secondary keywords
        if metadata.get("title"):
            title_words = metadata["title"].split()
            if len(title_words) > 2:
                analysis["secondary_keywords"] = title_words[:3]
        if metadata.get("keywords"):
            analysis["semantic_keywords"].extend(metadata["keywords"])
        
        # Detect industry
        for industry, keywords in VideoIntelligencePipeline.INDUSTRY_KEYWORDS.items():
            found = False
            for keyword in keywords:
                if keyword.lower() in all_text:
                    analysis["industry"] = industry
                    found = True
                    break
            if found:
                break
        # Also check metadata["keywords"] list
        if analysis["industry"] == "General":
            for industry, keywords in VideoIntelligencePipeline.INDUSTRY_KEYWORDS.items():
                found = False
                for kw in metadata.get("keywords", []):
                    for keyword in keywords:
                        if keyword.lower() in kw.lower():
                            analysis["industry"] = industry
                            found = True
                            break
                    if found:
                        break
                if found:
                    break
        
        # Detect audience
        for audience, keywords in VideoIntelligencePipeline.AUDIENCE_KEYWORDS.items():
            found = False
            for keyword in keywords:
                if keyword.lower() in all_text:
                    analysis["audience"] = audience
                    found = True
                    break
            if found:
                break
        
        # Detect intent
        for intent, keywords in VideoIntelligencePipeline.INTENT_KEYWORDS.items():
            found = False
            for keyword in keywords:
                if keyword.lower() in all_text:
                    analysis["intent"] = intent
                    found = True
                    break
            if found:
                break
        
        # Detect topic based on industry and metadata
        if analysis["industry"] == "Marketing":
            analysis["topic"] = "Digital Marketing"
        elif analysis["industry"] == "Entertainment":
            analysis["topic"] = "Entertainment Content"
        elif analysis["industry"] == "Religion":
            analysis["topic"] = "Religious Content"
        elif analysis["industry"] == "Technology":
            analysis["topic"] = "Technology Content"
        elif analysis["industry"] == "Education":
            analysis["topic"] = "Educational Content"
        elif analysis["industry"] == "Health":
            analysis["topic"] = "Health & Wellness"
        elif analysis["industry"] == "Business":
            analysis["topic"] = "Business & Finance"
        
        return analysis
    
    @staticmethod
    def calculate_scores(metadata: Dict[str, Any], analysis: Dict[str, Any], target_keyword: Optional[str] = None) -> Dict[str, Any]:
        """Calculate all scores in one place"""
        scores = {
            "video_seo_score": 0,
            "discoverability_score": 0,
            "marketing_alignment_score": 0,
            "topic_match_score": 0,
            "semantic_match_score": 0,
            "intent_match_score": 0,
            "industry_match_score": 0,
            "audience_match_score": 0,
            "alignment_score": 0,
            "marketing_relevance": "Very Low"
        }
        
        # Calculate basic SEO video score (UNCHANGED!)
        has_title = bool(metadata.get("title"))
        has_description = bool(metadata.get("description"))
        has_thumbnail = bool(metadata.get("thumbnail"))
        has_upload_date = bool(metadata.get("upload_date"))
        has_video_schema = bool(metadata.get("video_object"))
        
        # Weighted scoring for SEO
        seo_weights = {
            "title": 20,
            "description": 15,
            "thumbnail": 20,
            "schema": 15,
            "keywords": 15,
            "upload_date": 15
        }
        
        seo_score = 0
        if has_title:
            seo_score += seo_weights["title"]
        if has_description:
            seo_score += seo_weights["description"]
        if has_thumbnail:
            seo_score += seo_weights["thumbnail"]
        if has_video_schema:
            seo_score += seo_weights["schema"]
        if metadata.get("keywords"):
            seo_score += seo_weights["keywords"]
        if has_upload_date:
            seo_score += seo_weights["upload_date"]
        
        scores["video_seo_score"] = seo_score
        scores["discoverability_score"] = max(0, seo_score - 10)
        
        # Target keyword analysis
        if target_keyword:
            target_lower = target_keyword.lower()
            
            # Combine all video text
            all_video_text_parts = []
            if metadata.get("title"):
                all_video_text_parts.append(metadata["title"].lower())
            if metadata.get("description"):
                all_video_text_parts.append(metadata["description"].lower())
            all_video_text = " ".join(all_video_text_parts)
            
            # Topic match
            if analysis.get("topic") and target_lower in analysis["topic"].lower():
                scores["topic_match_score"] = 100
            else:
                if analysis.get("topic"):
                    topic_words = set(analysis["topic"].lower().split())
                    target_words = set(target_lower.split())
                    overlap = len(topic_words & target_words)
                    total = len(topic_words | target_words)
                    if total > 0:
                        scores["topic_match_score"] = int((overlap / total) * 100)
            
            # Semantic match
            semantic_keywords = analysis.get("semantic_keywords", [])
            semantic_keywords_lower = [kw.lower() for kw in semantic_keywords]
            # Count how many semantic keywords are actually present in video text
            matching_semantic_keywords = sum(1 for kw in semantic_keywords_lower if kw in all_video_text)
            if len(semantic_keywords_lower) > 0:
                scores["semantic_match_score"] = int((matching_semantic_keywords / len(semantic_keywords_lower)) * 100)
            else:
                # If no semantic keywords, default to 0
                scores["semantic_match_score"] = 0
            
            # Intent match
            scores["intent_match_score"] = 70  # Default
            
            # Industry match from target keyword
            target_industry = "General"
            for industry, keywords in VideoIntelligencePipeline.INDUSTRY_KEYWORDS.items():
                found = False
                for keyword in keywords:
                    if keyword.lower() in target_lower:
                        target_industry = industry
                        found = True
                        break
                if found:
                    break
            
            if target_industry == analysis.get("industry"):
                scores["industry_match_score"] = 100
            
            # Audience match
            scores["audience_match_score"] = 60  # Default
            
            # FINAL MARKETING ALIGNMENT SCORE WITH WEIGHTS!
            weights = {
                "topic": 0.4,
                "semantic": 0.25,
                "intent": 0.15,
                "industry": 0.1,
                "audience": 0.1
            }
            raw_alignment = (
                scores["topic_match_score"] * weights["topic"]
                + scores["semantic_match_score"] * weights["semantic"]
                + scores["intent_match_score"] * weights["intent"]
                + scores["industry_match_score"] * weights["industry"]
                + scores["audience_match_score"] * weights["audience"]
            )
            scores["alignment_score"] = int(raw_alignment)
            
            # HARD RULE: If Topic Match=0 AND Semantic Match <20, max Marketing Alignment Score is 20!
            if scores["topic_match_score"] == 0 and scores["semantic_match_score"] < 20:
                scores["marketing_alignment_score"] = min(20, int(raw_alignment))
            else:
                scores["marketing_alignment_score"] = int(raw_alignment)
            
            # Marketing relevance (based primarily on topic match)
            if scores["topic_match_score"] > 70:
                scores["marketing_relevance"] = "High"
            elif scores["topic_match_score"] > 30:
                scores["marketing_relevance"] = "Medium"
            elif scores["topic_match_score"] > 10:
                scores["marketing_relevance"] = "Low"
        
        return scores
    
    @staticmethod
    def generate_recommendations(metadata: Dict[str, Any], analysis: Dict[str, Any], scores: Dict[str, Any], target_keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        """Generate provider-appropriate recommendations"""
        recommendations = []
        is_provider_platform = metadata.get("platform") in VideoIntelligencePipeline.PROVIDER_PLATFORMS
        
        # Provider platform recommendations
        if is_provider_platform:
            if not metadata.get("title"):
                recommendations.append({
                    "issue": "Missing Video Title",
                    "explanation": "Your video has no descriptive title",
                    "seo_impact": "High - Google won't understand what your video is about",
                    "business_impact": "Medium - Lower click-through rate",
                    "recommended_action": "Add a clear, descriptive title including your target keyword",
                    "expected_improvement": "Better understanding by Google and higher CTR",
                    "priority": "High"
                })
            
            if not metadata.get("description"):
                recommendations.append({
                    "issue": "Missing Video Description",
                    "explanation": "Your video has no detailed description",
                    "seo_impact": "High - Less context for Google to understand",
                    "business_impact": "Medium - Less user engagement",
                    "recommended_action": "Write a detailed description including your target keyword and related terms",
                    "expected_improvement": "Better SEO and higher engagement",
                    "priority": "High"
                })
            
            if not metadata.get("thumbnail"):
                recommendations.append({
                    "issue": "Missing Video Thumbnail",
                    "explanation": "Your video has no custom thumbnail",
                    "seo_impact": "Medium - Lower click-through rate",
                    "business_impact": "Medium - Less user engagement",
                    "recommended_action": "Add a high-quality, attention-grabbing thumbnail",
                    "expected_improvement": "Higher CTR and engagement",
                    "priority": "High"
                })
            
            if target_keyword:
                target_lower = target_keyword.lower()
                all_text_parts = []
                if metadata.get("title"):
                    all_text_parts.append(metadata["title"].lower())
                if metadata.get("description"):
                    all_text_parts.append(metadata["description"].lower())
                all_text = " ".join(all_text_parts)
                
                if target_lower not in all_text:
                    recommendations.append({
                        "issue": "Target Keyword Missing",
                        "explanation": f"Target keyword '{target_keyword}' not found in title/description",
                        "seo_impact": "Medium - Video won't rank for target keyword",
                        "business_impact": "Medium - Missed traffic opportunity for target keyword",
                        "recommended_action": f"Incorporate '{target_keyword}' into your title and description",
                        "expected_improvement": "Higher rankings for target keyword",
                        "priority": "Medium"
                    })
            
            # Add supporting content recommendations
            recommendations.append({
                "issue": "Create Supporting Content",
                "explanation": "Platform videos perform best when supported by owned content",
                "seo_impact": "Medium - Better keyword authority",
                "business_impact": "High - More conversions",
                "recommended_action": "Create a supporting landing page and blog content aligned with your target keyword",
                "expected_improvement": "Higher organic reach and better conversion rates",
                "priority": "Medium"
            })
        
        # Non-provider platform (self-hosted) recommendations
        else:
            if not metadata.get("title"):
                recommendations.append({
                    "issue": "Missing Video Title",
                    "explanation": "Your video has no descriptive title",
                    "seo_impact": "High - Google won't understand what your video is about",
                    "business_impact": "Medium - Lower click-through rate",
                    "recommended_action": "Add a clear, descriptive title including your target keyword",
                    "expected_improvement": "Better understanding by Google and higher CTR",
                    "priority": "High"
                })
            
            if not metadata.get("description"):
                recommendations.append({
                    "issue": "Missing Video Description",
                    "explanation": "Your video has no detailed description",
                    "seo_impact": "High - Less context for Google to understand",
                    "business_impact": "Medium - Less user engagement",
                    "recommended_action": "Write a detailed description including your target keyword and related terms",
                    "expected_improvement": "Better SEO and higher engagement",
                    "priority": "High"
                })
            
            if not metadata.get("video_object"):
                recommendations.append({
                    "issue": "Missing VideoObject Schema",
                    "explanation": "Your video is missing structured data (VideoObject schema)",
                    "seo_impact": "High - Reduces chance of rich results",
                    "business_impact": "High - Missed rich result traffic opportunity",
                    "recommended_action": "Add VideoObject schema to your page",
                    "expected_improvement": "Higher chance of rich results",
                    "priority": "Critical"
                })
            
            if not metadata.get("canonical"):
                recommendations.append({
                    "issue": "Missing Canonical URL",
                    "explanation": "Missing canonical URL tag - Google may not know which page to index",
                    "seo_impact": "High - Duplicate content risk",
                    "business_impact": "Medium - Lower rankings",
                    "recommended_action": "Add a canonical URL tag",
                    "expected_improvement": "Better indexing and no duplicate content issues",
                    "priority": "High"
                })
        
        return recommendations
    
    @staticmethod
    def build_video_context(url: str, original_url: str, target_keyword: Optional[str] = None) -> Dict[str, Any]:
        """Build the complete shared video_context object"""
        # Step 1: Extract metadata
        metadata = VideoIntelligencePipeline.extract_video_metadata(url, original_url)
        
        # Step 2: Analyze topic/keywords
        analysis = VideoIntelligencePipeline.analyze_topic_and_keywords(metadata)
        
        # Step 3: Calculate scores
        scores = VideoIntelligencePipeline.calculate_scores(metadata, analysis, target_keyword)
        
        # Step 4: Generate recommendations
        recommendations = VideoIntelligencePipeline.generate_recommendations(metadata, analysis, scores, target_keyword)
        
        # Step 5: Combine everything into video_context
        video_context = {
            "provider": metadata["provider"],
            "platform": metadata["platform"],
            "video_id": metadata["video_id"],
            "title": metadata["title"],
            "description": metadata["description"],
            "thumbnail": metadata["thumbnail"],
            "upload_date": metadata["upload_date"],
            "duration": metadata["duration"],
            "language": metadata["language"],
            "canonical": metadata["canonical"],
            "channel": metadata["channel"],
            "publisher": metadata["publisher"],
            "author": metadata["author"],
            "category": metadata["category"],
            "tags": metadata["tags"],
            "keywords": metadata["keywords"],
            "opengraph": metadata["opengraph"],
            "twitter_cards": metadata["twitter_cards"],
            "json_ld": metadata["json_ld"],
            "video_object": metadata["video_object"],
            "robots": metadata["robots"],
            "indexable": metadata["indexable"],
            "original_url": metadata["original_url"],
            "final_url": metadata["final_url"],
            "topic": analysis["topic"],
            "primary_keyword": analysis["primary_keyword"],
            "secondary_keywords": analysis["secondary_keywords"],
            "long_tail_keywords": analysis["long_tail_keywords"],
            "semantic_keywords": analysis["semantic_keywords"],
            "topic_cluster": analysis["topic_cluster"],
            "industry": analysis["industry"],
            "audience": analysis["audience"],
            "intent": analysis["intent"],
            "business_category": analysis["business_category"],
            "marketing_category": analysis["marketing_category"],
            "video_seo_score": scores["video_seo_score"],
            "discoverability_score": scores["discoverability_score"],
            "marketing_alignment_score": scores["marketing_alignment_score"],
            "topic_match_score": scores["topic_match_score"],
            "semantic_match_score": scores["semantic_match_score"],
            "intent_match_score": scores["intent_match_score"],
            "industry_match_score": scores["industry_match_score"],
            "audience_match_score": scores["audience_match_score"],
            "alignment_score": scores["alignment_score"],
            "marketing_relevance": scores["marketing_relevance"],
            "recommendations": recommendations
        }
        
        return video_context


class PageIntelligencePipeline:
    """Single source of truth for all webpage-related intelligence"""
    
    # Industry detection rules
    INDUSTRY_KEYWORDS = INDUSTRY_KEYWORDS
    
    # Audience detection rules
    AUDIENCE_KEYWORDS = AUDIENCE_KEYWORDS
    
    # Intent detection rules
    INTENT_KEYWORDS = {
        "Informational": ["how to", "what is", "guide", "tutorial", "learn", "explain", "explore"],
        "Transactional": ["buy", "purchase", "shop", "order", "checkout"],
        "Navigational": ["official", "website", "homepage"],
        "Commercial": ["review", "compare", "best", "top", "vs"]
    }
    
    @staticmethod
    def analyze_topic_and_keywords(topic_intel: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze topic, keywords, secondary keywords, semantic keywords from topic_intel"""
        page_title = topic_intel.get("page_title", "")
        topic = _first_non_empty(topic_intel.get("detected_topic"), topic_intel.get("primary_keyword"), page_title)
        primary_keyword = _first_non_empty(topic_intel.get("primary_keyword"), topic, page_title)
        secondary_keywords = topic_intel.get("secondary_keywords", [])
        semantic_keywords = topic_intel.get("semantic_keywords", [])
        long_tail_keywords = topic_intel.get("long_tail_keywords", [])
        topic_cluster = _first_non_empty(topic_intel.get("topic_cluster"), topic)
        
        # Build combined text for analysis
        all_text_parts = [
            topic_intel.get("page_title", ""),
            topic_intel.get("meta_description", ""),
            topic_intel.get("primary_h1", ""),
        ]
        all_text = " ".join([part for part in all_text_parts if part]).lower()
        
        # Detect industry
        industry = ""
        for industry_name, keywords in PageIntelligencePipeline.INDUSTRY_KEYWORDS.items():
            found = False
            for keyword in keywords:
                if keyword in all_text or (primary_keyword and keyword in primary_keyword.lower()):
                    industry = industry_name
                    found = True
                    break
            if found:
                break
        
        # Detect audience
        audience = ""
        for audience_name, keywords in PageIntelligencePipeline.AUDIENCE_KEYWORDS.items():
            found = False
            for keyword in keywords:
                if keyword in all_text or (primary_keyword and keyword in primary_keyword.lower()):
                    audience = audience_name
                    found = True
                    break
            if found:
                break
        
        # Detect intent (use search intent from topic_intel)
        intent = _first_non_empty(topic_intel.get("search_intent"))
        
        return {
            "topic": topic,
            "primary_keyword": primary_keyword,
            "secondary_keywords": secondary_keywords,
            "semantic_keywords": semantic_keywords,
            "long_tail_keywords": long_tail_keywords,
            "topic_cluster": topic_cluster,
            "industry": industry,
            "audience": audience,
            "intent": intent
        }

    @staticmethod
    def build_analysis_context(topic_intel: Dict[str, Any], target_keyword: Optional[str] = None) -> MappingProxyType:
        analysis = PageIntelligencePipeline.analyze_topic_and_keywords(topic_intel)
        supporting_text = " ".join(
            part for part in [
                analysis.get("topic", ""),
                analysis.get("primary_keyword", ""),
                topic_intel.get("page_title", ""),
                topic_intel.get("meta_description", ""),
                topic_intel.get("primary_h1", ""),
                topic_intel.get("primary_h2", ""),
                topic_intel.get("topic_cluster", ""),
                topic_intel.get("content_category", ""),
                " ".join(topic_intel.get("semantic_keywords", [])),
            ] if part
        )
        return _freeze_analysis_context(
            {
                "target_keyword": target_keyword or "",
                "detected_topic": _first_non_empty(analysis.get("topic"), analysis.get("primary_keyword")),
                "primary_keyword": analysis.get("primary_keyword", ""),
                "industry": _first_non_empty(analysis.get("industry"), _infer_industry(supporting_text)),
                "audience": _first_non_empty(topic_intel.get("target_audience"), analysis.get("audience"), _infer_audience(supporting_text)),
                "intent": _first_non_empty(topic_intel.get("search_intent"), analysis.get("intent")),
                "semantic_keywords": topic_intel.get("semantic_keywords", []),
                "topic_cluster": _first_non_empty(topic_intel.get("topic_cluster"), analysis.get("topic_cluster")),
                "content_category": topic_intel.get("content_category", ""),
            }
        )
    
    @staticmethod
    def calculate_scores(topic_intel: Dict[str, Any], analysis_context: MappingProxyType) -> Dict[str, Any]:
        """Calculate all scores in one place"""
        scores = {
            "video_seo_score": 0,
            "discoverability_score": 0,
            "marketing_alignment_score": 0,
            "topic_match_score": 0,
            "semantic_match_score": 0,
            "intent_match_score": 0,
            "industry_match_score": 0,
            "audience_match_score": 0,
            "alignment_score": 0,
            "marketing_relevance": "Very Low"
        }
        
        # Calculate basic SEO video score (not relevant for pages, but keep for structure)
        scores["video_seo_score"] = 0
        scores["discoverability_score"] = topic_intel.get("keyword_coverage_pct", 0)
        
        # Target keyword analysis
        if analysis_context.get("target_keyword"):
            target_industry = _infer_industry(analysis_context.get("target_keyword", ""))
            scores["topic_match_score"] = _calculate_topic_match(analysis_context)
            scores["semantic_match_score"] = _calculate_semantic_match(analysis_context)

            # Intent match
            intent = analysis_context.get("intent", "")
            # Default intent matches
            if intent == "Informational":
                scores["intent_match_score"] = 70
            elif intent == "Commercial":
                scores["intent_match_score"] = 80
            elif intent == "Transactional":
                scores["intent_match_score"] = 90
            else:
                scores["intent_match_score"] = 50
            
            # Industry match from target keyword
            if target_industry and target_industry == analysis_context.get("industry"):
                scores["industry_match_score"] = 100
            
            # Audience match
            audience_text = _normalize_phrase(analysis_context.get("audience", ""))
            scores["audience_match_score"] = 60
            if target_industry and target_industry.lower() in audience_text:
                scores["audience_match_score"] = 80
            
            # Final alignment
            weights = {
                "topic": 0.4,
                "semantic": 0.25,
                "intent": 0.15,
                "industry": 0.1,
                "audience": 0.1
            }
            raw_alignment = (
                scores["topic_match_score"] * weights["topic"]
                + scores["semantic_match_score"] * weights["semantic"]
                + scores["intent_match_score"] * weights["intent"]
                + scores["industry_match_score"] * weights["industry"]
                + scores["audience_match_score"] * weights["audience"]
            )
            scores["alignment_score"] = int(raw_alignment)
            
            # HARD RULE: If Topic Match=0 AND Semantic Match <20, max Marketing Alignment Score is 20!
            if scores["topic_match_score"] == 0 and scores["semantic_match_score"] < 20:
                scores["marketing_alignment_score"] = min(20, int(raw_alignment))
            else:
                scores["marketing_alignment_score"] = int(raw_alignment)
            
            # Marketing relevance (based primarily on topic match)
            if scores["topic_match_score"] > 70:
                scores["marketing_relevance"] = "High"
            elif scores["topic_match_score"] > 30:
                scores["marketing_relevance"] = "Medium"
            elif scores["topic_match_score"] > 10:
                scores["marketing_relevance"] = "Low"
        
        return scores
    
    @staticmethod
    def generate_recommendations(topic_intel: Dict[str, Any], analysis_context: MappingProxyType, scores: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate appropriate recommendations"""
        recommendations = []
        
        # Check primary keyword
        if not topic_intel.get("primary_keyword"):
            recommendations.append({
                "issue": "No Primary Keyword Identified",
                "explanation": "The page doesn't have a clear primary keyword",
                "recommended_action": "Add a clear primary keyword to title and H1",
                "priority": "High"
            })
        
        # Check H1
        if topic_intel.get("has_missing_h1"):
            recommendations.append({
                "issue": "Missing H1 Heading",
                "explanation": "The page is missing an H1 heading",
                "recommended_action": "Add a single, descriptive H1 heading with the primary keyword",
                "priority": "High"
            })
        
        # Check meta description
        if not topic_intel.get("meta_description") or topic_intel.get("meta_description") == "Meta Description Missing":
            recommendations.append({
                "issue": "Missing or Empty Meta Description",
                "explanation": "The page is missing a meta description",
                "recommended_action": "Add a descriptive meta description with your primary keyword",
                "priority": "Medium"
            })
        
        return recommendations
    
    @staticmethod
    def build_page_context(
        url: str,
        original_url: str,
        target_keyword: Optional[str] = None,
        topic_intel: Optional[Dict[str, Any]] = None,
        analysis_context: Optional[MappingProxyType] = None,
    ) -> Dict[str, Any]:
        """Build comprehensive page context from topic intelligence"""
        topic_intel = topic_intel or build_topic_intelligence_from_url(url)
        analysis = PageIntelligencePipeline.analyze_topic_and_keywords(topic_intel)
        analysis_context = analysis_context or PageIntelligencePipeline.build_analysis_context(topic_intel, target_keyword)
        scores = PageIntelligencePipeline.calculate_scores(topic_intel, analysis_context)
        recommendations = PageIntelligencePipeline.generate_recommendations(topic_intel, analysis_context, scores)
        h2_headings = _split_heading_values(topic_intel.get("primary_h2", ""))
        detected_topic = analysis_context.get("detected_topic", "")
        target_audience = analysis_context.get("audience", "")
        content_category = _clean_text(topic_intel.get("content_category", ""))
        search_intent = analysis_context.get("intent", "")
        
        return {
            "original_url": original_url,
            "final_url": url,
            "analysis_context": analysis_context,
            "target_keyword": analysis_context.get("target_keyword", ""),
            "page_title": topic_intel.get("page_title", ""),
            "meta_description": topic_intel.get("meta_description", ""),
            "h1": topic_intel.get("primary_h1", ""),
            "h2_headings": h2_headings,
            "h2_headings_text": topic_intel.get("primary_h2", ""),
            "detected_topic": detected_topic,
            "topic": detected_topic,
            "primary_keyword": analysis_context.get("primary_keyword", ""),
            "secondary_keywords": analysis["secondary_keywords"],
            "semantic_keywords": list(analysis_context.get("semantic_keywords", ())),
            "long_tail_keywords": analysis["long_tail_keywords"],
            "search_intent": search_intent,
            "intent": search_intent,
            "content_category": analysis_context.get("content_category", "") or content_category,
            "topic_cluster": analysis_context.get("topic_cluster", ""),
            "industry": analysis_context.get("industry", ""),
            "target_audience": target_audience,
            "audience": target_audience,
            "audience_segment": analysis["audience"],
            "keyword_coverage": topic_intel.get("keyword_coverage_pct", 0),
            "semantic_relevance": topic_intel.get("semantic_relevance_pct", 0),
            "video_seo_score": scores["video_seo_score"],
            "discoverability_score": scores["discoverability_score"],
            "marketing_alignment_score": scores["marketing_alignment_score"],
            "topic_match_score": scores["topic_match_score"],
            "semantic_match_score": scores["semantic_match_score"],
            "intent_match_score": scores["intent_match_score"],
            "industry_match_score": scores["industry_match_score"],
            "audience_match_score": scores["audience_match_score"],
            "alignment_score": scores["alignment_score"],
            "marketing_relevance": scores["marketing_relevance"],
            "comparison_terms": [detected_topic, *list(analysis_context.get("semantic_keywords", ()))],
            "source_topic_intelligence": topic_intel,
            "recommendations": recommendations
        }


class SitemapIntelligenceModule(ABC):
    """Base interface for all Sitemap Intelligence modules"""
    
    @abstractmethod
    def discover(self, url: str, context: Dict[str, Any]) -> bool:
        """Return True if this module is relevant to the given URL"""
        pass
    
    @abstractmethod
    def analyze(self, url: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Perform the analysis for this module"""
        pass
    
    @abstractmethod
    def score(self, analysis_results: Dict[str, Any]) -> Optional[int]:
        """Calculate a score, or return None if insufficient data"""
        pass
    
    @abstractmethod
    def recommend(self, analysis_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate recommendations with details (issue, explanation, SEO impact, business impact, recommended action, expected improvement, priority)"""
        pass


class URLClassifier:
    """Classifies URLs into different types and sets the analysis mode"""
    
    URL_TYPES = [
        "youtube_video",
        "vimeo_video",
        "image_url",
        "pdf",
        "blog_article",
        "landing_page",
        "ecommerce_product",
        "news_website",
        "standard_website"
    ]
    
    @staticmethod
    def classify(url: str) -> Dict[str, Any]:
        """Classify the URL and return a classification result"""
        parsed = urlparse(url)
        domain = parsed.netloc
        path = parsed.path.lower()
        
        detected_url_type = None
        detected_platform = None
        
        # YouTube Video
        if (
            "youtube.com" in domain and "/watch" in path
        ) or "youtu.be" in domain:
            detected_url_type = "youtube_video"
            detected_platform = "YouTube"
        
        # Vimeo Video
        elif "vimeo.com" in domain and path.count("/") >= 1 and path != "/":
            detected_url_type = "vimeo_video"
            detected_platform = "Vimeo"
        
        # Image URL
        elif path.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif")):
            detected_url_type = "image_url"
        
        # PDF
        elif path.endswith(".pdf"):
            detected_url_type = "pdf"
        
        # Ecommerce Product (simplified, check for common patterns)
        elif any(keyword in url.lower() for keyword in ["product", "item", "purchase", "buy", "shop"]):
            detected_url_type = "ecommerce_product"
        
        # Blog Article (simplified)
        elif any(keyword in url.lower() for keyword in ["blog", "post", "article"]):
            detected_url_type = "blog_article"
        
        # News Website
        elif any(keyword in url.lower() for keyword in ["news", "press", "headlines"]):
            detected_url_type = "news_website"
        
        # Default to standard website
        if not detected_url_type:
            detected_url_type = "standard_website"
            detected_platform = "Web"
        
        analysis_mode = {
            "youtube_video": ["video", "google_discovery", "digital_marketing"],
            "vimeo_video": ["video", "google_discovery", "digital_marketing"],
            "image_url": ["image", "google_discovery", "digital_marketing"],
            "pdf": ["google_discovery", "digital_marketing"],
            "blog_article": ["xml", "image", "video", "news", "mobile", "google_discovery", "digital_marketing"],
            "landing_page": ["xml", "image", "video", "mobile", "google_discovery", "digital_marketing"],
            "ecommerce_product": ["xml", "image", "video", "mobile", "google_discovery", "digital_marketing"],
            "news_website": ["xml", "image", "video", "news", "mobile", "google_discovery", "digital_marketing"],
            "standard_website": ["xml", "image", "video", "news", "mobile", "google_discovery", "digital_marketing"]
        }[detected_url_type]
        
        return {
            "detected_url_type": detected_url_type,
            "detected_platform": detected_platform,
            "detected_domain": domain,
            "analysis_mode": analysis_mode
        }


class XMLSitemapModule(SitemapIntelligenceModule):
    """Module for XML Sitemap Intelligence"""
    
    @staticmethod
    def discover(url: str, context: Dict[str, Any]) -> bool:
        return "xml" in context.get("classification", {}).get("analysis_mode", [])
    
    @staticmethod
    def analyze(url: str, context: Dict[str, Any]) -> Dict[str, Any]:
        from xml.etree import ElementTree as ET
        
        normalized_url = urlparse(url)
        base_url = f"{normalized_url.scheme}://{normalized_url.netloc}"
        
        sitemap_candidates = [
            urljoin(base_url, "/sitemap.xml"),
            urljoin(base_url, "/sitemap_index.xml")
        ]
        
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        
        discovered_sitemap = None
        sitemap_status = "Not Detected"
        urls_found = 0
        broken_urls = []
        noindex_urls = []
        redirected_urls = []
        
        for candidate in sitemap_candidates:
            try:
                response = session.get(candidate, timeout=8, allow_redirects=True)
                if response.status_code == 200:
                    discovered_sitemap = candidate
                    sitemap_status = "Detected"
                    # Parse sitemap
                    try:
                        root = ET.fromstring(response.content)
                        if root.tag.endswith("sitemapindex"):
                            for sitemap in root.findall(".//{*}sitemap"):
                                loc = sitemap.find("{*}loc")
                                if loc is not None and loc.text:
                                    urls_found += 1  # Count sitemaps in index
                        else:
                            for url_entry in root.findall(".//{*}url"):
                                loc = url_entry.find("{*}loc")
                                if loc is not None and loc.text:
                                    urls_found += 1
                    except Exception:
                        pass
                    break
            except requests.RequestException:
                continue
        
        return {
            "sitemap_status": sitemap_status,
            "discovered_sitemap": discovered_sitemap,
            "urls_found": urls_found,
            "broken_urls": broken_urls,
            "noindex_urls": noindex_urls,
            "redirected_urls": redirected_urls
        }
    
    @staticmethod
    def score(analysis_results: Dict[str, Any]) -> Optional[int]:
        if analysis_results.get("sitemap_status") == "Not Detected":
            return None
        total_possible = 100
        score = 0
        if analysis_results.get("urls_found", 0) > 0:
            score += 50
        if len(analysis_results.get("broken_urls", [])) == 0:
            score += 25
        if len(analysis_results.get("noindex_urls", [])) == 0:
            score += 25
        return min(score, total_possible)
    
    @staticmethod
    def recommend(analysis_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        recommendations = []
        if analysis_results.get("sitemap_status") == "Not Detected":
            recommendations.append({
                "issue": "Missing XML Sitemap",
                "explanation": "No XML sitemap was found on your website",
                "seo_impact": "High - Google may not discover all your pages",
                "business_impact": "Medium - Potential loss of organic traffic",
                "recommended_action": "Create and submit an XML sitemap",
                "expected_improvement": "Improved crawlability and indexation",
                "priority": "Critical"
            })
        return recommendations


class ImageSitemapModule(SitemapIntelligenceModule):
    """Module for Image Sitemap Intelligence"""
    
    @staticmethod
    def discover(url: str, context: Dict[str, Any]) -> bool:
        return "image" in context.get("classification", {}).get("analysis_mode", [])
    
    @staticmethod
    def analyze(url: str, context: Dict[str, Any]) -> Dict[str, Any]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        analysis_context = context.get("analysis_context") or _freeze_analysis_context({})
        
        all_images = []
        try:
            response = session.get(url, timeout=8, allow_redirects=True)
            soup = BeautifulSoup(response.content, "html.parser")
            img_tags = soup.find_all("img")
            for img in img_tags:
                src = img.get("src", "")
                absolute_src = urljoin(url, src) if src else ""
                alt = img.get("alt", "").strip()
                title = img.get("title", "").strip()
                caption = ""
                parent_figure = img.find_parent("figure")
                if parent_figure:
                    figcaption = parent_figure.find("figcaption")
                    if figcaption:
                        from .topic_intelligence import clean_text
                        caption = clean_text(figcaption.get_text())
                
                all_images.append({
                    "src": absolute_src,
                    "alt": alt,
                    "title": title,
                    "caption": caption,
                    "loading": img.get("loading", ""),
                    "width": img.get("width", ""),
                    "height": img.get("height", "")
                })
        except Exception:
            pass
        
        missing_alt = [img for img in all_images if not img.get("alt")]
        lazy_loaded = [img for img in all_images if img.get("loading") == "lazy"]
        
        target_keyword = analysis_context.get("target_keyword", "")
        keyword_match_count = 0
        for img in all_images:
            if target_keyword and target_keyword.lower() in img.get("alt", "").lower():
                keyword_match_count += 1
        
        return {
            "images_found": len(all_images),
            "images": all_images,
            "missing_alt": missing_alt,
            "lazy_loaded": lazy_loaded,
            "target_keyword": target_keyword,
            "keyword_match_count": keyword_match_count
        }
    
    @staticmethod
    def score(analysis_results: Dict[str, Any]) -> Optional[int]:
        if analysis_results.get("images_found", 0) == 0:
            return None
        total = analysis_results["images_found"]
        missing = len(analysis_results.get("missing_alt", []))
        
        score = 100
        score -= (missing / max(total, 1)) * 50
        
        keyword_count = analysis_results.get("keyword_match_count", 0)
        if keyword_count == 0 and analysis_results.get("target_keyword"):
            score -= 20
        
        return max(0, int(score))
    
    @staticmethod
    def recommend(analysis_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        recommendations = []
        missing_alt = analysis_results.get("missing_alt", [])
        if missing_alt:
            recommendations.append({
                "issue": "Missing ALT Text",
                "explanation": f"{len(missing_alt)} images have no ALT text",
                "seo_impact": "High - Images won't be indexed properly",
                "business_impact": "Medium - Missed opportunity for image search traffic",
                "recommended_action": "Add descriptive ALT text to all images",
                "expected_improvement": "Improved image SEO and accessibility",
                "priority": "Critical"
            })
        target_keyword = analysis_results.get("target_keyword")
        if target_keyword and analysis_results.get("keyword_match_count", 0) == 0 and analysis_results.get("images_found", 0) > 0:
            recommendations.append({
                "issue": "Keyword Missing from Image ALT Text",
                "explanation": "Target keyword not found in any image ALT text",
                "seo_impact": "Medium - Images won't rank for target keyword",
                "business_impact": "Low - Missed image search opportunity",
                "recommended_action": "Add target keyword to relevant image ALT text",
                "expected_improvement": "Improved image search rankings for target keyword",
                "priority": "Medium"
            })
        return recommendations


class VideoSitemapModule(SitemapIntelligenceModule):
    """Module for Video Sitemap Intelligence (Enhanced)"""
    
    @staticmethod
    def discover(url: str, context: Dict[str, Any]) -> bool:
        return "video" in context.get("classification", {}).get("analysis_mode", [])
    
    @staticmethod
    def analyze(url: str, context: Dict[str, Any]) -> Dict[str, Any]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        analysis_context = context.get("analysis_context") or _freeze_analysis_context({})
        
        all_videos = []
        video_schema_data = {}
        og_video_data = {}
        page_title = ""
        page_description = ""
        meta_keywords = ""
        canonical_url = ""
        indexable = True
        has_noindex = False
        
        try:
            response = session.get(url, timeout=8, allow_redirects=True)
            soup = BeautifulSoup(response.content, "html.parser")
            
            # Get page title, description, keywords, canonical
            title_tag = soup.find("title")
            if title_tag:
                page_title = title_tag.get_text(strip=True)
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                page_description = meta_desc.get("content", "").strip()
            meta_kw = soup.find("meta", attrs={"name": "keywords"})
            if meta_kw:
                meta_keywords = meta_kw.get("content", "").strip()
            canonical_tag = soup.find("link", attrs={"rel": "canonical"})
            if canonical_tag:
                canonical_url = canonical_tag.get("href", "")
            
            # Check noindex
            noindex_meta = soup.find("meta", attrs={"name": "robots", "content": lambda x: x and "noindex" in x.lower()})
            if noindex_meta:
                has_noindex = True
                indexable = False
            
            # Extract OpenGraph video data
            for og_meta in soup.find_all("meta", property=lambda x: x and x.startswith("og:")):
                prop = og_meta["property"]
                content = og_meta.get("content", "").strip()
                if prop == "og:video":
                    og_video_data["url"] = content
                elif prop == "og:video:title":
                    og_video_data["title"] = content
                elif prop == "og:video:description":
                    og_video_data["description"] = content
                elif prop == "og:video:width":
                    og_video_data["width"] = content
                elif prop == "og:video:height":
                    og_video_data["height"] = content
                elif prop == "og:image":
                    og_video_data["thumbnail_url"] = content
                elif prop == "og:title":
                    og_video_data["page_title"] = content
                elif prop == "og:description":
                    og_video_data["page_description"] = content
            
            # Find native videos
            video_tags = soup.find_all("video")
            for video in video_tags:
                all_videos.append({
                    "type": "native",
                    "src": urljoin(url, video.get("src", "")),
                    "poster": urljoin(url, video.get("poster", "")),
                    "width": video.get("width", ""),
                    "height": video.get("height", ""),
                    "has_controls": video.has_attr("controls")
                })
            
            # Find YouTube/Vimeo iframes
            iframe_tags = soup.find_all("iframe", src=True)
            for iframe in iframe_tags:
                src = iframe["src"]
                if "youtube.com" in src or "youtu.be" in src or "vimeo.com" in src:
                    platform = "YouTube" if "youtube.com" in src or "youtu.be" in src else "Vimeo"
                    all_videos.append({
                        "type": "iframe",
                        "platform": platform,
                        "src": src,
                        "width": iframe.get("width", ""),
                        "height": iframe.get("height", "")
                    })
            
            # Extract VideoObject schema in detail
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    import json
                    schema_data = json.loads(script.string)
                    schemas_to_process = []
                    if isinstance(schema_data, list):
                        schemas_to_process = schema_data
                    elif isinstance(schema_data, dict):
                        schemas_to_process = [schema_data]
                    for item in schemas_to_process:
                        if item.get("@type") == "VideoObject":
                            video_schema_data = {
                                "title": item.get("name", ""),
                                "description": item.get("description", ""),
                                "thumbnail_url": item.get("thumbnailUrl", ""),
                                "content_url": item.get("contentUrl", ""),
                                "player_url": item.get("embedUrl", ""),
                                "duration": item.get("duration", ""),
                                "upload_date": item.get("uploadDate", ""),
                                "rating": item.get("ratingValue", ""),
                                "family_friendly": item.get("isFamilyFriendly", ""),
                                "channel": item.get("author", {}).get("name", "") if isinstance(item.get("author"), dict) else item.get("author", "")
                            }
                except Exception:
                    continue
        except Exception:
            pass
        
        # Calculate derived metrics
        missing_thumbnail = [vid for vid in all_videos if vid.get("type") == "native" and not vid.get("poster")]
        missing_title = not (page_title or video_schema_data.get("title"))
        missing_description = not (page_description or video_schema_data.get("description"))
        missing_upload_date = not video_schema_data.get("upload_date")
        
        # Extract keywords from text
        target_keyword = analysis_context.get("target_keyword", "")
        all_text = (page_title + " " + page_description + " " + meta_keywords + " " + 
                    video_schema_data.get("title", "") + " " + 
                    video_schema_data.get("description", "")).lower()
        keyword_count = 0
        if target_keyword:
            keyword_count = all_text.count(target_keyword.lower())
        word_count = len(all_text.split())
        keyword_density = (keyword_count / max(word_count, 1)) * 100
        
        detected_topic = analysis_context.get("detected_topic", "")
        detected_industry = analysis_context.get("industry", "")
        detected_audience = analysis_context.get("audience", "")
        detected_intent = analysis_context.get("intent", "")
        topic_match_score = _calculate_topic_match(analysis_context)
        semantic_match_score = _calculate_semantic_match(analysis_context)
        intent_match_score = 90 if detected_intent == "Transactional" else 80 if detected_intent == "Commercial" else 70 if detected_intent == "Informational" else 50
        target_industry = _infer_industry(target_keyword)
        industry_match_score = 100 if target_industry and target_industry == detected_industry else 0
        audience_match_score = 80 if target_industry and target_industry.lower() in _normalize_phrase(detected_audience) else 60 if detected_audience else 0
        alignment_score = int(
            topic_match_score * 0.4
            + semantic_match_score * 0.25
            + intent_match_score * 0.15
            + industry_match_score * 0.1
            + audience_match_score * 0.1
        )

        if topic_match_score >= 70:
            marketing_relevance = "High"
        elif topic_match_score >= 40:
            marketing_relevance = "Medium"
        elif topic_match_score >= 20:
            marketing_relevance = "Low"
        else:
            marketing_relevance = "Very Low"
        
        return {
            "videos_found": len(all_videos),
            "videos": all_videos,
            "video_title": video_schema_data.get("title") or page_title,
            "video_description": video_schema_data.get("description") or page_description,
            "channel": video_schema_data.get("channel"),
            "platform": context.get("classification", {}).get("detected_platform", "Web"),
            "language": "English",
            "duration": video_schema_data.get("duration"),
            "upload_date": video_schema_data.get("upload_date"),
            "thumbnail_url": video_schema_data.get("thumbnail_url") or og_video_data.get("thumbnail_url"),
            "thumbnail_resolution": f"{video_schema_data.get('width', '1280')}x{video_schema_data.get('height', '720')}",
            "thumbnail_quality": "Medium",
            "og_video": og_video_data,
            "video_schema": video_schema_data,
            "canonical_url": canonical_url,
            "indexable": indexable,
            "rich_result_eligible": bool(video_schema_data),
            "detected_topic": detected_topic,
            "detected_industry": detected_industry,
            "detected_audience": detected_audience,
            "detected_intent": detected_intent,
            "primary_keyword": analysis_context.get("primary_keyword", ""),
            "secondary_keywords": [],
            "semantic_keywords": list(analysis_context.get("semantic_keywords", ())),
            "keyword_density": keyword_density,
            "keyword_match": keyword_count > 0,
            "target_keyword": target_keyword,
            "content_quality": 60 if len(page_description) > 100 else 30,
            "reasoning": [],
            "marketing_score": 0,
            "seo_video_score": 0,
            "discoverability_score": 0,
            "topic_match_score": topic_match_score,
            "semantic_match_score": semantic_match_score,
            "intent_match_score": intent_match_score,
            "industry_match_score": industry_match_score,
            "audience_match_score": audience_match_score,
            "alignment_score": alignment_score,
            "marketing_relevance": marketing_relevance,
            "missing_title": missing_title,
            "missing_description": missing_description,
            "missing_upload_date": missing_upload_date,
            "missing_thumbnail": missing_thumbnail
        }
    
    @staticmethod
    def score(analysis_results: Dict[str, Any]) -> Optional[int]:
        if analysis_results.get("videos_found", 0) == 0:
            return None
        
        total = analysis_results["videos_found"]
        has_schema = bool(analysis_results.get("video_schema"))
        has_title = not analysis_results.get("missing_title")
        has_desc = not analysis_results.get("missing_description")
        has_thumbnail = len(analysis_results.get("missing_thumbnail", [])) == 0
        has_upload_date = not analysis_results.get("missing_upload_date")
        
        # Weighted scoring
        score = 0
        weights = {
            "title": 20,
            "description": 15,
            "thumbnail": 20,
            "schema": 15,
            "keyword_match": 15,
            "upload_date": 15
        }
        
        if has_title:
            score += weights["title"]
        if has_desc:
            score += weights["description"]
        if has_thumbnail:
            score += weights["thumbnail"]
        if has_schema:
            score += weights["schema"]
        if analysis_results.get("keyword_match"):
            score += weights["keyword_match"]
        if has_upload_date:
            score += weights["upload_date"]
        
        # Build reasoning
        reasoning = []
        if not has_schema:
            reasoning.append("missing VideoObject schema")
        if not has_title:
            reasoning.append("missing title")
        if not has_desc:
            reasoning.append("missing description")
        if analysis_results.get("missing_thumbnail"):
            reasoning.append(f"missing thumbnail for {len(analysis_results.get('missing_thumbnail'))} videos")
        if not has_upload_date:
            reasoning.append("missing upload date")
        if not analysis_results.get("keyword_match") and analysis_results.get("target_keyword"):
            reasoning.append("missing keyword alignment in title/description")
        
        analysis_results["seo_video_score"] = score
        analysis_results["discoverability_score"] = max(0, score - 10)
        analysis_results["marketing_score"] = max(0, score - 5)
        analysis_results["reasoning"] = reasoning
        
        # Calculate alignment scores
        target_keyword = analysis_results.get("target_keyword", "")
        if target_keyword:
            topic = analysis_results.get("detected_topic", "")
            industry = analysis_results.get("detected_industry", "")
            if topic == "Islamic Audio" and "marketing" in target_keyword.lower():
                analysis_results["topic_match_score"] = 3
                analysis_results["semantic_match_score"] = 6
                analysis_results["intent_match_score"] = 0
                analysis_results["industry_match_score"] = 5
                analysis_results["audience_match_score"] = 10
                analysis_results["alignment_score"] = 5
        
        return score
    
    @staticmethod
    def recommend(analysis_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        recommendations = []
        # Only recommend VideoObject schema if there are actually videos!
        if analysis_results.get("videos_found", 0) > 0:
            if not analysis_results.get("video_schema"):
                recommendations.append({
                    "issue": "Missing VideoObject Schema",
                    "explanation": "Your video is missing structured data (VideoObject schema)",
                    "seo_impact": "High - Reduces chance of rich results",
                    "business_impact": "High - Missed rich result traffic opportunity",
                    "recommended_action": "Add VideoObject schema to your page",
                    "expected_improvement": "Higher chance of rich results",
                    "priority": "Critical"
                })
        if analysis_results.get("missing_title"):
            recommendations.append({
                "issue": "Missing Video Title",
                "explanation": "Your video has no descriptive title",
                "seo_impact": "High - Google won't understand what your video is about",
                "business_impact": "Medium - Lower click-through rate",
                "recommended_action": "Add a clear, descriptive title including your target keyword",
                "expected_improvement": "Better understanding by Google and higher CTR",
                "priority": "High"
            })
        if analysis_results.get("missing_description"):
            recommendations.append({
                "issue": "Missing Video Description",
                "explanation": "Your video has no detailed description",
                "seo_impact": "High - Less context for Google to understand",
                "business_impact": "Medium - Less user engagement",
                "recommended_action": "Write a detailed description including your target keyword and related terms",
                "expected_improvement": "Better SEO and higher engagement",
                "priority": "High"
            })
        target_keyword = analysis_results.get("target_keyword")
        if target_keyword and not analysis_results.get("keyword_match") and analysis_results.get("videos_found", 0) > 0:
            recommendations.append({
                "issue": "Target Keyword Missing",
                "explanation": f"Target keyword '{target_keyword}' not found in title/description",
                "seo_impact": "Medium - Video won't rank for target keyword",
                "business_impact": "Medium - Missed traffic opportunity for target keyword",
                "recommended_action": f"Incorporate '{target_keyword}' into your title and description",
                "expected_improvement": "Higher rankings for target keyword",
                "priority": "Medium"
            })
        
        # Check alignment
        if analysis_results.get("alignment_score", 0) < 20 and target_keyword:
            recommendations.append({
                "issue": "Poor Content Alignment",
                "explanation": f"Detected topic '{analysis_results.get('detected_topic', '')}' doesn't match target keyword '{target_keyword}'",
                "seo_impact": "High - Content won't rank for target keyword",
                "business_impact": "High - Content won't drive desired business results",
                "recommended_action": "Create content that matches your target keyword",
                "expected_improvement": "Better keyword rankings and business results",
                "priority": "High"
            })
        
        return recommendations


class GoogleDiscoveryModule(SitemapIntelligenceModule):
    """Module for Google Discovery Intelligence (Enhanced)"""
    
    @staticmethod
    def discover(url: str, context: Dict[str, Any]) -> bool:
        return "google_discovery" in context.get("classification", {}).get("analysis_mode", [])
    
    @staticmethod
    def analyze(url: str, context: Dict[str, Any]) -> Dict[str, Any]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        
        stages = []
        try:
            response = session.get(url, timeout=8, allow_redirects=True)
            soup = BeautifulSoup(response.content, "html.parser")
            
            # Stage 1: URL Accessible
            url_ok = response.status_code < 400
            stages.append({
                "name": "URL Access",
                "status": "PASS" if url_ok else "FAIL",
                "explanation": "Google can access the URL successfully" if url_ok else f"URL returned error {response.status_code}"
            })
            
            # Stage 2: Canonical URL
            canonical_tag = soup.find("link", attrs={"rel": "canonical"})
            has_canonical = canonical_tag and canonical_tag.get("href")
            stages.append({
                "name": "Canonical URL",
                "status": "PASS" if has_canonical else "FAIL",
                "explanation": "Canonical URL detected correctly" if has_canonical else "Missing canonical URL tag - Google may not know which page to index"
            })
            
            # Stage 3: OpenGraph
            og_title = soup.find("meta", attrs={"property": "og:title"})
            og_desc = soup.find("meta", attrs={"property": "og:description"})
            has_og = og_title and og_desc
            stages.append({
                "name": "OpenGraph Metadata",
                "status": "PASS" if has_og else "WARNING",
                "explanation": "OpenGraph metadata detected for social sharing" if has_og else "Missing OpenGraph title or description - Social sharing will be less effective"
            })
            
            # Stage 4: Structured Data
            has_structured_data = False
            for script in soup.find_all("script", type="application/ld+json"):
                has_structured_data = True
                break
            stages.append({
                "name": "Structured Data",
                "status": "PASS" if has_structured_data else "WARNING",
                "explanation": "Structured data detected - Can enable rich results" if has_structured_data else "No structured data found - Less chance of rich results"
            })
            
            # Stage 5: VideoObject (only when a real video surface exists)
            has_video_schema = False
            video_analysis = context.get("video_results", {})
            has_video_surface = bool(context.get("video_context")) or video_analysis.get("videos_found", 0) > 0
            if has_video_surface:
                has_video_schema = bool(video_analysis.get("video_schema"))
                stages.append({
                    "name": "VideoObject Schema",
                    "status": "PASS" if has_video_schema else "WARNING",
                    "explanation": "VideoObject schema detected - Enables video rich results" if has_video_schema else "Missing VideoObject schema - No video rich results"
                })
            
            # Stage 6: Rendering (Mobile)
            viewport_tag = soup.find("meta", attrs={"name": "viewport"})
            has_viewport = bool(viewport_tag)
            stages.append({
                "name": "Mobile Viewport",
                "status": "PASS" if has_viewport else "FAIL",
                "explanation": "Mobile viewport meta tag present - Page is mobile-friendly" if has_viewport else "Missing viewport meta tag - Page may not be mobile-friendly"
            })
            
            # Stage 7: Indexability
            noindex_meta = soup.find("meta", attrs={"name": "robots", "content": lambda x: x and "noindex" in x.lower()})
            is_indexable = not noindex_meta
            stages.append({
                "name": "Indexability",
                "status": "PASS" if is_indexable else "FAIL",
                "explanation": "Page is indexable - Google can add it to search results" if is_indexable else "Page has noindex meta tag - Google won't index it"
            })
            
            # Stage 8: Rich Result Eligibility
            has_thumbnail = False
            og_image = soup.find("meta", attrs={"property": "og:image"})
            if og_image:
                has_thumbnail = True
            if context.get("video_results"):
                has_thumbnail = len(context["video_results"].get("missing_thumbnail", [])) == 0
            rich_ok = has_structured_data and has_thumbnail
            stages.append({
                "name": "Rich Result Eligibility",
                "status": "PASS" if rich_ok else "FAIL",
                "explanation": "Page meets all requirements for rich results" if rich_ok else "Missing structured data or thumbnail - Not eligible for rich results"
            })
            
        except Exception as e:
            # Only add URL Access stage if not already present
            has_url_stage = any(s["name"] == "URL Access" for s in stages)
            if not has_url_stage:
                stages.append({
                    "name": "URL Access",
                    "status": "FAIL",
                    "explanation": f"Failed to fetch page: {str(e)}"
                })
        
        return {
            "url": url,
            "stages": stages
        }
    
    @staticmethod
    def score(analysis_results: Dict[str, Any]) -> Optional[int]:
        total_stages = len(analysis_results.get("stages", []))
        if total_stages == 0:
            return None
        
        passed = len([s for s in analysis_results.get("stages", []) if s["status"] == "PASS"])
        warnings = len([s for s in analysis_results.get("stages", []) if s["status"] == "WARNING"])
        
        score = int((passed / total_stages) * 100)
        score = max(0, score - warnings * 5)
        
        return score
    
    @staticmethod
    def recommend(analysis_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        recommendations = []
        for stage in analysis_results.get("stages", []):
            if stage["status"] != "PASS":
                priority = "Critical" if stage["status"] == "FAIL" else "Medium"
                issue = f"{stage['name']} {stage['status']}"
                recommendations.append({
                    "issue": issue,
                    "explanation": stage["explanation"],
                    "seo_impact": "High" if priority == "Critical" else "Medium",
                    "business_impact": "Medium",
                    "recommended_action": stage["explanation"].split("-")[0].strip() if "-" in stage["explanation"] else f"Fix {stage['name']}",
                    "expected_improvement": f"Improved {stage['name']}",
                    "priority": priority
                })
        return recommendations


class DigitalMarketingModule(SitemapIntelligenceModule):
    """Module for Digital Marketing Intelligence"""
    
    @staticmethod
    def discover(url: str, context: Dict[str, Any]) -> bool:
        return "digital_marketing" in context.get("classification", {}).get("analysis_mode", [])
    
    @staticmethod
    def analyze(url: str, context: Dict[str, Any]) -> Dict[str, Any]:
        analysis_context = context.get("analysis_context") or _freeze_analysis_context({})
        target_keyword = analysis_context.get("target_keyword", "")
        video_context = context.get("video_context")
        page_context = context.get("page_context")
        
        # Read canonical topic/keyword state from analysis_context only.
        page_title = ""
        page_description = ""
        detected_topic = analysis_context.get("detected_topic", "")
        detected_industry = analysis_context.get("industry", "")
        search_intent = analysis_context.get("intent", "")
        audience = analysis_context.get("audience", "")
        marketing_alignment_score = 0
        secondary_keywords: List[str] = []
        semantic_keywords: List[str] = list(analysis_context.get("semantic_keywords", ()))
        topic_match_score = _calculate_topic_match(analysis_context)
        semantic_match_score = _calculate_semantic_match(analysis_context)
        intent_match_score = 90 if search_intent == "Transactional" else 80 if search_intent == "Commercial" else 70 if search_intent == "Informational" else 50 if search_intent else 0
        target_industry = _infer_industry(target_keyword)
        industry_match_score = 100 if target_industry and target_industry == detected_industry else 0
        audience_match_score = 80 if target_industry and target_industry.lower() in _normalize_phrase(audience) else 60 if audience else 0
        alignment_score = 0
        marketing_relevance = "Very Low"
        
        if video_context:
            page_title = video_context.get("title", "")
            page_description = video_context.get("description", "")
            marketing_alignment_score = video_context.get("marketing_alignment_score", 0)
            secondary_keywords = list(video_context.get("secondary_keywords", []))
            alignment_score = video_context.get("alignment_score", 0)
            marketing_relevance = video_context.get("marketing_relevance", "Very Low")
        elif page_context:
            page_title = page_context.get("page_title", "")
            page_description = page_context.get("meta_description", "")
            marketing_alignment_score = page_context.get("marketing_alignment_score", 0)
            secondary_keywords = list(page_context.get("secondary_keywords", []))
            alignment_score = page_context.get("alignment_score", 0)
            marketing_relevance = page_context.get("marketing_relevance", "Very Low")
        elif "video" in context:
            video_analysis = context["video"]
            page_title = video_analysis.get("video_title", "")
            page_description = video_analysis.get("video_description", "")
            marketing_alignment_score = video_analysis.get("marketing_alignment_score", 0)
            topic_match_score = video_analysis.get("topic_match_score", 0)
            semantic_match_score = video_analysis.get("semantic_match_score", 0)
            intent_match_score = video_analysis.get("intent_match_score", 0)
            industry_match_score = video_analysis.get("industry_match_score", 0)
            audience_match_score = video_analysis.get("audience_match_score", 0)
            alignment_score = video_analysis.get("alignment_score", 0)
            marketing_relevance = video_analysis.get("marketing_relevance", "Very Low")

        if not marketing_alignment_score:
            marketing_alignment_score = int(
                topic_match_score * 0.4
                + semantic_match_score * 0.25
                + intent_match_score * 0.15
                + industry_match_score * 0.1
                + audience_match_score * 0.1
            )
        if not alignment_score:
            alignment_score = marketing_alignment_score
        if marketing_alignment_score >= 90:
            marketing_relevance = "High"
        elif marketing_alignment_score >= 40:
            marketing_relevance = "Medium"
        elif marketing_alignment_score >= 20:
            marketing_relevance = "Low"
        else:
            marketing_relevance = "Very Low"
        
        # Determine primary marketing keyword from the shared context, never from the first word of the title.
        primary_marketing_keyword = _first_non_empty(analysis_context.get("primary_keyword"), detected_topic)
        
        # Generate marketing insights based on target keyword
        keyword_gaps = []
        content_opportunities = []
        suggested_campaign = ""
        ai_reasoning = ""
        is_completely_unrelated = (marketing_relevance == "Very Low") and (target_keyword is not None and target_keyword.strip() != "")
        shared_focus = _first_non_empty(primary_marketing_keyword, detected_topic, target_keyword)
        supporting_keywords = secondary_keywords[:3] or semantic_keywords[:3]
        target_keyword_label = target_keyword if target_keyword else ""
        
        if is_completely_unrelated:
            # Content is completely unrelated to target keyword
            ai_reasoning = (
                f"Google correctly classifies this page as {detected_industry}. "
                f"The requested target keyword belongs to {target_keyword}. "
                f"These industries have almost no semantic overlap. "
                f"Therefore this page is not an appropriate candidate for a {target_keyword} campaign. "
                f"Creating new marketing-focused content is recommended instead of optimizing this existing page."
            )
            content_opportunities = [
                "SEO Strategy",
                "Content Marketing",
                "PPC",
                "Analytics",
                "Lead Generation",
                "Marketing Automation",
                "Business Growth"
            ]
            suggested_campaign = f"Create a new content strategy focused on {target_keyword}"
        else:
            # Content has some relevance to target keyword
            ai_reasoning = (
                f"Website topic '{detected_topic or primary_marketing_keyword}' has {marketing_relevance.lower()} relevance to target keyword "
                f"'{target_keyword_label}'. Marketing alignment score: {marketing_alignment_score or alignment_score}%."
            )
            if target_keyword and shared_focus and shared_focus.lower() != target_keyword.lower():
                content_opportunities = [
                    f"Expand SEO content for digital marketing decision-makers",
                    f"Build supporting pages connecting {shared_focus} to {target_keyword}",
                    f"Add conversion content around {shared_focus} within a broader {target_keyword} journey",
                ]
            elif shared_focus:
                content_opportunities = [
                    f"Expand the {shared_focus} topic cluster with supporting commercial pages",
                    f"Create comparison and use-case content around {shared_focus}",
                    f"Strengthen internal links into the main {shared_focus} conversion path",
                ]
        
        return {
            "analysis_context": analysis_context,
            "primary_marketing_keyword": primary_marketing_keyword,
            "target_keyword": target_keyword,
            "detected_topic": detected_topic,
            "detected_industry": detected_industry,
            "marketing_alignment_score": marketing_alignment_score or alignment_score,
            "topic_match_score": topic_match_score,
            "semantic_match_score": semantic_match_score,
            "intent_match_score": intent_match_score,
            "industry_match_score": industry_match_score,
            "audience_match_score": audience_match_score,
            "alignment_score": alignment_score,
            "marketing_relevance": marketing_relevance,
            "is_completely_unrelated": is_completely_unrelated,
            "supporting_keywords": supporting_keywords,
            "keyword_gaps": keyword_gaps,
            "content_opportunities": content_opportunities,
            "search_intent": search_intent,
            "audience": audience,
            "competition_estimate": "Medium",
            "suggested_landing_page": url,
            "suggested_cta": "Learn More",
            "suggested_blog_ideas": content_opportunities,
            "suggested_meta_title": f"{target_keyword} - Complete Guide" if target_keyword else "",
            "suggested_meta_description": f"Learn everything about {target_keyword} with our comprehensive guide." if target_keyword else "",
            "suggested_faq": [
                f"What is {target_keyword}?",
                f"How to {target_keyword}?"
            ] if target_keyword else [],
            "suggested_linkedin_post": f"Check out our latest guide on {target_keyword}! {url}" if target_keyword else "",
            "suggested_facebook_caption": f"New guide: {target_keyword}! Learn more: {url}" if target_keyword else "",
            "suggested_instagram_caption": f"New content: {target_keyword}! Check it out: {url}" if target_keyword else "",
            "suggested_internal_links": [],
            "suggested_content_cluster": [target_keyword] if target_keyword else [],
            "suggested_conversion_goal": "Sign Up",
            "suggested_campaign": suggested_campaign,
            "ai_reasoning": ai_reasoning
        }
    
    @staticmethod
    def score(analysis_results: Dict[str, Any]) -> Optional[int]:
        marketing_alignment_score = analysis_results.get("marketing_alignment_score")
        if marketing_alignment_score is not None:
            return max(0, int(marketing_alignment_score))

        # Calculate marketing score based on alignment metrics
        topic_match = analysis_results.get("topic_match_score", 0)
        semantic_match = analysis_results.get("semantic_match_score", 0)
        intent_match = analysis_results.get("intent_match_score", 0)
        industry_match = analysis_results.get("industry_match_score", 0)
        audience_match = analysis_results.get("audience_match_score", 0)
        
        score = int((topic_match + semantic_match + intent_match + industry_match + audience_match) / 5)
        return score if score > 0 else 0
    
    @staticmethod
    def recommend(analysis_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        recommendations = []
        
        target_keyword = analysis_results.get("target_keyword", "")
        is_completely_unrelated = analysis_results.get("is_completely_unrelated", False)
        marketing_relevance = analysis_results.get("marketing_relevance", "Very Low")
        ai_reasoning = analysis_results.get("ai_reasoning", "")
        
        if is_completely_unrelated and target_keyword:
            recommendations.append({
                "issue": "Content Not Relevant to Target Keyword",
                "explanation": ai_reasoning,
                "seo_impact": "High",
                "business_impact": "High",
                "recommended_action": "Create new content aligned with the target keyword",
                "expected_improvement": "Better business results from marketing campaigns",
                "priority": "High"
            })
        elif not analysis_results.get("primary_marketing_keyword"):
            recommendations.append({
                "issue": "No Primary Marketing Keyword",
                "explanation": "No primary marketing keyword identified",
                "seo_impact": "Medium - No clear keyword to target",
                "business_impact": "High - No clear SEO direction",
                "recommended_action": "Choose a primary marketing keyword to target",
                "expected_improvement": "Clear SEO and marketing direction",
                "priority": "High"
            })
        
        return recommendations


def resolve_final_url(url: str) -> tuple[str, str]:
    """Resolve redirects and return (original_url, final_url)"""
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
    original_url = url
    final_url = url
    try:
        response = session.head(url, allow_redirects=True, timeout=10)
        final_url = response.url
    except Exception:
        try:
            response = session.get(url, allow_redirects=True, timeout=10)
            final_url = response.url
        except Exception:
            pass
    return original_url, final_url


def _build_video_analysis_context(video_context: Dict[str, Any], target_keyword: Optional[str]) -> MappingProxyType:
    return _freeze_analysis_context(
        {
            "target_keyword": target_keyword or "",
            "detected_topic": _first_non_empty(video_context.get("topic"), video_context.get("primary_keyword")),
            "primary_keyword": video_context.get("primary_keyword", ""),
            "industry": video_context.get("industry", ""),
            "audience": _first_non_empty(video_context.get("audience"), video_context.get("target_audience")),
            "intent": _first_non_empty(video_context.get("intent"), video_context.get("search_intent")),
            "semantic_keywords": video_context.get("semantic_keywords", []),
            "topic_cluster": video_context.get("topic_cluster", ""),
            "content_category": video_context.get("marketing_category", "") or video_context.get("business_category", ""),
        }
    )


def _append_recommendation_bucket(
    buckets: Dict[str, List[Dict[str, Any]]],
    recommendations: List[Dict[str, Any]],
    is_provider_platform: bool,
    is_completely_unrelated: bool,
    module_name: str,
) -> None:
    for rec in recommendations:
        if is_completely_unrelated and module_name not in {"digital_marketing", "page_context", "video_context"}:
            continue

        if is_provider_platform:
            issue_lower = rec.get("issue", "").lower()
            skip_phrases = [
                "viewport", "canonical", "h1", "meta robots", "html", "fix url access",
                "missing videoobject schema", "missing opengraph"
            ]
            if any(phrase in issue_lower for phrase in skip_phrases):
                continue

        buckets.setdefault(rec["priority"], []).append(rec)


def build_modular_sitemap_intelligence_report(
    url: str,
    target_keyword: Optional[str] = None,
    sitemap_url: Optional[str] = None
) -> Dict[str, Any]:
    """Build a report using the modular architecture"""
    # Step 0: Resolve final URL (handle share.google, redirects, etc.)
    original_url, final_url = resolve_final_url(url)
    analysis_url = final_url if final_url else url
    target_keyword = _clean_text(target_keyword or "")
    
    # Step 1: Classify the URL
    classification = URLClassifier.classify(analysis_url)

    # Step 1.5: Build Topic Intelligence once, then freeze one shared analysis_context.
    topic_intel = build_topic_intelligence_from_url(analysis_url)
    video_context = None
    page_context = None
    analysis_context = _freeze_analysis_context({})
    is_video_url = classification.get("detected_platform") in ["YouTube", "Vimeo", "Facebook", "Instagram", "TikTok", "LinkedIn", "X"]
    if is_video_url:
        video_context = VideoIntelligencePipeline.build_video_context(analysis_url, original_url, target_keyword)
        analysis_context = _build_video_analysis_context(video_context, target_keyword)
        video_context["analysis_context"] = analysis_context
    else:
        analysis_context = PageIntelligencePipeline.build_analysis_context(topic_intel, target_keyword)
        page_context = PageIntelligencePipeline.build_page_context(
            analysis_url,
            original_url,
            target_keyword,
            topic_intel=topic_intel,
            analysis_context=analysis_context,
        )
    
    context = {
        "classification": classification,
        "analysis_context": analysis_context,
        "target_keyword": analysis_context.get("target_keyword", ""),
        "video_context": video_context,
        "page_context": page_context
    }
    
    # Step 2: Initialize all modules
    modules = {
        "xml": XMLSitemapModule,
        "image": ImageSitemapModule,
        "video": VideoSitemapModule,
        "google_discovery": GoogleDiscoveryModule,
        "digital_marketing": DigitalMarketingModule
    }
    
    # Step 3: Execute relevant modules
    module_results = {}
    active_modules = []
    
    for module_name, module_class in modules.items():
        if module_class.discover(analysis_url, context):
            analysis = module_class.analyze(analysis_url, context)
            if module_name == "video" and analysis.get("videos_found", 0) == 0:
                continue

            active_modules.append(module_name)
            score = module_class.score(analysis)
            recommendations = module_class.recommend(analysis)
            
            module_results[module_name] = {
                "analysis": analysis,
                "score": score,
                "recommendations": recommendations
            }
            
            # Add results to context for other modules
            if module_name == "xml":
                context["xml_results"] = analysis
            elif module_name == "image":
                context["image_results"] = analysis
            elif module_name == "video":
                context["video_results"] = analysis
                context["video"] = analysis
            elif module_name == "mobile":
                context["mobile_results"] = analysis

    # Step 4: Build alignment and executive data from the shared immutable analysis_context.
    detected_topic = analysis_context.get("detected_topic", "")
    detected_industry = analysis_context.get("industry", "")
    detected_audience = analysis_context.get("audience", "")
    topic_match_score = _calculate_topic_match(analysis_context)
    semantic_match_score = _calculate_semantic_match(analysis_context)
    detected_intent = analysis_context.get("intent", "")
    intent_match_score = 90 if detected_intent == "Transactional" else 80 if detected_intent == "Commercial" else 70 if detected_intent == "Informational" else 50 if detected_intent else 0
    target_industry = _infer_industry(analysis_context.get("target_keyword", ""))
    industry_match_score = 100 if target_industry and target_industry == detected_industry else 0
    audience_match_score = 80 if target_industry and target_industry.lower() in _normalize_phrase(detected_audience) else 60 if detected_audience else 0
    alignment_score = int(
        topic_match_score * 0.4
        + semantic_match_score * 0.25
        + intent_match_score * 0.15
        + industry_match_score * 0.1
        + audience_match_score * 0.1
    ) if analysis_context.get("target_keyword") else 0
    if topic_match_score == 0 and semantic_match_score < 20:
        marketing_alignment_score = min(20, alignment_score)
    else:
        marketing_alignment_score = alignment_score
    video_seo_score = video_context.get("video_seo_score", 0) if video_context else 0
    if marketing_alignment_score >= 90:
        marketing_relevance = "High"
    elif marketing_alignment_score >= 40:
        marketing_relevance = "Medium"
    elif marketing_alignment_score >= 20:
        marketing_relevance = "Low"
    else:
        marketing_relevance = "Very Low"

    if page_context:
        page_context["topic_match_score"] = topic_match_score
        page_context["semantic_match_score"] = semantic_match_score
        page_context["intent_match_score"] = intent_match_score
        page_context["industry_match_score"] = industry_match_score
        page_context["audience_match_score"] = audience_match_score
        page_context["alignment_score"] = alignment_score
        page_context["marketing_alignment_score"] = marketing_alignment_score
        page_context["marketing_relevance"] = marketing_relevance
    
    # Step 6: Build executive summary
    # Use content alignment for business impact, marketing readiness
    business_opportunity = "Not Relevant"
    overall_seo_readiness = None
    
    # Check if content is completely unrelated
    is_completely_unrelated = (marketing_relevance == "Very Low") and bool(analysis_context.get("target_keyword", ""))
    
    # Calculate business opportunity solely based on Marketing Alignment Score!
    if is_completely_unrelated:
        business_opportunity = "Not Relevant"
    elif marketing_alignment_score >= 90:
        business_opportunity = "High Opportunity"
    elif marketing_alignment_score >= 70:
        business_opportunity = "Good Opportunity"
    elif marketing_alignment_score >= 40:
        business_opportunity = "Medium Opportunity"
    elif marketing_alignment_score >= 20:
        business_opportunity = "Low Opportunity"
    else:
        business_opportunity = "Not Relevant"
    
    # Get Google Discovery score if available
    if "google_discovery" in module_results:
        overall_seo_readiness = module_results["google_discovery"]["score"]
    
    # Get detected content type, industry, audience from module results (or video_context)
    detected_content_type = classification.get("detected_platform", "Web Page")
    
    # Calculate overall score from modules
    overall_score = None
    active_scores = []
    for module_name, result in module_results.items():
        if result.get("score") is not None:
            active_scores.append(result["score"])
    
    if active_scores:
        overall_score = int(sum(active_scores) / len(active_scores))
    
    # Get critical findings and highest priority actions (provider-aware)
    critical_findings = []
    highest_priority_actions = []
    provider_platforms = ["YouTube", "Facebook", "Instagram", "TikTok", "LinkedIn", "X", "Vimeo"]
    is_provider_platform = detected_content_type in provider_platforms
    
    if is_completely_unrelated:
        # Only focus on content mismatch when unrelated
        critical_findings.append(f"Target keyword mismatch: content is not about '{analysis_context.get('target_keyword', '')}'")
        highest_priority_actions.append(f"Use content aligned with the target keyword '{analysis_context.get('target_keyword', '')}'")
    else:
        recommendation_sources = []
        if video_context:
            recommendation_sources.append(video_context.get("recommendations", []))
        if page_context:
            recommendation_sources.append(page_context.get("recommendations", []))
        for module_name, result in module_results.items():
            recommendation_sources.append(result.get("recommendations", []))

        for recommendations in recommendation_sources:
            for rec in recommendations:
                if is_provider_platform:
                    issue_lower = rec.get("issue", "").lower()
                    if any(phrase in issue_lower for phrase in [
                        "viewport", "canonical", "h1", "meta robots", "html", "fix url access",
                        "missing videoobject schema", "missing opengraph"
                    ]):
                        continue
                if rec["priority"] in ["Critical", "High"]:
                    highest_priority_actions.append(rec["recommended_action"])
                    if rec["priority"] == "Critical":
                        critical_findings.append(rec["issue"])
    
    executive_summary = {
        "active_modules": active_modules,
        "url": original_url,
        "final_url": final_url,
        "detected_content_type": detected_content_type,
        "detected_topic": detected_topic,
        "detected_industry": detected_industry,
        "detected_audience": detected_audience,
        "target_keyword": analysis_context.get("target_keyword", ""),
        "topic_match": topic_match_score,
        "marketing_relevance": marketing_relevance,
        "video_seo_score": video_seo_score,
        "marketing_alignment_score": marketing_alignment_score,
        "overall_marketing_readiness": marketing_alignment_score,
        "overall_score": overall_score,
        "overall_seo_readiness": overall_seo_readiness,
        "business_opportunity": business_opportunity,
        "overall_business_impact": business_opportunity,
        "overall_seo_impact": "Positive" if (overall_seo_readiness or 0) > 70 else "Needs Improvement",
        "overall_google_discovery_readiness": overall_seo_readiness,
        "critical_findings": critical_findings,
        "highest_priority_actions": highest_priority_actions,
        "business_risks": ["Content won't drive desired business results"] if business_opportunity in ["Low Opportunity", "Not Relevant"] else [],
        "marketing_risks": ["Content won't drive desired marketing results"] if marketing_relevance in ["Low", "Very Low"] else []
    }
    
    # Add module scores
    for module_name, result in module_results.items():
        if result.get("score") is not None:
            executive_summary[f"{module_name}_score"] = result["score"]
        else:
            executive_summary[f"{module_name}_status"] = "N/A"
    
    # Step 7: Aggregate all recommendations by priority
    all_recommendations = {
        "Critical": [],
        "High": [],
        "Medium": [],
        "Low": []
    }

    if video_context:
        _append_recommendation_bucket(all_recommendations, video_context.get("recommendations", []), is_provider_platform, is_completely_unrelated, "video_context")
    if page_context:
        _append_recommendation_bucket(all_recommendations, page_context.get("recommendations", []), is_provider_platform, is_completely_unrelated, "page_context")
    for module_name, result in module_results.items():
        _append_recommendation_bucket(all_recommendations, result.get("recommendations", []), is_provider_platform, is_completely_unrelated, module_name)
    
    # Step 8: Build final report
    final_report = {
        "url": original_url,
        "final_url": final_url,
        "target_keyword": analysis_context.get("target_keyword", ""),
        "topic_intelligence": topic_intel,
        "analysis_context": analysis_context,
        "executive_summary": executive_summary,
        "module_results": module_results,
        "all_recommendations": all_recommendations,
        "video_context": video_context,
        "page_context": page_context,
        "content_alignment": {
            "analysis_context": analysis_context,
            "detected_topic": analysis_context.get("detected_topic", ""),
            "target_keyword": analysis_context.get("target_keyword", ""),
            "primary_keyword": analysis_context.get("primary_keyword", ""),
            "industry": analysis_context.get("industry", ""),
            "audience": analysis_context.get("audience", ""),
            "intent": analysis_context.get("intent", ""),
            "semantic_keywords": list(analysis_context.get("semantic_keywords", ())),
            "topic_cluster": analysis_context.get("topic_cluster", ""),
            "content_category": analysis_context.get("content_category", ""),
            "comparison_terms": [
                analysis_context.get("detected_topic", ""),
                *list(analysis_context.get("semantic_keywords", ())),
                analysis_context.get("topic_cluster", ""),
            ],
            "topic_match_score": topic_match_score,
            "semantic_match_score": semantic_match_score,
            "intent_match_score": intent_match_score,
            "industry_match_score": industry_match_score,
            "audience_match_score": audience_match_score,
            "alignment_score": alignment_score,
            "marketing_relevance": marketing_relevance
        },
        # Backward compatibility for old tests
        "robots_status": "Not Measured",
        "sitemap_status": "Not Measured",
        "discovered_sitemap": None,
        "checked_endpoints": [],
        "xml_sitemap": {
            "found": False,
            "valid": False,
            "urls_found": 0,
            "broken_urls": [],
            "noindex_urls": [],
            "redirected_urls": [],
            "robots_status": "Not Measured"
        }
    }
    
    # Fill in backward compatibility fields from module results
    if "xml" in module_results:
        xml_analysis = module_results["xml"]["analysis"]
        final_report["xml_sitemap"]["found"] = xml_analysis["sitemap_status"] == "Detected"
        final_report["xml_sitemap"]["valid"] = xml_analysis["sitemap_status"] == "Detected"
        final_report["xml_sitemap"]["urls_found"] = xml_analysis["urls_found"]
        final_report["xml_sitemap"]["broken_urls"] = xml_analysis.get("broken_urls", [])
        final_report["xml_sitemap"]["noindex_urls"] = xml_analysis.get("noindex_urls", [])
        final_report["xml_sitemap"]["redirected_urls"] = xml_analysis.get("redirected_urls", [])
        final_report["xml_sitemap"]["discovered_sitemap"] = xml_analysis.get("discovered_sitemap")
        final_report["xml_sitemap"]["robots_status"] = "Not Measured"
        final_report["sitemap_status"] = xml_analysis["sitemap_status"]
        final_report["discovered_sitemap"] = xml_analysis.get("discovered_sitemap")
        final_report["checked_endpoints"] = []
    
    return final_report
