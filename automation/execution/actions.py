"""Explicitly approved action handlers.

There is intentionally no dynamic import, ``eval``, ``exec`` or customer-supplied
Python path here. A workflow can only refer to a type registered in ``REGISTRY``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.validators import validate_email

from ..models import IntegrationConnection
from ..security.redaction import is_sensitive_key
from ..security.ssrf import (
    OutboundRequestBlocked,
    OutboundRequestError,
    safe_http_request,
)
from .errors import ActionError, ExecutionConfigurationError

logger = logging.getLogger('automation')

DEFAULT_MAX_EMAIL_RECIPIENTS = 20
MAX_EMAIL_BODY_BYTES = 200_000
MAX_HTTP_BODY_BYTES = 100_000
MAX_HEADER_COUNT = 20
MAX_HEADER_VALUE = 2_000
DISALLOWED_HTTP_HEADERS = {
    'authorization',
    'cookie',
    'host',
    'content-length',
    'transfer-encoding',
    'connection',
    'proxy-authorization',
    'proxy-connection',
    'upgrade',
}


@dataclass(frozen=True)
class ActionContext:
    execution: Any
    workflow: Any
    customer: Any


@dataclass(frozen=True)
class ActionHandler:
    type: str
    execute: Callable[[dict[str, Any], ActionContext], dict[str, Any]]


def _send_email(*, subject: str, body: str, from_email: str, recipients: list[str], html: bool) -> None:
    """Indirection so unit tests can mock delivery without touching SMTP."""
    message = EmailMessage(subject=subject, body=body, from_email=from_email, to=recipients)
    if html:
        message.content_subtype = 'html'
    message.send(fail_silently=False)


def _validate_plain_text(value: Any, field: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ActionError(f'{field} is required.', code='invalid_action_config')
    if len(value) > max_length:
        raise ActionError(f'{field} is too long.', code='invalid_action_config')
    return value


def _validate_email_config(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ActionError('Email action config must be an object.', code='invalid_action_config')

    recipients = config.get('to')
    if isinstance(recipients, str):
        recipients = [part for part in recipients.replace(';', ',').split(',') if part.strip()]
    if not isinstance(recipients, list) or not recipients:
        raise ActionError('At least one email recipient is required.', code='invalid_action_config')
    max_recipients = int(getattr(settings, 'AUTOMATION_MAX_EMAIL_RECIPIENTS', DEFAULT_MAX_EMAIL_RECIPIENTS))
    if len(recipients) > max_recipients:
        raise ActionError('Too many email recipients.', code='invalid_action_config')

    clean_recipients: list[str] = []
    for recipient in recipients:
        if not isinstance(recipient, str):
            raise ActionError('Email recipients must be strings.', code='invalid_action_config')
        recipient = recipient.strip()
        try:
            validate_email(recipient)
        except ValidationError as exc:
            raise ActionError('Email recipient is invalid.', code='invalid_action_config') from exc
        clean_recipients.append(recipient)

    subject = _validate_plain_text(config.get('subject'), 'subject', max_length=255)
    body = _validate_plain_text(config.get('body'), 'body', max_length=MAX_EMAIL_BODY_BYTES)

    from_email = config.get('from_email') or getattr(settings, 'DEFAULT_FROM_EMAIL', None)
    if not from_email:
        raise ActionError('A sender address is required.', code='invalid_action_config')
    if config.get('from_email'):
        try:
            validate_email(from_email)
        except ValidationError as exc:
            raise ActionError('Sender address is invalid.', code='invalid_action_config') from exc

    html = config.get('html', False)
    if not isinstance(html, bool):
        raise ActionError('html must be a boolean.', code='invalid_action_config')

    return {
        'to': clean_recipients,
        'subject': subject,
        'body': body,
        'from_email': str(from_email),
        'html': html,
    }


def execute_email_action(config: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    clean = _validate_email_config(config)
    try:
        _send_email(**clean)
    except Exception as exc:  # SMTP failures are usually transient
        logger.warning('Email action failed for execution %s: %s', context.execution.pk, exc.__class__.__name__)
        raise ActionError('Email delivery failed.', code='email_delivery_failed', retryable=True) from exc
    return {'recipients': len(clean['to']), 'html': clean['html']}


def _validate_http_headers(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > MAX_HEADER_COUNT:
        raise ActionError('HTTP headers must be a small object.', code='invalid_action_config')
    clean: dict[str, str] = {}
    for key, header_value in value.items():
        if not isinstance(key, str) or not isinstance(header_value, str):
            raise ActionError('HTTP headers must be string pairs.', code='invalid_action_config')
        lower = key.strip().lower()
        if lower in DISALLOWED_HTTP_HEADERS or is_sensitive_key(lower):
            raise ActionError(
                'Sensitive or transport headers must be supplied by an integration connection.',
                code='invalid_action_config',
            )
        if not lower or len(lower) > 100 or len(header_value) > MAX_HEADER_VALUE:
            raise ActionError('HTTP header is invalid.', code='invalid_action_config')
        if '\r' in header_value or '\n' in header_value or ':' in lower:
            raise ActionError('HTTP header contains invalid characters.', code='invalid_action_config')
        clean[lower] = header_value
    return clean


def _load_connection(context: ActionContext, connection_id: Any) -> IntegrationConnection:
    if connection_id in (None, ''):
        raise ActionError('HTTP action requires an integration connection.', code='invalid_action_config')
    try:
        connection_id = int(connection_id)
    except (TypeError, ValueError) as exc:
        raise ActionError('connection_id must be an integer.', code='invalid_action_config') from exc
    try:
        connection = IntegrationConnection.objects.get(
            pk=connection_id,
            customer=context.customer,
            status='active',
        )
    except IntegrationConnection.DoesNotExist as exc:
        # Deliberately do not reveal whether another tenant owns the connection.
        raise ActionError('Integration connection is not available.', code='connection_not_found') from exc
    return connection


def _credential_value(credentials: dict[str, Any], credential_key: str) -> str:
    candidates = [credential_key, 'token', 'api_key', 'access_token', 'secret']
    for key in candidates:
        value = credentials.get(key)
        if isinstance(value, str) and value:
            return value
    raise ActionError('Integration connection has no usable credential.', code='credential_missing')


def execute_http_action(config: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ActionError('HTTP action config must be an object.', code='invalid_action_config')

    allowed_keys = {
        'method', 'url', 'headers', 'json', 'body', 'timeout',
        'connection_id', 'auth_type', 'auth_header', 'credential_key',
    }
    unknown = set(config) - allowed_keys
    if unknown:
        raise ExecutionConfigurationError(
            f'HTTP action contains unsupported keys: {", ".join(sorted(unknown))}.'
        )

    method = str(config.get('method', 'POST')).upper()
    url = config.get('url')
    if not isinstance(url, str):
        raise ActionError('HTTP action URL is required.', code='invalid_action_config')

    headers = _validate_http_headers(config.get('headers'))
    json_body = config.get('json')
    text_body = config.get('body')
    if json_body is not None and text_body is not None:
        raise ActionError('Use either json or body, not both.', code='invalid_action_config')
    if isinstance(text_body, str):
        if len(text_body) > MAX_HTTP_BODY_BYTES:
            raise ActionError('HTTP body is too large.', code='invalid_action_config')
    elif text_body is not None:
        raise ActionError('HTTP body must be a string.', code='invalid_action_config')

    connection = _load_connection(context, config.get('connection_id'))
    auth_type = str(config.get('auth_type', 'bearer')).lower()
    if auth_type not in {'bearer', 'header'}:
        raise ActionError('auth_type must be bearer or header.', code='invalid_action_config')
    credential_key = str(config.get('credential_key', 'token'))
    try:
        credentials = connection.get_credentials()
    except Exception as exc:
        raise ActionError('Integration credentials could not be decrypted.', code='credential_error') from exc
    credential = _credential_value(credentials, credential_key)
    if auth_type == 'bearer':
        headers['authorization'] = f'Bearer {credential}'
    else:
        auth_header = str(config.get('auth_header', 'x-api-key')).strip().lower()
        if auth_header in DISALLOWED_HTTP_HEADERS:
            raise ActionError('auth_header is a transport header.', code='invalid_action_config')
        if not auth_header or ':' in auth_header or '\n' in auth_header:
            raise ActionError('auth_header is invalid.', code='invalid_action_config')
        headers[auth_header] = credential

    headers.setdefault('user-agent', 'OnWebApp-Automation/1.0')
    headers.setdefault('idempotency-key', str(context.execution.execution_key))

    try:
        response = safe_http_request(
            method,
            url,
            headers=headers,
            json_body=json_body,
            body=text_body,
            timeout=config.get('timeout'),
        )
    except OutboundRequestBlocked as exc:
        raise ActionError('Outbound URL was blocked by network policy.', code='ssrf_blocked') from exc
    except OutboundRequestError as exc:
        raise ActionError('Outbound HTTP request failed.', code='http_transport_error', retryable=exc.retryable) from exc

    if response.status_code in {408, 425, 429} or response.status_code >= 500:
        raise ActionError(
            'Outbound endpoint returned a transient error.',
            code='http_retryable_status',
            retryable=True,
        )
    if not response.ok:
        raise ActionError('Outbound endpoint rejected the request.', code='http_status_error')

    return {
        'status_code': response.status_code,
        'content_type': response.headers.get('Content-Type', ''),
        'response_bytes': len(response.body),
    }


REGISTRY: dict[str, ActionHandler] = {
    'email': ActionHandler(type='email', execute=execute_email_action),
    'http_request': ActionHandler(type='http_request', execute=execute_http_action),
}


def get_action(action_type: str) -> ActionHandler:
    if not isinstance(action_type, str) or action_type not in REGISTRY:
        raise ExecutionConfigurationError('Workflow references an action type that is not approved.')
    return REGISTRY[action_type]


def approved_action_types() -> list[str]:
    return sorted(REGISTRY)
