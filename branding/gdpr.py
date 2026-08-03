"""GDPR anonymization utilities for the Branding Service.

Provides functions to:
- Anonymize PII in completed/expired branding requests
- Remove personal data while preserving analytics integrity
- Bulk anonymize requests that have exceeded their retention period
"""
import hashlib
import logging

from django.utils import timezone

logger = logging.getLogger('branding.gdpr')


# ---------------------------------------------------------------------------
# PII field definitions
# ---------------------------------------------------------------------------

# Fields on BrandingRequest that contain personal information
REQUEST_PII_FIELDS = [
    'company_name', 'website', 'country', 'business_description',
    'company_description', 'target_audience', 'internal_notes',
    'additional_notes',
]

# Fields on BrandingMessage that contain personal information
MESSAGE_PII_FIELDS = ['content']

# Fields on BrandingTimeline that contain personal information
TIMELINE_PII_FIELDS = ['action', 'description']

# Fields on BrandingAsset that contain personal information
ASSET_PII_FIELDS = ['original_name', 'sanitized_name', 'scan_result']

# Pseudonymization marker
_ANON_MARKER = '[ANONYMIZED]'
_HASH_SALT = 'branding-gdpr-anonymization-v1'


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------

def _pseudonymize(value, field_name=''):
    """Replace a value with a deterministic pseudonymized hash.

    The same input always produces the same output, allowing
    aggregate analytics while removing identifiable text.
    """
    if not value or value == _ANON_MARKER:
        return _ANON_MARKER
    raw = f'{_HASH_SALT}:{field_name}:{value}'
    return f'anon_{hashlib.sha256(raw.encode()).hexdigest()[:12]}'


# ---------------------------------------------------------------------------
# Single-request anonymization
# ---------------------------------------------------------------------------

def anonymize_request(request_obj, keep_analytics=True):
    """Anonymize all PII in a BrandingRequest and its related objects.

    Args:
        request_obj: BrandingRequest instance
        keep_analytics: if True, preserves numeric/aggregated data for analytics

    Returns:
        dict with counts of anonymized objects
    """
    from .models import BrandingMessage, BrandingTimeline, BrandingAsset

    counts = {
        'messages': 0,
        'timelines': 0,
        'assets': 0,
    }

    # 1. Anonymize the request itself
    update_fields = []
    for field in REQUEST_PII_FIELDS:
        old_val = getattr(request_obj, field, '')
        if old_val and old_val != _ANON_MARKER:
            if keep_analytics:
                setattr(request_obj, field, _ANON_MARKER)
            else:
                setattr(request_obj, field, '')
            update_fields.append(field)

    # Clear designer assignment (PII)
    if request_obj.designer_id:
        request_obj.designer = None
        update_fields.append('designer')

    # Clear consent fields
    request_obj.consent_data_processing = False
    request_obj.consent_marketing = False
    request_obj.consent_analytics = False
    request_obj.consent_third_party = False
    request_obj.consent_timestamp = None
    update_fields.extend([
        'consent_data_processing', 'consent_marketing',
        'consent_analytics', 'consent_third_party', 'consent_timestamp',
    ])

    # Mark as anonymized
    request_obj.anonymized = True
    request_obj.anonymized_at = timezone.now()
    update_fields.extend(['anonymized', 'anonymized_at'])

    if update_fields:
        request_obj.save(update_fields=update_fields)

    # 2. Anonymize messages
    messages = BrandingMessage.objects.filter(request=request_obj)
    for msg in messages:
        msg_updates = {}
        for field in MESSAGE_PII_FIELDS:
            val = getattr(msg, field, '')
            if val and val != _ANON_MARKER:
                msg_updates[field] = _ANON_MARKER if keep_analytics else ''
        if msg_updates:
            msg.save(update_fields=list(msg_updates.keys()))
            counts['messages'] += 1

    # 3. Anonymize timeline entries
    timelines = BrandingTimeline.objects.filter(request=request_obj)
    for tl in timelines:
        tl_updates = {}
        for field in TIMELINE_PII_FIELDS:
            val = getattr(tl, field, '')
            if val and val != _ANON_MARKER:
                tl_updates[field] = _ANON_MARKER if keep_analytics else ''
        # Clear actor reference
        if tl.actor_id:
            tl.actor = None
            tl_updates['actor'] = None
        if tl_updates:
            tl.save(update_fields=list(tl_updates.keys()))
            counts['timelines'] += 1

    # 4. Anonymize asset metadata (keep files for now, just clear names)
    assets = BrandingAsset.objects.filter(request=request_obj)
    for asset in assets:
        asset_updates = {}
        for field in ASSET_PII_FIELDS:
            val = getattr(asset, field, '')
            if val and val != _ANON_MARKER:
                asset_updates[field] = _ANON_MARKER if keep_analytics else ''
        # Clear detected MIME and hash (could be identifying)
        if asset.detected_mime:
            asset_updates['detected_mime'] = ''
        if asset.file_hash:
            asset_updates['file_hash'] = ''
        if asset_updates:
            asset.save(update_fields=list(asset_updates.keys()))
            counts['assets'] += 1

    logger.info(
        'Anonymized request %s: %d messages, %d timelines, %d assets',
        request_obj.request_number, counts['messages'], counts['timelines'], counts['assets'],
    )

    return counts


