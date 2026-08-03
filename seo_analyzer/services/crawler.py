import logging
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import requests
from bs4 import BeautifulSoup, FeatureNotFound
from urllib.parse import urljoin
from .utils import (
    DEFAULT_REQUEST_TIMEOUT,
    build_http_session,
    classify_request_exception,
    clean_text,
    dns_cache_context,
    extract_domain,
    is_internal_url,
    normalize_url,
)
from django.utils import timezone
from ..models import SEOPageAudit

logger = logging.getLogger(__name__)
_HTML_PARSER = "lxml"
_CRAWL_EXTRACTION_WORKERS = 4
_CRAWL_FETCH_WORKERS = 8
_SITEMAP_FETCH_WORKERS = 4


class _CrawlProfiler:
    def __init__(self):
        self.started_at = time.perf_counter()
        self.stage_totals = defaultdict(float)
        self.requests_performed = 0
        self.cached_requests_reused = 0
        self.dns_lookups = 0
        self.dns_cache_hits = 0
        self._lock = threading.Lock()

    def add(self, stage: str, elapsed: float) -> None:
        with self._lock:
            self.stage_totals[stage] += max(elapsed, 0.0)

    def request_made(self) -> None:
        with self._lock:
            self.requests_performed += 1

    def cache_hit(self) -> None:
        with self._lock:
            self.cached_requests_reused += 1

    def dns_lookup(self, elapsed: float) -> None:
        with self._lock:
            self.dns_lookups += 1
            self.stage_totals["dns_resolution"] += max(elapsed, 0.0)

    def dns_cache_hit(self) -> None:
        with self._lock:
            self.dns_cache_hits += 1

    def total_elapsed(self) -> float:
        return time.perf_counter() - self.started_at

    def report(self) -> dict:
        with self._lock:
            stage_timings = {
                key: round(value, 4)
                for key, value in sorted(
                    self.stage_totals.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            }
            requests_performed = self.requests_performed
            cached_requests_reused = self.cached_requests_reused
            dns_lookups = self.dns_lookups
            dns_cache_hits = self.dns_cache_hits
        return {
            "total_execution_time": round(self.total_elapsed(), 4),
            "network_time": round(stage_timings.get("download_html", 0.0) + stage_timings.get("dns_resolution", 0.0), 4),
            "download_time": stage_timings.get("download_html", 0.0),
            "dns_time": stage_timings.get("dns_resolution", 0.0),
            "html_parsing_time": stage_timings.get("parse_html", 0.0),
            "stage_timings": stage_timings,
            "requests_performed": requests_performed,
            "cached_requests_reused": cached_requests_reused,
            "dns_lookups": dns_lookups,
            "dns_cache_hits": dns_cache_hits,
        }


class _CrawlRuntime:
    def __init__(self):
        self.session = build_http_session()
        self.request_cache: dict[tuple[str, str, bool], requests.Response] = {}
        self.request_validators: dict[str, dict[str, str]] = {}
        self.html_cache: dict[str, bytes] = {}
        self.soup_cache: dict[str, BeautifulSoup] = {}
        self.headers_cache: dict[str, dict] = {}
        self.status_cache: dict[str, int] = {}
        self._inflight_requests: dict[tuple[str, str, bool], threading.Event] = {}
        self._lock = threading.RLock()
        self.profiler = _CrawlProfiler()

    def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        allow_redirects: bool = True,
        conditional: bool = True,
    ) -> tuple[requests.Response, float]:
        normalized = normalize_url(url)
        cache_key = (method.upper(), normalized, allow_redirects)
        while True:
            with self._lock:
                cached = self.request_cache.get(cache_key)
                if cached is not None:
                    self.profiler.cache_hit()
                    return cached, 0.0
                inflight = self._inflight_requests.get(cache_key)
                if inflight is None:
                    inflight = threading.Event()
                    self._inflight_requests[cache_key] = inflight
                    break
            inflight.wait()

        started_at = time.perf_counter()
        request_headers = {}
        if conditional:
            validators = self.request_validators.get(normalized, {})
            if validators.get("etag"):
                request_headers["If-None-Match"] = validators["etag"]
            if validators.get("last_modified"):
                request_headers["If-Modified-Since"] = validators["last_modified"]
        try:
            response = self.session.request(
                method=method.upper(),
                url=normalized,
                timeout=DEFAULT_REQUEST_TIMEOUT,
                allow_redirects=allow_redirects,
                headers=request_headers or None,
            )
            elapsed = time.perf_counter() - started_at
            self.profiler.request_made()

            if response.status_code == 304:
                with self._lock:
                    cached_response = self.request_cache.get(cache_key)
                if cached_response is not None:
                    self.profiler.cache_hit()
                    return cached_response, elapsed

            final_url = normalize_url(response.url)
            validator_data = {
                "etag": response.headers.get("ETag", ""),
                "last_modified": response.headers.get("Last-Modified", ""),
                "cache_control": response.headers.get("Cache-Control", ""),
            }
            with self._lock:
                self.request_cache[cache_key] = response
                self.request_validators[normalized] = validator_data
                self.request_validators[final_url] = validator_data
                self.html_cache[final_url] = response.content
                self.headers_cache[final_url] = dict(response.headers)
                self.status_cache[final_url] = response.status_code
            return response, elapsed
        finally:
            with self._lock:
                inflight = self._inflight_requests.pop(cache_key, None)
                if inflight is not None:
                    inflight.set()

    def get_soup(self, final_url: str, html_bytes: bytes) -> BeautifulSoup:
        normalized = normalize_url(final_url)
        with self._lock:
            cached = self.soup_cache.get(normalized)
            if cached is not None:
                return cached
        try:
            soup = BeautifulSoup(html_bytes, _HTML_PARSER)
        except FeatureNotFound:
            soup = BeautifulSoup(html_bytes, "html.parser")
        with self._lock:
            self.soup_cache[normalized] = soup
        return soup


