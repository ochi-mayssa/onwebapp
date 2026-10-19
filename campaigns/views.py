"""Admin-only email campaign views (superuser restricted, CSRF-protected)."""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from home.views import superuser_required

from .audience import resolved_email_map
from .delivery import (
    start_send,
    resume_send,
    verify_unsubscribe_token,
)
from .forms import CampaignComposeForm
from .models import Campaign
from .sanitizer import sanitize_campaign_html

User = get_user_model()


def _render_campaign_preview(campaign, unsubscribe_url=None):
    """Server-side preview of the exact email that recipients will receive."""
    from django.template.loader import render_to_string
    return render_to_string('emails/campaign_message.html', {
        'subject': campaign.subject,
        'body_html_safe': mark_safe(sanitize_campaign_html(campaign.body_html)),
        'unsubscribe_url': unsubscribe_url,
    })


@superuser_required
def compose(request):
    if request.method == 'POST':
        form = CampaignComposeForm(request.POST)
        if form.is_valid():
            campaign = form.save(commit=False)
            campaign.created_by = request.user
            campaign.save()
            if campaign.audience == Campaign.AUDIENCE_SELECTED:
                campaign.selected_users.set(form.cleaned_data['selected_users'])
            messages.success(request, 'Draft created. Review the preview and confirm to send.')
            return redirect('campaigns:confirm', pk=campaign.pk)
    else:
        form = CampaignComposeForm()
    return render(request, 'campaigns/compose.html', {'form': form})


@superuser_required
def confirm(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    if campaign.status != Campaign.STATUS_DRAFT:
        return redirect('campaigns:detail', pk=campaign.pk)
    email_map = resolved_email_map(campaign)
    recipients = list(email_map.values())
    preview = _render_campaign_preview(campaign, unsubscribe_url='https://example.com/unsubscribe/…')
    if request.method == 'POST':
        ok, error = start_send(campaign)
        if ok:
            messages.success(
                request,
                f'Sending started to {len(recipients)} recipient(s) in the background.',
            )
            return redirect('campaigns:detail', pk=campaign.pk)
        if error == 'too_many_recipients':
            messages.error(
                request,
                f'This audience exceeds the configured limit '
                f'({len(recipients)} recipients). Narrow the audience and try again.',
            )
        else:
            messages.error(request, 'This campaign can no longer be sent.')
            return redirect('campaigns:detail', pk=campaign.pk)
    return render(request, 'campaigns/confirm.html', {
        'campaign': campaign,
        'recipient_count': len(recipients),
        'recipient_sample': recipients[:10],
        'preview': preview,
    })


@superuser_required
def history(request):
    qs = Campaign.objects.select_related('created_by')
    status_filter = request.GET.get('status', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'campaigns/history.html', {
        'page_obj': page_obj,
        'status_choices': Campaign.STATUS_CHOICES,
        'status_filter': status_filter,
    })


@superuser_required
def detail(request, pk):
    campaign = get_object_or_404(
        Campaign.objects.select_related('created_by'), pk=pk,
    )
    recipients = campaign.recipients.order_by('email')
    paginator = Paginator(recipients, 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'campaigns/detail.html', {
        'campaign': campaign,
        'page_obj': page_obj,
    })


@superuser_required
@require_POST
def resume(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    ok, error = resume_send(campaign)
    if ok:
        messages.success(request, 'Delivery resumed for pending recipients.')
    elif error == 'nothing_pending':
        messages.info(request, 'No pending recipients left to deliver.')
    else:
        messages.error(request, 'This campaign cannot be resumed.')
    return redirect('campaigns:detail', pk=campaign.pk)


@superuser_required
@require_POST
def cancel(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    if campaign.status == Campaign.STATUS_DRAFT:
        campaign.status = Campaign.STATUS_CANCELED
        campaign.save(update_fields=['status', 'updated_at'])
        messages.info(request, 'Draft canceled.')
    else:
        messages.error(request, 'Only drafts can be canceled.')
    return redirect('campaigns:history')


def unsubscribe(request, token):
    """Public, token-based marketing opt-out (GET confirms, POST applies)."""
    user_pk = verify_unsubscribe_token(token)
    if user_pk is None or not User.objects.filter(pk=user_pk).exists():
        return render(request, 'campaigns/unsubscribe.html', {
            'invalid': True,
        }, status=400)
    from users.models import UserProfile
    profile, _ = UserProfile.objects.get_or_create(user_id=user_pk)
    if request.method == 'POST':
        if profile.marketing_emails_enabled:
            profile.marketing_emails_enabled = False
            profile.save(update_fields=['marketing_emails_enabled'])
        return render(request, 'campaigns/unsubscribe.html', {
            'done': True,
        })
    return render(request, 'campaigns/unsubscribe.html', {
        'already': not profile.marketing_emails_enabled,
    })
