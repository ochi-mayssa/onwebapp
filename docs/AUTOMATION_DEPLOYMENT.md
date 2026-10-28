# Automation Execution & Billing — Deployment Notes

This document describes the production requirements for the `automation` app. It
records what is **actually present in the repository** and what still has to be
configured manually. It is not a statement that production is ready.

## 1. Current repository findings (verified 2026-10-26)

| Area | Finding |
| --- | --- |
| Coolify config | No Coolify service definition, `docker-compose.yml`, or `coolify.json` is present in the repository. |
| Dockerfile | Runs `migrate`, `initialize_onwebapp`, then one Gunicorn process (`--workers 1 --threads 8`). No worker or beat process. |
| `nixpacks.toml` | Only starts Gunicorn. No worker or beat process. |
| Celery app | `websity_project/celery.py` exists and auto-discovers tasks. |
| Celery default | `USE_CELERY=False` unless set in the environment. `CELERY_BROKER_URL` defaults to `redis://localhost:6379/0`. |
| Automation mode | `AUTOMATION_EXECUTION_MODE` defaults to `celery` when `USE_CELERY=True`, otherwise `inline`. |
| Redis | No Redis service is defined in the repository. `REDIS_URL` is optional and only changes Channels/cache behavior. |
| Worker / beat | Not configured anywhere in the repository. |
| Existing payments Stripe | `payments.views.webhook` exists for the legacy user subscription flow. It is separate from automation billing and does not deduplicate provider events. |
| Automation billing | Uses the existing `automation.Plan`, `Subscription`, `BillingEvent`, and `UsageRecord` models, with a provider adapter in `automation/billing/`. |

**Conclusion:** the current repository cannot process asynchronous automation
executions in production. Until Redis + a Celery worker (and beat, if scheduled
tasks are needed) are configured in Coolify, `AUTOMATION_EXECUTION_MODE` must not
be left at `inline` in production. Inline mode runs inside the web request and is
a local-development/testing fallback only.

## 2. Required Coolify services

Create these as separate processes/services (or as separate Coolify "services"
inside the same project):

1. **Web** — existing Dockerfile/Gunicorn process.
2. **Redis** — a persistent Redis 7 service (or managed Redis).
3. **Celery worker** — the automation task consumer.
4. **Celery beat** — only if you enable periodic tasks. The automation engine
   currently uses retries inside one task and does not require beat; the existing
   `CELERY_BEAT_SCHEDULE` already contains other apps' jobs, so beat is required
   if those are expected to run.
5. **Migration job** — preferably a one-off command run before web/worker start,
   rather than relying on the Dockerfile's `migrate` on every web boot.

The same code image and environment must be used for web, worker, and beat.

## 3. Required environment variables

Values in angle brackets are supplied by the operator. Do not commit real values.

| Variable | Required | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | yes | Existing Django secret. |
| `DEBUG` | yes | Must be `False` in production. |
| `ALLOWED_HOSTS` | yes | Production hosts. |
| `DATABASE_URL` | yes | PostgreSQL connection string. |
| `SITE_URL` | yes | Absolute URL used for Stripe return URLs. |
| `USE_CELERY` | yes | Set `True` in production. |
| `CELERY_BROKER_URL` | yes | Redis broker, e.g. `redis://<redis-host>:6379/0`. |
| `CELERY_RESULT_BACKEND` | recommended | Redis result backend. |
| `REDIS_URL` | recommended | Same Redis URL; used by Channels/cache. |
| `AUTOMATION_EXECUTION_MODE` | yes | `celery` in production. |
| `AUTOMATION_CREDENTIAL_ENCRYPTION_KEY` | yes | Fernet key for integration credentials. Generate once and store in the secret manager. |
| `STRIPE_SECRET_KEY` | yes, for billing | Existing Stripe secret key. |
| `STRIPE_PUBLISHABLE_KEY` | recommended | Existing Stripe publishable key. |
| `AUTOMATION_STRIPE_WEBHOOK_SECRET` | yes, for automation billing | Signing secret for the `/automation/billing/webhook/stripe/` endpoint. If omitted it falls back to `STRIPE_WEBHOOK_SECRET`, which is only correct if both endpoints share the same secret (usually they do not). |
| `AUTOMATION_EXECUTION_TIMEOUT_SECONDS` | optional | Default `60`. |
| `AUTOMATION_MAX_EXECUTION_ATTEMPTS` | optional | Default `3`; bounded retries. |
| `AUTOMATION_STALE_EXECUTION_SECONDS` | optional | Default `900`. A `running` row younger than this is never executed twice; keep above the worker task time limit. |
| `AUTOMATION_RETRY_BACKOFF_SECONDS` | optional | Default `2`. |
| `AUTOMATION_MAX_STEPS` | optional | Default `20`. |
| `AUTOMATION_MAX_PAYLOAD_BYTES` | optional | Default `65536`. |
| `AUTOMATION_MAX_EMAIL_RECIPIENTS` | optional | Default `20`. |
| `AUTOMATION_OUTBOUND_TIMEOUT_SECONDS` | optional | Default `10`. |
| `AUTOMATION_MAX_HTTP_RESPONSE_BYTES` | optional | Default `1048576`. |
| `AUTOMATION_ALLOWED_OUTBOUND_PORTS` | optional | Default `80,443,8443`. |
| `AUTOMATION_ALLOW_PRIVATE_OUTBOUND` | optional | Must remain `False` in production. |
| `AUTOMATION_WEBHOOK_MAX_BODY_BYTES` | optional | Default `1048576`. |
| `EMAIL_*` / `RESEND_API_KEY` | for email action | Existing Resend SMTP configuration (see `docs/RESEND_SETUP.md`). |

