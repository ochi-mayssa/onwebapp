"""Capacity, utilisation and assignment behaviour."""
from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError

from workload.models import (
    ResourceCapacity,
    WorkAssignment,
    WorkItem,
    WorkloadHistory,
    WorkloadPolicy,
    WorkloadResource,
)
from workload.services import (
    approve_recommendation,
    assign_work,
    assigned_hours_map,
    calculate_utilization,
    cancel_assignment,
    classify_utilization,
    get_effective_capacity,
    recommend_assignees,
    reject_recommendation,
    store_recommendations,
    team_capacity,
)
from workload.tests.base import WorkloadTestBase


class CapacityTests(WorkloadTestBase):
    def test_available_hours_scales_weekly_hours_and_removes_time_off(self):
        resource = self.make_resource(
            self.employee, weekly=40, availability=50, time_off=4,
        )
        self.assertEqual(resource.capacity.available_hours, Decimal('16'))

    def test_missing_capacity_falls_back_to_policy_default(self):
        resource = WorkloadResource.objects.create(
            user=self.employee,
            kind=WorkloadResource.KIND_PERSON,
            name='No capacity record',
        )
        available, source, is_assumed = get_effective_capacity(resource, self.policy)
        self.assertEqual(available, self.policy.default_weekly_hours)
        self.assertEqual(source, 'policy_default')
        self.assertTrue(is_assumed)

    def test_unavailable_resource_has_zero_capacity(self):
        resource = self.make_resource(self.employee)
        resource.availability_status = WorkloadResource.AVAILABILITY_ON_LEAVE
        resource.save(update_fields=['availability_status'])
        available, source, is_assumed = get_effective_capacity(resource, self.policy)
        self.assertEqual(available, Decimal('0'))
        self.assertEqual(source, 'availability_status')
        self.assertTrue(is_assumed)

    def test_utilization_formula_and_zero_division(self):
        resource = self.make_resource(self.employee, weekly=40)
        row = calculate_utilization(resource, self.policy, assigned_hours=Decimal('20'))
        self.assertEqual(row['assigned_hours'], 20.0)
        self.assertEqual(row['available_hours'], 40.0)
        self.assertEqual(row['utilization'], 50.0)
        self.assertEqual(row['level'], 'available')

        resource.capacity.weekly_hours = 0
        resource.capacity.save()
        empty = calculate_utilization(resource, self.policy, assigned_hours=Decimal('0'))
        self.assertIsNone(empty['utilization'])
        self.assertEqual(empty['level'], 'unavailable')
        busy = calculate_utilization(resource, self.policy, assigned_hours=Decimal('5'))
        self.assertIsNone(busy['utilization'])
        self.assertEqual(busy['level'], 'overloaded')

    def test_default_thresholds(self):
        self.assertEqual(float(self.policy.available_below), 60.0)
        self.assertEqual(float(self.policy.balanced_max), 85.0)
        self.assertEqual(float(self.policy.high_max), 100.0)

    def test_classification_boundaries(self):
        cases = [
            (59.9, 'available'),
            (60.0, 'balanced'),
            (85.0, 'balanced'),
            (85.1, 'high'),
            (100.0, 'high'),
            (100.1, 'overloaded'),
        ]
        for utilization, expected in cases:
            self.assertEqual(
                classify_utilization(utilization, 40, self.policy),
                expected,
                msg=f'{utilization}% should be {expected}',
            )

    def test_custom_policy_thresholds_are_used(self):
        policy = WorkloadPolicy.objects.create(
            name='Strict',
            available_below=Decimal('40'),
            balanced_max=Decimal('70'),
            high_max=Decimal('90'),
        )
        self.assertEqual(classify_utilization(50, 40, policy), 'balanced')
        self.assertEqual(classify_utilization(75, 40, policy), 'high')
        self.assertEqual(classify_utilization(95, 40, policy), 'overloaded')

    def test_assigned_hours_map_uses_allocation_then_estimate_and_direct_assignee(self):
        resource = self.make_resource(self.employee)
        allocated_explicit = self.make_item(
            title='Allocated', estimated_hours=10, assignee=self.employee,
        )
        WorkAssignment.objects.create(
            work_item=allocated_explicit,
            resource=resource,
            allocated_hours=3,
            status=WorkAssignment.STATUS_ACTIVE,
        )
        allocated_fallback = self.make_item(
            title='Fallback', estimated_hours=10, assignee=self.employee,
        )
        WorkAssignment.objects.create(
            work_item=allocated_fallback,
            resource=resource,
            allocated_hours=0,
            status=WorkAssignment.STATUS_ACTIVE,
        )
        self.make_item(title='Direct', estimated_hours=7, assignee=self.employee)
        # Closed work must not reserve capacity.
        closed = self.make_item(
            title='Closed', estimated_hours=100, status=WorkItem.STATUS_COMPLETED,
            assignee=self.employee,
        )
        self.assertEqual(closed.estimated_hours, Decimal('100'))

        hours = assigned_hours_map([resource.pk])
        self.assertEqual(hours[resource.pk], Decimal('20'))

    def test_team_capacity_aggregates_members(self):
        team = self.make_team(members=[self.employee, self.other], name='Platform')
        self.make_resource(self.employee, weekly=40)
        self.make_resource(self.other, weekly=20)
        summary = team_capacity(team, self.policy)
        self.assertEqual(summary['available_hours'], 60.0)
        self.assertEqual(summary['assigned_hours'], 0.0)
        self.assertEqual(summary['utilization'], 0.0)
        self.assertEqual(summary['member_count'], 2)
        self.assertEqual(summary['resource_count'], 2)


