"""Tests for the public RPA solutions page and its consultation form."""
import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .models import RPAConsultationRequest

User = get_user_model()


def _payload(**overrides):
    data = {
        'full_name': 'Ada Lovelace',
        'business_email': 'ada@example.com',
        'company_name': 'Analytical Engines',
        'current_tools': 'Excel, SAP, an internal portal',
        'process_to_automate': 'Every morning I copy rows from a spreadsheet into our ERP.',
        'task_frequency': 'daily',
        'time_spent': 'about 6 hours a week',
        'additional_requirements': '',
    }
    data.update(overrides)
    return data


class RPASolutionsPageTests(TestCase):
    def test_page_renders(self):
        response = self.client.get(reverse('home:rpa_solutions'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Automate Repetitive Tasks')
        self.assertContains(response, 'Tell Us What You Want to Automate')

    def test_seo_metadata(self):
        response = self.client.get(reverse('home:rpa_solutions'))
        title = re.search(
            r'<title>(.*?)</title>', response.content.decode(), re.S,
        ).group(1)
        self.assertIn('RPA Solutions', title)
        self.assertIn('Business Process Automation', title)
        self.assertTrue(title.endswith('| OnWebApp'))
        self.assertContains(
            response,
            'Automate repetitive business tasks with OnWebApp RPA solutions',
        )
        self.assertContains(response, 'Robotic Process Automation Services')

    def test_required_sections_are_present(self):
        response = self.client.get(reverse('home:rpa_solutions'))
        for marker in (
            'id="use-cases"',          # Section C — use cases anchor
            'id="consultation"',       # Section H — form anchor
            'Repetitive Data Entry',   # Section B
            'Invoice &amp; Document Processing',   # Section C
            'From Manual Process to Automated Workflow',  # Section D
            'The Right Automation for the Right Task',    # Section E
            'Automation That Fits Your Business',        # Section F
            'Start Small. Automate More Over Time.',     # Section G
            'What If Your Team Could Stop Doing the Same Task Every Day?',  # Section I
            'Custom quote',
            'Based on scope',
        ):
            with self.subTest(marker=marker):
                self.assertContains(response, marker)

    def test_hero_ctas_point_where_expected(self):
        response = self.client.get(reverse('home:rpa_solutions'))
        self.assertContains(response, 'href="#consultation"')
        self.assertContains(response, 'href="#use-cases"')

    def test_form_is_rendered_with_all_fields(self):
        response = self.client.get(reverse('home:rpa_solutions'))
        for field in (
            'id_full_name', 'id_business_email', 'id_company_name',
            'id_current_tools', 'id_process_to_automate', 'id_task_frequency',
            'id_time_spent', 'id_additional_requirements',
        ):
            with self.subTest(field=field):
                self.assertContains(response, f'name="{field[3:]}"')

    def test_required_fields_declare_html_required(self):
        # Client-side validation mirrors the server-side rules.
        response = self.client.get(reverse('home:rpa_solutions'))
        content = response.content.decode()
        for field in (
            'full_name', 'business_email', 'current_tools', 'process_to_automate',
        ):
            with self.subTest(field=field):
                tag = re.search(
                    r'<(?:input|textarea)[^>]*name="%s"[^>]*>' % field, content,
                )
                self.assertIsNotNone(tag, f'{field} widget not rendered')
                self.assertIn(' required', tag.group(0))

    def test_csrf_token_present(self):
        response = self.client.get(reverse('home:rpa_solutions'))
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_honeypot_field_present_and_hidden(self):
        response = self.client.get(reverse('home:rpa_solutions'))
        self.assertContains(response, 'name="website"')
        # The honeypot wrapper is hidden from assistive tech and from tab order.
        self.assertContains(response, '<div class="rp-hp" aria-hidden="true">')
        self.assertContains(response, 'tabindex="-1" autocomplete="off"')


class RPAConsultationFormSubmissionTests(TestCase):
    def test_post_creates_request_and_redirects(self):
        response = self.client.post(reverse('home:rpa_solutions'), _payload())
        self.assertEqual(response.status_code, 302)
        self.assertIn('#consultation', response.url)

        rpa_request = RPAConsultationRequest.objects.get()
        self.assertTrue(rpa_request.reference.startswith('RPA-'))
        self.assertEqual(rpa_request.status, 'new')
        self.assertEqual(rpa_request.task_frequency, 'daily')
        self.assertEqual(rpa_request.business_email, 'ada@example.com')
        self.assertIsNone(rpa_request.user)

        # Initial "submitted" status log is recorded.
        self.assertEqual(rpa_request.status_logs.count(), 1)
        self.assertEqual(rpa_request.status_logs.first().to_status, 'new')

        # Reference stashed in session for the confirmation panel.
        session = self.client.session
        self.assertEqual(session['rpa_reference'], rpa_request.reference)

        # Admin notification + client confirmation.
        self.assertEqual(len(mail.outbox), 2)

    def test_confirmation_panel_shows_reference(self):
        self.client.post(reverse('home:rpa_solutions'), _payload())
        response = self.client.get(reverse('home:rpa_solutions'))
        self.assertContains(response, 'RPA-')
        self.assertContains(response, 'Your request was received.')

    def test_confirmation_is_not_repeated_on_later_visits(self):
        self.client.post(reverse('home:rpa_solutions'), _payload())
        self.client.get(reverse('home:rpa_solutions'))  # consumes the session key
        response = self.client.get(reverse('home:rpa_solutions'))
        self.assertNotContains(response, 'Your request was received.')

    def test_invalid_post_redisplays_form(self):
        response = self.client.post(
            reverse('home:rpa_solutions'),
            _payload(business_email='not-an-email', full_name=''),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'], 'business_email', 'Enter a valid email address.',
        )
        self.assertFormError(response.context['form'], 'full_name', 'This field is required.')
        self.assertEqual(RPAConsultationRequest.objects.count(), 0)

    def test_short_process_description_is_rejected(self):
        response = self.client.post(
            reverse('home:rpa_solutions'),
            _payload(process_to_automate='too short'),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors['process_to_automate'])
        self.assertEqual(RPAConsultationRequest.objects.count(), 0)

    def test_optional_fields_may_be_blank(self):
        response = self.client.post(
            reverse('home:rpa_solutions'),
            _payload(company_name='', task_frequency='', time_spent=''),
        )
        self.assertEqual(response.status_code, 302)
        rpa_request = RPAConsultationRequest.objects.get()
        self.assertEqual(rpa_request.task_frequency, '')
        self.assertEqual(rpa_request.company_name, '')

    def test_honeypot_silently_drops_bots(self):
        response = self.client.post(
            reverse('home:rpa_solutions'),
            _payload(website='http://spam.example.com'),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RPAConsultationRequest.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_duplicate_submission_is_blocked(self):
        self.client.post(reverse('home:rpa_solutions'), _payload())
        response = self.client.post(reverse('home:rpa_solutions'), _payload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(RPAConsultationRequest.objects.count(), 1)
        self.assertTrue(response.context['form'].non_field_errors())

    def test_different_process_from_same_email_is_allowed(self):
        self.client.post(reverse('home:rpa_solutions'), _payload())
        self.client.post(
            reverse('home:rpa_solutions'),
            _payload(process_to_automate='A different monthly reconciliation task to automate.'),
        )
        self.assertEqual(RPAConsultationRequest.objects.count(), 2)

    def test_authenticated_user_is_attached_and_prefilled(self):
        user = User.objects.create_user('ada', 'ada@example.com', 'pass1234')
        self.client.login(username='ada', password='pass1234')

        response = self.client.get(reverse('home:rpa_solutions'))
        self.assertEqual(
            response.context['form'].fields['business_email'].initial, 'ada@example.com',
        )

        self.client.post(reverse('home:rpa_solutions'), _payload())
        self.assertEqual(RPAConsultationRequest.objects.get().user, user)

    def test_email_is_normalised(self):
        self.client.post(reverse('home:rpa_solutions'), _payload(business_email='  ADA@Example.COM '))
        self.assertEqual(
            RPAConsultationRequest.objects.get().business_email, 'ada@example.com',
        )


class RPAConsultationAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('root', 'root@example.com', 'pass1234')
        self.rpa_request = RPAConsultationRequest.objects.create(
            full_name='Ada Lovelace', business_email='ada@example.com',
            company_name='Analytical Engines', current_tools='Excel, SAP',
            process_to_automate='Copy invoice rows from Excel into SAP every morning.',
        )

    def test_admin_changelist_renders(self):
        self.client.login(username='root', password='pass1234')
        response = self.client.get(reverse('admin:home_rpaconsultationrequest_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.rpa_request.reference)

    def test_admin_change_page_renders(self):
        self.client.login(username='root', password='pass1234')
        response = self.client.get(
            reverse('admin:home_rpaconsultationrequest_change', args=[self.rpa_request.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Copy invoice rows from Excel into SAP')
        # Status log inline (history tracking) is present on the change page.
        self.assertContains(response, 'status_logs')

    def test_internal_notes_never_rendered_on_public_page(self):
        self.rpa_request.internal_notes = 'SECRET-STAFF-NOTE'
        self.rpa_request.save()
        response = self.client.get(reverse('home:rpa_solutions'))
        self.assertNotContains(response, 'SECRET-STAFF-NOTE')

    def test_status_change_logs_history_and_notifies_client(self):
        self.client.login(username='root', password='pass1234')
        initial_log = self.rpa_request.status_logs.first()
        mail.outbox.clear()  # Ignore welcome emails from setUp user creation.

        response = self.client.post(
            reverse('admin:home_rpaconsultationrequest_change', args=[self.rpa_request.pk]),
            {
                'full_name': 'Ada Lovelace',
                'business_email': 'ada@example.com',
                'company_name': 'Analytical Engines',
                'current_tools': 'Excel, SAP',
                'process_to_automate': 'Copy invoice rows from Excel into SAP every morning.',
                'task_frequency': 'daily',
                'time_spent': '',
                'additional_requirements': '',
                'internal_notes': 'Looks feasible.',
                'status': 'under_review',
                'assigned_to': '',
                'user': '',
                'is_archived': '',
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

        self.rpa_request.refresh_from_db()
        self.assertEqual(self.rpa_request.status, 'under_review')

        logs = self.rpa_request.status_logs.all()
        self.assertEqual(logs.count(), 2)
        change_log = logs.last()
        self.assertEqual(change_log.from_status, 'new')
        self.assertEqual(change_log.to_status, 'under_review')
        self.assertEqual(change_log.changed_by, self.admin)

        # Client was notified of the status change.
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('ada@example.com', mail.outbox[0].to)

    def test_archive_action(self):
        self.client.login(username='root', password='pass1234')
        response = self.client.post(
            reverse('admin:home_rpaconsultationrequest_changelist'),
            {'action': 'mark_archived', '_selected_action': [str(self.rpa_request.pk)]},
        )
        self.assertEqual(response.status_code, 302)
        self.rpa_request.refresh_from_db()
        self.assertTrue(self.rpa_request.is_archived)
