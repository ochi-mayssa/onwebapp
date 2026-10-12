import logging

from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import redirect, render

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


def _notify_team(inquiry):
    """Best-effort notification email. Failures are logged, never raised to the user."""
    recipient = getattr(settings, 'DASHBOARD_INQUIRY_EMAIL', None) or settings.DEFAULT_FROM_EMAIL
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
    try:
        send_mail(
            subject, body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=True,
        )
    except Exception:
        logger.exception("Failed to send dashboard inquiry notification for %s", inquiry.reference)
