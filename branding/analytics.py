"""Analytics data aggregation for the Branding Service.

Provides functions to:
- Aggregate daily metrics from raw data
- Compute staff workload statistics
- Track collection performance
- Generate chart data for the analytics dashboard
"""
import csv
import io
import json
import logging
from datetime import timedelta

from django.db.models import (
    Avg, Count, F, Q, Sum, Value,
)
from django.db.models.functions import TruncDate, TruncMonth
from django.http import HttpResponse
from django.utils import timezone

logger = logging.getLogger('branding.analytics')


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _parse_date_range(request):
    """Extract date_from/date_to from request GET params."""
    today = timezone.now().date()
    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')

    try:
        date_from = timezone.datetime.strptime(date_from, '%Y-%m-%d').date() if date_from else today - timedelta(days=30)
    except ValueError:
        date_from = today - timedelta(days=30)

    try:
        date_to = timezone.datetime.strptime(date_to, '%Y-%m-%d').date() if date_to else today
    except ValueError:
        date_to = today

    return date_from, date_to


# ---------------------------------------------------------------------------
# Overview metrics
# ---------------------------------------------------------------------------

def get_overview_metrics(date_from, date_to):
    """Compute overview metrics for the analytics dashboard."""
    from .models import BrandingRequest, BrandingFeedback, BrandingMessage, BrandingAsset

    base_qs = BrandingRequest.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )

    # Status distribution
    status_dist = dict(
        base_qs.values_list('status')
        .annotate(count=Count('id'))
        .values_list('status', 'count')
    )

    # Priority distribution
    priority_dist = dict(
        base_qs.values_list('priority')
        .annotate(count=Count('id'))
        .values_list('priority', 'count')
    )

    # Industry breakdown
    industry_dist = list(
        base_qs.exclude(industry='')
        .values('industry')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )

    # Completion rate
    total = base_qs.count()
    completed = base_qs.filter(status='COMPLETED').count()
    completion_rate = (completed / total * 100) if total > 0 else 0

    # Average satisfaction
    feedback_qs = BrandingFeedback.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )
    avg_satisfaction = feedback_qs.aggregate(avg=Avg('rating'))['avg'] or 0

    # Total messages
    total_messages = BrandingMessage.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    ).count()

    # Total uploads
    total_uploads = BrandingAsset.objects.filter(
        uploaded_at__date__gte=date_from,
        uploaded_at__date__lte=date_to,
    ).count()

    return {
        'total_requests': total,
        'completed_requests': completed,
        'completion_rate': round(completion_rate, 1),
        'status_distribution': status_dist,
        'priority_distribution': priority_dist,
        'industry_breakdown': industry_dist,
        'avg_satisfaction': round(avg_satisfaction, 2),
        'total_messages': total_messages,
        'total_uploads': total_uploads,
    }


def get_requests_over_time(date_from, date_to):
    """Get daily request counts for line chart."""
    from .models import BrandingRequest

    data = (
        BrandingRequest.objects.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )
        .annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(
            new=Count('id'),
            completed=Count('id', filter=Q(status='COMPLETED')),
        )
        .order_by('date')
    )

    return {
        'labels': [d['date'].strftime('%b %d') for d in data],
        'new': [d['new'] for d in data],
        'completed': [d['completed'] for d in data],
    }


# ---------------------------------------------------------------------------
# Staff metrics
# ---------------------------------------------------------------------------

def get_staff_metrics(date_from, date_to):
    """Get staff performance metrics."""
    from django.contrib.auth import get_user_model
    from .models import BrandingRequest, BrandingMessage

    User = get_user_model()
    staff_users = User.objects.filter(is_staff=True)

    metrics = []
    for staff in staff_users:
        assigned = BrandingRequest.objects.filter(
            designer=staff,
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        ).count()

        in_progress = BrandingRequest.objects.filter(
            designer=staff,
            status__in=['ASSIGNED', 'DESIGNING', 'WAITING_CLIENT', 'REVISION'],
        ).count()

        completed = BrandingRequest.objects.filter(
            designer=staff,
            status='COMPLETED',
            completed_at__date__gte=date_from,
            completed_at__date__lte=date_to,
        ).count()

        messages = BrandingMessage.objects.filter(
            sender=staff,
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        ).count()

        metrics.append({
            'user': staff,
            'assigned': assigned,
            'in_progress': in_progress,
            'completed': completed,
            'messages': messages,
        })

    # Sort by completed descending
    metrics.sort(key=lambda x: x['completed'], reverse=True)

    return metrics


