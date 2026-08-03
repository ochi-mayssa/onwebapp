from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from users.models import ActivityLog, UserSubscription
from services.decorators import require_subscription_with_limit, get_free_tier_usage

User = get_user_model()


class DecoratorQuotaTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username='tester', email='t@test.com', password='pass')

    def _simple_view(self, request):
        resp = HttpResponse('ok')
        resp.context_data = {}
        return resp

    def test_free_user_single_use_then_blocked(self):
        view = require_subscription_with_limit('predictive_maintenance')(self._simple_view)

        req = self.factory.get('/predict')
        req.user = self.user

        # First call should record usage
        resp1 = view(req)
        self.assertEqual(ActivityLog.objects.filter(user=self.user, action='feature_used_predictive_maintenance').count(), 1)
        self.assertFalse(resp1.context_data.get('has_subscription', False))
        self.assertFalse(resp1.context_data.get('reached_limit', False))  # reached_limit shows after recompute; first usage may still be under

        # Second call should not create another ActivityLog and should report reached_limit
        resp2 = view(req)
        self.assertEqual(ActivityLog.objects.filter(user=self.user, action='feature_used_predictive_maintenance').count(), 1)
        self.assertTrue(resp2.context_data.get('reached_limit', False))

    def test_subscribed_user_unlimited(self):
        # Give user an active subscription
        UserSubscription.objects.create(user=self.user, is_active=True)

        view = require_subscription_with_limit('predictive_maintenance')(self._simple_view)

        req = self.factory.get('/predict')
        req.user = self.user

        resp = view(req)
        # Should not create activity logs for subscriptions (decorator bypasses recording)
        self.assertEqual(ActivityLog.objects.filter(user=self.user, action='feature_used_predictive_maintenance').count(), 0)
        self.assertTrue(resp.context_data.get('has_subscription', False))

    def test_post_dedupe_prevents_double_count(self):
        view = require_subscription_with_limit('predictive_maintenance')(self._simple_view)

        body = b'{"input":"value"}'
        req1 = self.factory.post('/predict', data=body, content_type='application/json')
        req1.user = self.user
        req1.body = body

        req2 = self.factory.post('/predict', data=body, content_type='application/json')
        req2.user = self.user
        req2.body = body

        _ = view(req1)
        _ = view(req2)

        # Only one recorded due to dedupe
        self.assertEqual(ActivityLog.objects.filter(user=self.user, action='feature_used_predictive_maintenance').count(), 1)
