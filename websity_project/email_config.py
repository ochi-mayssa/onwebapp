"""Transactional email configuration helpers.

Kept out of ``settings.py`` so the resolution logic can be unit-tested with a
plain environment mapping. ``settings.py`` calls :func:`resolve_email_config`
once at import time.

Production uses Resend's SMTP endpoint (``smtp.resend.com``): the Resend API
key doubles as the SMTP password. When no credentials are configured the
console backend is selected so local development keeps printing emails to the
terminal.
"""

SMTP_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
CONSOLE_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DEFAULT_FROM_EMAIL = 'OnWebApp <notifications@onwebapp.com>'


def verification_policy(env, debug):
    """Decide whether email verification is mandatory.

    Security requirement: production (``DEBUG=False``) can NEVER disable
    verification, regardless of environment configuration. Only a development
    server may relax it, and only when explicitly asked (default: enabled).
    """
    requested = (env.get('EMAIL_VERIFICATION_REQUIRED') or 'True').strip().lower() in ('1', 'true', 'yes')
    if not debug:
        return True
    return requested


def resolve_email_config(env):
    """Return Django email settings derived from an environment mapping.

    Recognised keys: ``EMAIL_HOST``, ``EMAIL_PORT``, ``EMAIL_HOST_USER``,
    ``RESEND_API_KEY`` (preferred) / ``EMAIL_HOST_PASSWORD``,
    ``EMAIL_USE_TLS``, ``EMAIL_USE_SSL``, ``EMAIL_TIMEOUT``,
    ``DEFAULT_FROM_EMAIL``, ``SERVER_EMAIL``, ``ADMIN_EMAIL``.
    """
    host = (env.get('EMAIL_HOST') or '').strip()
    port = int(env.get('EMAIL_PORT', '587'))
    user = (env.get('EMAIL_HOST_USER') or '').strip()
    # Resend exposes a single API key that doubles as the SMTP password.
    password = (env.get('RESEND_API_KEY') or env.get('EMAIL_HOST_PASSWORD') or '').strip()
    use_tls = (env.get('EMAIL_USE_TLS') or 'True').strip().lower() in ('1', 'true', 'yes')
    use_ssl = (env.get('EMAIL_USE_SSL') or 'False').strip().lower() in ('1', 'true', 'yes')
    timeout = int(env.get('EMAIL_TIMEOUT', '15'))
    default_from = (env.get('DEFAULT_FROM_EMAIL') or DEFAULT_FROM_EMAIL).strip()
    server_email = (env.get('SERVER_EMAIL') or '').strip() or default_from
    configured = bool(host and user and password)
    return {
        'EMAIL_BACKEND': SMTP_BACKEND if configured else CONSOLE_BACKEND,
        'EMAIL_HOST': host,
        'EMAIL_PORT': port,
        'EMAIL_HOST_USER': user,
        'EMAIL_HOST_PASSWORD': password,
        'EMAIL_USE_TLS': use_tls,
        'EMAIL_USE_SSL': use_ssl,
        'EMAIL_TIMEOUT': timeout,
        'DEFAULT_FROM_EMAIL': default_from,
        'SERVER_EMAIL': server_email,
        'ADMIN_EMAIL': (env.get('ADMIN_EMAIL') or '').strip(),
        'EMAIL_CONFIGURED': configured,
    }
