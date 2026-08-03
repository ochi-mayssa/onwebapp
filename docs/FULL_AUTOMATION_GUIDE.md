# OnWebApp Full Automation & Integration Guide

This system has been extended with full-cycle automation: Client Onboarding -> Project Execution -> Billing -> Reporting.

## 1. Features Implemented

### A. Client Onboarding (Automated)
- **Welcome Email**: Sent via SMTP when a new client account is created.
- **Dashboard Notification**: Real-time push to the client's dashboard.
- **Code**: `projects/signals.py` -> `automated_welcome_message`

### B. Automated Billing
- **Invoice Generation**: When a project is created, a Draft Invoice is generated.
- **PDF Attachment**: A PDF is auto-generated using WeasyPrint and attached to the email.
- **Email Delivery**: Sent to the client immediately.
- **Code**: `projects/signals.py` -> `automated_invoice_generation`

### C. Real-Time Notifications (WebSockets)
- **Technology**: Django Channels (Redis).
- **Function**: Pushes alerts (Delays, Approvals) instantly to the dashboard without page refresh.
- **Code**: `projects/consumers.py`, `projects/routing.py`.

### D. Advanced Analytics & KPIs
- **Trend Analysis**: Line chart showing Completion Rate & Delays over the last 7 days.
- **Data Source**: `KPIHistory` model, populated daily by Celery.
- **Visualization**: Chart.js in Admin Dashboard.

### E. Daily Verification (Celery Beat)
- **Task**: `check_overdue_phases` and `check_pending_approvals`.
- **Action**: Checks for missed deadlines, sends reminders, and logs to Audit Trail.

## 2. Integration Steps

### Prerequisites
Ensure the following packages are installed:
```bash
pip install channels channels_redis weasyprint
```

### Configuration (`settings.py`)

1. **Email Backend** (For development, prints to console):
   ```python
   EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
   # For Production:
   # EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
   # EMAIL_HOST = 'smtp.gmail.com' ...
   ```

2. **Channels (Redis)**:
   ```python
   ASGI_APPLICATION = 'websity_project.asgi.application'
   CHANNEL_LAYERS = {
       "default": {
           "BACKEND": "channels_redis.core.RedisChannelLayer",
           "CONFIG": {
               "hosts": [("127.0.0.1", 6379)],
           },
       },
   }
   ```

### Running the System

1. **Start Redis Server**:
   ```bash
   redis-server
   ```

2. **Start Celery Worker & Beat**:
   ```bash
   celery -A websity_project worker -l info
   celery -A websity_project beat -l info
   ```

3. **Start Django Server (ASGI)**:
   ```bash
   daphne -p 8000 websity_project.asgi:application
   # OR for dev:
   python manage.py runserver
   ```

## 3. Testing Automation

### Manual Triggers (Django Shell)

```python
# 1. Test Welcome Email
from django.contrib.auth import get_user_model
User = get_user_model()
User.objects.create_user('test_client_auto', 'test@auto.com', 'password123')

# 2. Test Invoice PDF & Email
from projects.models import Project
client = User.objects.get(username='test_client_auto')
Project.objects.create(client=client, title="Auto Bill Project", project_type="IOT")

# 3. Test KPI Snapshot
from projects.tasks import capture_kpi_snapshot
capture_kpi_snapshot()
```

### Verification
Check `projects/invoice_pdfs/` folder for generated PDFs.
Check Console for Email Output.
Check Admin Dashboard for new KPI points.
