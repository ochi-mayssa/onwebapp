from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import BillingEvent, Subscription
from .testing import make_customer, make_plan, make_user

TEST_WEBHOOK_SECRET = 'whsec_automation_test'


@override_settings(
    STRIPE_SECRET_KEY='sk_test_automation',
    AUTOMATION_STRIPE_WEBHOOK_SECRET=TEST_WEBHOOK_SECRET,
    SITE_URL='https://app.example.test',
    AUTOMATION_EXECUTION_MODE='inline',
)
class BillingTestCase(TestCase):
    def setUp(self):
        self.user = make_user('billing-owner')
        self.customer = make_customer(self.user)
        self.plan = make_plan('billing-plan', limit=100, price='49.00')
        self.local_subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            provider='stripe',
            status='pending_payment',
            is_active=False,
            payment_status='pending',
        )
        self.client.force_login(self.user)

    def event(self, event_id, event_type, obj):
        return {
            'id': event_id,
            'type': event_type,
            'data': {'object': obj},
        }

    def post_event(self, event):
        return self.client.post(
            reverse('automation:stripe_webhook'),
            data=json.dumps(event),
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='test-signature',
        )

    def metadata(self):
        return {
            'local_subscription_id': str(self.local_subscription.pk),
            'customer_id': str(self.customer.pk),
            'plan_id': str(self.plan.pk),
        }


class StripeWebhookTests(BillingTestCase):
    @patch('automation.billing.stripe_adapter.stripe.Webhook.construct_event')
    def test_invalid_signature_is_rejected(self, construct_event):
        construct_event.side_effect = ValueError('bad signature')
        response = self.post_event(self.event('evt_bad', 'checkout.session.completed', {}))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BillingEvent.objects.filter(provider_event_id='evt_bad').exists())
        self.local_subscription.refresh_from_db()
        self.assertEqual(self.local_subscription.status, 'pending_payment')

    @patch('automation.billing.stripe_adapter.stripe.Webhook.construct_event')
    def test_checkout_completed_activates_only_from_provider_state(self, construct_event):
        period_end = timezone.now() + timedelta(days=30)
        construct_event.return_value = self.event('evt_checkout', 'checkout.session.completed', {
            'id': 'cs_test_1',
            'subscription': 'sub_test_1',
            'customer': 'cus_test_1',
            'metadata': self.metadata(),
        })
        with patch(
            'automation.billing.stripe_adapter.stripe.Subscription.retrieve',
            return_value={
                'id': 'sub_test_1',
                'customer': 'cus_test_1',
                'status': 'active',
                'current_period_start': int(timezone.now().timestamp()),
                'current_period_end': int(period_end.timestamp()),
                'cancel_at_period_end': False,
                'metadata': self.metadata(),
            },
        ) as retrieve:
            response = self.post_event(self.event('evt_checkout', 'checkout.session.completed', {}))
            self.assertEqual(response.status_code, 200)
            retrieve.assert_called_once_with('sub_test_1', api_key='sk_test_automation')

        self.local_subscription.refresh_from_db()
        self.assertEqual(self.local_subscription.status, 'active')
        self.assertTrue(self.local_subscription.is_active)
        self.assertEqual(self.local_subscription.provider_subscription_id, 'sub_test_1')
        event = BillingEvent.objects.get(provider_event_id='evt_checkout')
        self.assertTrue(event.processed)

    @patch('automation.billing.stripe_adapter.stripe.Webhook.construct_event')
    def test_duplicate_provider_event_is_deduplicated(self, construct_event):
        period_end = timezone.now() + timedelta(days=30)
        construct_event.return_value = self.event('evt_duplicate', 'checkout.session.completed', {
            'subscription': 'sub_duplicate',
            'customer': 'cus_duplicate',
            'metadata': self.metadata(),
        })
        with patch(
            'automation.billing.stripe_adapter.stripe.Subscription.retrieve',
            return_value={
                'id': 'sub_duplicate',
                'customer': 'cus_duplicate',
                'status': 'active',
                'current_period_end': int(period_end.timestamp()),
                'metadata': self.metadata(),
            },
        ) as retrieve:
            self.assertEqual(self.post_event(construct_event.return_value).status_code, 200)
            self.assertEqual(self.post_event(construct_event.return_value).status_code, 200)

        self.assertEqual(BillingEvent.objects.filter(provider_event_id='evt_duplicate').count(), 1)
        self.assertEqual(retrieve.call_count, 1)

    @patch('automation.billing.stripe_adapter.stripe.Webhook.construct_event')
    def test_invoice_payment_succeeded_handles_renewal(self, construct_event):
        self.local_subscription.provider_subscription_id = 'sub_renew'
        self.local_subscription.status = 'active'
        self.local_subscription.is_active = True
        self.local_subscription.payment_status = 'paid'
        self.local_subscription.save()
        period_end = timezone.now() + timedelta(days=60)

        construct_event.return_value = self.event('evt_renew', 'invoice.payment_succeeded', {
            'id': 'in_renew',
            'subscription': 'sub_renew',
            'customer': 'cus_renew',
            'period_start': int(timezone.now().timestamp()),
            'period_end': int(period_end.timestamp()),
            'metadata': {'customer_id': str(self.customer.pk)},
        })
        response = self.post_event(construct_event.return_value)
        self.assertEqual(response.status_code, 200)

        self.local_subscription.refresh_from_db()
        self.assertEqual(self.local_subscription.status, 'active')
        self.assertTrue(self.local_subscription.is_active)
        self.assertEqual(self.local_subscription.payment_status, 'paid')
        self.assertIsNotNone(self.local_subscription.billing_period_end)

    @patch('automation.billing.stripe_adapter.stripe.Webhook.construct_event')
    def test_invoice_payment_failed_moves_to_past_due(self, construct_event):
        self.local_subscription.provider_subscription_id = 'sub_failed'
        self.local_subscription.status = 'active'
        self.local_subscription.is_active = True
        self.local_subscription.save()
        construct_event.return_value = self.event('evt_failed', 'invoice.payment_failed', {
            'id': 'in_failed',
            'subscription': 'sub_failed',
            'customer': 'cus_failed',
            'metadata': {'customer_id': str(self.customer.pk)},
        })
        self.assertEqual(self.post_event(construct_event.return_value).status_code, 200)

        self.local_subscription.refresh_from_db()
        self.assertEqual(self.local_subscription.status, 'past_due')
        self.assertFalse(self.local_subscription.is_active)
        self.assertEqual(self.local_subscription.payment_status, 'failed')

    @patch('automation.billing.stripe_adapter.stripe.Webhook.construct_event')
    def test_subscription_cancellation_is_applied(self, construct_event):
        self.local_subscription.provider_subscription_id = 'sub_cancel'
        self.local_subscription.status = 'active'
        self.local_subscription.is_active = True
        self.local_subscription.save()
        construct_event.return_value = self.event('evt_cancel', 'customer.subscription.deleted', {
            'id': 'sub_cancel',
            'customer': 'cus_cancel',
            'status': 'canceled',
            'metadata': {'customer_id': str(self.customer.pk)},
            'cancel_at_period_end': False,
        })
        self.assertEqual(self.post_event(construct_event.return_value).status_code, 200)

        self.local_subscription.refresh_from_db()
        self.assertEqual(self.local_subscription.status, 'cancelled')
        self.assertFalse(self.local_subscription.is_active)
        self.assertIsNotNone(self.local_subscription.cancelled_at)

    @patch('automation.billing.stripe_adapter.stripe.Webhook.construct_event')
    def test_cross_tenant_webhook_cannot_modify_subscription(self, construct_event):
        other_user = make_user('billing-intruder')
        other_customer = make_customer(other_user, name='Other Billing')
        construct_event.return_value = self.event('evt_tenant', 'checkout.session.completed', {
            'subscription': 'sub_tenant',
            'customer': 'cus_tenant',
            'metadata': {
                'local_subscription_id': str(self.local_subscription.pk),
                'customer_id': str(other_customer.pk),
                'plan_id': str(self.plan.pk),
            },
        })
        response = self.post_event(construct_event.return_value)
        self.assertEqual(response.status_code, 500)
        self.local_subscription.refresh_from_db()
        self.assertEqual(self.local_subscription.status, 'pending_payment')
        self.assertFalse(self.local_subscription.is_active)


