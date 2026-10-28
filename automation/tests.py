from django.contrib.auth import get_user_model
from django.test import TestCase
from crm.models import Customer
from .models import AutomationRequest, Plan, Subscription, AutomationWorkflow, AutomationExecution

User = get_user_model()


class AutomationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='customer', email='customer@example.com', password='secret123')
        self.customer = Customer.objects.create(user=self.user, name='Acme Corp', email='sales@acme.test')
        self.plan = Plan.objects.create(
            name='Essential',
            slug='essential',
            price='29.00',
            currency='USD',
            max_active_workflows=3,
            monthly_execution_limit=1000,
            is_active=True,
        )

    def test_request_status_and_plan_defaults(self):
        request = AutomationRequest.objects.create(
            customer=self.customer,
            title='Lead routing workflow',
            description='Route leads between HubSpot and CRM.',
            requested_by=self.user,
        )
        self.assertEqual(request.status, 'draft')
        self.assertFalse(request.is_approved)

    def test_subscription_and_execution_tracking(self):
        subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status='active',
            provider='manual',
        )
        workflow = AutomationWorkflow.objects.create(
            customer=self.customer,
            title='Sync leads',
            request=None,
            status='approved',
            config={'schedule': 'daily'}
        )
        execution = AutomationExecution.objects.create(
            workflow=workflow,
            subscription=subscription,
            status='queued',
            trigger='manual',
            execution_key='exec-1',
        )
        self.assertEqual(subscription.customer, self.customer)
        self.assertEqual(execution.workflow.title, 'Sync leads')

    def test_customer_membership_is_scoped_to_customer_user(self):
        other_user = User.objects.create_user(username='other', email='other@example.com', password='secret123')
        other_customer = Customer.objects.create(user=other_user, name='Other Co', email='hello@other.test')

        request = AutomationRequest.objects.create(
            customer=self.customer,
            title='Quarterly reporting',
            description='Gather dashboard metrics',
            requested_by=self.user,
        )
        self.assertEqual(request.customer.user, self.user)
        self.assertNotEqual(request.customer, other_customer)
