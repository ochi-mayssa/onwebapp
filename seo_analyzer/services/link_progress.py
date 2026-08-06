from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from threading import Thread, local
from time import monotonic, time
from typing import Any
from uuid import uuid4

from django.core.cache import cache
from django.db import close_old_connections
from django.urls import reverse

from . import link_checker
from .backlink_engine import BacklinkAnalyzer
from .monitoring import record_link_snapshot
from .utils import classify_request_error, normalize_url

PROGRESS_TTL_SECONDS = 30 * 60

STAGE_PROGRESS = {
    "Preparing Analysis": 3,
    "Downloading HTML": 10,
    "Extracting Links": 18,
    "Deduplicating URLs": 30,
    "Checking Link Status": 35,
    "Analyzing Results": 84,
    "Generating AI Recommendations": 91,
    "Building Report": 97,
    "Completed": 100,
    "Fetching Backlink Data": 18,
    "Analysis Failed": 0,
}

DEFAULT_STAGE_PIPELINE = [
    "Preparing Analysis",
    "Downloading HTML",
    "Extracting Links",
    "Deduplicating URLs",
    "Checking Link Status",
    "Analyzing Results",
    "Generating AI Recommendations",
    "Building Report",
    "Completed",
]

BACKLINK_STAGE_PIPELINE = [
    "Preparing Analysis",
    "Fetching Backlink Data",
    "Checking Link Status",
    "Analyzing Results",
    "Generating AI Recommendations",
    "Building Report",
    "Completed",
]

_CACHE_PREFIX = 'link_progress:'
_PROGRESS_CONTEXT = local()
_HOOKS_INSTALLED = False


def _cache_key(task_id: str) -> str:
    return f'{_CACHE_PREFIX}{task_id}'


def start_link_analysis(url: str, analysis_type: str) -> str:
    install_progress_hooks()
    task_id = str(uuid4())
    normalized_url = normalize_url(url)
    now = time()
    stage_pipeline = (
        BACKLINK_STAGE_PIPELINE if analysis_type == "backlinks" else DEFAULT_STAGE_PIPELINE
    )

    progress_data = {
            "task_id": task_id,
            "url": normalized_url,
            "analysis_type": analysis_type,
            "status": "running",
            "stage": "Preparing Analysis",
            "stage_pipeline": stage_pipeline,
            "total_links_found": 0,
            "total_unique_urls": 0,
            "links_checked": 0,
            "broken_links_found": 0,
            "redirects_found": 0,
            "working_links_found": 0,
            "errors_found": 0,
            "duplicate_urls_skipped": 0,
            "percentage_completed": STAGE_PROGRESS["Preparing Analysis"],
            "started_at": now,
            "updated_at": now,
            "completed_at": None,
            "result_url": reverse("seo_analyzer:link_results", kwargs={"task_id": task_id}),
            "retry_url": reverse(
                "seo_analyzer:backlinks" if analysis_type == "backlinks" else "seo_analyzer:link_checker"
            ),
            "failure_reason": "",
            "report_data": None,
        }
    cache.set(_cache_key(task_id), progress_data, PROGRESS_TTL_SECONDS)

    Thread(
        target=_run_link_analysis,
        args=(task_id, normalized_url, analysis_type),
        daemon=True,
    ).start()
    return task_id


def get_link_progress(task_id: str) -> dict[str, Any] | None:
    progress = cache.get(_cache_key(str(task_id)))
    if not progress:
        return None

    now = time()
    started_at = progress.get("started_at") or now
    completed_at = progress.get("completed_at")
    finished_at = completed_at or now
    elapsed_seconds = max(0.0, finished_at - started_at)
    remaining_seconds = _estimate_remaining_seconds(progress, elapsed_seconds)

    progress["elapsed_time_seconds"] = round(elapsed_seconds, 2)
    progress["estimated_remaining_time_seconds"] = (
        round(remaining_seconds, 2) if remaining_seconds is not None else None
    )
    progress["is_complete"] = progress.get("status") == "completed"
    progress["is_failed"] = progress.get("status") == "failed"
    progress["links_checked_display"] = (
        f"{progress['links_checked']} / {progress['total_unique_urls']} Links Checked"
        if progress.get("total_unique_urls")
        else "Waiting for link inventory..."
    )
    progress["report_data"] = None
    return progress


def get_completed_link_report(task_id: str) -> dict[str, Any] | None:
    progress = cache.get(_cache_key(str(task_id)))
    if not progress or progress.get("status") != "completed":
        return None
    report = progress.get("report_data")
    return deepcopy(report) if report else None


