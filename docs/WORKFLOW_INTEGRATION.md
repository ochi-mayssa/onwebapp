# Automated Workflow Monitoring Integration Guide

This guide details how to integrate, configure, and run the Automated Workflow Monitoring system in the OnWebApp Django project.

## 1. System Overview

The system monitors project lifecycles, detects delays, and manages approvals for:
- **Community Clients**: Focus on Website & Brand projects.
- **Full Platform Users**: Focus on Industrial Automation, IoT, and Social Media.
- **Administrators**: Unified oversight with KPIs and Reporting.

## 2. Prerequisites

Ensure you have the following installed:
- **Redis**: Required for Celery task queuing.
- **Celery**: Python package for asynchronous tasks.

```bash
pip install celery redis django-celery-beat
```

## 3. Configuration

### Django Settings (`settings.py`)

Ensure Celery is configured in your main `settings.py`:

```python
# settings.py

CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'  # Or your local timezone
```

### Celery App (`celery.py`)

Create or update `websity_project/celery.py` (replace `websity_project` with your project name if different):

```python
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')

app = Celery('websity_project')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

## 4. Running the System

The workflow system relies on three components running simultaneously:

1.  **Django Web Server**:
    ```bash
    python manage.py runserver
    ```

2.  **Celery Worker** (Processes background tasks):
    ```bash
    celery -A websity_project worker -l info
    ```

3.  **Celery Beat** (Schedules periodic checks):
    ```bash
    celery -A websity_project beat -l info
    ```

## 5. Automation & Logic

### Automatic Notifications (Signals)
- **Trigger**: `post_save` on `ProjectPhase`.
- **Logic**: 
  - If status becomes `COMPLETED` -> Send success notification & update progress.
  - If status becomes `DELAYED` -> Send alert to Client & Admin.
  - If `approval_status` becomes `AWAITING_CLIENT` -> Send action required notification.
- **File**: `projects/signals.py`

### Periodic Monitoring (Celery Tasks)
- **Overdue Check**: Runs daily. Checks if `current_phase.end_date < today`. Marks phase as `DELAYED` if > 3 days overdue.
- **Pending Approvals**: Runs daily. Reminds clients of pending approvals > 3 days old.
- **Admin Report**: Runs daily. Generates a summary log for admins.
- **File**: `projects/tasks.py`

## 6. Dashboards & User Roles

### Client Dashboard
- **URL**: `/projects/workflow/dashboard/`
- **Logic**: Automatically detects user role based on `project_type`.
  - **Website/Brand Projects**: Shows detailed phase progress bars (Community Client view).
  - **Automation/IoT Projects**: Shows overall workflow completion & system status (Full Platform User view).

### Admin Dashboard
- **URL**: `/projects/workflow/admin/dashboard/`
- **Features**: 
  - Real-time KPIs (Completion Rate, Avg Delay).
  - Doughnut Chart for Project Status.
  - Critical list of delayed projects.
  - Audit log of all system notifications.

## 7. Testing the Workflow

1.  **Create a Project**: Go to the admin panel or client view and create a project.
2.  **Set Dates**: Assign a `ProjectPhase` with an `end_date` in the past.
3.  **Run Tasks Manually**:
    Open Django shell:
    ```python
    from projects.tasks import check_overdue_phases
    check_overdue_phases.delay()
    ```
4.  **Verify**: Check the Client Dashboard for a "Delayed" alert.

## 8. API Integration

- **Mark Notification Read**: `POST /projects/api/notifications/<id>/read/`
- **Export Data**: `GET /projects/admin/export.csv` (Admin only)

## 9. Verification & Maintenance

### Workflow Verification Script
To verify the system integrity, database consistency, and notification triggers, run the provided verification script:

```bash
python verify_workflow.py
```
This script will:
1. Load the Django environment.
2. Scan all projects and phases.
3. Identify overdue phases.
4. Verify that "Pending Approval" phases have corresponding notifications.
5. Simulate a phase status change to test Signal triggers.

### Auto-Update & KPI Generation
To ensure all missing notifications are backfilled and to export current KPIs to JSON, run:

```bash
python auto_update_workflow.py
```
This script will:
- Scan for any `DELAYED` or `PENDING_APPROVAL` phases that lack notifications.
- Auto-create the missing alerts.
- Export system KPIs to `kpi_auto.json` (Completion Rate, Delay stats, etc.).

### Visual Workflow Diagram
Refer to `workflow_diagram.svg` in the root directory for a visual representation of:
- Data flow from Models to Dashboards.
- Signal triggers.
- Periodic Celery task interactions.

### Final Verification Checklist
- [ ] Redis server is running (`redis-cli ping` returns `PONG`).
- [ ] Celery worker is active.
- [ ] Celery beat is active.
- [ ] Client Dashboard shows "Community Project" or "Platform Service" based on project type.
- [ ] Admin Dashboard KPIs display correct numbers.
- [ ] Notifications appear instantly (via WebSocket/refresh) when a phase status changes.

## 10. Manual Testing & Troubleshooting

### How to Manually Trigger Celery Tasks
You don't need to wait for the schedule to test background tasks. You can trigger them immediately via the Django Shell.

```bash
python manage.py shell
```

```python
# Import tasks
from projects.tasks import check_overdue_phases, check_pending_approvals, generate_daily_admin_report

# Run immediately (synchronous - good for debugging)
check_overdue_phases()

# Run as Celery task (asynchronous - tests Redis connection)
check_overdue_phases.delay()
```

### How to View Notifications & KPIs
1. **Notifications**:
   - **Frontend**: Log in as a Client or Admin. Notifications appear in the top "Alerts & Notifications" panel.
   - **Database**: Query the `WorkflowNotification` model:
     ```python
     from projects.models import WorkflowNotification
     print(WorkflowNotification.objects.all().values('recipient__username', 'message'))
     ```

2. **KPIs**:
   - **Admin Dashboard**: Visit `/projects/workflow/admin/dashboard/`.
   - **JSON Output**: For API consumers, refer to `kpi_sample.json` for the expected structure. The system calculates these real-time in `projects/views.py`.

### How to Simulate Real-time Triggers (Signals)
To test if a status change triggers a notification without using the UI:

```python
from projects.models import ProjectPhase

# Get a phase
phase = ProjectPhase.objects.first()

# Change status to 'DELAYED' or 'COMPLETED'
phase.status = 'DELAYED'
phase.save() 
# This save() call automatically fires the signal in projects/signals.py
# Check your console/logs or dashboard for the alert.
```

