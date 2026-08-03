"""HTML email sending utilities for the Branding Service.

Uses Django's EmailMultiAlternatives to send responsive HTML emails
with plain-text fallbacks. All sends are logged and fail gracefully.
"""
import logging
import os

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger('branding.emails')

DEFAULT_FROM = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@onwebapp.com')
SITE_URL = getattr(settings, 'SITE_URL', 'https://onwebapp.com')

# Status color map for email badges
STATUS_COLORS = {
    'DRAFT': '#94a3b8',
    'PENDING_REVIEW': '#f59e0b',
    'IN_REVIEW': '#f59e0b',
    'ASSIGNED': '#3b82f6',
    'DESIGNING': '#8b5cf6',
    'WAITING_CLIENT': '#f97316',
    'REVISION': '#ef4444',
    'APPROVED': '#22c55e',
    'COMPLETED': '#16a34a',
    'ARCHIVED': '#64748b',
}


def _base_context(**kwargs):
    """Build the base template context shared by all emails."""
    ctx = {
        'site_url': SITE_URL,
    }
    ctx.update(kwargs)
    return ctx


def send_html_email(recipient, subject, template_name, context=None,
                    attachments=None, cc=None, bcc=None,
                    from_email=None, log_label=''):
    """Send an HTML email with plain-text fallback.

    Args:
        recipient: User object or email string
        subject: Email subject line
        template_name: Path relative to templates/ (e.g. 'emails/status_update.html')
        context: Dict of template variables
        attachments: List of (filename, content, mimetype) tuples
        cc: List of CC email addresses
        bcc: List of BCC email addresses
        from_email: Sender address (defaults to DEFAULT_FROM_EMAIL)
        log_label: Label for the log entry

    Returns:
        True if sent successfully, False otherwise.
    """
    if not recipient:
        return False

    # Resolve recipient email
    if hasattr(recipient, 'email'):
        to_email = recipient.email
        if not to_email:
            logger.warning('[EMAIL] No email for user %s, skipping', recipient.pk)
            return False
    else:
        to_email = str(recipient)

    from_email = from_email or DEFAULT_FROM
    context = context or {}

    # Add base context
    full_context = _base_context(**context)

    try:
        # Render HTML
        html_body = render_to_string(template_name, full_context)

        # Generate plain-text version from rendered HTML
        text_body = strip_tags(html_body)
        # Clean up excessive whitespace
        lines = [line.strip() for line in text_body.splitlines() if line.strip()]
        text_body = '\n'.join(lines)

        # Build email
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[to_email],
            cc=cc or [],
            bcc=bcc or [],
        )
        msg.attach_alternative(html_body, 'text/html')

        # Attach files
        if attachments:
            for filename, content, mimetype in attachments:
                msg.attach(filename, content, mimetype)

        # Send
        msg.send(fail_silently=True)

        logger.info(
            '[EMAIL] Sent %s to %s | subject="%s" | id=%s',
            log_label or template_name, to_email, subject, getattr(recipient, 'pk', 'anon'),
        )
        return True

    except Exception as exc:
        logger.error(
            '[EMAIL] Failed to send %s to %s: %s',
            log_label or template_name, to_email, exc,
        )
        return False


# ---------------------------------------------------------------------------
# Convenience senders
# ---------------------------------------------------------------------------

def send_status_update_email(user, branding_request, old_status=''):
    """Send status update notification email."""
    from ..models import BrandingRequest

    status_display = branding_request.get_status_display()
    status_color = STATUS_COLORS.get(branding_request.status, '#4f46e5')

    return send_html_email(
        recipient=user,
        subject=f"[OnWebApp Branding] {branding_request.request_number} — {status_display}",
        template_name='emails/status_update.html',
        context={
            'request_number': branding_request.request_number,
            'company_name': branding_request.company_name,
            'status_display': status_display,
            'status_color': status_color,
            'old_status': old_status,
            'designer_name': str(branding_request.designer) if branding_request.designer else '',
            'action_url': f"{SITE_URL}/branding/requests/{branding_request.pk}/",
        },
        log_label='status_update',
    )