def set_progress_stage(stage: str, **extra_fields: Any) -> None:
    task_id = getattr(_PROGRESS_CONTEXT, "task_id", None)
    if not task_id:
        return

    progress = cache.get(_cache_key(task_id))
    if not progress or progress.get("status") != "running":
        return
    progress["stage"] = stage
    progress["updated_at"] = time()
    progress.update(extra_fields)
    if stage == "Checking Link Status":
        progress["percentage_completed"] = _progress_for_checking(progress)
    else:
        progress["percentage_completed"] = STAGE_PROGRESS.get(
            stage,
            progress.get("percentage_completed", 0),
        )
    cache.set(_cache_key(task_id), progress, PROGRESS_TTL_SECONDS)


def set_candidate_link_counts(total_links_found: int, total_unique_urls: int, duplicate_urls_skipped: int) -> None:
    set_progress_stage(
        "Deduplicating URLs",
        total_links_found=total_links_found,
        total_unique_urls=total_unique_urls,
        duplicate_urls_skipped=duplicate_urls_skipped,
    )


def record_status_result(status_key: str) -> None:
    task_id = getattr(_PROGRESS_CONTEXT, "task_id", None)
    if not task_id:
        return

    progress = cache.get(_cache_key(task_id))
    if not progress or progress.get("status") != "running":
        return
    progress["stage"] = "Checking Link Status"
    progress["links_checked"] += 1
    if status_key == "working":
        progress["working_links_found"] += 1
    elif status_key == "broken":
        progress["broken_links_found"] += 1
    elif status_key == "redirect":
        progress["redirects_found"] += 1
    else:
        progress["errors_found"] += 1
    progress["percentage_completed"] = _progress_for_checking(progress)
    progress["updated_at"] = time()
    cache.set(_cache_key(task_id), progress, PROGRESS_TTL_SECONDS)


def reset_progress_store() -> None:
    cache.clear()


def install_progress_hooks() -> None:
    global _HOOKS_INSTALLED
    if _HOOKS_INSTALLED:
        return

    original_analyze_page_links = link_checker._analyze_page_links
    original_collect_candidate_links = link_checker._collect_candidate_links
    original_run_fast_link_checks = link_checker._run_fast_link_checks
    original_build_summary = link_checker._build_summary
    original_build_page_link_recommendations = link_checker._build_page_link_recommendations
    original_build_backlink_recommendations = link_checker._build_backlink_recommendations
    original_analyze_domain = BacklinkAnalyzer.analyze_domain
    original_verify_backlink_status = BacklinkAnalyzer.verify_backlink_status

    def wrapped_analyze_page_links(url: str, analysis_type: str) -> dict[str, Any]:
        set_progress_stage("Downloading HTML")
        return original_analyze_page_links(url, analysis_type)

    def wrapped_collect_candidate_links(*args, **kwargs):
        set_progress_stage("Extracting Links")
        candidate_links, collection_stats = original_collect_candidate_links(*args, **kwargs)
        set_candidate_link_counts(
            total_links_found=collection_stats["total_links_found"],
            total_unique_urls=len(candidate_links),
            duplicate_urls_skipped=collection_stats["duplicate_urls_skipped"],
        )
        return candidate_links, collection_stats

    def wrapped_run_fast_link_checks(urls: list[str], *, analysis_type: str):
        normalized_urls: list[str] = []
        seen_urls: set[str] = set()
        for url in urls:
            normalized = normalize_url(url)
            if normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            normalized_urls.append(normalized)

        set_progress_stage(
            "Checking Link Status",
            total_unique_urls=len(normalized_urls),
        )

        cache: dict[str, tuple[int | None, str, str | dict[str, Any]]] = {}
        if not normalized_urls:
            return cache

        session = link_checker._build_session()
        max_workers = min(link_checker.LINK_CHECK_MAX_WORKERS, len(normalized_urls))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(link_checker._check_url_status, session, checked_url): checked_url
                for checked_url in normalized_urls
            }
            for future in as_completed(future_map):
                checked_url = future_map[future]
                try:
                    cache[checked_url] = future.result()
                except Exception as exc:  # pragma: no cover - defensive guard
                    error_type, message = classify_request_error(exc)
                    cache[checked_url] = (None, "error", f"{error_type}: {message}")
                record_status_result(cache[checked_url][1])
        return cache

    def wrapped_build_summary(links):
        set_progress_stage("Analyzing Results")
        return original_build_summary(links)

    def wrapped_build_page_link_recommendations(*args, **kwargs):
        set_progress_stage("Generating AI Recommendations")
        return original_build_page_link_recommendations(*args, **kwargs)

    def wrapped_build_backlink_recommendations(*args, **kwargs):
        set_progress_stage("Generating AI Recommendations")
        return original_build_backlink_recommendations(*args, **kwargs)

    def wrapped_analyze_domain(self, domain: str):
        set_progress_stage("Fetching Backlink Data")
        report = original_analyze_domain(self, domain)
        backlinks = report.get("backlinks", [])
        set_progress_stage(
            "Checking Link Status",
            total_links_found=len(backlinks),
            total_unique_urls=len(backlinks),
            duplicate_urls_skipped=0,
        )
        return report

    def wrapped_verify_backlink_status(self, backlink_data: dict[str, Any]):
        result = original_verify_backlink_status(self, backlink_data)
        status_key, _status_detail = link_checker._map_backlink_status(
            result.get("verification_status", ""),
            result.get("http_status"),
        )
        record_status_result(status_key)
        return result

    link_checker._analyze_page_links = wrapped_analyze_page_links
    link_checker._collect_candidate_links = wrapped_collect_candidate_links
    link_checker._run_fast_link_checks = wrapped_run_fast_link_checks
    link_checker._build_summary = wrapped_build_summary
    link_checker._build_page_link_recommendations = wrapped_build_page_link_recommendations
    link_checker._build_backlink_recommendations = wrapped_build_backlink_recommendations
    BacklinkAnalyzer.analyze_domain = wrapped_analyze_domain
    BacklinkAnalyzer.verify_backlink_status = wrapped_verify_backlink_status
    _HOOKS_INSTALLED = True