Generate the credential key once:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store it as a secret. Rotating it makes existing `IntegrationConnection`
ciphertext unreadable; re-save credentials after rotation. Never put the key in
`SECRET_KEY`.

Production (`DEBUG=False`) refuses to derive a key from `SECRET_KEY`. Only local
development may omit the variable, in which case a development-only key is
derived and a warning is logged.

## 4. Exact process commands

Web (existing image):

```bash
gunicorn websity_project.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 8 --timeout 120
```

Celery worker (Linux production):

```bash
celery -A websity_project worker -l info --concurrency=2
```

On Windows development only, prefork is unavailable; use `--pool=solo`. Do not
use `solo` as the production worker command.

Celery beat (only if scheduled tasks are required):

```bash
celery -A websity_project beat -l info \
  --pidfile=/tmp/celerybeat.pid \
  --schedule=/tmp/celerybeat-schedule
```

One-off migration:

```bash
python manage.py migrate --noinput
python manage.py check --deploy
```

Encrypt any legacy plaintext integration credentials after setting the key:

```bash
python manage.py encrypt_automation_credentials --dry-run
python manage.py encrypt_automation_credentials
```

Recover executions abandoned in `running` by a crashed worker (safe to run from a
scheduled job; it never touches rows younger than
`AUTOMATION_STALE_EXECUTION_SECONDS`):

```bash
python manage.py requeue_stale_executions --dry-run
python manage.py requeue_stale_executions
```

Redis health / worker check:

```bash
redis-cli -u "$CELERY_BROKER_URL" ping
celery -A websity_project inspect ping
```

## 5. Stripe webhook configuration

Create a Stripe endpoint:

```text
https://<your-domain>/automation/billing/webhook/stripe/
```

Subscribe at minimum to:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `customer.subscription.paused`
- `customer.subscription.resumed`
- `invoice.paid`
- `invoice.payment_succeeded`
- `invoice.payment_failed`
- `invoice.payment_action_required`

Copy that endpoint's signing secret into
`AUTOMATION_STRIPE_WEBHOOK_SECRET`. Do not reuse the legacy payments endpoint
secret unless it is genuinely the same endpoint.

The checkout success URL only renders a message. It never grants access. Access
is granted exclusively by a signature-verified, deduplicated webhook that
maps the provider event to the local subscription.

## 6. Manual verification checklist (do not skip)

- [ ] Redis reachable from the worker container.
- [ ] `celery -A websity_project inspect ping` returns a pong.
- [ ] Worker logs show `automation.execute_workflow` registered.
- [ ] `AUTOMATION_EXECUTION_MODE=celery` and `USE_CELERY=True`.
- [ ] `AUTOMATION_CREDENTIAL_ENCRYPTION_KEY` set and backed up.
- [ ] Stripe webhook signature secret is for the automation endpoint.
- [ ] Test mode: trigger a workflow and confirm `AutomationExecution.status` reaches
      `succeeded` through the worker, not inline.
- [ ] Test mode: duplicate webhook delivery produces one `BillingEvent` row.
- [ ] Test mode: failed payment moves the subscription to `past_due` and blocks
      new executions.
- [ ] Test mode: change `AUTOMATION_MAX_EXECUTION_ATTEMPTS` and confirm retries are
      bounded.
- [ ] Run `python manage.py test automation`.

## 7. Known limitations / decisions still required

- **No Coolify definition in the repo:** worker/beat/Redis must be created in the
  Coolify UI. This repository cannot verify that configuration.
- **Inline mode risk:** if `USE_CELERY` is false in production and the operator
  explicitly sets `AUTOMATION_EXECUTION_MODE=inline`, execution happens in the web
  worker. This is documented but not enforced as a startup error.
- **DNS rebinding:** outbound URL validation resolves the host and rejects
  private/loopback/link-local/reserved addresses, and re-validates redirects. A
  determined DNS-rebinding attack between resolution and connection is mitigated
  only by running egress through a policy-enforcing proxy.
- **Retry semantics:** completed steps are checkpointed and skipped on retry, but
  a crash after an external side effect and before the checkpoint can duplicate an
  email or HTTP call. HTTP actions send an `Idempotency-Key`; email delivery cannot
  be made exactly-once with SMTP.
- **Usage billing:** one accepted execution consumes one quota unit even if the
  action later fails. This is an explicit product decision, not a refund model.
- **Stripe event ordering:** the adapter applies events in arrival order. Stripe
  normally delivers in order, but a delayed older `customer.subscription.updated`
  event could overwrite a newer state. Add provider event timestamps/version
  comparison before relying on strict ordering.
- **Legacy payments webhook:** `payments.views.webhook` still exists and lacks the
  deduplication used by automation billing. It was intentionally not rewritten
  because it drives a separate user-plan flow. Unifying the two billing systems
  needs a product decision.
- **Pending unrelated migrations:** `makemigrations --check` reports pre-existing
  pending migrations in `branding` and `community`, unrelated to this change. Do
  not deploy the automation migration alongside unplanned unrelated migrations
  without review.
