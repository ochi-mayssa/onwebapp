# Automatic invoicing

The `documents` app can generate invoices automatically from configurable
billing rules (`BillingProfile`). It reuses the ReportLab PDF engine, CRM
customers, private storage, email delivery and the document audit trail.

Generated invoices are **drafts by default**. An administrator reviews the PDF
and clicks **Send to client**. Fully automatic sending is opt-in per rule.

## Where to configure it

1. Log in as a staff user.
2. Open **Documents -> Invoice automation** (`/documents/billing/`).
3. Click **New billing rule**.
4. Choose a CRM customer, document type (usually *Invoice*), and trigger.
5. Set pricing (a fixed line or itemized rows), tax, currency and due days.
6. Leave **Send automatically** off unless you fully trust the rule.
7. Save.

The same records are available in Django admin under **Billing profiles**.

## Triggers

| Trigger | When it runs |
| --- | --- |
| When a project is created | A `projects.Project` is created for the customer. |
| When a project is completed | The project's `current_status` becomes `COMPLETED`. |
| When a project phase is completed | A `ProjectPhase` becomes `COMPLETED` or its approval becomes `APPROVED`. Optionally restrict the rule to one phase type. |
| On a recurring schedule | The rule's `next_invoice_date` is due. Frequency can be monthly, quarterly or yearly. |

A rule can target one project or every project for the customer. Rules are
matched through the project's client user and the CRM `Customer.user` /
`Customer.email` link.

## Pricing

- **Single fixed line** uses `default_description` + `default_amount`.
- **Itemized line items** copies the rule's line items.
- If an itemized rule has no line items, the fixed line is used as a fallback.
- Tax, discount, totals and the PDF are calculated by the existing document
  engine.

## Duplicate protection

Each automatic document stores an `automation_key`, for example:

- `project-created:<project_id>:<profile_id>`
- `project-completed:<project_id>:<profile_id>`
- `phase-completed:<phase_id>:<profile_id>`
- `recurring:<profile_id>:<period_start>`

The column is unique, so repeated signals, duplicate web requests or retried
tasks cannot create the same invoice twice.

## Recurring invoices

Recurring rules advance `next_invoice_date` automatically after every run, even
when a period is skipped (for example, the customer has no email). This prevents
a permanently stuck schedule.

Run recurring rules in one of these ways:

### Celery Beat (recommended in production)

`CELERY_BEAT_SCHEDULE` already contains:

```python
'generate-due-invoices-daily': {
    'task': 'documents.tasks.generate_due_invoices',
    'schedule': 86400.0,
},
```

Start a worker and beat process:

```bash
celery -A websity_project worker -l info
celery -A websity_project beat -l info
```

Requires `USE_CELERY=True` and a reachable Redis broker.

### Management command (cron or manual)

```bash
python manage.py generate_due_invoices
python manage.py generate_due_invoices --date 2026-01-15
```

Add it to cron if Celery Beat is not available:

```cron
0 6 * * * cd /path/to/app && python manage.py generate_due_invoices
```

The staff UI also has a **Run due invoices** button.

## Auto-send

When **Send automatically** is enabled, the generated PDF is emailed to the CRM
customer's email immediately. The invoice is only auto-sent when its total is
greater than zero. If delivery fails, the invoice remains a draft and the
failure is recorded in the email log and audit trail.

## Legacy behaviour

The old `projects.signals.automated_invoice_generation` receiver (hardcoded
prices, WeasyPrint, `projects.Invoice`) is disabled by default. Control it with:

```env
LEGACY_PROJECT_AUTO_INVOICE=False
```

Do not enable both systems for the same project, or you will create two
invoices.

## Tests

```bash
python manage.py test documents projects home
```

The automation tests cover project-created, project-completed, phase-completed,
approval, recurring periods, month-end clamping, idempotency, auto-send, missing
customer email, staff permissions and the billing form.
