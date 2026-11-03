"""Centralized CRM customer synchronization.

The centralized client profile (``UserProfile``) is the source of truth for
reusable client information; the CRM ``Customer`` mirrors the parts of it that
the admin team needs.

``sync_customer_for_user`` implements the single synchronization entry point:

- idempotent (looks the customer up by linked user, then by email),
- transactional (wrapped in a database transaction),
- never overwrites curated CRM data with empty values,
- refreshes mirrored profile values coming from the (newer) profile.
"""
from django.db import transaction
from django.utils import timezone

from ..models import Customer

# Customer fields that mirror centralized profile information.
CUSTOMER_MIRROR_FIELDS = (
    'name',
    'phone',
    'customer_type',
    'company_name',
    'industry',
    'website',
    'job_title',
    'country',
    'city',
    'business_address',
    'business_description',
    'company_size',
)


def build_customer_values(user, profile=None):
    """Map a user + profile to normalized CRM ``Customer`` field values.

    Empty values are kept as empty strings so callers can decide whether an
    update should be persisted.
    """
    from users.services.profile_service import build_profile_payload

    payload = build_profile_payload(user, profile=profile)
    full_name = payload.get('full_name') or ''
    company_name = payload.get('company') or payload.get('company_name') or ''
    email = payload.get('email') or ''

    return {
        'name': company_name or full_name,
        'email': email,
        'phone': payload.get('phone') or '',
        'customer_type': 'COMPANY' if company_name else 'INDIVIDUAL',
        'company_name': company_name,
        'industry': payload.get('industry') or '',
        'website': payload.get('website') or '',
        'job_title': payload.get('job_title') or '',
        'country': payload.get('country') or '',
        'city': payload.get('city') or '',
        'business_address': payload.get('business_address') or '',
        'business_description': payload.get('business_description') or '',
        'company_size': payload.get('company_size') or '',
    }


def sync_customer_for_user(user, profile=None, source='Onboarding', changed_fields=None):
    """Synchronize (or create) the CRM customer for ``user`` from their profile.

    Returns ``(customer, changed_fields)``. ``changed_fields`` is empty when
    nothing was modified; ``['created']`` is returned when a new customer record
    was created.

    When ``changed_fields`` is provided, only those profile fields are mirrored to
    the CRM, which preserves manually curated CRM data that is not part of the
    latest user profile change set.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return None, []
    if not (user.email or '').strip():
        return None, []

    changed_field_set = set(changed_fields or [])
    field_aliases = {
        'display_name': {'name'},
        'company_name': {'name', 'company_name'},
        'phone_number': {'phone'},
        'industry': {'industry'},
        'company_size': {'company_size'},
        'country': {'country'},
        'job_title': {'job_title'},
        'city': {'city'},
        'website': {'website'},
        'business_address': {'business_address'},
        'business_description': {'business_description'},
    }

    with transaction.atomic():
        customer = Customer.objects.select_for_update().filter(user=user).first()
        if customer is None:
            customer = Customer.objects.filter(email__iexact=user.email.strip()).first()

        values = build_customer_values(user, profile)
        email = (values.pop('email') or user.email.strip()).strip()

        if customer is None:
            customer = Customer.objects.create(
                user=user,
                email=email,
                source=source,
                **values,
            )
            customer.profile_sync_status = 'SYNCED'
            customer.profile_last_synced_at = timezone.now()
            customer.save(update_fields=['profile_sync_status', 'profile_last_synced_at'])
            return customer, ['created']

        changed = []
        if customer.user_id is None:
            customer.user = user
            changed.append('user')

        for field in CUSTOMER_MIRROR_FIELDS:
            if field == 'customer_type':
                continue
            value = (values.get(field) or '').strip()
            current = (getattr(customer, field, None) or '').strip()
            if value and not current:
                setattr(customer, field, value)
                changed.append(field)
                continue

            if changed_field_set:
                direct_matches = set()
                for profile_field, crm_fields in field_aliases.items():
                    if profile_field in changed_field_set and field in crm_fields:
                        direct_matches.add(profile_field)
                if field == 'name' and ('display_name' in changed_field_set or 'company_name' in changed_field_set):
                    direct_matches.add('name')
                if direct_matches and value and value != current:
                    setattr(customer, field, value)
                    changed.append(field)

        customer_type = (values.get('customer_type') or '').strip()
        should_refresh_customer_type = (
            not changed_field_set
            or 'company_name' in changed_field_set
            or 'display_name' in changed_field_set
        )
        if customer_type and should_refresh_customer_type:
            if customer.customer_type != customer_type:
                customer.customer_type = customer_type
                changed.append('customer_type')

        customer.profile_last_synced_at = timezone.now()
        customer.profile_sync_status = 'SYNCED'

        update_fields = ['profile_last_synced_at', 'profile_sync_status']
        if changed:
            update_fields += [field for field in changed if field != 'user']
            if 'user' in changed:
                update_fields.append('user')
            customer.save(update_fields=update_fields)
        else:
            customer.save(update_fields=['profile_last_synced_at', 'profile_sync_status'])

        return customer, changed