def _extract_metadata(soup: BeautifulSoup) -> tuple[dict, dict[str, float]]:
    started_at = time.perf_counter()
    data = {}
    title_tag = soup.title
    if title_tag and title_tag.string:
        data["title_tag"] = clean_text(title_tag.string)
        data["title_tag_length"] = len(data["title_tag"])
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    if meta_desc_tag and meta_desc_tag.get("content"):
        data["meta_description"] = clean_text(meta_desc_tag["content"])
        data["meta_description_length"] = len(data["meta_description"])
    return data, {"extract_metadata": time.perf_counter() - started_at}


def _extract_headings(soup: BeautifulSoup) -> tuple[dict, dict[str, float]]:
    started_at = time.perf_counter()
    data = {}
    h1_tags = soup.find_all("h1")
    data["h1_count"] = len(h1_tags)
    if h1_tags and h1_tags[0].get_text(strip=True):
        data["h1_text"] = clean_text(h1_tags[0].get_text())
    h2_tags = soup.find_all("h2")
    data["h2_count"] = len(h2_tags)
    visible_text = soup.get_text(separator=" ")
    words = [word for word in visible_text.split() if word]
    data["word_count"] = len(words)
    return data, {"analyze_headings": time.perf_counter() - started_at}


def _extract_canonical_and_robots(soup: BeautifulSoup, base_url: str) -> tuple[dict, dict[str, float]]:
    canonical_started_at = time.perf_counter()
    data = {}
    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    if canonical_tag and canonical_tag.get("href"):
        data["has_canonical"] = True
        data["canonical_url"] = normalize_url(urljoin(base_url, canonical_tag["href"]))
    canonical_elapsed = time.perf_counter() - canonical_started_at

    robots_started_at = time.perf_counter()
    meta_robots_tag = soup.find("meta", attrs={"name": "robots"})
    if meta_robots_tag:
        content = meta_robots_tag.get("content", "").lower()
        if "noindex" in content:
            data["is_noindex"] = True
    robots_elapsed = time.perf_counter() - robots_started_at
    return data, {
        "canonical_analysis": canonical_elapsed,
        "robots_analysis": robots_elapsed,
    }


