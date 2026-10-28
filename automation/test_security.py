from __future__ import annotations

import json
import socket
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.test import TestCase, override_settings

from .models import IntegrationConnection
from .security.crypto import (
    CredentialDecryptionError,
    CredentialEncryptionError,
    decrypt_json,
    encrypt_json,
)
from .security.redaction import REDACTED, redact_mapping, redact_text
from .security.ssrf import (
    OutboundRequestBlocked,
    safe_http_request,
    validate_outbound_url,
)
from .testing import make_customer, make_user

TEST_FERNET_KEY = Fernet.generate_key().decode()


class CredentialProtectionTests(TestCase):
    def setUp(self):
        self.user = make_user('credential-owner')
        self.customer = make_customer(self.user)

    @override_settings(AUTOMATION_CREDENTIAL_ENCRYPTION_KEY=TEST_FERNET_KEY)
    def test_credentials_are_encrypted_at_rest_and_redacted(self):
        connection = IntegrationConnection.objects.create(
            customer=self.customer,
            name='Webhook',
            provider='custom',
            status='active',
        )
        connection.set_credentials({'token': 'super-secret-token', 'region': 'eu'})
        connection.save()
        connection.refresh_from_db()

        serialised = json.dumps(connection.credentials)
        self.assertNotIn('super-secret-token', serialised)
        self.assertNotIn('eu', serialised)
        self.assertEqual(connection.get_credentials()['token'], 'super-secret-token')
        self.assertEqual(connection.redacted_credentials['token'], REDACTED)
        self.assertEqual(connection.redacted_credentials['region'], 'eu')

    @override_settings(AUTOMATION_CREDENTIAL_ENCRYPTION_KEY=TEST_FERNET_KEY)
    def test_wrong_key_cannot_decrypt(self):
        envelope = encrypt_json({'token': 'abc'})
        with override_settings(AUTOMATION_CREDENTIAL_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            with self.assertRaises(CredentialDecryptionError):
                decrypt_json(envelope)

    def test_empty_credentials_are_safe(self):
        self.assertEqual(decrypt_json({}), {})
        self.assertEqual(encrypt_json({}), {})

    @override_settings(
        AUTOMATION_CREDENTIAL_ENCRYPTION_KEY='',
        SECRET_KEY='production-secret',
        DEBUG=False,
    )
    def test_production_refuses_to_derive_key_from_secret_key(self):
        with self.assertRaises(CredentialEncryptionError):
            encrypt_json({'token': 'must-not-be-stored'})

    @override_settings(AUTOMATION_CREDENTIAL_ENCRYPTION_KEY=TEST_FERNET_KEY)
    def test_legacy_plaintext_credentials_are_encrypted_on_save(self):
        connection = IntegrationConnection(
            customer=self.customer,
            name='Legacy',
            provider='custom',
            status='active',
            credentials={'token': 'legacy-plaintext'},
        )
        connection.save()
        connection.refresh_from_db()
        self.assertNotIn('legacy-plaintext', json.dumps(connection.credentials))
        self.assertEqual(connection.get_credentials()['token'], 'legacy-plaintext')

    def test_redaction_handles_nested_keys_and_text(self):
        payload = redact_mapping({
            'password': 'p',
            'nested': {'api_key': 'abc', 'safe': 'value'},
            'items': [{'Authorization': 'Bearer abc123'}],
        })
        self.assertEqual(payload['password'], REDACTED)
        self.assertEqual(payload['nested']['api_key'], REDACTED)
        self.assertEqual(payload['nested']['safe'], 'value')
        self.assertEqual(payload['items'][0]['Authorization'], REDACTED)
        self.assertNotIn('abc123', redact_text('Authorization: Bearer abc123'))
        self.assertNotIn('sk_live_abc123', redact_text('key sk_live_abc123'))
        self.assertNotIn('hunter2', redact_text('https://user:hunter2@example.test/hook'))


def _address(ip, port=443):
    family = socket.AF_INET6 if ':' in ip else socket.AF_INET
    return (family, socket.SOCK_STREAM, 6, '', (ip, port))


class SSRFTests(TestCase):
    def test_blocks_private_loopback_and_link_local(self):
        with patch('automation.security.ssrf.socket.getaddrinfo', return_value=[_address('10.0.0.5')]):
            with self.assertRaises(OutboundRequestBlocked):
                validate_outbound_url('https://internal.example.test/hook')
        with patch('automation.security.ssrf.socket.getaddrinfo', return_value=[_address('127.0.0.1')]):
            with self.assertRaises(OutboundRequestBlocked):
                validate_outbound_url('http://127.0.0.1/hook')
        with patch('automation.security.ssrf.socket.getaddrinfo', return_value=[_address('169.254.169.254')]):
            with self.assertRaises(OutboundRequestBlocked):
                validate_outbound_url('http://169.254.169.254/latest/meta-data')

    def test_blocks_non_http_schemes_and_embedded_credentials(self):
        for url in ('file:///etc/passwd', 'ftp://example.test/x', 'http://user:pass@example.test/x'):
            with self.assertRaises(OutboundRequestBlocked):
                validate_outbound_url(url)

    def test_allows_public_address(self):
        with patch('automation.security.ssrf.socket.getaddrinfo', return_value=[_address('93.184.216.34')]):
            self.assertEqual(
                validate_outbound_url('https://example.test/hook'),
                'https://example.test/hook',
            )

    @override_settings(AUTOMATION_ALLOW_PRIVATE_OUTBOUND=True, AUTOMATION_ALLOWED_OUTBOUND_PORTS='80,443')
    def test_private_destinations_require_explicit_setting(self):
        with patch('automation.security.ssrf.socket.getaddrinfo', return_value=[_address('127.0.0.1', 80)]):
            self.assertEqual(validate_outbound_url('http://127.0.0.1/'), 'http://127.0.0.1/')

    def test_redirect_to_private_address_is_blocked(self):
        class FakeResponse:
            status_code = 302
            content = b''
            headers = {'Location': 'http://127.0.0.1/admin'}

            def iter_content(self, chunk_size=8192):
                return iter([self.content])

            def close(self):
                pass

        def resolve(host, port, *args, **kwargs):
            if host in {'127.0.0.1', 'localhost'}:
                return [_address('127.0.0.1', port)]
            return [_address('93.184.216.34', port)]

        with patch('automation.security.ssrf.socket.getaddrinfo', side_effect=resolve):
            with patch('automation.security.ssrf.requests.request', return_value=FakeResponse()):
                with self.assertRaises(OutboundRequestBlocked):
                    safe_http_request('GET', 'https://example.test/start')

    def test_request_disallows_localhost_hostname(self):
        with self.assertRaises(OutboundRequestBlocked):
            validate_outbound_url('http://localhost:8000/hook')
