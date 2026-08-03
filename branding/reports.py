"""PDF report generation for completed branding projects using WeasyPrint."""
import base64
import io
import os
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, F, Q
from django.db.models.functions import TruncMonth
from django.http import FileResponse, HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone

from .models import (
    STATUS_CHOICES,
    BrandCollection,
    BrandingFeedback,
    BrandingRequest,
)

User = get_user_model()


class ProjectSummaryReport:
    """Generates a professional PDF summary for a branding request."""

    def __init__(self, branding_request):
        self.request = branding_request
        self.assets = branding_request.assets.all()
        self.timeline = branding_request.timeline_entries.all().order_by('created_at')
        self.feedback = getattr(branding_request, 'feedback', None)

    def generate_pdf(self):
        """Render the HTML template and return a FileResponse with the PDF."""
        context = {
            'request': self.request,
            'assets': self.assets,
            'timeline': self.timeline,
            'feedback': self.feedback,
            'brand_values_display': self._display_list(self.request.brand_values, 'BRAND_VALUES'),
            'preferred_colors_display': self._display_list(self.request.preferred_colors, 'PREFERRED_COLORS'),
            'current_branding_display': self._display_list(self.request.current_branding, 'CURRENT_BRANDING'),
            'collection': self.request.collection,
            'generated_at': timezone.now(),
            'company_initial': (self.request.company_name or 'B')[0].upper(),
        }

        html_string = render_to_string('branding/pdf/project_report.html', context)

        from weasyprint import HTML
        pdf_bytes = HTML(
            string=html_string,
            base_url=self._get_base_url(),
        ).write_pdf()

        buffer = io.BytesIO(pdf_bytes)
        buffer.seek(0)

        filename = f"{self.request.request_number or 'report'}_summary.pdf"
        return FileResponse(
            buffer,
            as_attachment=True,
            filename=filename,
            content_type='application/pdf',
        )

    def _get_base_url(self):
        """Return the base URL for resolving static files in WeasyPrint."""
        return os.path.join(settings.BASE_DIR, 'static') + '/'

    def _display_list(self, items, constant_name):
        """Convert a list of codes to human-readable labels."""
        from .models import BRAND_VALUES, PREFERRED_COLORS, CURRENT_BRANDING_CHOICES

        lookup = {
            'BRAND_VALUES': dict(BRAND_VALUES),
            'PREFERRED_COLORS': dict(PREFERRED_COLORS),
            'CURRENT_BRANDING': dict(CURRENT_BRANDING_CHOICES),
        }
        mapping = lookup.get(constant_name, {})
        if not items:
            return '—'
        return ', '.join(mapping.get(item, item) for item in items)


# ---------------------------------------------------------------------------
# Analytics Report
# ---------------------------------------------------------------------------

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402


# Consistent color palette
PALETTE = {
    'primary': '#6366f1',
    'secondary': '#818cf8',
    'success': '#10b981',
    'warning': '#f59e0b',
    'danger': '#ef4444',
    'info': '#3b82f6',
    'muted': '#94a3b8',
    'bg': '#f8fafc',
    'text': '#1e293b',
}

STATUS_COLORS = {
    'DRAFT': '#94a3b8',
    'PENDING_REVIEW': '#f59e0b',
    'IN_REVIEW': '#f97316',
    'ASSIGNED': '#3b82f6',
    'DESIGNING': '#6366f1',
    'WAITING_CLIENT': '#8b5cf6',
    'REVISION': '#ef4444',
    'APPROVED': '#10b981',
    'COMPLETED': '#22c55e',
    'ARCHIVED': '#64748b',
}


def _fig_to_base64(fig):
    """Convert a matplotlib figure to a base64-encoded PNG string."""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


def _apply_style():
    """Apply a clean style to matplotlib."""
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['Segoe UI', 'DejaVu Sans', 'Arial'],
        'font.size': 10,
        'axes.titlesize': 13,
        'axes.titleweight': 'bold',
        'axes.labelsize': 10,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'figure.facecolor': 'white',
        'axes.facecolor': 'white',
        'axes.edgecolor': '#e2e8f0',
        'xtick.color': '#64748b',
        'ytick.color': '#64748b',
    })