# ---------------------------------------------------------------------------
# Collection metrics
# ---------------------------------------------------------------------------

def get_collection_metrics(date_from, date_to):
    """Get collection popularity and performance metrics."""
    from .models import BrandCollection, BrandingRequest, BrandingFeedback

    collections = BrandCollection.objects.filter(is_active=True)
    metrics = []

    for col in collections:
        requests = BrandingRequest.objects.filter(
            collection=col,
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )
        total = requests.count()
        completed = requests.filter(status='COMPLETED').count()

        # Get feedback for requests using this collection
        feedback = BrandingFeedback.objects.filter(
            request__collection=col,
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )
        avg_rating = feedback.aggregate(avg=Avg('rating'))['avg'] or 0

        metrics.append({
            'collection': col,
            'total_requests': total,
            'completed': completed,
            'completion_rate': round((completed / total * 100) if total > 0 else 0, 1),
            'avg_satisfaction': round(avg_rating, 2),
        })

    metrics.sort(key=lambda x: x['total_requests'], reverse=True)
    return metrics


# ---------------------------------------------------------------------------
# Timeline metrics (monthly aggregation)
# ---------------------------------------------------------------------------

def get_timeline_metrics(date_from, date_to):
    """Get monthly aggregated metrics for the timeline view."""
    from .models import BrandingRequest, BrandingFeedback

    monthly = (
        BrandingRequest.objects.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(
            new=Count('id'),
            completed=Count('id', filter=Q(status='COMPLETED')),
            avg_satisfaction=Avg(
                'feedback__rating',
                filter=Q(feedback__rating__isnull=False),
            ),
        )
        .order_by('month')
    )

    return {
        'labels': [d['month'].strftime('%b %Y') for d in monthly],
        'new': [d['new'] for d in monthly],
        'completed': [d['completed'] for d in monthly],
        'satisfaction': [round(d['avg_satisfaction'] or 0, 2) for d in monthly],
    }


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def export_analytics_csv(date_from, date_to):
    """Export analytics data as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Overview
    overview = get_overview_metrics(date_from, date_to)
    writer.writerow(['=== ANALYTICS REPORT ==='])
    writer.writerow([f'Date Range: {date_from} to {date_to}'])
    writer.writerow([])
    writer.writerow(['Metric', 'Value'])
    writer.writerow(['Total Requests', overview['total_requests']])
    writer.writerow(['Completed', overview['completed_requests']])
    writer.writerow(['Completion Rate', f"{overview['completion_rate']}%"])
    writer.writerow(['Avg Satisfaction', overview['avg_satisfaction']])
    writer.writerow(['Total Messages', overview['total_messages']])
    writer.writerow(['Total Uploads', overview['total_uploads']])
    writer.writerow([])

    # Status distribution
    writer.writerow(['=== STATUS DISTRIBUTION ==='])
    writer.writerow(['Status', 'Count'])
    for status, count in overview['status_distribution'].items():
        writer.writerow([status, count])
    writer.writerow([])

    # Staff metrics
    writer.writerow(['=== STAFF PERFORMANCE ==='])
    writer.writerow(['Staff', 'Assigned', 'In Progress', 'Completed', 'Messages'])
    for m in get_staff_metrics(date_from, date_to):
        writer.writerow([
            m['user'].get_full_name() or m['user'].username,
            m['assigned'], m['in_progress'], m['completed'], m['messages'],
        ])
    writer.writerow([])

    # Collection metrics
    writer.writerow(['=== COLLECTION PERFORMANCE ==='])
    writer.writerow(['Collection', 'Requests', 'Completed', 'Completion %', 'Avg Rating'])
    for m in get_collection_metrics(date_from, date_to):
        writer.writerow([
            m['collection'].name, m['total_requests'], m['completed'],
            f"{m['completion_rate']}%", m['avg_satisfaction'],
        ])

    content = output.getvalue()
    response = HttpResponse(content, content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="branding_analytics_{date_from}_{date_to}.csv"'
    return response