class AssignmentServiceTests(WorkloadTestBase):
    def test_assign_work_creates_active_assignment_and_history(self):
        item = self.make_item()
        assignment = assign_work(
            item, user=self.employee, actor=self.manager, allocated_hours=6,
        )
        self.assertEqual(assignment.status, WorkAssignment.STATUS_ACTIVE)
        self.assertEqual(assignment.allocated_hours, Decimal('6'))
        item.refresh_from_db()
        self.assertEqual(item.assignee, self.employee)
        self.assertEqual(item.status, WorkItem.STATUS_ASSIGNED)
        self.assertTrue(
            item.history.filter(action=WorkloadHistory.ACTION_ASSIGNED).exists(),
        )

    def test_non_manager_cannot_assign(self):
        item = self.make_item()
        with self.assertRaises(PermissionDenied):
            assign_work(item, user=self.other, actor=self.employee)

    def test_reassignment_cancels_previous_active_assignment(self):
        item = self.make_item()
        first = assign_work(item, user=self.employee, actor=self.manager)
        second = assign_work(item, user=self.other, actor=self.manager)
        first.refresh_from_db()
        self.assertEqual(first.status, WorkAssignment.STATUS_CANCELLED)
        self.assertEqual(second.status, WorkAssignment.STATUS_ACTIVE)
        item.refresh_from_db()
        self.assertEqual(item.assignee, self.other)

    def test_automatic_critical_reassignment_requires_policy_permission(self):
        item = self.make_item(priority=WorkItem.PRIORITY_CRITICAL)
        assign_work(item, user=self.employee, actor=self.manager)

        with self.assertRaises(PermissionDenied):
            assign_work(
                item, user=self.other, actor=self.manager, automatic=True,
            )

        self.policy.auto_reassign_critical = True
        self.policy.save(update_fields=['auto_reassign_critical', 'updated_at'])

        assignment = assign_work(
            item, user=self.other, actor=self.manager, automatic=True,
        )
        self.assertEqual(assignment.status, WorkAssignment.STATUS_ACTIVE)
        item.refresh_from_db()
        self.assertEqual(item.assignee, self.other)

    def test_cancel_assignment_releases_assignee(self):
        item = self.make_item()
        assignment = assign_work(item, user=self.employee, actor=self.manager)
        cancel_assignment(assignment, self.manager)
        assignment.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(assignment.status, WorkAssignment.STATUS_CANCELLED)
        self.assertIsNone(item.assignee)

    def test_only_managers_can_cancel_assignments(self):
        item = self.make_item()
        assignment = assign_work(item, user=self.employee, actor=self.manager)
        with self.assertRaises(PermissionDenied):
            cancel_assignment(assignment, self.employee)


