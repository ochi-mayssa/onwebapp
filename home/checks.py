"""System checks for transactional email configuration."""
import logging

from django.conf import settings
from django.core.checks import Warning, register

logger = logging.getLogger(__name__)


@register()
def email_configuration_check(app_configs, **kwargs):
    """Warn (loudly) when production runs without a real email backend."""
    from django.conf import settings as dj_settings

    if dj_settings.DEBUG:
        return []
    if getattr(dj_settings, 'EMAIL_BACKEND', '').endswith('smtp.EmailBackend'):
        return []
    return [
        Warning(
            'Email is not configured for production use.',
            hint=(
                'Set EMAIL_HOST=smtp.resend.com, EMAIL_HOST_USER=resend and '
                'RESEND_API_KEY (or EMAIL_HOST_PASSWORD) so transactional emails '
                'are delivered. See docs/RESEND_SETUP.md.'
            ),
            id='onwebapp.W001',
        ),
    ]
