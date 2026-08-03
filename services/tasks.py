from django.conf import settings
from django.core.mail import EmailMessage
import threading
from django.template.loader import render_to_string

try:
    # Prefer Celery shared_task when available
    from celery import shared_task
    CELERY_AVAILABLE = True
except Exception:
    shared_task = None
    CELERY_AVAILABLE = False


def _deliver_email(subject, html_body, recipient_email, attachments=None):
    if attachments is None:
        attachments = []
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'athmarofficial4@gmail.com')
    to_list = [recipient_email] if recipient_email else []
    cc_list = []
    if from_email and from_email not in to_list:
        cc_list.append(from_email)

    msg = EmailMessage(subject=subject, body=html_body, from_email=from_email, to=to_list, cc=cc_list)
    msg.content_subtype = 'html'
    for fn, data, mimetype in attachments:
        try:
            msg.attach(fn, data, mimetype)
        except Exception:
            pass
    try:
        msg.send(fail_silently=False)
    except Exception:
        # swallow; this is a background worker/task
        pass


if CELERY_AVAILABLE and getattr(settings, 'USE_CELERY', False):
    @shared_task
    def send_result_email(recipient_email, subject, html_body, attachments=None):
        _deliver_email(subject, html_body, recipient_email, attachments=attachments or [])

else:
    def send_result_email(recipient_email, subject, html_body, attachments=None):
        # Use a background thread to avoid blocking the request in dev/fallback mode
        try:
            t = threading.Thread(target=_deliver_email, args=(subject, html_body, recipient_email, attachments or []), daemon=True)
            t.start()
        except Exception:
            # last resort: synchronous send
            _deliver_email(subject, html_body, recipient_email, attachments or [])
