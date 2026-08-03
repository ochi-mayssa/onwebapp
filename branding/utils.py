"""Cache utilities for the Branding Service app.

Provides key builders, get/set helpers, and invalidation functions.
Uses Django's low-level cache API (LocMem or Redis depending on settings).
"""
from django.core.cache import cache

# ---------------------------------------------------------------------------
# Timeouts (seconds)
# ---------------------------------------------------------------------------
TIMEOUT_DASHBOARD = 5 * 60       # 5 minutes
TIMEOUT_KANBAN = 5 * 60          # 5 minutes
TIMEOUT_COLLECTIONS = 60 * 60    # 1 hour
TIMEOUT_DESIGNERS = 60 * 60      # 1 hour


# ---------------------------------------------------------------------------
# Key builders
# ---------------------------------------------------------------------------

def _prefix(namespace):
    return f'branding:{namespace}'


def dashboard_stats_key(user_id):
    """Per-user dashboard stats (counts + avg completion time)."""
    return _prefix(f'dash:stats:{user_id}')


def dashboard_query_key(user_id, page):
    """Per-user + page filtered queryset cache key."""
    return _prefix(f'dash:query:{user_id}:p{page}')


def kanban_key():
    """Kanban board columns (shared across staff)."""
    return _prefix('kanban:columns')


def collections_key():
    """Active collection list (shared, changes rarely)."""
    return _prefix('collections:active')


def designers_key():
    """Staff designers list."""
    return _prefix('designers:list')


def feedback_stats_key():
    """Aggregate feedback stats (avg rating, total, recommend count)."""
    return _prefix('feedback:stats')


def designer_detail_key(user_id):
    """Supervisor designer detail metrics."""
    return _prefix(f'supervisor:designer:{user_id}')


def team_overview_key():
    """Supervisor team overview metrics."""
    return _prefix('supervisor:team')


# ---------------------------------------------------------------------------
# Get / Set helpers
# ---------------------------------------------------------------------------

def cache_get(key, default=None):
    """Retrieve a value from the cache, returning *default* on miss."""
    return cache.get(key, default)


def cache_set(key, value, timeout=None):
    """Store a value in the cache with an optional timeout override."""
    cache.set(key, value, timeout)


def cache_get_or_set(key, callable_fn, timeout=None):
    """Return cached value or compute it, store, and return."""
    value = cache.get(key)
    if value is None:
        value = callable_fn()
        cache.set(key, value, timeout)
    return value


# ---------------------------------------------------------------------------
# Invalidation — Dashboard
# ---------------------------------------------------------------------------

def invalidate_dashboard(user_id=None):
    """Clear dashboard cache for a specific user or all staff.

    When *user_id* is given, only that user's cache is purged.
    Pass None to purge every user's dashboard (used on global mutations).
    """
    if user_id is not None:
        cache.delete(dashboard_stats_key(user_id))
    else:
        # Brute-force: delete known keys is impossible with LocMem.
        # With Redis we can use delete_pattern; with LocMem we clear all.
        cache.clear()


def invalidate_all_dashboards():
    """Nuclear option: flush the entire cache (safe for LocMem)."""
    cache.clear()


# ---------------------------------------------------------------------------
# Invalidation — Kanban
# ---------------------------------------------------------------------------

def invalidate_kanban():
    """Remove the cached kanban board."""
    cache.delete(kanban_key())


# ---------------------------------------------------------------------------
# Invalidation — Collections
# ---------------------------------------------------------------------------

def invalidate_collections():
    """Remove the cached active collection list."""
    cache.delete(collections_key())


# ---------------------------------------------------------------------------
# Invalidation — Designers
# ---------------------------------------------------------------------------

def invalidate_designers():
    """Remove the cached designers list."""
    cache.delete(designers_key())


# ---------------------------------------------------------------------------
# Invalidation — Feedback
# ---------------------------------------------------------------------------

def invalidate_feedback_stats():
    """Remove the cached feedback aggregate stats."""
    cache.delete(feedback_stats_key())


def invalidate_designer_detail(user_id):
    """Remove cached supervisor designer detail."""
    cache.delete(designer_detail_key(user_id))


def invalidate_team_overview():
    """Remove cached supervisor team overview."""
    cache.delete(team_overview_key())


# ---------------------------------------------------------------------------
# Composite invalidation (call from status-change / mutation views)
# ---------------------------------------------------------------------------

def invalidate_after_status_change(user_id=None):
    """Call after any status change to keep dashboards + kanban fresh."""
    invalidate_dashboard(user_id)
    invalidate_kanban()
    invalidate_feedback_stats()


def invalidate_after_request_mutation():
    """Call after broader mutations (new request, designer assignment, etc.)."""
    invalidate_all_dashboards()
    invalidate_kanban()
    invalidate_designers()
    invalidate_team_overview()
