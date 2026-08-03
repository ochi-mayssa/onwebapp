from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import ServiceType, OnboardingSession, OnboardingAddon
from .services import calculate, get_package_comparison, EstimationResult
from users.models import UserProfile

User = get_user_model()


class EstimationEngineTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='est_user', password='testpass123')
        self.svc1 = ServiceType.objects.create(
            name='Website Development', slug='website-dev', category='web',
            description='Test', base_price=999, complexity_weight=5, order=1,
        )
        self.svc2 = ServiceType.objects.create(
            name='SEO', slug='seo', category='marketing',
            description='Test', base_price=599, complexity_weight=3, order=2,
        )

    def _make_session(self, **overrides):
        return OnboardingSession.objects.create(
            user=self.user, current_step=1, status='draft', **overrides,
        )

    def test_empty_session_returns_defaults(self):
        s = self._make_session()
        result = calculate(s)
        self.assertIsInstance(result, EstimationResult)
        self.assertGreaterEqual(result.budget_min, Decimal('0'))
        self.assertGreaterEqual(result.timeline_weeks, 2)

    def test_services_affect_estimation(self):
        s = self._make_session()
        s.selected_services.add(self.svc1, self.svc2)
        result = calculate(s)
        self.assertGreater(result.budget_min, Decimal('499'))

    def test_features_increase_complexity(self):
        s = self._make_session()
        s.selected_services.add(self.svc1)
        s.selected_features = ['ecommerce', 'blog', 'analytics', 'booking', 'membership']
        result = calculate(s)
        self.assertIn(result.complexity, ['Simple', 'Standard', 'Complex', 'Enterprise'])

    def test_design_style_multiplier(self):
        s1 = self._make_session(design_style='modern')
        s1.selected_services.add(self.svc1)
        r1 = calculate(s1)

        s2 = self._make_session(design_style='creative')
        s2.selected_services.add(self.svc1)
        r2 = calculate(s2)

        self.assertGreater(r2.budget_max, r1.budget_max)

    def test_to_dict(self):
        s = self._make_session()
        result = calculate(s)
        d = result.to_dict()
        self.assertIn('timeline_weeks', d)
        self.assertIn('budget_min', d)
        self.assertIn('budget_max', d)
        self.assertIn('complexity', d)
        self.assertIn('breakdown', d)
        self.assertIsInstance(d['breakdown'], list)

    def test_total_cost_and_days(self):
        s = self._make_session()
        s.selected_services.add(self.svc1)
        result = calculate(s)
        self.assertIsInstance(result.total_cost, str)
        self.assertIsInstance(result.total_days, int)
        self.assertGreater(result.total_days, 0)

    def test_package_comparison(self):
        s = self._make_session()
        s.selected_services.add(self.svc1)
        comparison = get_package_comparison(s)
        self.assertIn('recommended', comparison)
        self.assertIn('basic', comparison)
        self.assertIn('standard', comparison)
        self.assertIn('advanced', comparison)
        self.assertIn('enterprise', comparison)


class ServiceTypeModelTest(TestCase):
    def test_create(self):
        s = ServiceType.objects.create(
            name='Test Service', slug='test-svc', category='web',
            description='A test service', base_price=100, order=1,
        )
        self.assertEqual(str(s), 'Test Service')
        self.assertTrue(s.is_active)


class OnboardingAddonModelTest(TestCase):
    def test_create(self):
        a = OnboardingAddon.objects.create(
            name='Test Addon', slug='test-addon', price=50, order=1,
        )
        self.assertEqual(str(a), 'Test Addon ($50)')


class OnboardingSessionModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.session = OnboardingSession.objects.create(
            user=self.user, current_step=1, status='draft',
        )

    def test_str(self):
        s = str(self.session)
        self.assertIn('testuser', s)
        self.assertIn('Step 1', s)

    def test_mark_step_complete(self):
        self.session.mark_step_complete(2)
        self.assertIn(2, self.session.completed_steps)
        self.session.mark_step_complete(2)
        self.assertEqual(self.session.completed_steps.count(2), 1)

    def test_get_progress_pct(self):
        self.session.completed_steps = [1, 2, 3]
        pct = self.session.get_progress_pct()
        self.assertEqual(pct, round((3 / 13) * 100))

    def test_get_step_name(self):
        self.session.current_step = 2
        self.assertEqual(self.session.get_step_name(), 'Choose Service')

    def test_get_estimated_time_left(self):
        self.session.completed_steps = [1, 2, 3, 4, 5]
        time_left = self.session.get_estimated_time_left()
        self.assertIn('min', time_left)

    def test_complete(self):
        self.session.complete()
        self.assertEqual(self.session.status, 'completed')
        self.assertIsNotNone(self.session.completed_at)

    def test_helper_methods_string_addons(self):
        self.session.selected_features = ['ecommerce', 'blog']
        self.session.selected_addons = ['hosting', 'domain']
        self.session.selected_package = 'standard_pkg'
        self.session.design_style = 'modern'
        self.session.typography_style = 'sans-serif'
        self.session.budget_range = '5k_10k'
        self.session.save()

        self.assertEqual(self.session.get_features_list(), ['Ecommerce', 'Blog'])
        self.assertEqual(self.session.get_addons_list(), ['Hosting', 'Domain'])
        self.assertEqual(self.session.get_package_display(), 'Standard Pkg')
        self.assertEqual(self.session.get_design_style_display(), 'Modern')
        self.assertEqual(self.session.get_typography_style_display(), 'Sans Serif')
        self.assertEqual(self.session.get_budget_range_display(), '5K 10K')

    def test_helper_methods_dict_addons(self):
        self.session.selected_addons = [{'slug': 'hosting', 'name': 'Hosting Setup', 'price': 149}]
        result = self.session.get_addons_list()
        self.assertEqual(result, ['Hosting Setup'])


class WizardViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='wizarduser', password='testpass123',
            email='wizard@test.com',
        )
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.service_type = 'community'
        profile.save()
        self.client.login(username='wizarduser', password='testpass123')
        self._ensure_data()

    def _ensure_data(self):
        from .views import _ensure_services_exist, _ensure_addons_exist, _ensure_plans_exist
        _ensure_services_exist()
        _ensure_addons_exist()
        _ensure_plans_exist()

    def _start_wizard(self):
        self.client.post(reverse('community:wizard_start'))

    def _advance_to_step(self, target):
        """Walk through all steps up to target, posting minimal valid data."""
        self._start_wizard()
        steps_posted = {2}
        step_data = {
            2: {'services': ['website-dev']},
            3: {'business_name': 'Test', 'industry': 'Tech', 'business_description': 'Desc', 'target_audience': 'All'},
            4: {'project_name': 'Proj', 'project_goals': 'Goals', 'budget_range': '5k_10k'},
            5: {'design_style': 'modern', 'primary_color': '#000', 'accent_color': '#111', 'typography_style': 'sans-serif'},
            6: {'features': ['blog']},
            7: {},
            8: {'package': 'standard_pkg'},
            9: {'addons': []},
            10: {},
            11: {},
            12: {},
        }
        for step in range(2, target + 1):
            self.client.post(
                reverse('community:wizard_step', args=[step]),
                data=step_data.get(step, {}),
            )
            steps_posted.add(step)

    def test_wizard_start_creates_session(self):
        resp = self.client.post(reverse('community:wizard_start'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('step/2', resp.url)
        self.assertEqual(OnboardingSession.objects.count(), 1)

    def test_wizard_start_redirects_to_existing(self):
        session = OnboardingSession.objects.create(
            user=self.user, current_step=4, status='in_progress',
        )
        resp = self.client.get(reverse('community:wizard_start'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('step/4', resp.url)

    def test_step2_services(self):
        self._start_wizard()
        resp = self.client.post(
            reverse('community:wizard_step', args=[2]),
            data={'services': ['website-dev', 'seo']},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn('step/3', resp.url)
        session = OnboardingSession.objects.first()
        self.assertEqual(session.selected_services.count(), 2)

    def test_step3_business(self):
        self._advance_to_step(2)
        resp = self.client.post(
            reverse('community:wizard_step', args=[3]),
            data={
                'business_name': 'Acme Corp',
                'industry': 'SaaS',
                'business_description': 'We make widgets',
                'target_audience': 'Developers',
            },
        )
        self.assertEqual(resp.status_code, 302)
        session = OnboardingSession.objects.first()
        self.assertEqual(session.business_name, 'Acme Corp')

    def test_step4_project(self):
        self._advance_to_step(3)
        resp = self.client.post(
            reverse('community:wizard_step', args=[4]),
            data={
                'project_name': 'New Website',
                'project_goals': 'Grow leads',
                'budget_range': '10k_25k',
            },
        )
        self.assertEqual(resp.status_code, 302)
        session = OnboardingSession.objects.first()
        self.assertEqual(session.project_name, 'New Website')
        self.assertEqual(session.budget_range, '10k_25k')

    def test_step5_design(self):
        self._advance_to_step(4)
        resp = self.client.post(
            reverse('community:wizard_step', args=[5]),
            data={
                'design_style': 'modern',
                'primary_color': '#6366f1',
                'accent_color': '#8b5cf6',
                'typography_style': 'sans-serif',
            },
        )
        self.assertEqual(resp.status_code, 302)
        session = OnboardingSession.objects.first()
        self.assertEqual(session.design_style, 'modern')

    def test_step6_features(self):
        self._advance_to_step(5)
        resp = self.client.post(
            reverse('community:wizard_step', args=[6]),
            data={'features': ['ecommerce', 'blog'], 'integrations': 'Stripe'},
        )
        self.assertEqual(resp.status_code, 302)
        session = OnboardingSession.objects.first()
        self.assertIn('ecommerce', session.selected_features)

    def test_step7_estimation_renders(self):
        self._advance_to_step(6)
        resp = self.client.get(reverse('community:wizard_step', args=[7]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'AI Cost Estimation')

    def test_step8_package(self):
        self._advance_to_step(7)
        resp = self.client.post(
            reverse('community:wizard_step', args=[8]),
            data={'package': 'standard_pkg'},
        )
        self.assertEqual(resp.status_code, 302)
        session = OnboardingSession.objects.first()
        self.assertEqual(session.selected_package, 'standard_pkg')

    def test_step9_addons(self):
        self._advance_to_step(8)
        resp = self.client.post(
            reverse('community:wizard_step', args=[9]),
            data={'addons': ['hosting', 'domain']},
        )
        self.assertEqual(resp.status_code, 302)
        session = OnboardingSession.objects.first()
        self.assertEqual(len(session.selected_addons), 2)

    def test_step10_summary_renders(self):
        self._advance_to_step(9)
        resp = self.client.get(reverse('community:wizard_step', args=[10]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Project Summary')

    def test_step11_proposal_renders(self):
        self._advance_to_step(10)
        resp = self.client.get(reverse('community:wizard_step', args=[11]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Your Proposal')

    def test_step12_payment_renders(self):
        self._advance_to_step(11)
        resp = self.client.get(reverse('community:wizard_step', args=[12]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Secure Payment')

    def test_autosave_endpoint(self):
        import json
        self._advance_to_step(3)
        resp = self.client.post(
            reverse('community:wizard_autosave'),
            data=json.dumps({'step': 3, 'data': {'business_name': 'Saved Corp'}}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        session = OnboardingSession.objects.first()
        session.refresh_from_db()
        self.assertEqual(session.business_name, 'Saved Corp')

    def test_step_redirect_if_no_session(self):
        resp = self.client.get(reverse('community:wizard_step', args=[5]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('onboarding', resp.url)

    def test_cannot_skip_steps(self):
        self._start_wizard()
        resp = self.client.get(reverse('community:wizard_step', args=[10]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('step/2', resp.url)

    def test_workspace_generation_on_payment(self):
        from projects.models import Project, ProjectPhase, PhaseTask
        self._advance_to_step(11)
        session = OnboardingSession.objects.first()
        self.assertIsNotNone(session.estimation_data)

        resp = self.client.post(reverse('community:wizard_step', args=[12]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('step/13', resp.url)

        session.refresh_from_db()
        self.assertTrue(session.payment_completed)
        self.assertIsNotNone(session.linked_project)
        self.assertIsInstance(session.linked_project, Project)

        project = session.linked_project
        self.assertEqual(project.client, self.user)
        self.assertIn('Test', project.title)
        self.assertEqual(project.current_status, 'PLANNING')

        phases = ProjectPhase.objects.filter(project=project)
        self.assertEqual(phases.count(), 5)

        planning = phases.filter(phase_type='PLANNING').first()
        self.assertIsNotNone(planning)
        tasks = PhaseTask.objects.filter(phase=planning)
        self.assertGreaterEqual(tasks.count(), 4)

    def test_step13_renders_with_project(self):
        self._advance_to_step(12)
        resp = self.client.post(reverse('community:wizard_step', args=[12]))
        self.assertEqual(resp.status_code, 302)

        resp = self.client.get(reverse('community:wizard_step', args=[13]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Workspace is Ready')
        self.assertContains(resp, 'Open Project Board')

    def test_full_walkthrough_end_to_end(self):
        from projects.models import Project
        self._start_wizard()
        steps = [
            (2, {'services': ['website-dev']}),
            (3, {'business_name': 'E2E Corp', 'industry': 'Tech', 'business_description': 'E2E', 'target_audience': 'All'}),
            (4, {'project_name': 'E2E Site', 'project_goals': 'Revenue', 'budget_range': '5k_10k'}),
            (5, {'design_style': 'minimal', 'primary_color': '#000', 'accent_color': '#fff', 'typography_style': 'sans-serif'}),
            (6, {'selected_features': ['blog', 'contact-form']}),
            (7, {}),
            (8, {'package': 'standard_pkg'}),
            (9, {}),
            (10, {}),
            (11, {}),
            (12, {}),
        ]
        for step_num, data in steps:
            resp = self.client.post(reverse('community:wizard_step', args=[step_num]), data=data)
            self.assertEqual(resp.status_code, 302, f"Step {step_num} failed with {resp.status_code}")

        resp = self.client.get(reverse('community:wizard_step', args=[13]))
        self.assertEqual(resp.status_code, 200)

        session = OnboardingSession.objects.first()
        self.assertTrue(session.payment_completed)
        self.assertIsNotNone(session.linked_project)
        self.assertEqual(session.linked_project.title, 'E2E Corp - Website Development')

        session.complete()
        self.assertEqual(session.status, 'completed')
        self.assertIsNotNone(session.completed_at)
