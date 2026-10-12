from django.test import TestCase
from django.urls import reverse

from .models import DashboardInquiry


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
