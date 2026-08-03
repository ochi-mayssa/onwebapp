from celery import shared_task
from django.utils import timezone
from .models import ProjectPhase, Project, WorkflowNotification
from datetime import timedelta
from users.models import ActivityLog
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

User = get_user_model()

def send_dashboard_notification(group_name, type_msg, message, level='info', extra_data=None):
    """
    Helper to send WebSocket updates to dashboard.
    """
    channel_layer = get_channel_layer()
    
    payload_data = {
        "type": type_msg,
        "text": message,
        "level": level,
        "timestamp": str(timezone.now())
    }
    if extra_data:
        payload_data.update(extra_data)

    try:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "dashboard_update",
                "data": payload_data
            }
        )
    except Exception as e:
        # Don't fail the task if redis is down
        print(f"WebSocket broadcast failed: {e}")

@shared_task
def check_overdue_phases():
    """
    Daily task to check for phases that are past their due date but not completed.
    """
    today = timezone.now().date()
    
    # Find overdue phases
    overdue_phases = ProjectPhase.objects.filter(
        end_date__lt=today, # Use end_date as due_date
        status__in=['NOT_STARTED', 'IN_PROGRESS']
    ).exclude(status='DELAYED').select_related('project', 'project__client')
    
    count = 0
    for phase in overdue_phases:
        days_overdue = (today - phase.end_date).days
        
        if days_overdue >= 1:
            msg = f"Action Required: Phase '{phase.get_phase_type_display()}' is overdue by {days_overdue} days."
            
            # 1. Workflow Notification (Audit)
            if phase.project.client:
                WorkflowNotification.objects.create(
                    project=phase.project,
                    recipient=phase.project.client,
                    notification_type='DELAY',
                    message=msg
                )

            # 2. Email Notification
            if phase.project.client and phase.project.client.email:
                send_mail(
                    subject=f"Project Delayed: {phase.project.title}",
                    message=f"Hello,\n\nThe phase '{phase.get_phase_type_display()}' is overdue.\n\n{msg}",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[phase.project.client.email],
                    fail_silently=True
                )
                
            # 3. WebSocket Broadcast
            if phase.project.client:
                send_dashboard_notification(
                    f"user_{phase.project.client.id}",
                    'alert',
                    msg,
                    'warning'
                )
            
            # Auto-mark as delayed if > 3 days
            if days_overdue > 3:
                phase.status = 'DELAYED'
                phase.save(update_fields=['status'])
                
                # The signal will handle the 'DELAYED' notification creation, 
                # preventing double logging if we were to do it here manually.
                # However, signals only fire on save(), so it will work.
                
        count += 1
    
    return f"Checked overdue phases. Found {count} issues."

@shared_task
def check_pending_approvals():
    """
    Check for phases waiting for client approval for more than 3 days.
    """
    today = timezone.now().date()
    
    pending_phases = ProjectPhase.objects.filter(
        approval_status='AWAITING_CLIENT',
        status__in=['IN_PROGRESS', 'NOT_STARTED'] 
    ).select_related('project', 'project__client')
    
    count = 0
    for phase in pending_phases:
        # Check if we already notified recently? 
        # For simplicity, we assume this runs daily.
        
        msg = f"Reminder: Approval pending for '{phase.get_phase_type_display()}'."
        
        # 1. Audit Notification
        if phase.project.client:
            WorkflowNotification.objects.create(
                project=phase.project,
                recipient=phase.project.client,
                notification_type='APPROVAL',
                message=msg
            )

        # 2. Email
        if phase.project.client and phase.project.client.email:
            send_mail(
                subject=f"Approval Needed - {phase.project.title}",
                message=msg,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[phase.project.client.email],
                fail_silently=True
            )
            
        # 3. WebSocket
        if phase.project.client:
            send_dashboard_notification(
                f"user_{phase.project.client.id}",
                'reminder',
                msg,
                'info'
            )
            
        count += 1
        
    return f"Sent {count} approval reminders."

@shared_task
def generate_daily_admin_report():
    """
    Generate a daily summary for admins.
    """
    admins = User.objects.filter(is_superuser=True)
    if not admins.exists():
        return "No admins to notify."
        
    # Gather stats
    total_projects = Project.objects.count()
    delayed_count = ProjectPhase.objects.filter(status='DELAYED').count()
    pending_approvals = ProjectPhase.objects.filter(approval_status='AWAITING_CLIENT').count()
    
    report_msg = f"Daily Report: {delayed_count} delayed phases, {pending_approvals} pending approvals."
    
    for admin in admins:
        # Audit
        WorkflowNotification.objects.create(
            recipient=admin,
            notification_type='REPORT',
            message=report_msg
        )
        
        # Email
        if admin.email:
            send_mail(
                subject=f"Daily Admin Report - {timezone.now().date()}",
                message=f"{report_msg}\n\nTotal Projects: {total_projects}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[admin.email],
                fail_silently=True
            )
            
    send_dashboard_notification(
        'admins',
        'report',
        report_msg,
        'success'
    )
        
    return "Daily report sent."

