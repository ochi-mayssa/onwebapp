"""Signed, expiring links used in document emails.

Links are bearer capabilities: whoever holds the link can view the document.
They therefore expire, are bound to the document version, and every access is
recorded in the document audit trail.
"""
from django.conf import settings
from django.core import signing
from django.urls import reverse

SALT = 'documents.access'


class TokenError(Exception):
    """Base class for unusable document links."""


class TokenInvalid(TokenError):
    pass


class TokenExpired(TokenError):
    pass


def max_age():
    return int(getattr(settings, 'DOCUMENT_LINK_MAX_AGE', 60 * 24 * 60 * 60))


def make_token(document):
    return signing.dumps({'d': document.pk, 'v': document.version}, salt=SALT)


def read_token(token):
    """Return the Document for a token or raise :class:`TokenError`."""
    from .models import Document

    try:
        payload = signing.loads(token, salt=SALT, max_age=max_age())
    except signing.SignatureExpired as exc:
        raise TokenExpired('This link has expired.') from exc
    except signing.BadSignature as exc:
        raise TokenInvalid('This link is not valid.') from exc

    try:
        document = Document.objects.select_related('doc_type', 'customer').get(pk=payload['d'])
    except (Document.DoesNotExist, KeyError) as exc:
        raise TokenInvalid('This document no longer exists.') from exc

    if int(payload.get('v', 0)) != int(document.version):
        raise TokenInvalid('This document was updated after the link was sent. Please use the latest email.')

    return document


def public_url(document):
    site = (getattr(settings, 'SITE_URL', '') or '').rstrip('/')
    path = reverse('documents:public_view', args=[make_token(document)])
    return f'{site}{path}' if site else path
