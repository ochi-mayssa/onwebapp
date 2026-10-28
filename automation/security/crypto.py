"""Credential encryption for integration connections.

The preferred production configuration is a dedicated, managed encryption key::

    AUTOMATION_CREDENTIAL_ENCRYPTION_KEY=<urlsafe base64 32-byte Fernet key>

Generate one with::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

For local development (``DEBUG=True``), when the dedicated key is absent, a key
is derived from Django's ``SECRET_KEY``. Production (``DEBUG=False``) refuses to
derive a key and raises ``CredentialEncryptionError`` so credentials are never
encrypted with an implicit key.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger('automation')

ENVELOPE_MARKER = '__automation_enc__'
ENVELOPE_VERSION = 1
_DERIVATION_SALT = b'onwebapp:automation:credentials:v1'


class CredentialDecryptionError(ValueError):
    """Raised when a stored credential envelope cannot be decrypted."""


class CredentialEncryptionError(ValueError):
    """Raised when credentials cannot be encrypted."""


@lru_cache(maxsize=4)
def _fernet_from_material(key_material: str) -> Fernet:
    """Build a Fernet instance from a Fernet key or a passphrase.

    A valid Fernet key is used as-is. Any other non-empty string is treated as a
    passphrase and stretched with PBKDF2 so operators can supply a long random
    secret from their secret manager without having to know Fernet's format.
    """
    try:
        return Fernet(key_material.encode('ascii'))
    except (ValueError, TypeError):
        digest = hashlib.pbkdf2_hmac(
            'sha256',
            key_material.encode('utf-8'),
            _DERIVATION_SALT,
            200_000,
        )
        return Fernet(base64.urlsafe_b64encode(digest))


def _get_fernet() -> Fernet:
    configured = (getattr(settings, 'AUTOMATION_CREDENTIAL_ENCRYPTION_KEY', '') or '').strip()
    if configured:
        return _fernet_from_material(configured)

    secret_key = getattr(settings, 'SECRET_KEY', '') or ''
    if not secret_key:
        raise CredentialEncryptionError(
            'No encryption key is available. Set AUTOMATION_CREDENTIAL_ENCRYPTION_KEY.'
        )
    if not getattr(settings, 'DEBUG', False):
        # Fail closed: deriving from SECRET_KEY in production would silently
        # couple credential data to a key that is rotated for other reasons.
        raise CredentialEncryptionError(
            'AUTOMATION_CREDENTIAL_ENCRYPTION_KEY must be set in production; '
            'refusing to derive a credential key from SECRET_KEY.'
        )
    return _fernet_from_material(f'derived:{secret_key}')


def encrypt_json(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Encrypt a JSON-serialisable mapping into a versioned envelope."""
    if not payload:
        return {}
    if not isinstance(payload, dict):
        raise CredentialEncryptionError('Credential payload must be a mapping.')
    try:
        serialised = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
        token = _get_fernet().encrypt(serialised).decode('ascii')
    except (TypeError, ValueError) as exc:
        raise CredentialEncryptionError('Credentials are not JSON-serialisable.') from exc
    return {
        ENVELOPE_MARKER: ENVELOPE_VERSION,
        'ciphertext': token,
    }


def decrypt_json(envelope: dict[str, Any] | None) -> dict[str, Any]:
    """Decrypt a credential envelope.

    Empty ``{}`` is treated as "no credentials". Plaintext dictionaries written by
    the original scaffold are returned unchanged for backwards compatibility, but
    new writes always use the encrypted envelope.
    """
    if not envelope:
        return {}
    if not isinstance(envelope, dict):
        raise CredentialDecryptionError('Stored credentials are not a mapping.')
    if ENVELOPE_MARKER not in envelope:
        # Legacy plaintext row. Do not log the contents.
        return dict(envelope)

    if envelope.get(ENVELOPE_MARKER) != ENVELOPE_VERSION:
        raise CredentialDecryptionError('Unsupported credential envelope version.')

    token = envelope.get('ciphertext')
    if not isinstance(token, str) or not token:
        raise CredentialDecryptionError('Credential envelope is missing ciphertext.')

    try:
        plaintext = _get_fernet().decrypt(token.encode('ascii'))
        data = json.loads(plaintext.decode('utf-8'))
    except (InvalidToken, ValueError, TypeError) as exc:
        raise CredentialDecryptionError(
            'Credentials could not be decrypted. Check the automation encryption key.'
        ) from exc

    if not isinstance(data, dict):
        raise CredentialDecryptionError('Decrypted credentials are not a mapping.')
    return data