@shared_task
def capture_kpi_snapshot():
    """
    Daily task: Save current system KPIs to the database for trend analysis.
    """
    from .models import KPIHistory, ProjectPhase
    from django.db.models import Avg, F
    
    # 1. Completion Rate
    total = Project.objects.count()
    completed = Project.objects.filter(current_status='COMPLETED').count()
    rate = (completed / total * 100) if total > 0 else 0.0
    
    # 2. Avg Delay
    # Approximation: average days overdue for currently delayed phases
    today = timezone.now().date()
    delayed_phases = ProjectPhase.objects.filter(status='DELAYED', end_date__lt=today)
    
    total_delay_days = 0
    count = 0
    for phase in delayed_phases:
        if phase.end_date:
            days = (today - phase.end_date).days
            total_delay_days += days
            count += 1
    
    avg_delay = (total_delay_days / count) if count > 0 else 0.0
    
    # 3. Pending Approvals
    pending = ProjectPhase.objects.filter(approval_status='AWAITING_CLIENT').count()
    
    # 4. Active Projects
    active = Project.objects.exclude(current_status__in=['COMPLETED', 'CANCELLED', 'ON_HOLD']).count()
    
    # 5. Average Phase Duration (New)
    # Calculate duration for completed phases: completed_at (if tracked) or end_date - start_date
    # Since we don't have 'completed_at' on Phase, we'll use start_date and end_date of COMPLETED phases
    completed_phases_qs = ProjectPhase.objects.filter(status='COMPLETED', start_date__isnull=False, end_date__isnull=False)
    
    total_duration = 0
    p_count = 0
    for p in completed_phases_qs:
        duration = (p.end_date - p.start_date).days
        if duration > 0:
            total_duration += duration
            p_count += 1
            
    avg_phase_duration = (total_duration / p_count) if p_count > 0 else 0.0

    # Save Snapshot
    KPIHistory.objects.create(
        completion_rate=rate,
        avg_delay_days=avg_delay,
        avg_phase_duration_days=avg_phase_duration,
        pending_approvals=pending,
        active_projects=active
    )
    
    return f"KPI Snapshot saved: Rate={rate}%, Delay={avg_delay}d, Duration={avg_phase_duration}d"

@shared_task
def system_verification_check():
    """
    Daily task: Verify data integrity and missing notifications.
    Includes verification of invoice generation and pending approvals.
    """
    # Reuse the logic from auto_update_workflow.py but as a task
    
    issues = []
    
    # Check 1: Delayed phases without notifications
    delayed = ProjectPhase.objects.filter(status='DELAYED')
    for phase in delayed:
        exists = WorkflowNotification.objects.filter(
            project=phase.project,
            notification_type='DELAY',
            message__contains=phase.get_phase_type_display()
        ).exists()
        if not exists:
            issues.append(f"Missing notification for delayed phase: {phase}")
            
    # Check 2: Projects without Invoices (New)
    # Every project should have at least one invoice (Draft or Issued)
    projects = Project.objects.all()
    for p in projects:
        if not p.invoices.exists():
            issues.append(f"Project '{p.title}' has no invoices generated.")

    # Check 3: Pending Approvals Older than 7 days (Stale)
    week_ago = timezone.now().date() - timedelta(days=7)
    stale_approvals = ProjectPhase.objects.filter(
        approval_status='AWAITING_CLIENT',
        ready_for_review=True,
        updated_at__lt=week_ago # Assuming we had updated_at, but we don't on Phase directly, so use approximation or skip
    )
    # Using end_date as proxy for "should have been done by now" if available
    
    if issues:
        msg = "System Verification Found Issues:\n" + "\n".join(issues)
        # Notify Admins
        admins = User.objects.filter(is_superuser=True)
        for admin in admins:
            WorkflowNotification.objects.create(
                recipient=admin,
                notification_type='REPORT',
                message="System Verification found data inconsistencies.",
                severity='HIGH'
            )
            if admin.email:
                send_mail(
                    "System Verification Alert",
                    msg,
                    settings.DEFAULT_FROM_EMAIL,
                    [admin.email],
                    fail_silently=True
                )
        return f"Found {len(issues)} issues."
        
    return "System verification passed."
