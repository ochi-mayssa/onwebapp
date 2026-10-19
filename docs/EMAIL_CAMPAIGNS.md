# Email Campaigns (admin)

Superusers can compose marketing email campaigns from the admin navigation
(**Campaigns**). Campaigns are delivered through the same Resend SMTP
configuration as transactional email (`docs/RESEND_SETUP.md`), via the
centralized helper in `home/emails.py`.

## Features

- **Compose**: internal campaign name, subject, plain-text body and optional
  HTML body (sanitized with a strict allowlist — scripts, event handlers and
  unsafe links are stripped before storage and again before sending).
- **Recipient selection**:
  - All eligible clients
  - Clients with / without an active subscription (`users.UserSubscription`)
  - Selected individual clients
  - Eligible = active, non-staff/non-superuser accounts with a valid email
    who have **not** opted out of marketing email
    (`UserProfile.marketing_emails_enabled`). Staff accounts are never
    included.
- **Preview & confirmation**: the exact rendered email (including the
  unsubscribe footer) and the recipient count are shown before sending.
- **History & delivery results**: per-campaign counters (sent / failed /
  pending) plus a per-recipient table with attempts and truncated error
  messages (no SMTP credentials or message bodies are stored).

## How sending works (important limitations)

This deployment has **no Celery worker**. Campaigns are delivered by a
**daemon thread inside the web process**, started when the administrator
confirms the send:

- The confirm request returns immediately; delivery continues in the
  background in small batches (`CAMPAIGN_BATCH_SIZE` recipients, then a
  `CAMPAIGN_BATCH_DELAY_SECONDS` pause — defaults sized for Resend's ~2
  requests/second rate limit).
- Each recipient gets an individual message (no shared To/CC), so recipient
  addresses are never exposed to each other.
- Per-recipient rows are the source of truth; counters are recomputed after
  every batch. If the process is restarted mid-send, the campaign stays in
  "Sending" (shown as *Interrupted* after 30 minutes) with accurate pending
  counts and can be **resumed** from the campaign detail page — only pending
  rows are re-processed.
- Campaigns are capped at `CAMPAIGN_MAX_RECIPIENTS` (default 500). For larger
  volumes, run proper background workers (Celery + Redis are already in
  `requirements.txt`) and re-point `campaigns.delivery.start_send` at a task.
- Because delivery is in-process, a hard crash can delay or drop the remaining
  pending sends until an admin resumes the campaign. Do not rely on campaigns
  for time-critical or essential transactional messaging — those flows
  (verification, password reset, API request updates, quotes) are separate
  and unaffected.

## Unsubscribe

Every campaign email contains an unsubscribe link (signed, per-user token, no
login required). The public page at `/campaigns/unsubscribe/<token>/` confirms
and then sets `UserProfile.marketing_emails_enabled = False`. Users can also
toggle the preference in **Profile → Notification preferences**. Campaign
audiences always exclude opted-out users. Transactional email is never
affected by this flag.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `CAMPAIGN_MAX_RECIPIENTS` | `500` | Hard cap per campaign |
| `CAMPAIGN_BATCH_SIZE` | `5` | Recipients per batch |
| `CAMPAIGN_BATCH_DELAY_SECONDS` | `2.5` | Pause between batches (~2 sends/sec) |

Email transport variables (`EMAIL_HOST`, `RESEND_API_KEY`, ...) are shared
with transactional email — see `docs/RESEND_SETUP.md`. Secrets never appear
in campaign pages, logs emitted by the campaign code, or the repository.

## Safe usage guidance

- Always check the preview and the recipient count before confirming; the
  send cannot be repeated (duplicate submissions are refused atomically).
- Keep subjects and bodies free of secrets — delivery errors are stored per
  recipient as a short status string only, but the campaign content itself is
  visible to all superusers in history.
- Test with a small selected audience first (e.g. one test account) before
  sending to everyone.
- Respect local laws for marketing email (CAN-SPAM, GDPR): the unsubscribe
  link and opt-out enforcement are provided for this purpose; sender identity
  comes from the verified `DEFAULT_FROM_EMAIL` domain.

## URLs (superuser only except unsubscribe)

- `/campaigns/` — compose
- `/campaigns/history/` — history
- `/campaigns/<id>/confirm/` — preview + confirmation
- `/campaigns/<id>/detail/` — delivery results (+ resume)
- `/campaigns/<id>/resume/`, `/campaigns/<id>/cancel/` — POST actions
- `/campaigns/unsubscribe/<token>/` — public opt-out
