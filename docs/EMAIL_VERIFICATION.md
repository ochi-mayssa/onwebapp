# Mandatory email verification

Every account must verify its email address before it can sign in.
This document describes the flow, the settings, and how to troubleshoot
emails that do not appear in the Resend dashboard.

## Flow

1. **Sign up** (`/users/signup/`)
   - The account is created **inactive** (`is_active=False`) and the user is
     **not** signed in.
   - A verification email is sent **synchronously** (in-process; this
     deployment has no Celery worker) with a link built from `SITE_URL`:
     `/users/verify-email/<uid>/<token>/`.
   - The response redirects to `/users/check-email/` with a success message.
     If sending fails, a safe error message is shown, the account is kept,
     and the page offers a resend option. Nothing is reported as delivered
     unless the send actually succeeded.
2. **Check your email page** (`/users/check-email/`)
   - Neutral confirmation page plus a **resend** form (POST-only, CSRF
     protected, throttled to one attempt per address per 60 seconds).
   - Every response is **generic** ("If an account exists for this
     address...") so the endpoint cannot be used to discover accounts.
3. **Verify** (`/users/verify-email/<uid>/<token>/`)
   - Validates uid **and** token (Django's `default_token_generator`; a user
     id alone never activates anything).
   - The token expires after Django's default `PASSWORD_RESET_TIMEOUT`
     (3 days).
   - On success: activates the account, sets `profile.email_verified`,
     logs the activity, signs the user in, and renders the success page.
     Logging in changes `last_login`, which is part of the token hash - so
     the link **cannot be used a second time** (re-use shows "Already
     verified").
   - Invalid/expired/used tokens render the invalid/already-verified page;
     the account stays inactive.
4. **Sign in** (`/users/login/`)
   - Inactive accounts are rejected by Django's `ModelBackend` server-side
     (correct password + inactive = "pending verification" hint; wrong
     password = generic "Invalid email or password").
   - Verified users and superusers sign in exactly as before.

## Settings

- `EMAIL_VERIFICATION_REQUIRED` - resolved by
  `verification_policy(env, debug)` in `websity_project/email_config.py`.
  - **`DEBUG=False` (production): always `True`, environment cannot disable
    it.**
  - `DEBUG=True`: default `True`; set `EMAIL_VERIFICATION_REQUIRED=False` in
    `.env` to skip verification during local development.
- `SITE_URL` - base for absolute verification links (use the public HTTPS
  origin in production, e.g. `https://onwebapp.com`).
- `PASSWORD_RESET_TIMEOUT` (not overridden) - 3-day token lifetime.

## Why emails did not appear in the Resend logs

Diagnosis of the original incident (checked in this order):

1. **No Celery worker** - verification used to be dispatched with `.delay()`
   in a background thread; without a worker the task was silently dropped.
   Verification/resend are now sent synchronously in-process, and ERP
   provisioning remains the only best-effort background task.
2. **Console backend fallback** - if `EMAIL_HOST`/`EMAIL_HOST_USER`/
   `RESEND_API_KEY` are missing in Coolify, Django falls back to the console
   backend (emails print to the server log, never reach Resend). The app now
   logs an error at startup and `manage.py check` warns with `onwebapp.W001`
   when `DEBUG=False` and email is unconfigured.
3. **Link scheme** - links were built with `request.build_absolute_uri`
   (could yield `http://`); they are now built from `SITE_URL` (HTTPS).

### Production checklist

- `DEBUG=False`, `SITE_URL=https://onwebapp.com`
- `EMAIL_HOST=smtp.resend.com`, `EMAIL_HOST_USER=resend`,
  `RESEND_API_KEY=re_...` set in Coolify
- Domain `onwebapp.com` verified in Resend (DNS records) - see
  `docs/RESEND_SETUP.md`
- `python manage.py check` shows no `W001` warning
- Test: sign up with a real address, receive the email, click the link,
  sign in. Then check the Resend **Logs** dashboard.

## Tests

`users/tests.py` covers the flow:

- `VerificationEmailTests` - email content/dispatch from signup.
- `VerifyEmailViewTests` - token validation and result pages.
- `MandatoryVerificationTests` - inactive-until-verified, activation,
  expiry, single use, login blocking (both normal and forced sessions),
  resend throttling/generic responses, delivery-failure messaging, and the
  development opt-out.

Run: `python manage.py test home users dashboard_inquiry campaigns`