def _extract_videos(soup: BeautifulSoup, base_url: str) -> tuple[dict, dict[str, float]]:
    started_at = time.perf_counter()
    videos = []
    
    # Extract native <video> tags
    for video in soup.find_all("video"):
        src = video.get("src", "")
        poster = video.get("poster", "")
        videos.append({
            "type": "native",
            "src": urljoin(base_url, src) if src else "",
            "poster": urljoin(base_url, poster) if poster else "",
            "width": video.get("width", ""),
            "height": video.get("height", ""),
            "controls": video.has_attr("controls"),
        })
    
    # Extract YouTube/Vimeo embeds
    for iframe in soup.find_all("iframe", src=True):
        src = iframe["src"]
        if "youtube.com" in src or "youtu.be" in src or "vimeo.com" in src:
            videos.append({
                "type": "iframe",
                "src": src,
                "width": iframe.get("width", ""),
                "height": iframe.get("height", ""),
            })
    
    # Check for VideoObject schema
    has_video_schema = False
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json
            schema_data = json.loads(script.string)
            if isinstance(schema_data, list):
                for item in schema_data:
                    if item.get("@type") == "VideoObject":
                        has_video_schema = True
            elif schema_data.get("@type") == "VideoObject":
                has_video_schema = True
        except:
            continue
    
    return {
        "videos_count": len(videos),
        "videos_details": videos,
        "has_video_schema": has_video_schema,
    }, {"videos": time.perf_counter() - started_at}


def _extract_images(soup: BeautifulSoup, base_url: str) -> tuple[dict, dict[str, float]]:
    started_at = time.perf_counter()
    images = soup.find_all("img")
    missing_alt = 0
    images_details = []
    
    for img in images:
        src = img.get("src", "")
        absolute_src = urljoin(base_url, src) if src else ""
        alt = img.get("alt", "").strip()
        title = img.get("title", "").strip()
        caption = ""
        # Try to find caption in figure
        parent_figure = img.find_parent("figure")
        if parent_figure:
            figcaption = parent_figure.find("figcaption")
            if figcaption:
                caption = clean_text(figcaption.get_text())
        loading_attr = img.get("loading", "")
        
        if not alt:
            missing_alt += 1
            
        images_details.append({
            "src": absolute_src,
            "alt": alt,
            "title": title,
            "caption": caption,
            "loading": loading_attr,
            "width": img.get("width", ""),
            "height": img.get("height", ""),
        })
        
    return {
        "images_count": len(images),
        "images_missing_alt": missing_alt,
        "images_details": images_details,
    }, {"images": time.perf_counter() - started_at}


def _extract_links(soup: BeautifulSoup, base_url: str, base_domain: str) -> tuple[dict, dict[str, float], list[str]]:
    started_at = time.perf_counter()
    discovered_internal_links = set()
    external_links_count = 0
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute_url = normalize_url(urljoin(base_url, href))
        if is_internal_url(absolute_url, base_domain):
            discovered_internal_links.add(absolute_url)
        else:
            external_links_count += 1
    elapsed = time.perf_counter() - started_at
    return (
        {
            "broken_internal_links_count": 0,
        },
        {
            "internal_links": elapsed,
            "external_links": 0.0,
        },
        sorted(discovered_internal_links),
    )


def _inspect_optional_markups(soup: BeautifulSoup, headers: dict) -> dict[str, float]:
    structured_started_at = time.perf_counter()
    soup.find_all("script", attrs={"type": "application/ld+json"})
    structured_elapsed = time.perf_counter() - structured_started_at

    open_graph_started_at = time.perf_counter()
    soup.find_all("meta", attrs={"property": lambda value: value and value.startswith("og:")})
    open_graph_elapsed = time.perf_counter() - open_graph_started_at

    twitter_started_at = time.perf_counter()
    soup.find_all("meta", attrs={"name": lambda value: value and value.startswith("twitter:")})
    twitter_elapsed = time.perf_counter() - twitter_started_at

    security_started_at = time.perf_counter()
    for header_name in ["Content-Security-Policy", "X-Frame-Options", "Strict-Transport-Security"]:
        headers.get(header_name)
    security_elapsed = time.perf_counter() - security_started_at

    performance_started_at = time.perf_counter()
    headers.get("Content-Length")
    performance_elapsed = time.perf_counter() - performance_started_at

    return {
        "structured_data": structured_elapsed,
        "open_graph": open_graph_elapsed,
        "twitter_cards": twitter_elapsed,
        "security_headers": security_elapsed,
        "performance_metrics": performance_elapsed,
    }


