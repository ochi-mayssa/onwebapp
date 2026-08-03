import os
import django
import sys
import json
from django.utils import timezone
from django.db.models import Avg, Count, F

# Setup Django Environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()

from projects.models import Project, ProjectPhase, WorkflowNotification
from django.contrib.auth import get_user_model

User = get_user_model()

def auto_generate_notifications():
    """
    Scans for missing notifications and creates them.
    Hooks into the existing notification system logic.
    """
    print("--- Auto-Generating Missing Notifications ---")
    created_count = 0
    
    # 1. Check Delayed Phases
    delayed_phases = ProjectPhase.objects.filter(status='DELAYED')
    for phase in delayed_phases:
        project = phase.project
        msg = f"Alert: Phase '{phase.get_phase_type_display()}' is now DELAYED."
        
        # Check if notification already exists (heuristic match)
        exists = WorkflowNotification.objects.filter(
            project=project,
            notification_type='DELAY',
            message__contains=phase.get_phase_type_display()
        ).exists()
        
        if not exists and project.client:
            print(f"Creating missing DELAY notification for {project.title} - {phase.get_phase_type_display()}")
            WorkflowNotification.objects.create(
                project=project,
                recipient=project.client,
                notification_type='DELAY',
                message=msg
            )
            created_count += 1
            
            # Notify Admins as well (per existing logic)
            for admin in User.objects.filter(is_superuser=True):
                 WorkflowNotification.objects.create(
                    project=project,
                    recipient=admin,
                    notification_type='DELAY',
                    message=f"Project '{project.title}' phase '{phase.get_phase_type_display()}' is DELAYED."
                )

    # 2. Check Pending Approvals
    pending_phases = ProjectPhase.objects.filter(approval_status='AWAITING_CLIENT')
    for phase in pending_phases:
        project = phase.project
        msg = f"Action Required: Approval needed for {phase.get_phase_type_display()}"
        
        exists = WorkflowNotification.objects.filter(
            project=project,
            notification_type='APPROVAL',
            message__contains=phase.get_phase_type_display()
        ).exists()
        
        if not exists and project.client:
            print(f"Creating missing APPROVAL notification for {project.title} - {phase.get_phase_type_display()}")
            WorkflowNotification.objects.create(
                project=project,
                recipient=project.client,
                notification_type='APPROVAL',
                message=msg
            )
            created_count += 1

    print(f"Total Notifications Created: {created_count}")

def export_kpis():
    """
    Calculates KPIs and exports them to kpi_auto.json.
    """
    print("\n--- Exporting KPIs ---")
    
    # 1. Completion Rate
    total_projects = Project.objects.count()
    completed_projects = Project.objects.filter(current_status='COMPLETED').count()
    completion_rate = (completed_projects / total_projects * 100) if total_projects > 0 else 0.0
    
    # 2. Average Delay
    # Heuristic: Count number of delayed phases per project or assume delay duration logic if available.
    # Since we don't have a 'days_delayed' field on Phase, we'll count delayed phases as a proxy or use simple count.
    # Requirement asks for "Average Delay per phase". 
    # Without a specific 'delay_days' field stored, we can only count *how many* are delayed 
    # or calculate (today - end_date) for currently delayed phases.
    
    delayed_phases = ProjectPhase.objects.filter(status='DELAYED')
    total_delay_days = 0
    today = timezone.now().date()
    
    for phase in delayed_phases:
        if phase.end_date and phase.end_date < today:
            total_delay_days += (today - phase.end_date).days
            
    avg_delay = (total_delay_days / delayed_phases.count()) if delayed_phases.exists() else 0.0
    
    # 3. Pending Approvals
    pending_approvals = ProjectPhase.objects.filter(approval_status='AWAITING_CLIENT').count()
    
    # 4. Delayed Projects Count
    delayed_projects_count = Project.objects.filter(phases__status='DELAYED').distinct().count()
    
    # 5. Alerts Sent (Total)
    alerts_sent = WorkflowNotification.objects.filter(notification_type='DELAY').count()

    data = {
        "generated_at": str(timezone.now()),
        "kpis": {
            "completion_rate_percentage": round(completion_rate, 2),
            "average_delay_days": round(avg_delay, 1),
            "pending_approvals_count": pending_approvals,
            "delayed_projects_count": delayed_projects_count,
            "total_delay_alerts_sent": alerts_sent
        },
        "system_status": "healthy"
    }
    
    file_path = "kpi_auto.json"
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)
    
    print(f"KPIs exported to {file_path}")
    print(json.dumps(data, indent=2))

if __name__ == "__main__":
    try:
        auto_generate_notifications()
        export_kpis()
    except Exception as e:
        print(f"Error during auto update: {e}")