def _run_link_analysis(task_id: str, url: str, analysis_type: str) -> None:
    close_old_connections()
    _PROGRESS_CONTEXT.task_id = task_id
    try:
        set_progress_stage("Preparing Analysis")
        report_data = link_checker.analyze_links(url, analysis_type)
        report_data["task_id"] = task_id
        set_progress_stage("Building Report")
        try:
            record_link_snapshot(report_data)
        except Exception:
            # Monitoring must never block the primary report flow.
            pass
        progress = cache.get(_cache_key(task_id))
        if progress:
            progress["status"] = "completed"
            progress["stage"] = "Completed"
            progress["percentage_completed"] = 100
            progress["updated_at"] = time()
            progress["completed_at"] = time()
            progress["report_data"] = report_data
            cache.set(_cache_key(task_id), progress, PROGRESS_TTL_SECONDS)
    except Exception as exc:  # pragma: no cover - defensive guard
        progress = cache.get(_cache_key(task_id))
        if progress:
            progress["status"] = "failed"
            progress["stage"] = "Analysis Failed"
            progress["failure_reason"] = str(exc) or "Unexpected analysis error."
            progress["updated_at"] = time()
            progress["completed_at"] = time()
            cache.set(_cache_key(task_id), progress, PROGRESS_TTL_SECONDS)
    finally:
        _PROGRESS_CONTEXT.task_id = None
        close_old_connections()


def _progress_for_checking(progress: dict[str, Any]) -> int:
    total = progress.get("total_unique_urls", 0) or 0
    checked = progress.get("links_checked", 0) or 0
    if total <= 0:
        return STAGE_PROGRESS["Checking Link Status"]
    completed_ratio = min(1.0, checked / total)
    return min(96, STAGE_PROGRESS["Checking Link Status"] + int(completed_ratio * 45))


def _estimate_remaining_seconds(progress: dict[str, Any], elapsed_seconds: float) -> float | None:
    status = progress.get("status")
    if status == "completed":
        return 0.0
    if status == "failed":
        return None

    total_unique_urls = progress.get("total_unique_urls", 0) or 0
    links_checked = progress.get("links_checked", 0) or 0
    if total_unique_urls > 0 and links_checked > 0:
        rate = links_checked / max(elapsed_seconds, 0.1)
        remaining = max(total_unique_urls - links_checked, 0) / max(rate, 0.1)
        return remaining

    percentage = progress.get("percentage_completed", 0) or 0
    if percentage > 0:
        estimated_total = elapsed_seconds / (percentage / 100)
        return max(estimated_total - elapsed_seconds, 0.0)
    return None
