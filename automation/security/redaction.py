"""Central secret redaction helpers.

Every automation log/payload goes through these helpers so tokens, passwords and
authorization headers cannot leak into ``ExecutionLog`` rows or application logs.
"""

from __future__ import annotations

import logging
import re
from typing import Any

REDACTED = '***REDACTED***'

_SENSITIVE_KEY_RE = re.compile(
    r'(?:^|[_\-\s])(?:'
    r'pass(?:word|phrase)?|secret|token|api[_\-]?key|apikey|access[_\-]?key|'
    r'private[_\-]?key|client[_\-]?secret|authorization|auth(?:entication)?|'
    r'cookie|credential|session[_\-]?id|signature|webhook[_\-]?secret|'
    r'stripe[_\-]?secret|bearer'
    r')(?:$|[_\-\s])',
    re.IGNORECASE,
)

_TEXT_PATTERNS = (
    re.compile(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=\-]+'),
    re.compile(r'(?i)\b(?:sk|pk|rk|whsec)_(?:live|test)_[A-Za-z0-9]+'),
    re.compile(r'(?i)\bsk-[A-Za-z0-9]{20,}\b'),
    re.compile(r'(?i)\b(api[_-]?key|token|secret|password|authorization)\b\s*[:=]\s*[^\s,;"\']+'),
)

_URL_USERINFO_RE = re.compile(r'(?i)\b(https?://)([^/\s@:]+):([^/\s@]+)@')


def is_sensitive_key(key: Any) -> bool:
    text = str(key)
    return bool(_SENSITIVE_KEY_RE.search(text))


def redact_text(value: Any) -> str:
    text = '' if value is None else str(value)
    text = _URL_USERINFO_RE.sub(lambda m: f'{m.group(1)}{REDACTED}@', text)
    for pattern in _TEXT_PATTERNS:
        text = pattern.sub(lambda m: _redacted_match(m.group(0)), text)
    return text


def _redacted_match(match: str) -> str:
    if ':' in match:
        return f'{match.split(":", 1)[0]}: {REDACTED}'
    if '=' in match:
        return f'{match.split("=", 1)[0]}={REDACTED}'
    return REDACTED


def redact_mapping(value: Any, *, _depth: int = 0) -> Any:
    """Recursively redact sensitive keys in dicts/lists."""
    if _depth > 12:
        return REDACTED
    if isinstance(value, dict):
        return {
            key: (REDACTED if is_sensitive_key(key) else redact_mapping(item, _depth=_depth + 1))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_mapping(item, _depth=_depth + 1) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


class SecretRedactingFilter(logging.Filter):
    """Logging filter that redacts common secret shapes from messages."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging API
        try:
            message = record.getMessage()
            record.msg = redact_text(message)
            record.args = ()
        except Exception:  # pragma: no cover - logging must never raise
            record.msg = '***REDACTED LOG RECORD***'
            record.args = ()
        return True