def send_assignment_email(user, branding_request):
    """Send designer assignment notification email."""
    return send_html_email(
        recipient=user,
        subject=f"[OnWebApp Branding] {branding_request.request_number} — Designer Assigned",
        template_name='emails/assignment.html',
        context={
            'request_number': branding_request.request_number,
            'company_name': branding_request.company_name,
            'designer_name': str(branding_request.designer) if branding_request.designer else '',
            'designer_email': branding_request.designer.email if branding_request.designer else '',
            'estimated_delivery': branding_request.estimated_delivery_date.strftime('%B %d, %Y') if branding_request.estimated_delivery_date else '',
            'action_url': f"{SITE_URL}/branding/requests/{branding_request.pk}/",
        },
        log_label='assignment',
    )


def send_completion_email(user, branding_request):
    """Send project completion email."""
    return send_html_email(
        recipient=user,
        subject=f"[OnWebApp Branding] {branding_request.request_number} — Project Completed!",
        template_name='emails/completion.html',
        context={
            'request_number': branding_request.request_number,
            'company_name': branding_request.company_name,
            'designer_name': str(branding_request.designer) if branding_request.designer else '',
            'completed_at': branding_request.completed_at,
            'action_url': f"{SITE_URL}/branding/requests/{branding_request.pk}/",
            'feedback_url': f"{SITE_URL}/branding/requests/{branding_request.pk}/#feedback",
        },
        log_label='completion',
    )


def send_feedback_request_email(user, branding_request):
    """Send feedback request email after project completion."""
    return send_html_email(
        recipient=user,
        subject=f"[OnWebApp Branding] How was your experience with {branding_request.request_number}?",
        template_name='emails/feedback_request.html',
        context={
            'request_number': branding_request.request_number,
            'company_name': branding_request.company_name,
            'action_url': f"{SITE_URL}/branding/requests/{branding_request.pk}/#feedback",
        },
        log_label='feedback_request',
    )


def send_message_notification_email(user, branding_request, sender_name, message_text):
    """Send new message notification email."""
    preview = message_text[:300]
    truncated = len(message_text) > 300

    return send_html_email(
        recipient=user,
        subject=f"[OnWebApp Branding] New message from {sender_name} — {branding_request.request_number}",
        template_name='emails/message_notification.html',
        context={
            'request_number': branding_request.request_number,
            'company_name': branding_request.company_name,
            'sender_name': sender_name,
            'message_preview': preview,
            'message_truncated': truncated,
            'action_url': f"{SITE_URL}/branding/requests/{branding_request.pk}/#messages",
        },
        log_label='message_notification',
    )


def send_test_email(to_email, template_name='emails/status_update.html'):
    """Send a test email to verify email configuration.

    Uses sample data to render the template.
    """
    context = {
        'request_number': 'BR-2026-00001',
        'company_name': 'Test Company',
        'status_display': 'Designing',
        'status_color': '#8b5cf6',
        'old_status': 'Assigned',
        'designer_name': 'Jane Designer',
        'designer_email': 'jane@onwebapp.com',
        'estimated_delivery': 'August 15, 2026',
        'completed_at': None,
        'company_name': 'Test Company',
        'sender_name': 'John Client',
        'message_preview': 'This is a test message to verify the email template renders correctly. It includes sample content to preview the layout.',
        'message_truncated': False,
        'action_url': f'{SITE_URL}/branding/requests/1/',
        'feedback_url': f'{SITE_URL}/branding/requests/1/#feedback',
        'site_url': SITE_URL,
    }

    return send_html_email(
        recipient=to_email,
        subject='[OnWebApp Branding] Test Email',
        template_name=template_name,
        context=context,
        log_label='test',
    )
