"""Centralized client profile service.

``UserProfile`` is the single source of truth for reusable client information
(full name, contact details, company details and onboarding choices).

This module exposes the canonical helpers used by:

- the onboarding wizard (read initial values, persist the submitted profile),
- the profile editing screens (persist updates, detect changed fields),
- every client-facing form (build the prefill payload).

Nothing else in the platform should reach into the profile models directly for
prefill or persistence; they should go through this service so behaviour stays
consistent and reusable.
"""
from django.contrib.auth import get_user_model

from ..models import UserProfile

User = get_user_model()


# Profile fields that hold free-form / text values.
PROFILE_STRING_FIELDS = (
    'display_name',
    'bio',
    'avatar',
    'phone_number',
    'company_name',
    'industry',
    'company_size',
    'country',
    'job_title',
    'city',
    'website',
    'business_address',
    'business_description',
)

# Profile fields that hold onboarding choices.
PROFILE_CHOICE_FIELDS = (
    'service_type',
    'project_description',
    'start_timeline',
)


def get_or_create_profile(user):
    """Return the centralized profile for ``user`` (or ``None`` when anonymous)."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return None
    profile, _created = UserProfile.objects.get_or_create(user=user)
    return profile


def _clean(value):
    """Normalize any incoming value into a stripped string."""
    if value is None:
        return ''
    if not isinstance(value, str):
        value = str(value)
    return value.strip()


def _field(profile, name):
    if profile is None:
        return ''
    return _clean(getattr(profile, name, '') or '')


def _user_value(user, name):
    if user is None:
        return ''
    if name == 'full_name':
        return _clean(
            f"{getattr(user, 'first_name', None) or ''} "
            f"{getattr(user, 'last_name', None) or ''}".strip()
        )
    if name == 'email':
        return _clean(getattr(user, 'email', None) or '')
    return _clean(getattr(user, name, None) or '')


def build_profile_payload(user, profile=None):
    """Build the canonical, normalized payload of a client's reusable info.

    The payload is keyed with the names used by the most common client-facing
    forms (``full_name``/``name``, ``email``/``business_email``, ``company``/
    ``company_name``, ...) so any form can consume it directly as ``initial`` or
    for further processing without per-form mapping tables.
    """
    if profile is None and user is not None and getattr(user, 'is_authenticated', False):
        profile = get_or_create_profile(user)

    full_name = (
        _field(profile, 'display_name')
        or _user_value(user, 'full_name')
        or _clean(getattr(user, 'username', None) or '')
    )
    company_name = _field(profile, 'company_name')
    email = _user_value(user, 'email')

    return {
        # Identity
        'full_name': full_name,
        'name': full_name,
        'email': email,
        'business_email': email,
        'phone': _field(profile, 'phone_number'),
        'phone_number': _field(profile, 'phone_number'),
        'job_title': _field(profile, 'job_title'),
        # Company / business
        'company': company_name,
        'company_name': company_name,
        'industry': _field(profile, 'industry'),
        'company_size': _field(profile, 'company_size'),
        'website': _field(profile, 'website'),
        'country': _field(profile, 'country'),
        'city': _field(profile, 'city'),
        'business_address': _field(profile, 'business_address'),
        'business_description': _field(profile, 'business_description'),
        # Onboarding choices (kept for future service/project forms)
        'service_type': _field(profile, 'service_type'),
        'project_description': _field(profile, 'project_description'),
        'start_timeline': _field(profile, 'start_timeline'),
        'community_needs': list(getattr(profile, 'community_needs', None) or []) if profile is not None else [],
        'source': 'profile',
    }


DEFAULT_PROFILE_FIELD_MAPPING = {
    'full_name': ('full_name', 'name'),
    'name': ('full_name', 'name'),
    'email': ('email', 'business_email'),
    'business_email': ('email', 'business_email'),
    'phone': ('phone', 'phone_number'),
    'phone_number': ('phone', 'phone_number'),
    'company': ('company', 'company_name', 'business_name'),
    'company_name': ('company', 'company_name', 'business_name'),
    'job_title': ('job_title', 'position'),
    'industry': ('industry', 'business_industry'),
    'company_size': ('company_size', 'business_size'),
    'website': ('website', 'business_website'),
    'country': ('country', 'business_country'),
    'city': ('city', 'business_city'),
    'business_address': ('business_address', 'address', 'street_address'),
    'business_description': ('business_description', 'description'),
}


def apply_profile_prefill(form, user, profile=None, field_mapping=None):
    """Populate a form's initial values from the centralized client profile.

    The function is intentionally generic: it only sets missing values on the form,
    leaving user-entered or explicitly supplied initial values untouched.
    """
    if form is None:
        return form
    payload = build_profile_payload(user, profile=profile)
    mapping = dict(DEFAULT_PROFILE_FIELD_MAPPING)
    if field_mapping:
        mapping.update(field_mapping)

    if hasattr(form, 'initial') and not isinstance(form.initial, dict):
        form.initial = dict(form.initial)
    form.initial = form.initial or {}

    for field_name in list(getattr(form, 'fields', {}).keys()):
        if field_name in form.initial and form.initial.get(field_name) not in ('', None):
            continue
        candidates = tuple(mapping.get(field_name, (field_name,)))
        value = None
        for key in candidates:
            if payload.get(key, '') not in ('', None):
                value = payload.get(key)
                break
        if value in ('', None):
            continue
        form.initial[field_name] = value
        field = form.fields.get(field_name)
        if field is not None and getattr(field, 'initial', None) in ('', None):
            field.initial = value

    return form


def update_profile(user, data, commit=True):
    """Persist a set of profile fields supplied as a mapping.

    ``data`` is expected to use centralized profile field names as keys (the
    same names used by the onboarding/profile models). Only fields present in
    ``data`` are written; values are normalized (stripped) before storing.

    Returns ``(profile, changed_fields)`` where ``changed_fields`` lists the
    profile fields whose value actually changed.
    """
    profile = get_or_create_profile(user)
    if profile is None:
        return None, []

    updates = {}
    changed = []

    for field in PROFILE_STRING_FIELDS:
        if data.get(field) is None:
            continue
        value = _clean(data.get(field))
        if value != _field(profile, field):
            changed.append(field)
        updates[field] = value

    for field in PROFILE_CHOICE_FIELDS:
        if data.get(field) is None:
            continue
        value = _clean(data.get(field))
        if value != _field(profile, field):
            changed.append(field)
        updates[field] = value

    community_needs = data.get('community_needs')
    if community_needs is not None:
        if isinstance(community_needs, (list, tuple)):
            needs = [str(item) for item in community_needs if str(item)]
        else:
            needs = [str(needs_item) for needs_item in str(community_needs).split(',') if str(needs_item).strip()]
        if list(getattr(profile, 'community_needs', None) or []) != needs:
            changed.append('community_needs')
        updates['community_needs'] = needs

    for field, value in updates.items():
        setattr(profile, field, value)

    if updates and commit:
        profile.save()

    return profile, changed
