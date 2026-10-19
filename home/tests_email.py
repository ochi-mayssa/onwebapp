"""Tests for the centralized Resend/SMTP transactional email integration."""
from unittest import mock

from django.conf import settings
from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from websity_project.email_config import (
    CONSOLE_BACKEND,
    SMTP_BACKEND,
    resolve_email_config,
)

from .emails import send_notification_email, valid_recipients
from .models import APIRequest
from .tests import _payload


class EmailConfigResolutionTests(SimpleTestCase):
    """Pure-function tests for websity_project.email_config.resolve_email_config."""

    def test_uses_smtp_when_resend_key_configured(self):
        config = resolve_email_config({
            'EMAIL_HOST': 'smtp.resend.com',
            'EMAIL_HOST_USER': 'resend',
            'RESEND_API_KEY': 're_secret_123',
        })
        self.assertEqual(config['EMAIL_BACKEND'], SMTP_BACKEND)
        self.assertEqual(config['EMAIL_HOST'], 'smtp.resend.com')
        self.assertEqual(config['EMAIL_PORT'], 587)
        self.assertEqual(config['EMAIL_HOST_USER'], 'resend')
        self.assertEqual(config['EMAIL_HOST_PASSWORD'], 're_secret_123')
        self.assertTrue(config['EMAIL_USE_TLS'])
        self.assertFalse(config['EMAIL_USE_SSL'])
        self.assertEqual(config['EMAIL_TIMEOUT'], 15)
        self.assertTrue(config['EMAIL_CONFIGURED'])

    def test_resend_api_key_preferred_over_email_host_password(self):
        config = resolve_email_config({
            'EMAIL_HOST': 'smtp.resend.com',
            'EMAIL_HOST_USER': 'resend',
            'RESEND_API_KEY': 're_primary',
            'EMAIL_HOST_PASSWORD': 'legacy',
        })
        self.assertEqual(config['EMAIL_HOST_PASSWORD'], 're_primary')

    def test_falls_back_to_email_host_password(self):
        config = resolve_email_config({
            'EMAIL_HOST': 'smtp.resend.com',
            'EMAIL_HOST_USER': 'resend',
            'EMAIL_HOST_PASSWORD': 'legacy',
        })
        self.assertEqual(config['EMAIL_BACKEND'], SMTP_BACKEND)
        self.assertEqual(config['EMAIL_HOST_PASSWORD'], 'legacy')

    def test_console_backend_when_not_fully_configured(self):
        for env in (
            {},
            {'EMAIL_HOST': 'smtp.resend.com'},
            {'EMAIL_HOST': 'smtp.resend.com', 'EMAIL_HOST_USER': 'resend'},
        ):
            with self.subTest(env=env):
                config = resolve_email_config(env)
                self.assertEqual(config['EMAIL_BACKEND'], CONSOLE_BACKEND)
                self.assertFalse(config['EMAIL_CONFIGURED'])

    def test_defaults(self):
        config = resolve_email_config({})
        self.assertEqual(config['DEFAULT_FROM_EMAIL'], 'OnWebApp <notifications@onwebapp.com>')
        self.assertEqual(config['SERVER_EMAIL'], 'OnWebApp <notifications@onwebapp.com>')
        self.assertEqual(config['ADMIN_EMAIL'], '')
        self.assertEqual(config['EMAIL_PORT'], 587)
        self.assertEqual(config['EMAIL_TIMEOUT'], 15)
        self.assertTrue(config['EMAIL_USE_TLS'])
        self.assertFalse(config['EMAIL_USE_SSL'])

    def test_server_email_and_admin_email_from_env(self):
        config = resolve_email_config({
            'SERVER_EMAIL': 'server@onwebapp.com',
            'ADMIN_EMAIL': 'ops@onwebapp.com',
        })
        self.assertEqual(config['SERVER_EMAIL'], 'server@onwebapp.com')
        self.assertEqual(config['ADMIN_EMAIL'], 'ops@onwebapp.com')


class ValidRecipientsTests(SimpleTestCase):
    def test_filters_invalid_and_deduplicates(self):
        result = valid_recipients([
            'ada@example.com',
            ' ADA@example.com ',
            '',
            'not-an-email',
            None,
            'bob@example.com',
        ])
        self.assertEqual(result, ['ada@example.com', 'bob@example.com'])

    def test_strips_display_name_format(self):
        result = valid_recipients(['OnWebApp <notifications@onwebapp.com>'])
        self.assertEqual(result, ['notifications@onwebapp.com'])