def _parse_sitemap_document(content: bytes) -> tuple[set[str], set[str]]:
    soup = BeautifulSoup(content, "xml")
    nested_sitemaps = set()
    page_urls = set()

    if soup.find("sitemapindex"):
        for sitemap_tag in soup.find_all("sitemap"):
            loc_tag = sitemap_tag.find("loc")
            if loc_tag and loc_tag.text:
                nested_sitemaps.add(normalize_url(loc_tag.text.strip()))
    else:
        for url_tag in soup.find_all("url"):
            loc_tag = url_tag.find("loc")
            if loc_tag and loc_tag.text:
                page_urls.add(normalize_url(loc_tag.text.strip()))

    return nested_sitemaps, page_urls


def _fetch_sitemap_details(runtime: _CrawlRuntime, sitemap_url: str) -> dict:
    normalized_url = normalize_url(sitemap_url)
    started_at = time.perf_counter()
    try:
        response, fetch_elapsed = runtime.fetch(normalized_url)
        nested_sitemaps = set()
        page_urls = set()
        if response.status_code == 200:
            nested_sitemaps, page_urls = _parse_sitemap_document(response.content)
        return {
            "sitemap_url": normalized_url,
            "fetch_elapsed": fetch_elapsed,
            "elapsed": time.perf_counter() - started_at,
            "status_code": response.status_code,
            "nested_sitemaps": nested_sitemaps,
            "page_urls": page_urls,
            "error": None,
        }
    except Exception as exc:
        return {
            "sitemap_url": normalized_url,
            "fetch_elapsed": 0.0,
            "elapsed": time.perf_counter() - started_at,
            "status_code": None,
            "nested_sitemaps": set(),
            "page_urls": set(),
            "error": exc,
        }


def _fetch_page_payload(
    runtime: _CrawlRuntime,
    current_url: str,
    base_url: str,
    base_domain: str,
    has_robots: bool,
    has_sitemap: bool,
) -> dict:
    try:
        response, request_elapsed = runtime.fetch(current_url)
        runtime.profiler.add("download_html", request_elapsed)
        response_time = request_elapsed
        final_url = normalize_url(response.url)
        status_code = response.status_code
        page_size = len(response.content)

        page_data = {
            "url": current_url,
            "final_url": final_url,
            "status_code": status_code,
            "response_time": response_time,
            "page_size": page_size,
            "has_robots": has_robots,
            "has_sitemap": has_sitemap,
            "internal_links_count": 0,
        }
        discovered_links = []

        if status_code == 200 and "text/html" in response.headers.get("Content-Type", ""):
            parse_started_at = time.perf_counter()
            soup = runtime.get_soup(final_url, response.content)
            runtime.profiler.add("parse_html", time.perf_counter() - parse_started_at)
            headers = runtime.headers_cache.get(final_url, dict(response.headers))

            with ThreadPoolExecutor(max_workers=_CRAWL_EXTRACTION_WORKERS) as executor:
                metadata_future = executor.submit(_extract_metadata, soup)
                headings_future = executor.submit(_extract_headings, soup)
                canonical_future = executor.submit(_extract_canonical_and_robots, soup, base_url)
                images_future = executor.submit(_extract_images, soup, base_url)
                videos_future = executor.submit(_extract_videos, soup, base_url)
                links_future = executor.submit(_extract_links, soup, base_url, base_domain)
                optional_future = executor.submit(_inspect_optional_markups, soup, headers)

                metadata_data, metadata_timings = metadata_future.result()
                headings_data, headings_timings = headings_future.result()
                canonical_data, canonical_timings = canonical_future.result()
                images_data, images_timings = images_future.result()
                videos_data, videos_timings = videos_future.result()
                links_data, links_timings, discovered_links = links_future.result()
                optional_timings = optional_future.result()

            page_data.update(metadata_data)
            page_data.update(headings_data)
            page_data.update(canonical_data)
            page_data.update(images_data)
            page_data.update(videos_data)
            page_data.update(links_data)

            for timing_group in [
                metadata_timings,
                headings_timings,
                canonical_timings,
                images_timings,
                videos_timings,
                links_timings,
                optional_timings,
            ]:
                for stage_name, elapsed in timing_group.items():
                    runtime.profiler.add(stage_name, elapsed)

        return {
            "success": True,
            "url": current_url,
            "page_data": page_data,
            "discovered_links": discovered_links,
            "error": None,
        }
    except Exception as exc:
        return {
            "success": False,
            "url": current_url,
            "page_data": None,
            "discovered_links": [],
            "error": exc,
        }


