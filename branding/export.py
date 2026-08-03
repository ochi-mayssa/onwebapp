"""GDPR data export for the Branding Service.

Generates JSON and CSV exports of all user data
as required by GDPR Article 20 (data portability).
"""
import csv
import io
import json
import logging

from django.http import HttpResponse
from django.utils import timezone

logger = logging.getLogger('branding.gdpr')


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------

def export_user_data_json(user):
    """Generate a complete JSON export of a user's branding data.

    Returns a dict with all user-related data.
    """
    from .models import (
        BrandingRequest, BrandingMessage, BrandingTimeline,
        BrandingAsset, BrandingAssetVersion, BrandingFeedback,
        ConsentRecord, DataExportRequest, PrivacyAcceptance,
    )

    requests = BrandingRequest.objects.filter(user=user)
    request_pks = list(requests.values_list('pk', flat=True))

    export = {
        'export_info': {
            'generated_at': timezone.now().isoformat(),
            'user_id': user.pk,
            'username': getattr(user, 'username', ''),
            'email': getattr(user, 'email', ''),
        },
        'profile': {
            'username': getattr(user, 'username', ''),
            'email': getattr(user, 'email', ''),
            'first_name': getattr(user, 'first_name', ''),
            'last_name': getattr(user, 'last_name', ''),
            'date_joined': user.date_joined.isoformat() if hasattr(user, 'date_joined') else None,
        },
        'branding_requests': [],
        'messages': [],
        'timeline_events': [],
        'assets': [],
        'asset_versions': [],
        'feedback': [],
        'consent_records': [],
        'privacy_acceptances': [],
    }

    # Branding requests
    for req in requests:
        export['branding_requests'].append({
            'request_number': req.request_number,
            'status': req.status,
            'company_name': req.company_name,
            'industry': req.industry,
            'website': req.website,
            'country': req.country,
            'business_description': req.business_description,
            'company_description': req.company_description,
            'target_audience': req.target_audience,
            'brand_values': req.brand_values,
            'preferred_colors': req.preferred_colors,
            'current_branding': req.current_branding,
            'additional_notes': req.additional_notes,
            'priority': req.priority,
            'estimated_delivery_date': req.estimated_delivery_date.isoformat() if req.estimated_delivery_date else None,
            'completed_at': req.completed_at.isoformat() if req.completed_at else None,
            'created_at': req.created_at.isoformat(),
            'updated_at': req.updated_at.isoformat(),
            'consent': req.get_consent_dict(),
            'retention_period': req.retention_period,
            'collection': req.collection.name if req.collection else None,
        })

    # Messages
    messages = BrandingMessage.objects.filter(request_id__in=request_pks)
    for msg in messages:
        export['messages'].append({
            'request_number': msg.request.request_number if msg.request else None,
            'sender': str(msg.sender) if msg.sender else None,
            'content': msg.content,
            'is_read_by_client': msg.is_read_by_client,
            'is_read_by_staff': msg.is_read_by_staff,
            'created_at': msg.created_at.isoformat(),
        })

    # Timeline
    timelines = BrandingTimeline.objects.filter(request_id__in=request_pks)
    for tl in timelines:
        export['timeline_events'].append({
            'request_number': tl.request.request_number if tl.request else None,
            'event_type': tl.event_type,
            'action': tl.action,
            'description': tl.description,
            'actor': str(tl.actor) if tl.actor else None,
            'created_at': tl.created_at.isoformat(),
        })

    # Assets
    assets = BrandingAsset.objects.filter(request_id__in=request_pks)
    asset_pks = list(assets.values_list('pk', flat=True))
    for asset in assets:
        export['assets'].append({
            'request_number': asset.request.request_number if asset.request else None,
            'original_name': asset.original_name,
            'asset_type': asset.asset_type,
            'content_type': asset.content_type,
            'size': asset.size,
            'scan_status': asset.scan_status,
            'uploaded_at': asset.uploaded_at.isoformat(),
        })

    # Asset versions
    versions = BrandingAssetVersion.objects.filter(asset_id__in=asset_pks)
    for ver in versions:
        export['asset_versions'].append({
            'asset_original_name': ver.asset.original_name if ver.asset else None,
            'version_number': ver.version_number,
            'original_name': ver.original_name,
            'content_type': ver.content_type,
            'size': ver.size,
            'note': ver.note,
            'uploaded_by': str(ver.uploaded_by) if ver.uploaded_by else None,
            'created_at': ver.created_at.isoformat(),
        })

    # Feedback
    feedback = BrandingFeedback.objects.filter(request_id__in=request_pks)
    for fb in feedback:
        export['feedback'].append({
            'request_number': fb.request.request_number if fb.request else None,
            'rating': fb.rating,
            'comment': fb.comment,
            'would_recommend': fb.would_recommend,
            'staff_response': fb.staff_response,
            'created_at': fb.created_at.isoformat(),
        })

    # Consent records
    consents = ConsentRecord.objects.filter(user=user)
    for c in consents:
        export['consent_records'].append({
            'consent_type': c.consent_type,
            'action': c.action,
            'ip_address': c.ip_address,
            'created_at': c.created_at.isoformat(),
        })

    # Privacy acceptances
    privacies = PrivacyAcceptance.objects.filter(user=user)
    for p in privacies:
        export['privacy_acceptances'].append({
            'page': p.page,
            'version': p.version,
            'accepted': p.accepted,
            'created_at': p.created_at.isoformat(),
        })

    return export


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def export_user_data_csv(user):
    """Generate a CSV export of a user's branding data.

    Returns an HttpResponse with the CSV file attached.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # -- Requests sheet --
    writer.writerow(['=== BRANDING REQUESTS ==='])
    writer.writerow([
        'Request Number', 'Status', 'Company', 'Industry', 'Website',
        'Country', 'Description', 'Priority', 'Created', 'Completed',
    ])
    for req in BrandingRequest.objects.filter(user=user):
        writer.writerow([
            req.request_number, req.status, req.company_name, req.industry,
            req.website, req.country, req.business_description,
            req.priority, req.created_at.isoformat(),
            req.completed_at.isoformat() if req.completed_at else '',
        ])
    writer.writerow([])

    # -- Messages sheet --
    writer.writerow(['=== MESSAGES ==='])
    writer.writerow(['Request', 'Sender', 'Content', 'Read (Client)', 'Read (Staff)', 'Date'])
    request_pks = list(BrandingRequest.objects.filter(user=user).values_list('pk', flat=True))
    for msg in BrandingMessage.objects.filter(request_id__in=request_pks):
        writer.writerow([
            msg.request.request_number if msg.request else '',
            str(msg.sender) if msg.sender else '',
            msg.content,
            msg.is_read_by_client, msg.is_read_by_staff,
            msg.created_at.isoformat(),
        ])
    writer.writerow([])

    # -- Assets sheet --
    writer.writerow(['=== ASSETS ==='])
    writer.writerow(['Request', 'Name', 'Type', 'Size', 'Scan Status', 'Uploaded'])
    for asset in BrandingAsset.objects.filter(request_id__in=request_pks):
        writer.writerow([
            asset.request.request_number if asset.request else '',
            asset.original_name, asset.asset_type, asset.size,
            asset.scan_status, asset.uploaded_at.isoformat(),
        ])
    writer.writerow([])

    # -- Consent sheet --
    writer.writerow(['=== CONSENT RECORDS ==='])
    writer.writerow(['Type', 'Action', 'IP Address', 'Date'])
    for c in ConsentRecord.objects.filter(user=user):
        writer.writerow([
            c.consent_type, c.action, c.ip_address or '',
            c.created_at.isoformat(),
        ])

    content = output.getvalue()
    response = HttpResponse(content, content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="branding_data_export_{user.pk}_{timezone.now():%Y%m%d}.csv"'
    return response


def export_user_data_json_response(user):
    """Generate a JSON HttpResponse for user data export."""
    data = export_user_data_json(user)
    content = json.dumps(data, indent=2, default=str)
    response = HttpResponse(content, content_type='application/json; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="branding_data_export_{user.pk}_{timezone.now():%Y%m%d}.json"'
    return response
