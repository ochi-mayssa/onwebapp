"""Centralized transactional email delivery.

All application emails should go through :func:`send_notification_email` so
that the from-address, HTML alternatives, recipient validation and failure
logging stay consistent (Resend SMTP in production, console backend in
development). The function never raises: callers keep their own domain logic
(e.g. saving an inquiry) independent of email delivery.
"""
import logging
from email.utils import parseaddr

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def valid_recipients(addresses):
    """Filter, de-duplicate and validate a list of email addresses.

    Accepts bare addresses as well as ``Name <addr>`` display formats (the
    latter appear when ``DEFAULT_FROM_EMAIL`` is used as a fallback
    recipient); only the bare address is kept.
    """
    valid = []
    seen = set()
    for address in addresses or []:
        address = (address or '').strip()
        if not address:
            continue
        # Strip an optional display name ("OnWebApp <x@y.z>" -> "x@y.z").
        address = parseaddr(address)[1].strip()
        if not address:
            continue
        try:
            validate_email(address)
        except ValidationError:
            logger.warning('Skipping invalid recipient address for %r', address)
            continue
        key = address.lower()
        if key in seen:
            continue
        seen.add(key)
        valid.append(address)
    return valid


def send_notification_email(*, subject, recipients, text_body=None,
                            template_name=None, context=None, cc=None,
                            bcc=None, from_email=None, reply_to=None,
                            label='notification'):
    """Send one transactional email (optionally multipart HTML + text).

    Returns ``True`` when Django reports at least one delivered message,
    ``False`` otherwise. Never raises; failures are logged with tracebacks.
    """
    to = valid_recipients(recipients)
    if not to:
        logger.warning('Not sending %s email %r: no valid recipients', label, subject)
        return False

    html_body = None
    if template_name:
        html_body = render_to_string(template_name, context or {})
    if text_body is not None:
        body = text_body
    elif html_body:
        body = strip_tags(html_body)
    else:
        body = ''

    message = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=to,
        cc=valid_recipients(cc) or None,
        bcc=valid_recipients(bcc) or None,
        reply_to=[reply_to] if reply_to else None,
    )
    if html_body:
        message.attach_alternative(html_body, 'text/html')
    try:
        sent = message.send(fail_silently=False)
    except Exception:
        logger.exception('Failed to send %s email: %s', label, subject)
        return False
    if not sent:
        logger.error('%s email reported as not sent: %s', label, subject)
    return bool(sent)