class SendNotificationEmailTests(TestCase):
    def test_sends_multipart_with_default_from(self):
        sent = send_notification_email(
            subject='Hello',
            recipients=['ada@example.com'],
            template_name='emails/base_email.html',
            context={},
            text_body='Hello in text',
            label='test',
        )
        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['ada@example.com'])
        self.assertEqual(message.from_email, 'OnWebApp <notifications@onwebapp.com>')
        self.assertEqual(message.body, 'Hello in text')
        self.assertEqual(message.alternatives[0][1], 'text/html')

    def test_html_only_message_gets_text_fallback(self):
        with mock.patch('home.emails.render_to_string', return_value='<p>Hi <b>Ada</b></p>'):
            sent = send_notification_email(
                subject='Hello',
                recipients=['ada@example.com'],
                template_name='emails/dummy.html',
                label='test',
            )
        self.assertTrue(sent)
        self.assertEqual(mail.outbox[0].body, 'Hi Ada')

    def test_returns_false_and_logs_on_smtp_failure(self):
        with mock.patch(
            'home.emails.EmailMultiAlternatives.send',
            side_effect=OSError('connection refused'),
        ):
            with self.assertLogs('home.emails', level='ERROR'):
                sent = send_notification_email(
                    subject='Hello',
                    recipients=['ada@example.com'],
                    text_body='Hi',
                    label='test',
                )
        self.assertFalse(sent)
        self.assertEqual(len(mail.outbox), 0)

    def test_no_valid_recipients_returns_false(self):
        sent = send_notification_email(
            subject='Hello',
            recipients=['not-an-email', ''],
            text_body='Hi',
            label='test',
        )
        self.assertFalse(sent)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(ADMIN_EMAIL='boss@onwebapp.com')
class ApiRequestEmailTests(TestCase):
    def test_admin_notification_links_to_admin_page_and_uses_admin_email(self):
        response = self.client.post(reverse('home:request_api'), _payload())
        self.assertEqual(response.status_code, 302)

        admin_mails = [m for m in mail.outbox if m.subject.startswith('[API Request]')]
        self.assertEqual(len(admin_mails), 1)
        self.assertIn('boss@onwebapp.com', admin_mails[0].to)

        api_request = APIRequest.objects.get()
        admin_url = f'{settings.SITE_URL.rstrip("/")}/software/api-requests/manage/{api_request.pk}/'
        self.assertIn(admin_url, admin_mails[0].body)

    def test_client_ack_is_multipart_with_reference(self):
        self.client.post(reverse('home:request_api'), _payload())
        acks = [m for m in mail.outbox if 'We received your API request' in m.subject]
        self.assertEqual(len(acks), 1)
        self.assertIn('ada@example.com', acks[0].to)
        body = acks[0].body
        api_request = APIRequest.objects.get()
        self.assertIn(api_request.reference, body)
        self.assertEqual(acks[0].alternatives[0][1], 'text/html')
        self.assertIn(api_request.reference, acks[0].alternatives[0][0])

    def test_request_is_persisted_when_email_delivery_fails(self):
        with mock.patch(
            'home.emails.EmailMultiAlternatives.send',
            side_effect=OSError('smtp down'),
        ):
            with self.assertLogs('home.emails', level='ERROR'):
                response = self.client.post(reverse('home:request_api'), _payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(APIRequest.objects.count(), 1)

    def test_notifications_are_idempotent_for_retry(self):
        api_request = APIRequest.objects.create(
            full_name='Ada Lovelace',
            business_email='ada@example.com',
            request_type='custom',
            api_name_or_category='Invoicing API',
            use_case='Generate invoices.',
            required_features='Create invoice.',
        )
        from .notifications import notify_admins

        mail.outbox.clear()
        notify_admins(api_request)
        notify_admins(api_request)
        self.assertEqual(len(mail.outbox), 2)


class EmailSystemCheckTests(SimpleTestCase):
    def test_warning_when_production_unconfigured(self):
        from .checks import email_configuration_check

        with override_settings(DEBUG=False, EMAIL_BACKEND=CONSOLE_BACKEND):
            problems = email_configuration_check(None)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0].id, 'onwebapp.W001')

    def test_no_warning_with_smtp_backend(self):
        from .checks import email_configuration_check

        with override_settings(DEBUG=False, EMAIL_BACKEND=SMTP_BACKEND):
            self.assertEqual(email_configuration_check(None), [])

    def test_silent_in_debug_mode(self):
        from .checks import email_configuration_check

        with override_settings(DEBUG=True, EMAIL_BACKEND=CONSOLE_BACKEND):
            self.assertEqual(email_configuration_check(None), [])
