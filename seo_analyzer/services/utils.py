import re
import socket
import threading
import time
from contextlib import contextmanager
from functools import lru_cache
from urllib.parse import urlparse, urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_REQUEST_TIMEOUT = 15
MAX_REQUEST_REDIRECTS = 5
DEFAULT_POOL_CONNECTIONS = 32
DEFAULT_POOL_MAXSIZE = 32
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def build_http_session(*, pool_connections=DEFAULT_POOL_CONNECTIONS, pool_maxsize=DEFAULT_POOL_MAXSIZE):
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": DEFAULT_USER_AGENT,
            "Connection": "keep-alive",
        }
    )
    session.max_redirects = MAX_REQUEST_REDIRECTS
    retry_strategy = Retry(
        total=0,
        connect=0,
        read=0,
        redirect=MAX_REQUEST_REDIRECTS,
        status=0,
        backoff_factor=0,
        raise_on_redirect=False,
        raise_on_status=False,
        allowed_methods=frozenset(["GET", "HEAD"]),
    )
    adapter = HTTPAdapter(
        pool_connections=pool_connections,
        pool_maxsize=pool_maxsize,
        max_retries=retry_strategy,
        pool_block=True,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


@contextmanager
def dns_cache_context(on_lookup=None, on_cache_hit=None):
    original_getaddrinfo = socket.getaddrinfo

    @lru_cache(maxsize=256)
    def cached_getaddrinfo(*args, **kwargs):
        started_at = time.perf_counter()
        result = original_getaddrinfo(*args, **kwargs)
        elapsed = time.perf_counter() - started_at
        if on_lookup is not None:
            on_lookup(elapsed)
        return result

    cache_lock = threading.Lock()

    def cached_wrapper(*args, **kwargs):
        with cache_lock:
            previous_hits = cached_getaddrinfo.cache_info().hits
        result = cached_getaddrinfo(*args, **kwargs)
        with cache_lock:
            current_hits = cached_getaddrinfo.cache_info().hits
        if current_hits > previous_hits and on_cache_hit is not None:
            on_cache_hit()
        return result

    socket.getaddrinfo = cached_wrapper
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo
        cached_getaddrinfo.cache_clear()


def normalize_url(url):
    """Normalize a URL: add scheme, remove trailing slash, etc."""
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"
        parsed = urlparse(url)
    normalized = parsed._replace(fragment="").geturl()
    if normalized.endswith("/") and len(normalized) > 8:
        normalized = normalized[:-1]
    return normalized


def extract_domain(url):
    """Extract domain (including www if present)"""
    parsed = urlparse(normalize_url(url))
    return parsed.netloc.lower()


def is_internal_url(url, base_domain):
    """Check if URL is internal to the base domain"""
    try:
        url_domain = extract_domain(url)
        return url_domain == base_domain
    except Exception:
        return False


def check_https_validity(domain):
    """Check if domain has a working HTTPS endpoint.

    This helper is only a fallback signal. The crawler's real HTTP response
    should remain the primary source of truth whenever it exists.
    """
    session = build_http_session()
    https_url = f"https://{domain}"

    try:
        try:
            response = session.head(
                https_url,
                timeout=DEFAULT_REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            if response.status_code in {405, 406, 410, 501}:
                raise requests.RequestException("HEAD not supported")
        except requests.RequestException:
            response = session.get(
                https_url,
                timeout=DEFAULT_REQUEST_TIMEOUT,
                allow_redirects=True,
                stream=True,
            )
        response.close()
        return bool(response.url and urlparse(response.url).scheme == "https")
    except requests.RequestException:
        return False


def unwrap_exception(exc):
    """Unwrap nested exceptions to find the root cause."""
    current = exc
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (requests.exceptions.Timeout, requests.exceptions.SSLError)):
            return current
        cause = getattr(current, '__cause__', None)
        context = getattr(current, '__context__', None)
        if cause is not None and id(cause) not in seen:
            current = cause
        elif context is not None and id(context) not in seen:
            current = context
        else:
            break
    return exc

def classify_request_exception(exc):
    """Map real requests exceptions to stable, user-friendly error types."""
    # Unwrap nested exceptions first
    unwrapped = unwrap_exception(exc)
    message = str(exc).lower()
    unwrapped_message = str(unwrapped).lower()

    # Check for SSL errors
    if isinstance(unwrapped, requests.exceptions.SSLError):
        if "hostname" in unwrapped_message or "doesn't match" in unwrapped_message or "certificate verify failed" in unwrapped_message:
            return "SSL Error", "The website SSL certificate could not be verified."
        return "SSL Error", "The website SSL certificate could not be verified."

    # Check for timeout errors (including wrapped ones)
    if isinstance(unwrapped, requests.exceptions.Timeout) or "read timed out" in message or "connect timed out" in message:
        return "Timeout", "The website did not respond within the allowed timeout period."

    if isinstance(exc, requests.exceptions.ConnectionError):
        dns_markers = [
            "name or service not known",
            "temporary failure in name resolution",
            "getaddrinfo failed",
            "nodename nor servname provided",
            "no address associated with hostname",
            "failed to resolve",
        ]
        if any(marker in message for marker in dns_markers):
            return "DNS Resolution Error", "The website domain could not be resolved."
        if "refused" in message:
            return "Connection Refused", "The website refused the connection."
        return "Connection Error", "The website could not be reached."

    return "Connection Error", "An unexpected network error prevented the website from being reached."


def classify_request_error(exc, status_code=None):
    """Compatibility wrapper used by the link checker service."""
    if isinstance(exc, requests.exceptions.HTTPError):
        response = getattr(exc, "response", None)
        status_code = status_code or getattr(response, "status_code", None)
        if status_code:
            return "HTTP Error", f"The website returned HTTP status {status_code}."
        return "HTTP Error", "The website returned an HTTP error response."

    error_type, message = classify_request_exception(exc)
    if error_type == "Timeout":
        return "Connection Timeout", message
    if error_type == "SSL Error":
        return "SSL Certificate Error", message
    return error_type, message


def inspect_https_endpoint(domain):
    """Check HTTPS reachability and preserve a structured result."""
    url = f"https://{domain}"
    try:
        response = requests.head(
            url,
            timeout=DEFAULT_REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        if response.status_code >= 400:
            return {
                "measured": True,
                "ok": False,
                "error_type": "HTTP Error",
                "message": f"The website returned HTTP status {response.status_code}.",
                "status_code": response.status_code,
            }
        return {
            "measured": True,
            "ok": True,
            "error_type": "",
            "message": "",
            "status_code": response.status_code,
        }
    except requests.RequestException as exc:
        error_type, message = classify_request_error(exc)
        return {
            "measured": True,
            "ok": False,
            "error_type": error_type,
            "message": message,
            "status_code": None,
        }


def build_redirect_chain(requested_url, response):
    chain = [normalize_url(requested_url)]
    for history_response in getattr(response, "history", []):
        history_url = normalize_url(history_response.url)
        if history_url != chain[-1]:
            chain.append(history_url)
    final_url = normalize_url(response.url)
    if final_url != chain[-1]:
        chain.append(final_url)
    return chain


def clean_text(text):
    """Clean text: remove extra whitespace"""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()
