from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from payments.models import PaymentPlan
from unittest.mock import patch, MagicMock

User = get_user_model()


class CheckoutEndpointTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='payer', email='p@p.com', password='pw')
        self.plan = PaymentPlan.objects.create(name='Pro', price=9.99, interval='month', is_active=True)

    def test_checkout_fallback_when_no_stripe_key(self):
        self.client.login(username='payer', password='pw')
        with override_settings(STRIPE_SECRET_KEY=''):
            resp = self.client.post(reverse('payments:create_checkout', args=[self.plan.id]))
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            # When no Stripe key, view returns redirect to plans page as checkout_url
            self.assertIn('checkout_url', data)

    @patch('payments.views.stripe.checkout.Session.create')
    def test_checkout_creates_session_and_returns_url(self, mock_create):
        mock_session = MagicMock()
        mock_session.url = 'https://checkout.test/session/123'
        mock_create.return_value = mock_session

        self.client.login(username='payer', password='pw')
        resp = self.client.post(reverse('payments:create_checkout', args=[self.plan.id]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get('checkout_url'), mock_session.url)
