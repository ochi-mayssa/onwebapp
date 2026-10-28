"""Notification emails for API requests.

All delivery goes through ``home.emails.send_notification_email`` (Resend SMTP
in production). Failures are logged, never raised: the database state of a
request must not depend on email delivery.
"""
import logging

from django.conf import settings
from django.urls import reverse

from .emails import send_notification_email
from .models import APIRequest, RPAConsultationRequest

logger = logging.getLogger(__name__)


def _site_absolute(path):
    """Build an absolute HTTPS URL from SITE_URL for use inside emails."""
    return f'{settings.SITE_URL.rstrip("/")}{path}'


def _admin_recipients():
    recipients = [
        getattr(settings, 'ADMIN_EMAIL', ''),
        getattr(settings, 'API_REQUEST_EMAIL', ''),
    ]
    if not any(recipients):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        recipients.extend(
            User.objects.filter(is_staff=True, is_active=True)
            .exclude(email='')
            .values_list('email', flat=True)
            .distinct()[:25]
        )
    if not any(recipients):
        recipients.append(settings.DEFAULT_FROM_EMAIL)
    return recipients


def notify_admins(api_request):
    """Notify the admin team about a new API request."""
    subject = f'[API Request] {api_request.reference} - {api_request.full_name}'
    admin_url = _site_absolute(
        reverse('home:admin_api_request_detail', args=[api_request.pk])
    )
    body = (
        f'A new API request was submitted.\n\n'
        f'Reference: {api_request.reference}\n'
        f'Type: {api_request.get_request_type_display()}\n'
        f'Name: {api_request.full_name}\n'
        f'Email: {api_request.business_email}\n'
        f'Company: {api_request.company_name or "-"}\n'
        f'API name / category: {api_request.api_name_or_category}\n'
        f'Expected usage: {api_request.expected_usage or "-"}\n'
        f'Budget: {api_request.get_budget_range_display() if api_request.budget_range else "-"}\n\n'
        f'Use case:\n{api_request.use_case}\n\n'
        f'Required features:\n{api_request.required_features}\n\n'
        f'Additional requirements:\n{api_request.additional_requirements or "-"}\n\n'
        f'Open in admin:\n{admin_url}\n'
    )
    send_notification_email(
        subject=subject,
        recipients=_admin_recipients(),
        text_body=body,
        label='api-request-admin',
    )


def notify_client_submitted(api_request):
    """Confirmation email to the client after submission."""
    subject = f'We received your API request ({api_request.reference})'
    tracking_url = _site_absolute(reverse('users:api_requests_list'))
    context = {
        'api_request': api_request,
        'reference': api_request.reference,
        'full_name': api_request.full_name,
        'tracking_url': tracking_url,
    }
    text_body = (
        f'Hello {api_request.full_name},\n\n'
        f'Thank you for your API request. Your reference is {api_request.reference}.\n'
        f'Our team will review it and get back to you. '
        f'You will receive an email when the status of your request changes.\n\n'
        f'You can track this request from your OnWebApp account: {tracking_url}\n'
    )
    send_notification_email(
        subject=subject,
        recipients=[api_request.business_email],
        template_name='emails/api_request_received.html',
        context=context,
        text_body=text_body,
        label='api-request-ack',
    )


def notify_client_status_change(api_request, old_status, new_status):
    """Client notification when an admin updates the request status."""
    labels = dict(APIRequest.STATUS_CHOICES)
    old_label = labels.get(old_status, old_status)
    new_label = labels.get(new_status, new_status)
    subject = f'Your API request {api_request.reference} is now {new_label}'
    tracking_url = _site_absolute(reverse('users:api_requests_list'))
    body = (
        f'Hello {api_request.full_name},\n\n'
        f'The status of your API request {api_request.reference} has changed:\n'
        f'  {old_label} -> {new_label}\n\n'
        f'You can view the request from your OnWebApp account: {tracking_url}\n'
    )
    send_notification_email(
        subject=subject,
        recipients=[api_request.business_email],
        text_body=body,
        label='api-request-status',
    )


# ── RPA consultation requests ──────────────────────────────────────────────


def _rpa_admin_url(rpa_request):
    return _site_absolute(
        reverse('admin:home_rpaconsultationrequest_change', args=[rpa_request.pk])
    )


def notify_rpa_admins(rpa_request):
    """Notify the admin team about a new RPA consultation request."""
    subject = f'[RPA Consultation] {rpa_request.reference} - {rpa_request.full_name}'
    body = (
        f'A new RPA consultation request was submitted.\n\n'
        f'Reference: {rpa_request.reference}\n'
        f'Name: {rpa_request.full_name}\n'
        f'Email: {rpa_request.business_email}\n'
        f'Company: {rpa_request.company_name or "-"}\n'
        f'Current tools: {rpa_request.current_tools or "-"}\n'
        f'Task frequency: {rpa_request.get_task_frequency_display() or "-"}\n'
        f'Time spent: {rpa_request.time_spent or "-"}\n\n'
        f'Process to automate:\n{rpa_request.process_to_automate}\n\n'
        f'Additional requirements:\n{rpa_request.additional_requirements or "-"}\n\n'
        f'Open in admin:\n{_rpa_admin_url(rpa_request)}\n'
    )
    send_notification_email(
        subject=subject,
        recipients=_admin_recipients(),
        text_body=body,
        label='rpa-consultation-admin',
    )


def notify_rpa_client_submitted(rpa_request):
    """Confirmation email to the visitor after submitting a consultation."""
    subject = f'We received your RPA consultation request ({rpa_request.reference})'
    body = (
        f'Hello {rpa_request.full_name},\n\n'
        f'Thank you for your RPA consultation request. Your reference is '
        f'{rpa_request.reference}.\n\n'
        f'Our team will review the process you described and get back to you with '
        f'a practical next step. You will receive an email when the status of your '
        f'request changes.\n'
    )
    send_notification_email(
        subject=subject,
        recipients=[rpa_request.business_email],
        text_body=body,
        label='rpa-consultation-ack',
    )


def notify_rpa_client_status_change(rpa_request, old_status, new_status):
    """Client notification when an admin updates the consultation status."""
    labels = dict(RPAConsultationRequest.STATUS_CHOICES)
    old_label = labels.get(old_status, old_status)
    new_label = labels.get(new_status, new_status)
    subject = f'Your RPA consultation request {rpa_request.reference} is now {new_label}'
    body = (
        f'Hello {rpa_request.full_name},\n\n'
        f'The status of your RPA consultation request {rpa_request.reference} '
        f'has changed:\n'
        f'  {old_label} -> {new_label}\n\n'
        f'Reply to this email if you have any questions about the next steps.\n'
    )
    send_notification_email(
        subject=subject,
        recipients=[rpa_request.business_email],
        text_body=body,
        label='rpa-consultation-status',
    )