class CheckoutFlowTests(BillingTestCase):
    @patch('automation.billing.stripe_adapter.stripe.checkout.Session.create')
    def test_checkout_creates_pending_subscription_and_never_activates_on_redirect(self, create_session):
        create_session.return_value = MagicMock(id='cs_checkout', url='https://checkout.stripe.test/cs_checkout')
        response = self.client.post(
            reverse('automation:billing_checkout'),
            {'plan_id': self.plan.pk},
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['checkout_url'], 'https://checkout.stripe.test/cs_checkout')
        self.local_subscription.refresh_from_db()
        self.assertEqual(self.local_subscription.status, 'pending_payment')
        self.assertFalse(self.local_subscription.is_active)

        # The success landing page must not grant access.
        success = self.client.get(reverse('automation:billing_success'))
        self.assertEqual(success.status_code, 200)
        self.local_subscription.refresh_from_db()
        self.assertEqual(self.local_subscription.status, 'pending_payment')
        self.assertFalse(self.local_subscription.is_active)

    @patch('automation.billing.stripe_adapter.stripe.checkout.Session.create')
    def test_checkout_requires_authentication(self, create_session):
        self.client.logout()
        response = self.client.post(reverse('automation:billing_checkout'), {'plan_id': self.plan.pk})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response['Location'])


@override_settings(AUTOMATION_STRIPE_WEBHOOK_SECRET='')
class MissingWebhookSecretTests(BillingTestCase):
    def test_webhook_without_configured_secret_is_rejected(self):
        response = self.client.post(
            reverse('automation:stripe_webhook'),
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='anything',
        )
        self.assertEqual(response.status_code, 400)
