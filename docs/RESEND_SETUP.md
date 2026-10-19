# Transactional email setup (Resend)

OnWebApp sends all transactional email (account verification, password
resets, API-request notifications, dashboard-quote notifications, ...) through
Django's SMTP email backend. In production this is **Resend**; in local
development the console backend prints emails to the terminal.

## How it works

- Configuration is resolved at startup from environment variables in
  `websity_project/email_config.py` and consumed by `websity_project/settings.py`.
- If `EMAIL_HOST`, `EMAIL_HOST_USER` and a password (`RESEND_API_KEY` or
  `EMAIL_HOST_PASSWORD`) are all set, the SMTP backend is used. Otherwise the
  console backend is selected (local dev).
- When `DEBUG=False` and email is not configured, Django logs an error at
  startup and `manage.py check` reports warning `onwebapp.W001`.
- All senders deliver through the central helper
  `home.emails.send_notification_email` (or Django's auth email views, which
  use the same settings). Emails never block or break database writes:
  failures are logged, the application flow continues.
- `SITE_URL` is used to build absolute links inside emails (e.g. the admin
  link in API-request notifications). Behind Coolify's reverse proxy,
  `SECURE_PROXY_SSL_HEADER` is already enabled so password-reset links use
  HTTPS automatically.

## 1. Create a Resend account and API key

1. Sign up at <https://resend.com> and open the dashboard.
2. Go to **API Keys** and create a key (give it sending permission).
   Copy it now - the value is shown only once.
3. You will set it as `RESEND_API_KEY` in Coolify (see step 3). Never commit
   the key to the repository; `.env` files are git-ignored.

## 2. Verify the onwebapp.com sending domain

1. In the Resend dashboard open **Domains** → **Add Domain** and enter
   `onwebapp.com`.
2. Resend shows the exact DNS records your domain needs (record types and
   values depend on when the domain was created; typically TXT/MX records for
   SPF plus a DKIM TXT record - newer domains may show CNAME records
   instead). **Copy every value verbatim from the Resend dashboard** -
   do not invent, reformat or truncate them.
3. Add the records at your DNS provider (or in the Coolify/DNS panel that
   manages `onwebapp.com`):
   - Create each record with the exact **type**, **host/name** and **value**
     shown by Resend.
   - If a record is a CNAME and your DNS provider offers "proxying" (e.g.
     Cloudflare's orange cloud), disable it - proxied CNAMEs never verify.
4. Back in Resend, click **Verify DNS Records**. Verification usually
   completes within 15 minutes but can take up to 72 hours. You can check
   public visibility with <https://dns.email/>.
5. After the domain shows **Verified**, implement the DMARC policy Resend
   suggests for your domain (start with `p=none` monitoring if you are new to
   DMARC). The exact record is generated in Resend's domain settings.

This project never modifies DNS records automatically - all DNS changes are
made by you in your DNS provider's panel.

## 3. Configure Coolify environment variables

In your Coolify service, set (values in angle brackets are yours):

| Variable | Value |
| --- | --- |
| `EMAIL_HOST` | `smtp.resend.com` |
| `EMAIL_PORT` | `587` |
| `EMAIL_HOST_USER` | `resend` |
| `RESEND_API_KEY` | your Resend API key (secret) |
| `EMAIL_USE_TLS` | `True` |
| `EMAIL_USE_SSL` | `False` |
| `EMAIL_TIMEOUT` | `15` |
| `DEFAULT_FROM_EMAIL` | `OnWebApp <notifications@onwebapp.com>` (must be a domain verified in Resend) |
| `SERVER_EMAIL` | `OnWebApp <server@onwebapp.com>` (optional; Django error mails) |
| `ADMIN_EMAIL` | internal ops mailbox that should receive operational notifications |
| `SITE_URL` | `https://onwebapp.com` (used for absolute links inside emails) |

Then **redeploy** the service so the new environment is picked up.

## 4. Verify delivery

1. Open a Django shell on the server (Coolify terminal or `docker exec`):

   ```bash
   python manage.py shell
   ```

2. Send a test email:

   ```python
   from django.core.mail import send_mail
   from django.conf import settings
   print(settings.EMAIL_BACKEND)  # must be ...smtp.EmailBackend
   send_mail('OnWebApp SMTP test', 'It works.', settings.DEFAULT_FROM_EMAIL, ['you@example.com'])
   ```

   A `1` return value means one message was handed to Resend.
3. Trigger a real workflow (e.g. sign up with a second email address, or use
   "Forgot password") and confirm the message arrives.
4. Check the **Logs** section of the Resend dashboard: accepted, delivered,
   bounced and complained messages all appear there.

## 5. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `manage.py check` shows `onwebapp.W001` / startup log says email not configured | `EMAIL_HOST`/`EMAIL_HOST_USER`/`RESEND_API_KEY` missing in Coolify; redeploy after setting them |
| `SMTPAuthenticationError` | Wrong API key, or the key was revoked; create a new key |
| `SMTPRecipientsRefused` / messages accepted but not delivered | Sender domain not verified, or `DEFAULT_FROM_EMAIL` uses a domain that is not verified in Resend |
| Emails go to spam | DNS records not (fully) verified; DMARC missing; check the Resend domain page for every record still pending |
| Password-reset links are `http://` | `SITE_URL` not set to `https://onwebapp.com`, or the proxy is not sending `X-Forwarded-Proto` |
| Local dev sees no emails | Working as intended - the console backend prints them to the `runserver` terminal |

Application-level failures (SMTP timeouts, refused connections) are logged
with full tracebacks under the `home.emails` logger; the affected workflow
(e.g. an API request or quote) is still saved.
