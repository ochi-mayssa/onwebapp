from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .models import APIRequest, APIRequestStatusLog

User = get_user_model()


def _payload(**overrides):
    data = {
        'full_name': 'Ada Lovelace',
        'business_email': 'ada@example.com',
        'company_name': 'Analytical Engines',
        'request_type': 'custom',
        'api_name_or_category': 'Invoicing API',
        'use_case': 'Generate invoices automatically from our CRM data.',
        'required_features': 'Create invoice, list invoices, export to PDF.',
        'expected_usage': '~5,000 requests/day',
        'budget_range': '5k-20k',
        'additional_requirements': '',
    }
    data.update(overrides)
    return data


class APIRequestPageTests(TestCase):
    def test_request_page_renders(self):
        response = self.client.get(reverse('home:request_api'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Submit API Request')
        self.assertContains(response, 'API Request Type')

    def test_post_creates_request_and_redirects(self):
        response = self.client.post(reverse('home:request_api'), _payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home:request_api_success'))

        api_request = APIRequest.objects.get()
        self.assertTrue(api_request.reference.startswith('API-'))
        self.assertEqual(api_request.status, 'pending')
        self.assertEqual(api_request.request_type, 'custom')
        self.assertEqual(api_request.budget_range, '5k-20k')
        self.assertIsNone(api_request.user)

        # Reference stashed in session for the success page.
        session = self.client.session
        self.assertEqual(session['api_request_reference'], api_request.reference)

        # Initial "submitted" status log is recorded.
        self.assertEqual(api_request.status_logs.count(), 1)
        self.assertEqual(api_request.status_logs.first().to_status, 'pending')

        # Admin notification + client confirmation.
        self.assertEqual(len(mail.outbox), 2)

    def test_success_page_shows_reference(self):
        self.client.post(reverse('home:request_api'), _payload())
        response = self.client.get(reverse('home:request_api_success'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'API-')

    def test_authenticated_user_is_attached_and_prefilled(self):
        user = User.objects.create_user('ada', 'ada@example.com', 'pass1234')
        self.client.login(username='ada', password='pass1234')

        response = self.client.get(reverse('home:request_api'))
        self.assertEqual(response.context['form'].initial['business_email'], 'ada@example.com')

        self.client.post(reverse('home:request_api'), _payload())
        self.assertEqual(APIRequest.objects.get().user, user)

    def test_honeypot_silently_drops_bots(self):
        response = self.client.post(
            reverse('home:request_api'),
            _payload(website='http://spam.example.com'),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(APIRequest.objects.count(), 0)

    def test_invalid_post_redisplays_form(self):
        response = self.client.post(
            reverse('home:request_api'),
            _payload(business_email='not-an-email', full_name=''),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'business_email', 'Enter a valid email address.')
        self.assertEqual(APIRequest.objects.count(), 0)

    def test_duplicate_submission_is_blocked(self):
        self.client.post(reverse('home:request_api'), _payload())
        response = self.client.post(reverse('home:request_api'), _payload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(APIRequest.objects.count(), 1)
        self.assertTrue(response.context['form'].non_field_errors())

    def test_different_api_name_is_allowed(self):
        self.client.post(reverse('home:request_api'), _payload())
        self.client.post(reverse('home:request_api'), _payload(api_name_or_category='Payments API'))
        self.assertEqual(APIRequest.objects.count(), 2)


class APIRequestWizardTests(TestCase):
    """Client-side wizard markup regressions (server behavior is covered elsewhere)."""

    def test_page_has_three_steps_and_progress(self):
        response = self.client.get(reverse('home:request_api'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-step="1"')
        self.assertContains(response, 'data-step="2"')
        self.assertContains(response, 'data-step="3"')
        self.assertContains(response, 'class="rq-steps"')
        self.assertContains(response, 'data-nav="next"')
        self.assertContains(response, 'data-nav="back"')
        self.assertContains(response, 'data-nav="submit"')

    def test_helper_text_is_linked_via_aria_describedby(self):
        response = self.client.get(reverse('home:request_api'))
        self.assertContains(response, 'aria-describedby="id_business_email-help"')
        self.assertContains(response, 'id_business_email-help')
        self.assertContains(response, 'id_api_name_or_category-hint3p')

    def test_conditional_usage_field_and_draft_autosave_present(self):
        response = self.client.get(reverse('home:request_api'))
        self.assertContains(response, 'data-conditional="usage"')
        self.assertContains(response, 'data-count-for')
        self.assertContains(response, 'onwebapp_api_request_draft')

    def test_wizard_is_progressive_enhancement(self):
        # Submit button is rendered outside JS-only visibility so the form
        # still works end-to-end when JavaScript is unavailable.
        response = self.client.get(reverse('home:request_api'))
        self.assertContains(response, '<button type="submit" class="rq-submit" id="rq-submit"', count=1)


class APIRequestTrackingTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user('ada', 'ada@example.com', 'pass1234')
        self.user_b = User.objects.create_user('grace', 'grace@example.com', 'pass1234')
        self.req_a = APIRequest.objects.create(
            user=self.user_a, full_name='Ada', business_email='ada@example.com',
            request_type='existing', api_name_or_category='Branding API',
            use_case='Sync brand data.', required_features='Read collections.',
        )
        self.req_b = APIRequest.objects.create(
            user=self.user_b, full_name='Grace', business_email='grace@example.com',
            request_type='custom', api_name_or_category='Payments API',
            use_case='Take payments.', required_features='Create charge.',
        )

    def test_login_required(self):
        response = self.client.get(reverse('users:api_requests_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_lists_only_own_requests(self):
        self.client.login(username='ada', password='pass1234')
        response = self.client.get(reverse('users:api_requests_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.req_a.reference)
        self.assertNotContains(response, self.req_b.reference)

    def test_status_filter(self):
        self.client.login(username='grace', password='pass1234')
        response = self.client.get(reverse('users:api_requests_list') + '?status=rejected')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.req_b.reference)
        response = self.client.get(reverse('users:api_requests_list') + '?status=pending')
        self.assertContains(response, self.req_b.reference)

    def test_archived_requests_hidden(self):
        self.req_a.is_archived = True
        self.req_a.save()
        self.client.login(username='ada', password='pass1234')
        response = self.client.get(reverse('users:api_requests_list'))
        self.assertNotContains(response, self.req_a.reference)

    def test_internal_notes_never_rendered(self):
        self.req_a.internal_notes = 'SECRET-STAFF-NOTE'
        self.req_a.save()
        self.client.login(username='ada', password='pass1234')
        response = self.client.get(reverse('users:api_requests_list'))
        self.assertNotContains(response, 'SECRET-STAFF-NOTE')


class APIRequestAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('root', 'root@example.com', 'pass1234')
        self.api_request = APIRequest.objects.create(
            full_name='Ada Lovelace', business_email='ada@example.com',
            request_type='custom', api_name_or_category='Invoicing API',
            use_case='Generate invoices.', required_features='Create invoice.',
        )

    def test_admin_changelist_renders(self):
        self.client.login(username='root', password='pass1234')
        response = self.client.get(reverse('admin:home_apirequest_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.api_request.reference)

    def test_admin_change_page_renders(self):
        self.client.login(username='root', password='pass1234')
        response = self.client.get(
            reverse('admin:home_apirequest_change', args=[self.api_request.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invoicing API')
        # Status log inline (history tracking) is present on the change page.
        self.assertContains(response, 'status_logs')

    def test_status_change_logs_history_and_notifies_client(self):
        self.client.login(username='root', password='pass1234')
        initial_log = self.api_request.status_logs.first()
        response = self.client.post(
            reverse('admin:home_apirequest_change', args=[self.api_request.pk]),
            {
                'full_name': 'Ada Lovelace',
                'business_email': 'ada@example.com',
                'company_name': '',
                'request_type': 'custom',
                'api_name_or_category': 'Invoicing API',
                'use_case': 'Generate invoices.',
                'required_features': 'Create invoice.',
                'expected_usage': '',
                'budget_range': '',
                'additional_requirements': '',
                'internal_notes': 'Looks feasible.',
                'status': 'under_review',
                'assigned_to': '',
                'user': '',
                # Inline management data for the status-log formset.
                'status_logs-TOTAL_FORMS': '1',
                'status_logs-INITIAL_FORMS': '1',
                'status_logs-MIN_NUM_FORMS': '0',
                'status_logs-MAX_NUM_FORMS': '1000',
                'status_logs-0-id': str(initial_log.pk),
                '_save': 'Save',
            },
        )
        self.assertEqual(response.status_code, 302)

        self.api_request.refresh_from_db()
        self.assertEqual(self.api_request.status, 'under_review')

        # Initial "submitted" log + admin status-change log.
        logs = self.api_request.status_logs.all()
        self.assertEqual(logs.count(), 2)
        change_log = logs.last()
        self.assertEqual(change_log.from_status, 'pending')
        self.assertEqual(change_log.to_status, 'under_review')
        self.assertEqual(change_log.changed_by, self.admin)

        # Client was notified of the status change.
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('ada@example.com', mail.outbox[0].to)

    def test_archive_action(self):
        self.client.login(username='root', password='pass1234')
        response = self.client.post(reverse('admin:home_apirequest_changelist'), {
            'action': 'mark_archived',
            '_selected_action': [str(self.api_request.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.api_request.refresh_from_db()
        self.assertTrue(self.api_request.is_archived)


class AdminApiRequestsPageTests(TestCase):
    """Custom admin management page at /software/api-requests/manage/."""

    def setUp(self):
        self.root = User.objects.create_superuser('root', 'root@example.com', 'pass1234')
        self.staff = User.objects.create_user(
            'agent', 'agent@example.com', 'pass1234', is_staff=True,
        )
        self.client_user = User.objects.create_user(
            'ada', 'ada@example.com', 'pass1234',
        )
        self.api_request = APIRequest.objects.create(
            user=self.client_user,
            full_name='Ada Lovelace', business_email='ada@example.com',
            request_type='custom', api_name_or_category='Invoicing API',
            use_case='Generate invoices.', required_features='Create invoice.',
        )

    def test_list_requires_superuser(self):
        self.assertEqual(
            self.client.get(reverse('home:admin_api_requests')).status_code, 302,
        )
        self.client.login(username='agent', password='pass1234')
        self.assertEqual(
            self.client.get(reverse('home:admin_api_requests')).status_code, 302,
        )
        self.client.logout()
        self.client.login(username='root', password='pass1234')
        self.assertEqual(
            self.client.get(reverse('home:admin_api_requests')).status_code, 200,
        )

    def test_list_shows_requests_and_filters(self):
        APIRequest.objects.create(
            full_name='Grace Hopper', business_email='grace@example.com',
            request_type='existing', api_name_or_category='Branding API',
            use_case='Sync brands.', required_features='Read collections.',
            status='under_review',
        )
        self.client.login(username='root', password='pass1234')

        response = self.client.get(reverse('home:admin_api_requests'))
        self.assertContains(response, 'API-')
        self.assertContains(response, 'Ada Lovelace')
        self.assertContains(response, 'Grace Hopper')

        response = self.client.get(
            reverse('home:admin_api_requests') + '?status=under_review',
        )
        self.assertContains(response, 'Grace Hopper')
        self.assertNotContains(response, 'Ada Lovelace')

        response = self.client.get(
            reverse('home:admin_api_requests') + '?q=Invoicing',
        )
        self.assertContains(response, 'Ada Lovelace')
        self.assertNotContains(response, 'Grace Hopper')

    def test_archived_hidden_by_default_and_shown_with_flag(self):
        self.api_request.is_archived = True
        self.api_request.save()
        self.client.login(username='root', password='pass1234')

        response = self.client.get(reverse('home:admin_api_requests'))
        self.assertNotContains(response, 'Ada Lovelace')

        response = self.client.get(reverse('home:admin_api_requests') + '?archived=1')
        self.assertContains(response, 'Ada Lovelace')

    def test_detail_renders_and_requires_superuser(self):
        url = reverse('home:admin_api_request_detail', args=[self.api_request.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.login(username='root', password='pass1234')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.api_request.reference)
        self.assertContains(response, 'Generate invoices.')

    def test_status_change_logs_history_and_notifies_client(self):
        self.client.login(username='root', password='pass1234')
        url = reverse('home:admin_api_request_detail', args=[self.api_request.pk])
        # Ignore welcome emails triggered by creating users in setUp.
        mail.outbox.clear()
        response = self.client.post(url, {
            'status': 'under_review',
            'assigned_to': str(self.staff.pk),
            'internal_notes': 'Checking feasibility.',
            'is_archived': '',
        })
        self.assertEqual(response.status_code, 302)

        self.api_request.refresh_from_db()
        self.assertEqual(self.api_request.status, 'under_review')
        self.assertEqual(self.api_request.assigned_to, self.staff)

        log = self.api_request.status_logs.order_by('-created_at').first()
        self.assertEqual(log.to_status, 'under_review')
        self.assertEqual(log.from_status, 'pending')
        self.assertEqual(log.changed_by, self.root)

        # Client status-change email went out.
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('ada@example.com', mail.outbox[0].to)

    def test_same_status_save_creates_no_log_and_no_email(self):
        self.client.login(username='root', password='pass1234')
        url = reverse('home:admin_api_request_detail', args=[self.api_request.pk])
        before = self.api_request.status_logs.count()
        mail.outbox.clear()  # Ignore welcome emails from setUp user creation.
        response = self.client.post(url, {
            'status': 'pending',
            'assigned_to': '',
            'internal_notes': 'Just a note.',
            'is_archived': '',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.api_request.status_logs.count(), before)
        self.assertEqual(len(mail.outbox), 0)

    def test_archive_from_detail_page(self):
        self.client.login(username='root', password='pass1234')
        url = reverse('home:admin_api_request_detail', args=[self.api_request.pk])
        self.client.post(url, {
            'status': 'pending',
            'assigned_to': '',
            'internal_notes': '',
            'is_archived': 'on',
        })
        self.api_request.refresh_from_db()
        self.assertTrue(self.api_request.is_archived)
