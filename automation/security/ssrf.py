"""Outbound HTTP protection and a small SSRF-aware request helper.

Rules enforced here:

* only ``http``/``https`` URLs;
* no embedded usernames/passwords;
* only approved ports (default ``80,443,8443``);
* the hostname is resolved and every returned address must be public;
* redirects are followed manually and re-validated at every hop;
* connect/read timeouts and a maximum response size are enforced.

Residual risk: DNS can change between validation and connection (DNS rebinding).
For higher assurance, run egress through a proxy that applies the same policy.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from django.conf import settings

logger = logging.getLogger('automation')

DEFAULT_ALLOWED_PORTS = '80,443,8443'
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_MAX_RESPONSE_BYTES = 1_048_576
MAX_REDIRECTS = 3
ALLOWED_METHODS = {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'}

_EXTRA_BLOCKED_NETWORKS = (
    ipaddress.ip_network('0.0.0.0/8'),
    ipaddress.ip_network('100.64.0.0/10'),  # carrier-grade NAT
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('169.254.0.0/16'),  # link-local / cloud metadata
    ipaddress.ip_network('192.0.0.0/24'),
    ipaddress.ip_network('192.0.2.0/24'),
    ipaddress.ip_network('198.18.0.0/15'),
    ipaddress.ip_network('198.51.100.0/24'),
    ipaddress.ip_network('203.0.113.0/24'),
    ipaddress.ip_network('240.0.0.0/4'),
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fc00::/7'),
    ipaddress.ip_network('fe80::/10'),
    ipaddress.ip_network('ff00::/8'),
    ipaddress.ip_network('::/128'),
    ipaddress.ip_network('2001:db8::/32'),
)

_BLOCKED_HOSTNAMES = {
    'localhost',
    'localhost.localdomain',
    'metadata',
    'metadata.google.internal',
    'instance-data',
}


class OutboundRequestBlocked(ValueError):
    """The destination is not allowed by the outbound network policy."""


class OutboundRequestError(RuntimeError):
    """The outbound request failed; ``retryable`` tells the engine if it may retry."""

    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class SafeHTTPResponse:
    status_code: int
    url: str
    headers: dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode('utf-8', errors='replace')

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


def _setting_bool(name: str, default: bool = False) -> bool:
    value = getattr(settings, name, default)
    if isinstance(value, bool):
        return value
    return str(value).lower() in ('1', 'true', 'yes', 'on')


def _allowed_ports() -> set[int]:
    raw = getattr(settings, 'AUTOMATION_ALLOWED_OUTBOUND_PORTS', DEFAULT_ALLOWED_PORTS)
    ports: set[int] = set()
    for part in str(raw).split(','):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise OutboundRequestBlocked('Outbound port configuration is invalid.')
        ports.add(int(part))
    return ports


def _is_blocked_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return True
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True
    if not ip.is_global:
        return True
    return any(ip in network for network in _EXTRA_BLOCKED_NETWORKS if network.version == ip.version)


def _normalise_hostname(hostname: str) -> str:
    return hostname.rstrip('.').lower()


def _resolve_host(hostname: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise OutboundRequestBlocked('Outbound hostname could not be resolved.') from exc
    addresses = []
    for info in infos:
        address = info[4][0]
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise OutboundRequestBlocked('Outbound hostname resolved to no addresses.')
    return addresses


def validate_outbound_url(url: str, *, allow_private: bool | None = None) -> str:
    """Validate a URL for outbound use and return a normalised URL.

    Raises ``OutboundRequestBlocked`` with a safe message that never contains
    credentials. Private destinations are allowed only when explicitly enabled by
    ``AUTOMATION_ALLOW_PRIVATE_OUTBOUND`` (development/testing only).
    """
    if not isinstance(url, str) or not url.strip():
        raise OutboundRequestBlocked('Outbound URL is required.')
    if len(url) > 2048:
        raise OutboundRequestBlocked('Outbound URL is too long.')

    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    if scheme not in {'http', 'https'}:
        raise OutboundRequestBlocked('Only http and https outbound URLs are allowed.')
    if parsed.username or parsed.password:
        raise OutboundRequestBlocked('Outbound URLs must not embed credentials.')
    if not parsed.hostname:
        raise OutboundRequestBlocked('Outbound URL must include a hostname.')

    hostname = _normalise_hostname(parsed.hostname)
    if hostname in _BLOCKED_HOSTNAMES or hostname.endswith('.local') or hostname.endswith('.internal'):
        raise OutboundRequestBlocked('Outbound destination is an internal hostname.')

    try:
        port = parsed.port or (443 if scheme == 'https' else 80)
    except ValueError as exc:
        raise OutboundRequestBlocked('Outbound URL has an invalid port.') from exc

    if port not in _allowed_ports():
        raise OutboundRequestBlocked('Outbound destination port is not allowed.')

    if allow_private is None:
        allow_private = _setting_bool('AUTOMATION_ALLOW_PRIVATE_OUTBOUND', False)
    if not allow_private:
        for address in _resolve_host(hostname, port):
            if _is_blocked_ip(address):
                raise OutboundRequestBlocked('Outbound destination resolves to a private or internal address.')

    # Drop any fragment; it is not sent over HTTP.
    return urlunsplit((scheme, parsed.netloc, parsed.path or '/', parsed.query, ''))


def _timeout_seconds(value: float | None = None) -> float:
    configured = getattr(settings, 'AUTOMATION_OUTBOUND_TIMEOUT_SECONDS', DEFAULT_TIMEOUT_SECONDS)
    try:
        maximum = float(configured)
    except (TypeError, ValueError):
        maximum = float(DEFAULT_TIMEOUT_SECONDS)
    if value is None:
        return maximum
    try:
        return max(0.1, min(float(value), maximum))
    except (TypeError, ValueError):
        return maximum


def safe_http_request(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    json_body: Any = None,
    body: str | bytes | None = None,
    timeout: float | None = None,
    max_redirects: int = MAX_REDIRECTS,
) -> SafeHTTPResponse:
    """Perform a bounded outbound request with SSRF validation on every hop."""
    method = str(method or '').upper()
    if method not in ALLOWED_METHODS:
        raise OutboundRequestBlocked('HTTP method is not allowed.')

    max_response_bytes = int(
        getattr(settings, 'AUTOMATION_MAX_HTTP_RESPONSE_BYTES', DEFAULT_MAX_RESPONSE_BYTES)
    )
    request_timeout = _timeout_seconds(timeout)
    current_url = validate_outbound_url(url)
    request_kwargs: dict[str, Any] = {
        'headers': dict(headers or {}),
        'timeout': (min(5.0, request_timeout), request_timeout),
        'allow_redirects': False,
        'stream': True,
    }

    for redirect_count in range(max_redirects + 1):
        current_url = validate_outbound_url(current_url)
        kwargs = dict(request_kwargs)
        if json_body is not None:
            kwargs['json'] = json_body
        if body is not None:
            kwargs['data'] = body
        try:
            response = requests.request(method, current_url, **kwargs)
        except requests.exceptions.RequestException as exc:
            raise OutboundRequestError(
                f'Outbound request failed ({exc.__class__.__name__}).',
                retryable=True,
            ) from exc

        status = int(getattr(response, 'status_code', 0) or 0)
        location = (getattr(response, 'headers', {}) or {}).get('Location')
        if status in {301, 302, 303, 307, 308} and location:
            if redirect_count >= max_redirects:
                _close(response)
                raise OutboundRequestError('Outbound request exceeded the redirect limit.', retryable=False)
            next_url = urljoin(current_url, location)
            # Re-validate in the next loop iteration before connecting.
            current_url = next_url
            if status == 303 or (status in {301, 302} and method == 'POST'):
                method = 'GET'
                json_body = None
                body = None
            _close(response)
            continue

        try:
            chunks = []
            total_bytes = 0
            for chunk in response.iter_content(8192):
                total_bytes += len(chunk)
                if total_bytes > max_response_bytes:
                    raise OutboundRequestError('Outbound response exceeded the size limit.', retryable=False)
                chunks.append(chunk)
            raw_body = b''.join(chunks)
        except (AttributeError, TypeError):
            raw_body = getattr(response, 'content', b'') or b''
            if len(raw_body) > max_response_bytes:
                raise OutboundRequestError('Outbound response exceeded the size limit.', retryable=False)
        finally:
            _close(response)

        response_headers = getattr(response, 'headers', {}) or {}
        safe_headers = {
            key: str(response_headers.get(key))
            for key in ('Content-Type', 'Retry-After', 'X-Request-Id')
            if response_headers.get(key) is not None
        }
        return SafeHTTPResponse(
            status_code=status,
            url=current_url,
            headers=safe_headers,
            body=raw_body,
        )

    raise OutboundRequestError('Outbound request exceeded the redirect limit.', retryable=False)


def _close(response: Any) -> None:
    close = getattr(response, 'close', None)
    if callable(close):
        try:
            close()
        except Exception:  # pragma: no cover - close best effort
            pass
