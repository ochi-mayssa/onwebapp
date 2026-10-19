from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import DashboardInquiry


def _quote_payload(**overrides):
    data = {
        'name': 'Ada Lovelace',
        'email': 'ada@example.com',
        'company': 'Analytical Engines',
        'phone': '+1 555 0100',
        'package': 'business',
        'data_sources': 'SQL, ERP',
        'budget': '5-15',
        'timeline': '1-2m',
        'message': 'We need a multi-source operations dashboard.',
    }
    data.update(overrides)
    return data


class DashboardInquiryTests(TestCase):
    def test_quote_get_renders(self):
        response = self.client.get(reverse('dashboard_inquiry:quote') + '?package=starter')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dashboard')

    def test_package_preselected(self):
        response = self.client.get(reverse('dashboard_inquiry:quote') + '?package=enterprise')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['package'], 'enterprise')
        self.assertEqual(response.context['package_label'], 'Enterprise')

    def test_invalid_package_falls_back_to_business(self):
        response = self.client.get(reverse('dashboard_inquiry:quote') + '?package=nope')
        self.assertEqual(response.context['package'], 'business')

    def test_post_creates_inquiry_and_redirects(self):
        response = self.client.post(
            reverse('dashboard_inquiry:quote') + '?package=business',
            {
                'name': 'Ada Lovelace',
                'email': 'ada@example.com',
                'company': 'Analytical Engines',
                'phone': '+1 555 0100',
                'package': 'business',
                'data_sources': 'SQL, ERP',
                'budget': '5-15',
                'timeline': '1-2m',
                'message': 'We need a multi-source operations dashboard.',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard_inquiry:success'))
        inquiry = DashboardInquiry.objects.get()
        self.assertTrue(inquiry.reference.startswith('DD-'))
        self.assertEqual(inquiry.package, 'business')
        self.assertEqual(inquiry.budget, '5-15')
        self.assertEqual(inquiry.status, 'pending')

    def test_honeypot_silently_drops_bots(self):
        response = self.client.post(
            reverse('dashboard_inquiry:quote'),
            {
                'name': 'Bot', 'email': 'bot@example.com', 'package': 'starter',
                'website': 'http://spam.example.com',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(DashboardInquiry.objects.count(), 0)

    def test_budget_and_timeline_render_choices(self):
        response = self.client.get(reverse('dashboard_inquiry:quote'))
        self.assertContains(response, 'Under $5k')
        self.assertContains(response, 'As soon as possible')

    def test_package_price_rendered(self):
        response = self.client.get(reverse('dashboard_inquiry:quote') + '?package=starter')
        self.assertEqual(response.context['package_price'], 2500)
        self.assertContains(response, '$2,500')

        response = self.client.get(reverse('dashboard_inquiry:quote') + '?package=enterprise')
        self.assertEqual(response.context['package_price'], 15000)
        self.assertContains(response, '$15,000')

    def test_invalid_post_redisplays_form(self):
        response = self.client.post(
            reverse('dashboard_inquiry:quote'),
            {'name': '', 'email': 'not-an-email', 'package': 'starter'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'email', 'Enter a valid email address.')
        self.assertEqual(DashboardInquiry.objects.count(), 0)

    def test_success_page_renders(self):
        response = self.client.get(reverse('dashboard_inquiry:success'))
        self.assertEqual(response.status_code, 200)


class QuoteEmailTests(TestCase):
    """Quote submissions send a team notification + customer confirmation."""

    def test_post_sends_team_and_customer_emails(self):
        mail.outbox.clear()
        response = self.client.post(
            reverse('dashboard_inquiry:quote'),
            _quote_payload(),
        )
        self.assertEqual(response.status_code, 302)

        team = [m for m in mail.outbox if 'Dashboard Inquiry' in m.subject]
        customer = [m for m in mail.outbox if 'quote request' in m.subject]
        self.assertEqual(len(team), 1)
        self.assertEqual(len(customer), 1)
        self.assertIn('ada@example.com', customer[0].to)
        self.assertIn('DD-', customer[0].body)
        self.assertTrue(customer[0].alternatives)
        self.assertEqual(customer[0].alternatives[0][1], 'text/html')

    @override_settings(ADMIN_EMAIL='boss@onwebapp.com', DASHBOARD_INQUIRY_EMAIL='team@onwebapp.com')
    def test_team_notification_includes_admin_email(self):
        mail.outbox.clear()
        self.client.post(reverse('dashboard_inquiry:quote'), _quote_payload())
        team = [m for m in mail.outbox if 'Dashboard Inquiry' in m.subject]
        self.assertEqual(len(team), 1)
        self.assertIn('boss@onwebapp.com', team[0].to)
        self.assertIn('team@onwebapp.com', team[0].to)

    def test_inquiry_is_persisted_when_email_delivery_fails(self):
        mail.outbox.clear()
        with mock.patch(
            'home.emails.EmailMultiAlternatives.send',
            side_effect=OSError('smtp down'),
        ):
            with self.assertLogs('home.emails', level='ERROR'):
                response = self.client.post(
                    reverse('dashboard_inquiry:quote'),
                    _quote_payload(),
                )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(DashboardInquiry.objects.count(), 1)