def _save_page_audit(task, page_data: dict) -> SEOPageAudit:
    payload = {"task": task, **page_data}
    page_audit, created = SEOPageAudit.objects.get_or_create(
        task=task,
        final_url=payload["final_url"],
        defaults=payload,
    )
    if not created:
        for key, value in payload.items():
            setattr(page_audit, key, value)
        page_audit.save()
    return page_audit


def _enqueue_discovered_links(
    discovered_links: list[str],
    crawled_urls: set[str],
    queued_urls: set[str],
    frontier: deque,
    next_discovery_order: int,
) -> tuple[int, int]:
    new_links_count = 0
    for discovered_link in discovered_links:
        if discovered_link in crawled_urls or discovered_link in queued_urls:
            continue
        queued_urls.add(discovered_link)
        frontier.append((next_discovery_order, discovered_link))
        next_discovery_order += 1
        new_links_count += 1
    return next_discovery_order, new_links_count


def crawl(task):
    """Crawl a website starting from task.url"""
    crawl_started_at = time.perf_counter()
    base_url = normalize_url(task.url)
    base_domain = extract_domain(base_url)
    crawled_urls = set()
    queued_urls = set()
    sitemap_entries = set()
    has_robots = False
    has_sitemap = False
    pages_crawled = 0
    root_error = None
    root_error_type = None
    runtime = _CrawlRuntime()
    root_page = None

    task.status = "running"
    task.started_at = timezone.now()
    task.save()

    with dns_cache_context(runtime.profiler.dns_lookup, runtime.profiler.dns_cache_hit):
        robots_url = urljoin(base_url, "/robots.txt")
        try:
            robots_response, robots_fetch_elapsed = runtime.fetch(robots_url)
            runtime.profiler.add("download_html", robots_fetch_elapsed)
            robots_started_at = time.perf_counter()
            if robots_response.status_code == 200:
                has_robots = True
                for line in robots_response.text.splitlines():
                    line = line.strip().lower()
                    if line.startswith("sitemap:"):
                        sitemap_url = line.split(":", 1)[1].strip()
                        sitemap_entries.add(normalize_url(sitemap_url))
            runtime.profiler.add("robots_analysis", time.perf_counter() - robots_started_at)
        except Exception as e:
            print(f"Error checking robots.txt: {e}")

        if not sitemap_entries:
            for sitemap_path in ["/sitemap.xml", "/sitemap_index.xml"]:
                sitemap_url = urljoin(base_url, sitemap_path)
                try:
                    sitemap_response, sitemap_fetch_elapsed = runtime.fetch(sitemap_url)
                    runtime.profiler.add("download_html", sitemap_fetch_elapsed)
                    sitemap_started_at = time.perf_counter()
                    if sitemap_response.status_code == 200 and "xml" in sitemap_response.headers.get("Content-Type", ""):
                        has_sitemap = True
                        sitemap_entries.add(normalize_url(sitemap_url))
                        runtime.profiler.add("robots_analysis", time.perf_counter() - sitemap_started_at)
                        break
                    runtime.profiler.add("robots_analysis", time.perf_counter() - sitemap_started_at)
                except Exception as e:
                    print(f"Error checking {sitemap_path}: {e}")

        pending_sitemap_urls = set(sitemap_entries)
        seen_sitemap_urls = set(sitemap_entries)
        while pending_sitemap_urls:
            sitemap_batch = sorted(pending_sitemap_urls)
            pending_sitemap_urls = set()
            max_workers = min(_SITEMAP_FETCH_WORKERS, len(sitemap_batch))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(_fetch_sitemap_details, runtime, sitemap_url)
                    for sitemap_url in sitemap_batch
                ]
                for future in futures:
                    sitemap_result = future.result()
                    runtime.profiler.add("download_html", sitemap_result["fetch_elapsed"])
                    runtime.profiler.add("robots_analysis", sitemap_result["elapsed"] - sitemap_result["fetch_elapsed"])
                    if sitemap_result["error"] is not None:
                        print(f"Error parsing sitemap {sitemap_result['sitemap_url']}: {sitemap_result['error']}")
                        continue
                    if sitemap_result["status_code"] != 200:
                        continue
                    sitemap_entries.update(sitemap_result["page_urls"])
                    for nested_sitemap in sitemap_result["nested_sitemaps"]:
                        if nested_sitemap not in seen_sitemap_urls:
                            seen_sitemap_urls.add(nested_sitemap)
                            sitemap_entries.add(nested_sitemap)
                            pending_sitemap_urls.add(nested_sitemap)

        frontier = deque()
        next_discovery_order = 2

        pages_crawled = 1
        print(f"Crawling {base_url} ({pages_crawled}/{task.max_pages})")
        root_result = _fetch_page_payload(
            runtime,
            base_url,
            base_url,
            base_domain,
            has_robots,
            has_sitemap,
        )
        crawled_urls.add(base_url)
        if root_result["success"]:
            next_discovery_order, new_links_count = _enqueue_discovered_links(
                root_result["discovered_links"],
                crawled_urls,
                queued_urls,
                frontier,
                next_discovery_order,
            )
            root_result["page_data"]["internal_links_count"] = new_links_count
            root_page = _save_page_audit(task, root_result["page_data"])
        else:
            print(f"Error crawling {base_url}: {root_result['error']}")
            root_error_type, root_error = classify_request_exception(root_result["error"])

        completed_results: dict[int, dict] = {}
        in_flight: dict = {}
        next_finalize_order = 2

        with ThreadPoolExecutor(max_workers=_CRAWL_FETCH_WORKERS) as executor:
            while pages_crawled < task.max_pages and (frontier or in_flight):
                while (
                    frontier
                    and len(in_flight) < _CRAWL_FETCH_WORKERS
                    and pages_crawled + len(in_flight) < task.max_pages
                ):
                    crawl_order, current_url = frontier.popleft()
                    in_flight[
                        executor.submit(
                            _fetch_page_payload,
                            runtime,
                            current_url,
                            base_url,
                            base_domain,
                            has_robots,
                            has_sitemap,
                        )
                    ] = crawl_order

                if not in_flight:
                    break

                done_futures, _ = wait(in_flight.keys(), return_when=FIRST_COMPLETED)
                for future in done_futures:
                    crawl_order = in_flight.pop(future)
                    completed_results[crawl_order] = future.result()

                while (
                    next_finalize_order in completed_results
                    and pages_crawled < task.max_pages
                ):
                    page_result = completed_results.pop(next_finalize_order)
                    current_url = normalize_url(page_result["url"])
                    queued_urls.discard(current_url)
                    crawled_urls.add(current_url)
                    pages_crawled += 1
                    print(f"Crawling {current_url} ({pages_crawled}/{task.max_pages})")

                    if page_result["success"]:
                        next_discovery_order, new_links_count = _enqueue_discovered_links(
                            page_result["discovered_links"],
                            crawled_urls,
                            queued_urls,
                            frontier,
                            next_discovery_order,
                        )
                        page_result["page_data"]["internal_links_count"] = new_links_count
                        _save_page_audit(task, page_result["page_data"])
                    else:
                        print(f"Error crawling {current_url}: {page_result['error']}")
                    next_finalize_order += 1

    runtime.profiler.add("crawl_pages", time.perf_counter() - crawl_started_at)
    crawl_succeeded = root_page is not None
    task.status = "completed" if crawl_succeeded else "failed"
    task.completed_at = timezone.now()
    task.error_message = None if crawl_succeeded else (root_error or "The website could not be reached.")
    task.save()

    timing_report = runtime.profiler.report()
    logger.info(
        "Website crawler timing report for %s: total=%ss pages=%s requests=%s cache_hits=%s stages=%s",
        task.url,
        timing_report["total_execution_time"],
        pages_crawled,
        timing_report["requests_performed"],
        timing_report["cached_requests_reused"],
        timing_report["stage_timings"],
    )

    return {
        "root_page": root_page,
        "crawl_succeeded": crawl_succeeded,
        "error_type": root_error_type,
        "root_error": root_error,
        "pages_crawled": pages_crawled,
        "sitemap_entries": sitemap_entries,
        "has_robots": has_robots,
        "has_sitemap": has_sitemap,
        "performance_report": timing_report,
    }
