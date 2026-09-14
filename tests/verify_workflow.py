import os
import django
import sys
from datetime import timedelta
from django.utils import timezone

# Setup Django Environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()

from projects.models import Project, ProjectPhase, WorkflowNotification
from django.db.models import Count

def verify_workflow():
    print("=== Automated Workflow System Verification ===")
    print(f"Time: {timezone.now()}")
    
    # 1. Check Projects & Phases
    projects = Project.objects.all()
    print(f"\n[INFO] Total Projects Found: {projects.count()}")
    
    delayed_phases = ProjectPhase.objects.filter(status='DELAYED')
    print(f"[INFO] Delayed Phases: {delayed_phases.count()}")
    
    for phase in delayed_phases:
        print(f"  -> ALERT: Project '{phase.project.title}' - Phase '{phase.get_phase_type_display()}' is DELAYED.")

    # 2. Check Pending Approvals
    pending_approvals = ProjectPhase.objects.filter(approval_status='AWAITING_CLIENT')
    print(f"\n[INFO] Pending Approvals: {pending_approvals.count()}")
    
    for phase in pending_approvals:
        print(f"  -> ACTION REQUIRED: '{phase.project.title}' waiting for approval on '{phase.get_phase_type_display()}'.")
        
        # Verify notification exists
        notif_exists = WorkflowNotification.objects.filter(
            project=phase.project, 
            notification_type='APPROVAL',
            is_read=False
        ).exists()
        
        status = "OK" if notif_exists else "MISSING"
        print(f"     [Notification Check]: {status}")

    # 3. Simulate Signal Trigger (Optional)
    print("\n[TEST] Simulating Phase Update...")
    if projects.exists():
        p = projects.first()
        if p.phases.exists():
            phase = p.phases.first()
            old_status = phase.status
            # Toggle status to trigger signal
            phase.status = 'IN_PROGRESS' if old_status != 'IN_PROGRESS' else 'COMPLETED'
            phase.save()
            print(f"  -> Phase '{phase}' updated to {phase.status}. Check 'WorkflowNotification' table for new entry.")
            
            # Revert for safety if needed, or leave as test
            # phase.status = old_status
            # phase.save()
    else:
        print("  -> No projects to test signals.")

    # 4. Check Invoices
    from projects.models import Invoice
    invoices = Invoice.objects.all()
    print(f"\n[INFO] Total Invoices: {invoices.count()}")
    if invoices.exists():
        inv = invoices.last()
        print(f"  -> Latest Invoice: #{inv.id} for {inv.amount} ({inv.status})")

    # 5. Check KPI History
    from projects.models import KPIHistory
    history = KPIHistory.objects.all()
    print(f"\n[INFO] KPI Snapshots: {history.count()}")
    if history.exists():
        last = history.last()
        print(f"  -> Latest Snapshot: Duration={last.avg_phase_duration_days}d")
    
    print("\n=== Verification Complete ===")

if __name__ == "__main__":
    verify_workflow()
