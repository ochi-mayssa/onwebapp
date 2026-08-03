# OnWebApp Automation Extensions

This document outlines the new automation features added to the OnWebApp Workflow Monitoring System.

## 1. SMS Notifications (Optional)
- **Feature**: Sends SMS alerts for critical events (Delayed Phases, Pending Approvals) if enabled.
- **Configuration**:
  - `sms_notifications_enabled` (Boolean) in UserProfile.
  - `phone_number` (Char) in UserProfile.
- **Implementation**: `projects/signals.py` simulates SMS sending (prints to console). Integrate Twilio/Vonage here for production.

## 2. Trend Analysis & KPI Enhancements
- **Average Phase Duration**: Now tracked in `KPIHistory` model.
- **KPI Export**: Admins can export historical KPI data to CSV via `/projects/admin/analytics/export/kpi/`.
- **Severity**: Notifications now have a severity level (LOW, MEDIUM, HIGH, CRITICAL).

## 3. Invoice System Enhancements
- **PDF Generation**: Invoices are generated as PDF using `WeasyPrint` (graceful fallback if missing).
- **Email Delivery**: PDF is attached to the automated email sent to the client upon project creation.
- **Download**: Clients can download the PDF from their invoice detail page.

## 4. Automated Verification
- **Daily Task**: `system_verification_check` verifies:
  - Missing notifications for delayed phases.
  - Projects missing invoices.
  - Stale pending approvals (> 7 days).
- **Reporting**: Emails a summary report to Admins if issues are found.

## 5. Integration Instructions

### Database Updates
Run migrations to add new fields:
```bash
python manage.py makemigrations users projects
python manage.py migrate
```

### Testing
1. **Run Verification Script**:
   ```bash
   python verify_workflow.py
   ```
2. **Trigger Tasks Manually**:
   ```python
   from projects.tasks import capture_kpi_snapshot, system_verification_check
   capture_kpi_snapshot()
   system_verification_check()
   ```
3. **Check Admin Dashboard**: Verify the new "Export KPI" link (add to template if needed) or access via URL.

### Dependencies
Ensure `weasyprint` is installed for PDF generation:
```bash
pip install weasyprint
```
