"""Recipient selection for marketing campaigns.

Eligible clients are active, non-staff accounts with a valid email address
who have not opted out of marketing email. Staff and superuser accounts are
never included by default.
"""
from django.contrib.auth import get_user_model

from home.emails import valid_recipients

from .models import Campaign

User = get_user_model()


def eligible_client_queryset():
    """Active non-staff accounts with an email, minus marketing opt-outs.

    Users without a UserProfile row are eligible (opt-outs only apply when the
    profile flag is explicitly False).
    """
    return (
        User.objects.filter(is_active=True)
        .exclude(is_staff=True)
        .exclude(is_superuser=True)
        .exclude(email__isnull=True)
        .exclude(email='')
        .exclude(profile__marketing_emails_enabled=False)
    )


def resolve_recipients(campaign):
    """Return the ordered user queryset a campaign would deliver to."""
    qs = eligible_client_queryset()
    audience = campaign.audience
    if audience == Campaign.AUDIENCE_SUBSCRIBERS:
        qs = qs.filter(subscriptions__is_active=True).distinct()
    elif audience == Campaign.AUDIENCE_NON_SUBSCRIBERS:
        qs = qs.exclude(subscriptions__is_active=True).distinct()
    elif audience == Campaign.AUDIENCE_SELECTED:
        qs = qs.filter(pk__in=campaign.selected_users.values_list('pk', flat=True))
    return qs.order_by('pk')


def resolved_email_map(campaign):
    """Return {user_pk: email} for recipients with a valid address."""
    pairs = resolve_recipients(campaign).values_list('pk', 'email')
    mapping = {}
    seen = set()
    for pk, email in pairs:
        cleaned = valid_recipients([email])
        if not cleaned:
            continue
        address = cleaned[0]
        key = address.lower()
        if key in seen:
            continue
        seen.add(key)
        mapping[pk] = address
    return mapping
