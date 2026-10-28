"""Small factories shared by the automation test modules (not a test module)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone

from crm.models import Customer

from .models import AutomationWorkflow, Plan, Subscription

User = get_user_model()


def make_user(username='owner', email=None, password='secret123'):
    return User.objects.create_user(
        username=username,
        email=email or f'{username}@example.test',
        password=password,
    )


def make_customer(user, name='Acme Corp', email=None):
    return Customer.objects.create(
        user=user,
        name=name,
        email=email or f'{user.username}.customer@example.test',
    )


def make_plan(slug='essential', *, limit=10, price='29.00'):
    return Plan.objects.create(
        name=slug.title(),
        slug=slug,
        price=price,
        currency='USD',
        max_active_workflows=3,
        monthly_execution_limit=limit,
        is_active=True,
    )


def make_subscription(customer, plan, *, status='active', is_active=True, period_end=None):
    return Subscription.objects.create(
        customer=customer,
        plan=plan,
        status=status,
        provider='manual',
        is_active=is_active,
        payment_status='paid' if is_active else 'pending',
        billing_period_end=period_end,
    )


def make_workflow(customer, *, status='active', config=None, trigger='manual', user=None):
    return AutomationWorkflow.objects.create(
        customer=customer,
        title='Test workflow',
        description='Test workflow',
        status=status,
        trigger=trigger,
        config=config or {
            'steps': [{
                'type': 'email',
                'config': {
                    'to': 'recipient@example.test',
                    'subject': 'Test',
                    'body': 'Hello from OnWebApp',
                },
            }],
        },
        created_by=user,
    )


def utc_now():
    return timezone.now()