# ---------------------------------------------------------------------------
# Bulk anonymization
# ---------------------------------------------------------------------------

def anonymize_expired_requests(batch_size=100):
    """Find and anonymize all requests whose retention period has expired.

    Returns the number of requests anonymized.
    """
    from .models import BrandingRequest

    now = timezone.now()
    expired = BrandingRequest.objects.filter(
        anonymized=False,
        retention_period__in=['1y', '2y', '3y', '5y', '7y'],
    )

    anonymized_count = 0
    for req in expired[:batch_size]:
        if req.is_retention_expired:
            try:
                anonymize_request(req, keep_analytics=True)
                anonymized_count += 1
            except Exception as exc:
                logger.error(
                    'Failed to anonymize request %s: %s',
                    req.request_number, exc,
                )

    if anonymized_count:
        logger.info('Anonymized %d expired requests', anonymized_count)

    return anonymized_count


def anonymize_user_data(user):
    """Anonymize ALL branding data for a specific user (right to erasure).

    This is a more aggressive anonymization — removes all PII without
    keeping analytics data.
    """
    from .models import BrandingRequest

    requests = BrandingRequest.objects.filter(user=user, anonymized=False)
    total = 0
    for req in requests:
        try:
            anonymize_request(req, keep_analytics=False)
            total += 1
        except Exception as exc:
            logger.error('Failed to anonymize request %s for user %s: %s', req.pk, user.pk, exc)

    # Also clear user reference on all requests
    requests.update(user=None)

    logger.info('Anonymized %d requests for user %s', total, user.pk)
    return total


# ---------------------------------------------------------------------------
# Privacy consent helpers
# ---------------------------------------------------------------------------

def record_consent(user, consent_type, action, request_obj=None, ip_address=None, user_agent=''):
    """Record a consent grant or revocation."""
    from .models import ConsentRecord

    record = ConsentRecord.objects.create(
        user=user,
        request=request_obj,
        consent_type=consent_type,
        action=action,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # Update the request's consent fields if applicable
    if request_obj:
        field_map = {
            'data_processing': 'consent_data_processing',
            'marketing': 'consent_marketing',
            'analytics': 'consent_analytics',
            'third_party': 'consent_third_party',
        }
        field_name = field_map.get(consent_type)
        if field_name:
            setattr(request_obj, field_name, action == ConsentRecord.ACTION_GRANTED)
            if action == ConsentRecord.ACTION_GRANTED:
                request_obj.consent_timestamp = timezone.now()
            request_obj.save(update_fields=[field_name, 'consent_timestamp'])

    logger.info(
        'Consent %s: user=%s type=%s action=%s',
        record.pk, user.pk, consent_type, action,
    )

    return record


def record_privacy_acceptance(user, page, version='1.0', accepted=True, ip_address=None):
    """Record acceptance or rejection of a privacy document."""
    from .models import PrivacyAcceptance

    obj, created = PrivacyAcceptance.objects.update_or_create(
        user=user,
        page=page,
        defaults={
            'version': version,
            'accepted': accepted,
            'ip_address': ip_address,
        },
    )

    logger.info(
        'Privacy %s: user=%s page=%s v%s accepted=%s',
        'acceptance' if created else 'update',
        user.pk, page, version, accepted,
    )

    return obj


def get_user_consents(user):
    """Get the current consent status for a user across all types."""
    from .models import ConsentRecord

    consents = {}
    for consent_type, _ in [('data_processing', ''), ('marketing', ''), ('analytics', ''), ('third_party', '')]:
        latest = ConsentRecord.objects.filter(
            user=user, consent_type=consent_type,
        ).order_by('-created_at').first()
        consents[consent_type] = {
            'granted': latest.action == ConsentRecord.ACTION_GRANTED if latest else False,
            'timestamp': latest.created_at.isoformat() if latest else None,
            'record_id': latest.pk if latest else None,
        }

    return consents


def get_privacy_acceptances(user):
    """Get the current privacy acceptance status for a user."""
    from .models import PrivacyAcceptance

    return {
        page: {
            'accepted': True,
            'version': acc.version,
            'accepted_at': acc.created_at.isoformat(),
        }
        for page, _ in PRIVACY_PAGES
        if PrivacyAcceptance.objects.filter(
            user=user, page=page, accepted=True,
        ).exists()
    }