class AnalyticsReport:
    """Generates an analytics PDF report for the branding staff dashboard."""

    def __init__(self, months=6):
        self.months = months
        self.now = timezone.now()
        self.cutoff = self.now - timedelta(days=months * 30)
        _apply_style()

    def generate_pdf(self):
        """Build all charts and render the analytics PDF."""
        context = {
            'generated_at': self.now,
            'report_period': f'{self.months} months',
            'charts': self._build_charts(),
            'data': self._build_data_tables(),
        }

        html_string = render_to_string('branding/pdf/analytics_report.html', context)

        from weasyprint import HTML
        pdf_bytes = HTML(
            string=html_string,
            base_url=os.path.join(settings.BASE_DIR, 'static') + '/',
        ).write_pdf()

        buffer = io.BytesIO(pdf_bytes)
        buffer.seek(0)

        filename = f"branding_analytics_{self.now.strftime('%Y_%m')}.pdf"
        return FileResponse(buffer, as_attachment=True, filename=filename, content_type='application/pdf')

    # ------------------------------------------------------------------
    # Chart builders (each returns a base64 PNG)
    # ------------------------------------------------------------------

    def _build_charts(self):
        return {
            'status_distribution': self._chart_status_distribution(),
            'monthly_trend': self._chart_monthly_trend(),
            'staff_workload': self._chart_staff_workload(),
            'collection_popularity': self._chart_collection_popularity(),
            'satisfaction': self._chart_satisfaction(),
            'industry_breakdown': self._chart_industry_breakdown(),
            'priority_distribution': self._chart_priority_distribution(),
            'completion_time': self._chart_completion_time(),
        }

    def _chart_status_distribution(self):
        qs = BrandingRequest.objects.values('status').annotate(cnt=Count('id')).order_by('status')
        data = {row['status']: row['cnt'] for row in qs}
        labels = [label for code, label in STATUS_CHOICES if data.get(code, 0) > 0]
        sizes = [data.get(code, 0) for code, _ in STATUS_CHOICES if data.get(code, 0) > 0]
        colors = [STATUS_COLORS.get(code, '#94a3b8') for code, _ in STATUS_CHOICES if data.get(code, 0) > 0]

        if not sizes:
            return None

        fig, ax = plt.subplots(figsize=(7, 3.5))
        bars = ax.barh(labels, sizes, color=colors, edgecolor='white', height=0.6)
        ax.set_xlabel('Number of Requests')
        ax.set_title('Requests by Status')
        for bar, val in zip(bars, sizes):
            ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2, str(val),
                    va='center', fontsize=9, color=PALETTE['text'], fontweight='bold')
        ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        fig.tight_layout()
        return _fig_to_base64(fig)

    def _chart_monthly_trend(self):
        qs = (
            BrandingRequest.objects
            .filter(created_at__gte=self.cutoff)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(total=Count('id'))
            .order_by('month')
        )
        months = [row['month'].strftime('%b %Y') for row in qs]
        totals = [row['total'] for row in qs]

        if not months:
            return None

        fig, ax = plt.subplots(figsize=(7, 3.5))
        ax.fill_between(range(len(months)), totals, alpha=0.15, color=PALETTE['primary'])
        ax.plot(range(len(months)), totals, color=PALETTE['primary'], linewidth=2.5, marker='o', markersize=7)
        for i, v in enumerate(totals):
            ax.annotate(str(v), (i, v), textcoords='offset points', xytext=(0, 10),
                        ha='center', fontsize=9, fontweight='bold', color=PALETTE['primary'])
        ax.set_xticks(range(len(months)))
        ax.set_xticklabels(months, rotation=30, ha='right', fontsize=8)
        ax.set_ylabel('Requests')
        ax.set_title('Monthly Request Trend')
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        fig.tight_layout()
        return _fig_to_base64(fig)

    def _chart_staff_workload(self):
        qs = (
            BrandingRequest.objects
            .filter(designer__isnull=False)
            .exclude(status__in=['DRAFT', 'ARCHIVED'])
            .values('designer__username')
            .annotate(cnt=Count('id'))
            .order_by('-cnt')[:10]
        )
        designers = [row['designer__username'] for row in qs]
        counts = [row['cnt'] for row in qs]

        if not designers:
            return None

        fig, ax = plt.subplots(figsize=(7, 3.5))
        gradient = plt.cm.viridis([i / max(len(designers) - 1, 1) for i in range(len(designers))])
        bars = ax.barh(designers[::-1], counts[::-1], color=gradient[::-1], edgecolor='white', height=0.6)
        ax.set_xlabel('Active Requests')
        ax.set_title('Staff Workload Distribution')
        for bar, val in zip(bars, counts[::-1]):
            ax.text(bar.get_width() + 0.2, bar.get_y() + bar.get_height() / 2, str(val),
                    va='center', fontsize=9, color=PALETTE['text'], fontweight='bold')
        ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        fig.tight_layout()
        return _fig_to_base64(fig)

    def _chart_collection_popularity(self):
        qs = (
            BrandingRequest.objects
            .filter(collection__isnull=False)
            .values('collection__name')
            .annotate(cnt=Count('id'))
            .order_by('-cnt')[:8]
        )
        names = [row['collection__name'] for row in qs]
        counts = [row['cnt'] for row in qs]

        if not names:
            return None

        fig, ax = plt.subplots(figsize=(5, 4))
        colors = plt.cm.Pastel1([i / max(len(names) - 1, 1) for i in range(len(names))])
        wedges, texts, autotexts = ax.pie(
            counts, labels=names, autopct='%1.0f%%', startangle=140,
            colors=colors, pctdistance=0.75,
            wedgeprops=dict(width=0.5, edgecolor='white', linewidth=2),
        )
        for t in autotexts:
            t.set_fontsize(8)
            t.set_fontweight('bold')
        for t in texts:
            t.set_fontsize(8)
        ax.set_title('Collection Popularity')
        fig.tight_layout()
        return _fig_to_base64(fig)

    def _chart_satisfaction(self):
        if not BrandingFeedback.objects.exists():
            return None

        qs = BrandingFeedback.objects.values('rating').annotate(cnt=Count('id')).order_by('rating')
        data = {row['rating']: row['cnt'] for row in qs}
        labels = [f'{i} Star{"s" if i > 1 else ""}' for i in range(1, 6)]
        sizes = [data.get(i, 0) for i in range(1, 6)]
        colors = ['#ef4444', '#f97316', '#f59e0b', '#84cc16', '#22c55e']

        fig, ax = plt.subplots(figsize=(7, 3))
        bars = ax.bar(labels, sizes, color=colors, edgecolor='white', width=0.55)
        ax.set_ylabel('Responses')
        ax.set_title('Client Satisfaction Scores')
        for bar, val in zip(bars, sizes):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.15, str(val),
                        ha='center', fontsize=9, fontweight='bold', color=PALETTE['text'])
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        fig.tight_layout()
        return _fig_to_base64(fig)

    def _chart_industry_breakdown(self):
        qs = (
            BrandingRequest.objects
            .exclude(industry='')
            .values('industry')
            .annotate(cnt=Count('id'))
            .order_by('-cnt')[:10]
        )
        industries = [row['industry'].replace('_', ' ').title() for row in qs]
        counts = [row['cnt'] for row in qs]

        if not industries:
            return None

        fig, ax = plt.subplots(figsize=(7, 3.5))
        colors = plt.cm.Set2([i / max(len(industries) - 1, 1) for i in range(len(industries))])
        bars = ax.barh(industries[::-1], counts[::-1], color=colors[::-1], edgecolor='white', height=0.6)
        ax.set_xlabel('Requests')
        ax.set_title('Industry Breakdown')
        for bar, val in zip(bars, counts[::-1]):
            ax.text(bar.get_width() + 0.2, bar.get_y() + bar.get_height() / 2, str(val),
                    va='center', fontsize=9, color=PALETTE['text'], fontweight='bold')
        ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        fig.tight_layout()
        return _fig_to_base64(fig)

    def _chart_priority_distribution(self):
        from .models import PRIORITY_CHOICES
        qs = BrandingRequest.objects.values('priority').annotate(cnt=Count('id')).order_by('priority')
        data = {row['priority']: row['cnt'] for row in qs}
        p_map = dict(PRIORITY_CHOICES)
        labels = [p_map.get(code, code) for code, _ in PRIORITY_CHOICES if data.get(code, 0) > 0]
        sizes = [data.get(code, 0) for code, _ in PRIORITY_CHOICES if data.get(code, 0) > 0]
        colors_p = ['#22c55e', '#3b82f6', '#f59e0b', '#ef4444']
        active_colors = [colors_p[i] for i, (code, _) in enumerate(PRIORITY_CHOICES) if data.get(code, 0) > 0]

        if not sizes:
            return None

        fig, ax = plt.subplots(figsize=(5, 3.5))
        wedges, texts, autotexts = ax.pie(
            sizes, labels=labels, autopct='%1.0f%%', startangle=90,
            colors=active_colors, pctdistance=0.8,
            wedgeprops=dict(edgecolor='white', linewidth=2),
        )
        for t in autotexts:
            t.set_fontsize(9)
            t.set_fontweight('bold')
        for t in texts:
            t.set_fontsize(9)
        ax.set_title('Priority Distribution')
        fig.tight_layout()
        return _fig_to_base64(fig)

    def _chart_completion_time(self):
        completed = BrandingRequest.objects.filter(status='COMPLETED', completed_at__isnull=False)
        if not completed.exists():
            return None

        data = []
        for req in completed:
            delta = req.completed_at - req.created_at
            data.append(delta.total_seconds() / 86400)

        if not data:
            return None

        fig, ax = plt.subplots(figsize=(7, 3))
        ax.hist(data, bins=min(15, max(5, len(data) // 2)), color=PALETTE['primary'], edgecolor='white', alpha=0.85)
        ax.set_xlabel('Days to Complete')
        ax.set_ylabel('Number of Projects')
        ax.set_title('Completion Time Distribution')
        avg_days = sum(data) / len(data)
        ax.axvline(avg_days, color=PALETTE['danger'], linestyle='--', linewidth=1.5, label=f'Avg: {avg_days:.1f}d')
        ax.legend(fontsize=9)
        fig.tight_layout()
        return _fig_to_base64(fig)

    # ------------------------------------------------------------------
    # Data tables
    # ------------------------------------------------------------------

    def _build_data_tables(self):
        return {
            'status_summary': self._table_status_summary(),
            'top_designers': self._table_top_designers(),
            'feedback_summary': self._table_feedback_summary(),
            'monthly_summary': self._table_monthly_summary(),
            'industry_summary': self._table_industry_summary(),
        }

    def _table_status_summary(self):
        qs = BrandingRequest.objects.values('status').annotate(cnt=Count('id')).order_by('status')
        p_map = dict(STATUS_CHOICES)
        total = sum(row['cnt'] for row in qs)
        rows = []
        for row in qs:
            pct = (row['cnt'] / total * 100) if total else 0
            rows.append({
                'status': p_map.get(row['status'], row['status']),
                'count': row['cnt'],
                'percentage': f'{pct:.1f}%',
            })
        return {'rows': rows, 'total': total}

    def _table_top_designers(self):
        qs = (
            BrandingRequest.objects
            .filter(designer__isnull=False)
            .exclude(status__in=['DRAFT', 'ARCHIVED'])
            .values('designer__username', 'designer__first_name', 'designer__last_name')
            .annotate(cnt=Count('id'))
            .order_by('-cnt')[:10]
        )
        rows = []
        for row in qs:
            name = f"{row['designer__first_name']} {row['designer__last_name']}".strip()
            if not name:
                name = row['designer__username']
            rows.append({'name': name, 'active': row['cnt']})
        return rows

    def _table_feedback_summary(self):
        from django.db.models import Avg
        agg = BrandingFeedback.objects.aggregate(
            avg_rating=Avg('rating'),
            total=Count('id'),
            recommend=Count('id', filter=Q(would_recommend=True)),
        )
        total = agg['total'] or 0
        recommend_pct = (agg['recommend'] / total * 100) if total else 0
        return {
            'avg_rating': f"{agg['avg_rating']:.1f}" if agg['avg_rating'] else '—',
            'total': total,
            'recommend_pct': f'{recommend_pct:.0f}%',
        }

    def _table_monthly_summary(self):
        qs = (
            BrandingRequest.objects
            .filter(created_at__gte=self.cutoff)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(total=Count('id'))
            .order_by('month')
        )
        return [{'month': row['month'].strftime('%b %Y'), 'count': row['total']} for row in qs]

    def _table_industry_summary(self):
        qs = (
            BrandingRequest.objects
            .exclude(industry='')
            .values('industry')
            .annotate(cnt=Count('id'))
            .order_by('-cnt')[:10]
        )
        total = sum(row['cnt'] for row in qs)
        rows = []
        for row in qs:
            label = row['industry'].replace('_', ' ').title()
            pct = (row['cnt'] / total * 100) if total else 0
            rows.append({'industry': label, 'count': row['cnt'], 'percentage': f'{pct:.1f}%'})
        return rows


# ────────────────────────────────────────────────────────────────────────────
# Team Performance Report (Supervisor)
# ────────────────────────────────────────────────────────────────────────────

class TeamPerformanceReport:
    """PDF report summarizing team performance metrics."""

    WORKLOAD_THRESHOLD = 5

    def __init__(self):
        self.now = timezone.now()

    def _build_team_data(self):
        from .models import ACTIVE_STATUSES
        designers = User.objects.filter(is_staff=True, is_active=True).order_by('username')
        data = []
        for d in designers:
            active = BrandingRequest.objects.filter(
                designer=d, status__in=ACTIVE_STATUSES
            ).count()
            completed = BrandingRequest.objects.filter(
                designer=d, status='COMPLETED'
            ).count()
            avg_comp = BrandingRequest.objects.filter(
                designer=d, status='COMPLETED', completed_at__isnull=False
            ).aggregate(avg=Avg(F('completed_at') - F('created_at')))['avg']
            avg_days = round(avg_comp.total_seconds() / 86400, 1) if avg_comp else None

            on_time_total = BrandingRequest.objects.filter(
                designer=d, status='COMPLETED', estimated_delivery_date__isnull=False
            ).count()
            on_time_done = BrandingRequest.objects.filter(
                designer=d, status='COMPLETED',
                completed_at__date__lte=F('estimated_delivery_date'),
            ).count() if on_time_total else 0
            on_time_pct = round(on_time_done / on_time_total * 100) if on_time_total else None

            rating_agg = BrandingFeedback.objects.filter(
                request__designer=d
            ).aggregate(avg=Avg('rating'), count=Count('id'))
            satisfaction = round(rating_agg['avg'], 1) if rating_agg['avg'] else None

            data.append({
                'name': d.get_full_name() or d.username,
                'email': d.email,
                'active': active,
                'completed': completed,
                'avg_days': avg_days,
                'on_time_pct': on_time_pct,
                'satisfaction': satisfaction,
                'feedback_count': rating_agg['count'],
                'is_overloaded': active > self.WORKLOAD_THRESHOLD,
            })
        data.sort(key=lambda x: (-x['active'], x['name']))
        return data

    def _chart_workload(self, team_data):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        buf = io.BytesIO()
        names = [d['name'][:15] for d in team_data]
        active = [d['active'] for d in team_data]
        completed = [d['completed'] for d in team_data]
        colors_active = ['#ef4444' if a > self.WORKLOAD_THRESHOLD else '#6366f1' for a in active]

        fig, ax = plt.subplots(figsize=(8, 3.5))
        x = range(len(names))
        bars1 = ax.bar([i - 0.2 for i in x], active, 0.4, label='Active', color=colors_active, edgecolor='white', linewidth=0.5)
        bars2 = ax.bar([i + 0.2 for i in x], completed, 0.4, label='Completed', color='#22c55e', alpha=0.7, edgecolor='white', linewidth=0.5)
        ax.axhline(y=self.WORKLOAD_THRESHOLD, color='#ef4444', linestyle='--', linewidth=1, alpha=0.6, label=f'Threshold ({self.WORKLOAD_THRESHOLD})')
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontsize=8, rotation=30, ha='right')
        ax.set_ylabel('Projects')
        ax.set_title('Team Workload', fontsize=12, fontweight='bold')
        ax.legend(fontsize=8)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        plt.tight_layout()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode()

    def _chart_on_time(self, team_data):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        buf = io.BytesIO()
        names = [d['name'][:15] for d in team_data if d['on_time_pct'] is not None]
        pcts = [d['on_time_pct'] for d in team_data if d['on_time_pct'] is not None]
        if not names:
            return None

        colors = ['#22c55e' if p >= 90 else '#f59e0b' if p >= 70 else '#ef4444' for p in pcts]
        fig, ax = plt.subplots(figsize=(8, 3))
        bars = ax.barh(names, pcts, color=colors, edgecolor='white', linewidth=0.5)
        ax.set_xlim(0, 100)
        ax.set_xlabel('On-Time %')
        ax.set_title('On-Time Delivery Rate', fontsize=12, fontweight='bold')
        ax.axvline(x=90, color='#22c55e', linestyle='--', linewidth=1, alpha=0.5)
        for bar, pct in zip(bars, pcts):
            ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2, f'{pct}%', va='center', fontsize=8)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        plt.tight_layout()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode()

    def _chart_satisfaction(self, team_data):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        buf = io.BytesIO()
        names = [d['name'][:15] for d in team_data if d['satisfaction'] is not None]
        ratings = [d['satisfaction'] for d in team_data if d['satisfaction'] is not None]
        if not names:
            return None

        colors = ['#f59e0b' for _ in ratings]
        fig, ax = plt.subplots(figsize=(8, 3))
        bars = ax.barh(names, ratings, color=colors, edgecolor='white', linewidth=0.5)
        ax.set_xlim(0, 5)
        ax.set_xlabel('Avg Rating')
        ax.set_title('Client Satisfaction', fontsize=12, fontweight='bold')
        for bar, r in zip(bars, ratings):
            ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2, f'{r}', va='center', fontsize=9, fontweight='bold')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        plt.tight_layout()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode()

    def render_response(self):
        team_data = self._build_team_data()
        chart_workload_b64 = self._chart_workload(team_data)
        chart_on_time_b64 = self._chart_on_time(team_data)
        chart_satisfaction_b64 = self._chart_satisfaction(team_data)

        html = render_to_string('branding/pdf/team_report.html', {
            'team_data': team_data,
            'chart_workload': chart_workload_b64,
            'chart_on_time': chart_on_time_b64,
            'chart_satisfaction': chart_satisfaction_b64,
            'generated_at': self.now,
            'threshold': self.WORKLOAD_THRESHOLD,
        })

        try:
            from weasyprint import HTML
            pdf_bytes = HTML(string=html, base_url=getattr(settings, 'BASE_DIR', '')).write_pdf()
            response = FileResponse(io.BytesIO(pdf_bytes), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="team_performance_{self.now:%Y%m%d}.pdf"'
            return response
        except ImportError:
            return HttpResponse(
                '<h3>WeasyPrint not available</h3><p>Install WeasyPrint to generate PDF reports.</p>',
                content_type='text/html',
                status=503,
            )
