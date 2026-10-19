import logging

from django.conf import settings
from django.shortcuts import redirect, render

from home.emails import send_notification_email

from .forms import DashboardInquiryForm
from .models import PACKAGE_PRICES

logger = logging.getLogger(__name__)

PACKAGE_LABELS = {
    'starter': 'Starter',
    'business': 'Business',
    'enterprise': 'Enterprise',
}


def quote(request):
    """Render and process the Dashboard Development quote / requirements form.

    The package is preselected (and locked) via ``?package=starter|business|enterprise``.
    """
    package = request.GET.get('package', '').lower()
    if package not in PACKAGE_LABELS:
        package = 'business'

    if request.method == 'POST':
        # Honeypot: real users never see or fill this field. Silently drop bots.
        if request.POST.get('website', ''):
            return redirect('dashboard_inquiry:success')

        form = DashboardInquiryForm(request.POST)
        if form.is_valid():
            inquiry = form.save(commit=False)
            if request.user.is_authenticated:
                inquiry.user = request.user
            inquiry.save()
            _notify_team(inquiry)
            _notify_customer(inquiry)
            request.session['dd_inquiry_reference'] = inquiry.reference
            return redirect('dashboard_inquiry:success')
    else:
        form = DashboardInquiryForm(initial={'package': package})

    return render(request, 'dashboard_inquiry/quote.html', {
        'form': form,
        'package': package,
        'package_label': PACKAGE_LABELS[package],
        'package_price': PACKAGE_PRICES.get(package),
    })


def success(request):
    """Confirmation page after a successful submission."""
    return render(request, 'dashboard_inquiry/success.html', {
        'reference': request.session.get('dd_inquiry_reference', ''),
    })


def _team_recipients():
    return [
        getattr(settings, 'ADMIN_EMAIL', ''),
        getattr(settings, 'DASHBOARD_INQUIRY_EMAIL', ''),
        settings.DEFAULT_FROM_EMAIL,
    ]


def _notify_team(inquiry):
    """Best-effort notification email. Failures are logged, never raised to the user."""
    subject = f"[Dashboard Inquiry] {inquiry.get_package_display()} — {inquiry.name}"
    body = (
        f"Reference: {inquiry.reference}\n"
        f"Package: {inquiry.get_package_display()}\n"
        f"Name: {inquiry.name}\n"
        f"Email: {inquiry.email}\n"
        f"Company: {inquiry.company or '—'}\n"
        f"Phone: {inquiry.phone or '—'}\n"
        f"Data sources: {inquiry.data_sources or '—'}\n"
        f"Budget: {inquiry.budget or '—'}\n"
        f"Timeline: {inquiry.timeline or '—'}\n\n"
        f"Message:\n{inquiry.message or '—'}\n"
    )
    send_notification_email(
        subject=subject,
        recipients=_team_recipients(),
        text_body=body,
        label='dashboard-inquiry-team',
    )


def _notify_customer(inquiry):
    """Confirmation email to the customer. Failures are logged, never raised."""
    send_notification_email(
        subject=f'We received your quote request ({inquiry.reference})',
        recipients=[inquiry.email],
        template_name='emails/dashboard_inquiry_confirmation.html',
        context={
            'name': inquiry.name,
            'reference': inquiry.reference,
            'package_label': inquiry.get_package_display(),
        },
        text_body=(
            f'Hello {inquiry.name},\n\n'
            f'Thank you for your interest in a dashboard development quote. '
            f'Your reference is {inquiry.reference} '
            f'(package: {inquiry.get_package_display()}).\n'
            f'Our team will review your requirements and contact you shortly.\n\n'
            f'OnWebApp\n'
        ),
        label='dashboard-inquiry-customer',
    )