class RecommendationTests(WorkloadTestBase):
    def test_recommendations_rank_skill_match_first(self):
        skill = self.make_skill('Django')
        item = self.make_item(title='Build API')
        item.required_skills.add(skill)
        skilled = self.make_resource(self.employee)
        skilled.skills.add(skill)
        self.make_resource(self.other)

        rows = recommend_assignees(item, policy=self.policy)
        self.assertEqual(rows[0]['resource'], skilled)
        self.assertEqual(rows[0]['skill_score'], 100.0)
        self.assertFalse(rows[0]['would_overload'])

    def test_unavailable_resources_are_excluded(self):
        item = self.make_item()
        resource = self.make_resource(self.employee)
        resource.availability_status = WorkloadResource.AVAILABILITY_ON_LEAVE
        resource.save(update_fields=['availability_status'])
        rows = recommend_assignees(item, policy=self.policy)
        self.assertEqual(rows, [])

    def test_store_approve_and_reject_recommendations(self):
        item = self.make_item(title='Needs owner', estimated_hours=6)
        self.make_resource(self.employee)
        self.make_resource(self.other)

        created = store_recommendations(item, self.manager, limit=3)
        self.assertEqual(len(created), 2)
        self.assertTrue(all(
            assignment.status == WorkAssignment.STATUS_RECOMMENDED
            for assignment, _row in created
        ))

        approved, _row = created[0]
        approve_recommendation(approved, self.manager)
        approved.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(approved.status, WorkAssignment.STATUS_ACTIVE)
        self.assertEqual(item.assignee, approved.resource.user)
        rejected = WorkAssignment.objects.get(
            work_item=item, status=WorkAssignment.STATUS_REJECTED,
        )
        self.assertNotEqual(rejected.pk, approved.pk)

    def test_reject_recommendation_records_status(self):
        item = self.make_item(title='Reject me')
        self.make_resource(self.employee)
        created = store_recommendations(item, self.manager, limit=1)
        assignment, _row = created[0]
        reject_recommendation(assignment, self.manager, note='Wrong skills')
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, WorkAssignment.STATUS_REJECTED)
        self.assertEqual(assignment.notes, 'Wrong skills')

    def test_recommendation_actions_require_manager(self):
        item = self.make_item()
        self.make_resource(self.employee)
        assignment = WorkAssignment.objects.create(
            work_item=item,
            resource=WorkloadResource.objects.get(user=self.employee),
            status=WorkAssignment.STATUS_RECOMMENDED,
        )
        with self.assertRaises(PermissionDenied):
            approve_recommendation(assignment, self.employee)
        with self.assertRaises(PermissionDenied):
            reject_recommendation(assignment, self.employee)
        with self.assertRaises(PermissionDenied):
            store_recommendations(item, self.employee)


class ValidationTests(WorkloadTestBase):
    def test_work_item_due_date_before_start_is_rejected(self):
        item = WorkItem(
            title='Bad dates',
            start_date=self.due(2),
            due_date=self.due(1),
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_resource_requires_matching_target(self):
        person = WorkloadResource(kind=WorkloadResource.KIND_PERSON)
        with self.assertRaises(ValidationError):
            person.full_clean()
        team = WorkloadResource(kind=WorkloadResource.KIND_TEAM)
        with self.assertRaises(ValidationError):
            team.full_clean()
        system = WorkloadResource(kind=WorkloadResource.KIND_SYSTEM)
        with self.assertRaises(ValidationError):
            system.full_clean()

    def test_capacity_availability_cannot_exceed_100(self):
        resource = WorkloadResource.objects.create(
            user=self.employee, kind=WorkloadResource.KIND_PERSON, name='Person',
        )
        capacity = ResourceCapacity(
            resource=resource, weekly_hours=40, availability_percent=120,
        )
        with self.assertRaises(ValidationError):
            capacity.full_clean()

    def test_policy_threshold_ordering_is_validated(self):
        policy = WorkloadPolicy(
            name='Invalid',
            available_below=Decimal('80'),
            balanced_max=Decimal('60'),
            high_max=Decimal('100'),
        )
        with self.assertRaises(ValidationError):
            policy.full_clean()

    def test_policy_weights_must_be_within_unit_interval(self):
        policy = WorkloadPolicy(
            name='Bad weights',
            available_below=Decimal('60'),
            balanced_max=Decimal('85'),
            high_max=Decimal('100'),
            weights={'skills': 2},
        )
        with self.assertRaises(ValidationError):
            policy.full_clean()
