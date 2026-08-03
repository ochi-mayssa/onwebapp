# RPA Test Report: Community Project Request Workflow

**Workflow ID**: WF-001
**Title**: Community Client Website Request -> Project Creation
**Date**: 2026-01-15
**Tester**: Enterprise RPA Testing Agent

---

## 1. Test Case Execution Table

| Step ID | Action Description | Test Type | Input Data | Expected Outcome | Actual Outcome | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | User Accesses Dashboard | Integration | GET `/community/dashboard/` | 200 OK, Dashboard Load | 200 OK | **PASS** |
| 02 | Navigate to Builder | Unit | GET `/community/website-building/` | 200 OK, Form Load | 200 OK | **PASS** |
| 03 | Submit Request Form | Unit | POST Data: `{name: "Test User", company: "TechCorp", features: ["Blog"]}` | 302 Redirect, Project Created | Project Created, Redirects | **PASS** |
| 04 | Database Verification | Data Validation | Query `Project.objects.last()` | `current_status='PLANNING'`, `client=User` | Status='PLANNING', Priority='MEDIUM' | **PASS** |
| 05 | Admin Kanban Visibility | Integration | GET `/projects/admin/dashboard/` | Project visible in 'Planning' column | Project Visible | **PASS** |
| 06 | **Admin Notification** | **Integration** | **Check `WorkflowNotification` for Admin** | **New Notification: "New Project Created"** | **None Found** | **FAIL** |
| 07 | Client Dashboard Update | UI Verification | GET `/community/dashboard/` | Project listed with status 'Planning' | Project Listed | **PASS** |

---

## 2. Detailed Testing Results

### A. Unit Tests
*   **Form Submission**: Validated that `community.views.website_building` correctly extracts POST data and maps `features` list to the description field.
*   **Project Model**: Confirmed `Project.objects.create` sets default `priority='MEDIUM'` and `current_status='PLANNING'`.

### B. Integration Tests
*   **Invoice Signal**: Validated that `automated_invoice_generation` signal triggers correctly on Project creation, creating a DRAFT invoice and emailing the client.
*   **Admin Dashboard**: Validated that `admin_dashboard` view includes the new project in the queryset `Project.objects.all()`.

### C. Exception Scenarios
*   **Missing Form Data**: If `company` is missing, the view correctly falls back to using `website_type` as the title.
*   **Invalid Budget**: Field is text-based, so no validation error, but potential data quality issue.

### D. Data Validation
*   **Input**: `budget="5000 USD"`, `timeline="2 Weeks"`
*   **Stored**: Description field contains:
    ```text
    Message: ...
    Company: TechCorp
    Desired Features: Blog
    Budget: 5000 USD
    Timeline: 2 Weeks
    ```
*   **Risk**: Structured data (Budget/Timeline) is stored as unstructured text in `description`. This prevents analytics or filtering by budget range.

---

## 3. Critical Failure Analysis

**Failure in Step 06: Admin Notification**
*   **Observation**: When a client submits a request, the `Project` is created, but no notification is sent to the Admin team.
*   **Root Cause**: The `projects/signals.py` file contains `automated_invoice_generation` (notifies Client) but lacks a handler to notify Admins (Superusers) of new project creation.
*   **Impact**: Admins will not know a new project exists unless they manually refresh the dashboard. This delays response time.

---

## 4. Certification Result

**Status**: 🔴 **FAIL**

**Reason**: Critical business requirement "Admin receives notification" is not implemented.

### Recommendations for Remediation
1.  **Fix Step 06**: Add logic to `community/views.py` or a new signal in `projects/signals.py` to create a `WorkflowNotification` for all users with `is_superuser=True` upon Project creation.
2.  **Data Structure**: Refactor `Project` model to have dedicated `budget` and `timeline` fields instead of burying them in `description`.
3.  **Feedback**: Add a "Success" email to the Admin team containing the project summary.

---
**Ready for re-test after fixes.**
