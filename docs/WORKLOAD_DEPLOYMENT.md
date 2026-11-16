# Workload Management — Deployment & Operations

This document covers the production settings, scheduled jobs, role model and
operational commands for the `workload` app. It describes what is **actually in
the repository**; it does not claim that a production deployment is complete.

## 1. Installation

The app is registered in `INSTALLED_APPS` and mounted at `/workload/` by
`websity_project/urls.py`. Its REST API is exposed under `/api/workload/`
through `workload/api_urls.py`.

```powershell
python manage.py migrate workload
python manage.py check
python manage.py collectstatic --noinput
```

Migrations:

| Migration | Purpose |
|---|---|
| `0001_initial` | Full workload schema, indexes and the per-resource active-assignment rule. |
| `0002_active_assignment_constraint` | Cancels duplicate ACTIVE assignments, then enforces one ACTIVE assignment per work item. |

`0002` is data-safe: the newest active assignment for each work item is kept and
older duplicates are set to `CANCELLED` (never deleted), so history remains
auditable.

## 2. Environment variables

| Variable | Default | Notes |
|---|---|---|
| `WORKLOAD_SYNC_SIGNALS` | `True` | Live project-task and CRM-request mirroring. Set to `False` on a large installation and run the sync command from cron/Celery instead. |
| `USE_CELERY` | `False` | Celery is **not** enabled automatically. The workload app works with `False`; use the management commands below. |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Required only when `USE_CELERY=True`. |
| `REDIS_URL` | unset | Used to derive the channel layer; not required for workload. |

Thresholds, assignment weights and the default weekly hours are **database
values** in `WorkloadPolicy`, not environment variables. Defaults: 60 % /
85 % / 100 %, weights 0.40 / 0.30 / 0.15 / 0.15, 40 h/week. They can be edited
by workload administrators in the UI or API.

## 3. Roles and tenancy

The platform scopes customer data by `auth.User`; there is no separate
Organization/Team model. Workload follows that convention:

| Role | Detection | Scope |
|---|---|---|
| Administrator | superuser or `Workload Administrators` group | Entire installation, policy configuration, integration sync. |
| Manager | Django `is_staff` **or** `Workload Managers` group | Staff managers are global; group-only managers are workspace-scoped. |
| Employee | `Workload Employees` group or active `operations.EmployeeProfile` | Own assignments, own team membership, items they created, own tenant. |
| Client | any other authenticated user | Only `is_client_visible` items for their own tenant/customer. |

Object-level checks live in `workload/permissions.py` and are applied by both the
web views and the REST API. Cross-tenant foreign keys (assignee, team, resource,
CRM customer, project) are rejected by querysets and serializer/form validation,
in addition to service-layer validation.

Managers and employees can only assign work to:

* active users returned by `assignable_users(user)`, and
* active resources returned by `assignable_resources(user)`.

Shared `SYSTEM` resources with no tenant are deliberately available to every
workspace; every other resource must belong to the caller's tenant/team.

## 4. Scheduled jobs (optional Celery)

`CELERY_BEAT_SCHEDULE` contains three workload entries:

| Beat entry | Task | Schedule |
|---|---|---|
| `refresh-workload-alerts-hourly` | `workload.tasks.refresh_workload_alerts` | 3600 s |
| `capture-workload-metrics-daily` | `workload.tasks.capture_workload_metrics` | 86400 s |
| `sync-workload-integrations-hourly` | `workload.tasks.sync_workload_integrations` | 3600 s |

Tasks are idempotent and retry transient failures with exponential backoff
(3 retries, 60 s initial delay). They log terminal failures with a stack trace.
Nothing enables Celery automatically; Beat only emits these tasks when a worker
and scheduler are deliberately started with `USE_CELERY=True`.

Without Celery, schedule the equivalent management commands with the platform
scheduler (Task Scheduler, cron, systemd timer):

```powershell
python manage.py refresh_workload_alerts
python manage.py capture_workload_metrics
python manage.py sync_workload_integrations
```

All three accept `--tenant <username>` where applicable (`refresh` and
`capture`); the integration sync is installation-wide by design.

Recommended cadence: alerts hourly, metrics once per day (running twice in the
same day replaces that day's snapshot), integrations hourly or after bulk
project/CRM imports.

## 5. Integration behaviour

* Project tasks (`projects.PhaseTask`) and CRM service requests
  (`crm.ServiceRequest`) have unique `OneToOneField` mirrors on `WorkItem`, so a
  repeated sync updates rather than duplicates.
* Workload-managed fields (assignments, actual hours, visibility, blocked
  reason) are preserved. CRM/project-owned fields (title, description,
  priority, due date, source status) are refreshed.
* A deleted project task or CRM request cancels its mirror. A rejected CRM
  service request also cancels its mirror.
* Automatic assignment from a project task respects the critical-reassignment
  policy (`WorkloadPolicy.auto_reassign_critical`, default **off**).
* If `WORKLOAD_SYNC_SIGNALS=False`, run `sync_workload_integrations` on a
  schedule; deleted sources are not mirrored by the command, so pair a disable
  with an application-level deletion workflow.

## 6. Operational checks

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test workload
```

Useful diagnostics:

* `WorkloadMetric` rows are written per day, tenant, resource and team. They
  contain JSON-safe primitives only; model instances and live alert rows are
  intentionally excluded.
* `WorkloadAlert.dedupe_key` is unique. Repeated scans update the same alert and
  resolve alerts that are no longer applicable.
* Attachments are served through `workload.views.attachment_download`, which
  re-checks the caller's work-item scope; the media directory itself should not
  be exposed directly by the web server.

## 7. Known limits

* Tenant identity is the workspace owner user. A future Organization model
  would require a data migration of `tenant_id` fields.
* SQLite is supported for local development; production should use PostgreSQL
  so `select_for_update()` provides real row locking for concurrent assignment.
* Celery/Redis are optional and are not started by this change.
* The automation landing-page test still reflects a customized template heading;
  that is unrelated to workload.
