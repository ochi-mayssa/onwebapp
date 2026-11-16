"""Shared fixtures and helpers for workload tests."""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone

from workload.models import (
    ResourceCapacity,
    WorkItem,
    WorkloadPolicy,
    WorkloadResource,
    WorkloadSkill,
    WorkloadTeam,
)
from workload.permissions import GROUP_EMPLOYEES

User = get_user_model()


class WorkloadTestBase(TestCase):
    """Creates the four platform roles and a default workload policy."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username='workload-admin',
            email='workload-admin@example.com',
            password='test-pass-123',
        )
        cls.manager = User.objects.create_user(
            username='workload-manager',
            email='workload-manager@example.com',
            password='test-pass-123',
            is_staff=True,
        )
        cls.employee_group, _ = Group.objects.get_or_create(name=GROUP_EMPLOYEES)
        cls.employee = User.objects.create_user(
            username='workload-employee',
            email='workload-employee@example.com',
            password='test-pass-123',
            first_name='Erin',
            last_name='Employee',
        )
        cls.employee.groups.add(cls.employee_group)
        cls.other = User.objects.create_user(
            username='workload-other',
            email='workload-other@example.com',
            password='test-pass-123',
            first_name='Omar',
            last_name='Other',
        )
        cls.other.groups.add(cls.employee_group)
        cls.client_user = User.objects.create_user(
            username='workload-client',
            email='workload-client@example.com',
            password='test-pass-123',
        )
        cls.policy = WorkloadPolicy.get_for()

    # ------------------------------------------------------------------ #
    # Fixture helpers
    # ------------------------------------------------------------------ #
    def make_resource(self, user, *, weekly=40, availability=100, time_off=0,
                      tenant=None, name=''):
        resource = WorkloadResource.objects.create(
            user=user,
            kind=WorkloadResource.KIND_PERSON,
            tenant=tenant,
            name=name,
        )
        ResourceCapacity.objects.create(
            resource=resource,
            weekly_hours=weekly,
            availability_percent=availability,
            time_off_hours=time_off,
        )
        return resource

    def make_team(self, *, members=None, name='Delivery', lead=None, tenant=None):
        team = WorkloadTeam.objects.create(name=name, lead=lead, tenant=tenant)
        if members:
            team.members.set(members)
        return team

    def make_item(self, **overrides):
        values = {
            'title': 'Test work item',
            'category': WorkItem.CATEGORY_HUMAN,
            'priority': WorkItem.PRIORITY_MEDIUM,
            'status': WorkItem.STATUS_NEW,
            'source_module': WorkItem.SOURCE_MANUAL,
            'estimated_hours': 8,
        }
        values.update(overrides)
        return WorkItem.objects.create(**values)

    def make_skill(self, name):
        return WorkloadSkill.objects.create(name=name)

    def due(self, days):
        return timezone.localdate() + timedelta(days=days)
