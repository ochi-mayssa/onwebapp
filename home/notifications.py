"""Best-effort notification emails for API requests. Failures are logged, never raised."""
import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import APIRequest

logger = logging.getLogger(__name__)


def _admin_recipients():
    explicit = getattr(settings, 'API_REQUEST_EMAIL', None)
    if explicit:
        return [explicit]
    from django.contrib.auth import get_user_model
    User = get_user_model()
    emails = list(
        User.objects.filter(is_staff=True, is_active=True)
        .exclude(email='')
        .values_list('email', flat=True)
        .distinct()[:25]
    )
    return emails or [settings.DEFAULT_FROM_EMAIL]


def _send(subject, body, recipients):
    if not recipients:
        return
    try:
        send_mail(
            subject, body,
            settings.DEFAULT_FROM_EMAIL,
            recipients,
            fail_silently=True,
        )
    except Exception:
        logger.exception('Failed to send API request email: %s', subject)


def notify_admins(api_request):
    """Notify the admin team about a new API request."""
    subject = f'[API Request] {api_request.reference} - {api_request.full_name}'
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
        f'Additional requirements:\n{api_request.additional_requirements or "-"}\n'
    )
    _send(subject, body, _admin_recipients())


def notify_client_submitted(api_request):
    """Confirmation email to the client after submission."""
    subject = f'We received your API request ({api_request.reference})'
    body = (
        f'Hello {api_request.full_name},\n\n'
        f'Thank you for your API request. Your reference is {api_request.reference}.\n'
        f'Our team will review it and get back to you. '
        f'You will receive an email when the status of your request changes.\n\n'
        f'You can track this request from your OnWebApp account.\n'
    )
    _send(subject, body, [api_request.business_email])


def notify_client_status_change(api_request, old_status, new_status):
    """Optional client notification when an admin updates the request status."""
    labels = dict(APIRequest.STATUS_CHOICES)
    old_label = labels.get(old_status, old_status)
    new_label = labels.get(new_status, new_status)
    subject = f'Your API request {api_request.reference} is now {new_label}'
    body = (
        f'Hello {api_request.full_name},\n\n'
        f'The status of your API request {api_request.reference} has changed:\n'
        f'  {old_label} -> {new_label}\n\n'
        f'You can view the request from your OnWebApp account.\n'
    )
    _send(subject, body, [api_request.business_email])
