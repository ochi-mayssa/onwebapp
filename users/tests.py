from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.conf import settings
from django.urls import reverse

from unittest import mock

User = get_user_model()


class LoginDuplicateEmailTests(TestCase):
    """Login must not crash when two accounts share an email (email is not unique)."""

    def setUp(self):
        self.active = User.objects.create_user(
            'admin', 'shared@example.com', 'correct-pass',
            is_staff=True, is_superuser=True,
        )
        self.dormant = User.objects.create_user(
            'old_admin', 'shared@example.com', 'other-pass',
            is_staff=True, is_superuser=True,
        )

    def test_login_with_correct_password_of_one_of_two_accounts(self):
        response = self.client.post(
            reverse('users:login_view'),
            {'email': 'shared@example.com', 'password': 'correct-pass'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get('_auth_user_id'), str(self.active.pk))

    def test_login_with_second_accounts_password_also_works(self):
        response = self.client.post(
            reverse('users:login_view'),
            {'email': 'shared@example.com', 'password': 'other-pass'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get('_auth_user_id'), str(self.dormant.pk))

    def test_wrong_password_on_duplicate_email_is_graceful(self):
        response = self.client.post(
            reverse('users:login_view'),
            {'email': 'shared@example.com', 'password': 'nope'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid email or password')


class LoginRedirectTests(TestCase):
    """Superusers land on their admin dashboard; regular users on the homepage."""

    def test_superuser_lands_on_admin_dashboard(self):
        User.objects.create_superuser('root', 'root@example.com', 'pass1234')
        response = self.client.post(
            reverse('users:login_view'),
            {'email': 'root@example.com', 'password': 'pass1234'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('projects:admin_dashboard'))

    def test_regular_user_lands_on_homepage(self):
        User.objects.create_user('client', 'client@example.com', 'pass1234')
        response = self.client.post(
            reverse('users:login_view'),
            {'email': 'client@example.com', 'password': 'pass1234'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home:home'))

    def test_next_parameter_still_wins(self):
        User.objects.create_superuser('root', 'root@example.com', 'pass1234')
        response = self.client.post(
            reverse('users:login_view') + '?next=/crm/dashboard/',
            {'email': 'root@example.com', 'password': 'pass1234'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/crm/dashboard/')

    def test_superusers_get_admin_navbar_not_marketing_nav(self):
        user = User.objects.create_superuser('root', 'root@example.com', 'pass1234')
        self.client.force_login(user)
        response = self.client.get(reverse('home:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ADMIN')
        self.assertContains(response, reverse('home:admin_api_requests'))
        # Marketing menus are gone for superusers.
        self.assertNotContains(response, 'id="softwareMenuUnified"')

    def test_regular_users_keep_marketing_navbar(self):
        User.objects.create_user('client', 'client@example.com', 'pass1234')
        self.client.login(username='client', password='pass1234')
        response = self.client.get(reverse('home:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="softwareMenuUnified"')
        self.assertNotContains(response, 'ADMIN')


class VerificationEmailTests(TestCase):
    """Verification emails are multipart, OnWebApp-branded and actually dispatched."""

    PASSWORD = 'Str0ng-Passw0rd!2026'

    def test_send_verification_email_task_delivers_multipart(self):
        from .tasks import send_verification_email

        user = User.objects.create_user('grace', 'grace@example.com', self.PASSWORD)
        mail.outbox.clear()
        result = send_verification_email(user.id, 'http://testserver/users/verify-email/uid/token/')
        self.assertEqual(result, 'Email sent')

        messages = [m for m in mail.outbox if 'Verify your email' in m.subject]
        self.assertEqual(len(messages), 1)
        message = messages[0]
        self.assertEqual(message.subject, 'Verify your email for OnWebApp')
        self.assertIn('grace@example.com', message.to)
        self.assertIn('/users/verify-email/', message.body)
        self.assertTrue(message.alternatives)
        self.assertEqual(message.alternatives[0][1], 'text/html')
        self.assertIn('/users/verify-email/', message.alternatives[0][0])
        self.assertNotIn('AutomationIQ', message.subject)
        self.assertNotIn('AutomationIQ', message.alternatives[0][0])

    def test_send_verification_email_unknown_user(self):
        from .tasks import send_verification_email

        self.assertEqual(send_verification_email(999999, 'http://x/'), 'Unknown user')

    def test_signup_sends_verification_email_synchronously(self):
        with mock.patch('users.tasks.send_verification_email') as task:
            task.return_value = 'Email sent'
            response = self.client.post(reverse('users:signup'), {
                'username': 'grace',
                'email': 'grace@example.com',
                'password1': self.PASSWORD,
                'password2': self.PASSWORD,
            })
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, reverse('users:check_email'))
            # Sent in-process (no Celery worker) — available immediately.
            self.assertTrue(task.called, 'verification task was not dispatched')
            user_id, verify_url = task.call_args[0]
            self.assertEqual(user_id, User.objects.get(username='grace').pk)
            self.assertIn('/users/verify-email/', verify_url)
            self.assertTrue(verify_url.startswith(settings.SITE_URL))


class PasswordResetEmailTests(TestCase):
    def _request_reset(self, **kwargs):
        user = User.objects.create_user('ada', 'ada@example.com', 'Str0ng-Passw0rd!2026')
        # Ignore the welcome email sent by the projects signal on user creation.
        mail.outbox.clear()
        response = self.client.post(
            reverse('users:password_reset'),
            {'email': user.email},
            **kwargs,
        )
        messages = [m for m in mail.outbox if 'Reset your password' in m.subject]
        return user, response, (messages[0] if messages else None)

    def test_reset_email_delivered_with_https_link_behind_proxy(self):
        user, response, message = self._request_reset(
            secure=True,
            HTTP_X_FORWARDED_PROTO='https',
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(message)
        self.assertIn('OnWebApp', message.subject)
        self.assertNotIn('AutomationIQ', message.subject)
        self.assertIn(user.email, message.to)
        # HTTPS when the proxy reports a secure request (SECURE_PROXY_SSL_HEADER).
        self.assertIn('https://', message.body)
        self.assertNotIn('http://', message.body)
        self.assertIn('/users/reset/', message.body)

    def test_reset_email_has_html_alternative(self):
        _, _, message = self._request_reset()
        self.assertIsNotNone(message)
        self.assertTrue(message.alternatives)
        self.assertEqual(message.alternatives[0][1], 'text/html')
        self.assertIn('/users/reset/', message.alternatives[0][0])

    def test_reset_email_http_in_local_dev(self):
        _, _, message = self._request_reset()
        self.assertIsNotNone(message)
        self.assertIn('http://', message.body)


class VerifyEmailViewTests(TestCase):
    """verify-email validates uid+token and renders the result page (namespaced URLs)."""

    def _link_for(self, user):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        return reverse('users:verify_email', args=[uid, token])

    def test_invalid_token_renders_invalid_page_without_error(self):
        response = self.client.get(
            reverse('users:verify_email', args=['MTM', 'bogus-token']),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid or expired link')

    def test_valid_token_verifies_and_renders_success(self):
        user = User.objects.create_user('ada', 'ada@example.com', 'Str0ng-Passw0rd!2026')
        response = self.client.get(self._link_for(user))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Email verified')
        self.assertEqual(response.context['next_url'], reverse('users:onboarding'))
        from users.models import UserProfile
        self.assertTrue(UserProfile.objects.get(user=user).email_verified)
        # Verified and signed in automatically.
        self.assertEqual(self.client.session.get('_auth_user_id'), str(user.pk))


class MandatoryVerificationTests(TestCase):
    """Accounts stay inactive until their email is verified; access is blocked server-side."""

    PASSWORD = 'Str0ng-Passw0rd!2026'

    def setUp(self):
        cache.clear()

    def _signup(self, username='grace', email='grace@example.com'):
        return self.client.post(reverse('users:signup'), {
            'username': username,
            'email': email,
            'password1': self.PASSWORD,
            'password2': self.PASSWORD,
        })

    def _link_for(self, user):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        return reverse('users:verify_email', args=[uid, token])

    def test_signup_creates_pending_inactive_account_without_login(self):
        response = self._signup()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('users:check_email'))
        user = User.objects.get(username='grace')
        self.assertFalse(user.is_active)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_signup_sends_verification_email_with_site_url_link(self):
        mail.outbox.clear()
        response = self._signup()
        self.assertEqual(response.status_code, 302)
        messages = [m for m in mail.outbox if 'Verify your email' in m.subject]
        self.assertEqual(len(messages), 1)
        body = messages[0].body + messages[0].alternatives[0][0]
        self.assertIn('/users/verify-email/', body)
        self.assertTrue(
            settings.SITE_URL.rstrip('/') in body,
            'verification link must be built from SITE_URL',
        )
        self.assertIn('grace@example.com', messages[0].to)

    def test_verification_link_activates_account_and_signs_in(self):
        self._signup()
        user = User.objects.get(username='grace')
        response = self.client.get(self._link_for(user))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Email verified')
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        from users.models import UserProfile
        self.assertTrue(UserProfile.objects.get(user=user).email_verified)
        self.assertEqual(self.client.session.get('_auth_user_id'), str(user.pk))

    @override_settings(PASSWORD_RESET_TIMEOUT=-1)
    def test_expired_token_does_not_activate(self):
        self._signup()
        user = User.objects.get(username='grace')
        response = self.client.get(self._link_for(user))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid or expired link')
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_token_is_single_use_after_success(self):
        self._signup()
        user = User.objects.get(username='grace')
        link = self._link_for(user)
        first = self.client.get(link)
        self.assertContains(first, 'Email verified')
        self.client.logout()
        second = self.client.get(link)
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, 'Already verified')

    def test_unknown_uid_renders_invalid_page(self):
        response = self.client.get(
            reverse('users:verify_email', args=['MTM', 'bogus-token']),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid or expired link')

    def test_unverified_user_cannot_login_with_correct_password(self):
        self._signup()
        response = self.client.post(reverse('users:login_view'), {
            'email': 'grace@example.com',
            'password': self.PASSWORD,
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'pending email verification')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_unverified_user_blocked_even_when_session_exists(self):
        user = User.objects.create_user('ghost', 'ghost@example.com', self.PASSWORD, is_active=False)
        self.client.force_login(user)
        response = self.client.get(reverse('users:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('users:login_view')))

    def test_unverified_user_blocked_from_home_admin_state(self):
        user = User.objects.create_user('ghost', 'ghost@example.com', self.PASSWORD, is_active=False)
        self.client.force_login(user)
        response = self.client.get(reverse('home:home'))
        self.assertEqual(response.status_code, 200)
        # ModelBackend refuses inactive users: the request is anonymous
        # even though a session id was planted by force_login.
        self.assertTrue(response.wsgi_request.user.is_anonymous)

    def test_wrong_password_still_gets_generic_invalid_message(self):
        self._signup()
        response = self.client.post(reverse('users:login_view'), {
            'email': 'grace@example.com',
            'password': 'totally-wrong',
        }, follow=True)
        self.assertContains(response, 'Invalid email or password')
        self.assertNotContains(response, 'pending email verification')

    def test_verified_user_can_login_normally(self):
        self._signup()
        user = User.objects.get(username='grace')
        self.client.get(self._link_for(user))
        self.client.logout()
        response = self.client.post(reverse('users:login_view'), {
            'email': 'grace@example.com',
            'password': self.PASSWORD,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home:home'))

    def test_superuser_login_and_admin_access_untouched(self):
        User.objects.create_superuser('root', 'root@example.com', self.PASSWORD)
        response = self.client.post(reverse('users:login_view'), {
            'email': 'root@example.com',
            'password': self.PASSWORD,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('projects:admin_dashboard'))
        page = self.client.get(reverse('projects:admin_dashboard'))
        self.assertEqual(page.status_code, 200)

    def test_delivery_failure_shows_error_and_keeps_account(self):
        with mock.patch('users.tasks.send_verification_email', return_value='Email failed'):
            response = self._signup()
        self.assertEqual(response.status_code, 302)
        follow = self.client.get(response.url)
        self.assertContains(follow, 'could not send the verification email')
        user = User.objects.get(username='grace')
        self.assertFalse(user.is_active)
        self.assertTrue(user.has_usable_password())

    @override_settings(EMAIL_VERIFICATION_REQUIRED=False)
    def test_dev_opt_out_keeps_old_active_login_flow(self):
        response = self._signup()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('users:onboarding'))
        user = User.objects.get(username='grace')
        self.assertTrue(user.is_active)
        self.assertEqual(self.client.session.get('_auth_user_id'), str(user.pk))

    def test_check_email_page_renders(self):
        response = self.client.get(reverse('users:check_email'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Check your email')

    def test_resend_requires_post(self):
        response = self.client.get(reverse('users:resend_verification'))
        self.assertEqual(response.status_code, 405)

    def test_resend_unknown_address_gets_generic_response(self):
        response = self.client.post(
            reverse('users:resend_verification'),
            {'email': 'nobody@example.com'},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'If an account exists for this address')

    def test_resend_sends_for_pending_account(self):
        self._signup()
        mail.outbox.clear()
        response = self.client.post(
            reverse('users:resend_verification'),
            {'email': 'grace@example.com'},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'If an account exists for this address')
        messages = [m for m in mail.outbox if 'Verify your email' in m.subject]
        self.assertEqual(len(messages), 1)
        user = User.objects.get(username='grace')
        self.assertFalse(user.is_active)

    def test_resend_throttled_within_cooldown(self):
        first = self.client.post(
            reverse('users:resend_verification'),
            {'email': 'grace@example.com'},
            follow=True,
        )
        self.assertNotContains(first, 'Too many resend requests')
        second = self.client.post(
            reverse('users:resend_verification'),
            {'email': 'grace@example.com'},
            follow=True,
        )
        self.assertContains(second, 'Too many resend requests')


class OnboardingFlowTests(TestCase):
    """First-run onboarding: rendering, validation, persistence and CRM sync."""

    def setUp(self):
        self.user = User.objects.create_user(
            'ada', 'ada@example.com', 'correct-pass',
            first_name='Ada', last_name='Lovelace',
        )
        self.client.force_login(self.user)
        self.url = reverse('users:onboarding')

    def _payload(self, **overrides):
        data = {
            'service_type': 'full_platform',
            'community_needs_selection': ['website', 'branding'],
            'project_description': 'business',
            'start_timeline': '1_month',
            'display_name': 'Ada Lovelace',
            'phone_number': '+1 555 000 1111',
            'company_name': 'Analytical Engines',
            'job_title': 'Founder',
            'country': 'United Kingdom',
            'city': 'London',
            'website': 'https://example.com',
            'industry': 'Technology',
            'company_size': '11-50',
            'business_address': '1 Main Street',
        }
        data.update(overrides)
        return data

    def test_get_renders_all_four_steps(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['initial_step'], 1)
        for heading in (
            'Choose Your Path',
            'What Do You Need?',
            'What Are You Looking to Achieve?',
            'When Are You Planning to Get Started?',
        ):
            self.assertContains(response, heading)

        form = response.context['form']
        self.assertEqual([w.data['value'] for w in form['service_type']], ['full_platform', 'community'])
        self.assertEqual(len(list(form['community_needs_selection'])), 4)
        self.assertEqual([w.data['value'] for w in form['project_description']], ['personal', 'business', 'community'])
        self.assertEqual([w.data['value'] for w in form['start_timeline']], ['immediately', '1_month', '3_months', 'exploring'])

    def test_successful_submission_saves_profile_and_shows_completion(self):
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['completed'])
        self.assertContains(response, 'All Set!')
        self.assertContains(response, 'Full Digital Platform')
        self.assertContains(response, 'Website Development')
        self.assertContains(response, 'Brand Identity &amp; Design')
        self.assertContains(response, 'Grow an Existing Business')
        self.assertContains(response, 'Within a Month')
        self.assertContains(response, 'Go to My Dashboard')
        self.assertContains(response, 'id="redirectNote"')
        self.assertContains(response, 'data-url="{}"'.format(reverse('users:dashboard')))

        profile = self.user.profile
        self.assertEqual(profile.service_type, 'full_platform')
        self.assertEqual(profile.community_needs, ['website', 'branding'])
        self.assertEqual(profile.project_description, 'business')
        self.assertEqual(profile.start_timeline, '1_month')
        self.assertEqual(profile.display_name, 'Ada Lovelace')
        self.assertEqual(profile.phone_number, '+1 555 000 1111')
        self.assertEqual(profile.company_name, 'Analytical Engines')
        self.assertEqual(profile.job_title, 'Founder')
        self.assertEqual(profile.country, 'United Kingdom')
        self.assertEqual(profile.city, 'London')
        self.assertEqual(profile.website, 'https://example.com')
        self.assertEqual(profile.industry, 'Technology')
        self.assertEqual(profile.company_size, '11-50')
        self.assertEqual(profile.business_address, '1 Main Street')
        self.assertEqual(
            profile.community_needs_labels,
            ['Website Development', 'Brand Identity & Design'],
        )

    def test_timeline_is_optional(self):
        payload = self._payload()
        payload.pop('start_timeline')
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['completed'])
        self.assertEqual(self.user.profile.start_timeline, '')

    def test_missing_services_reopens_step_two(self):
        payload = self._payload()
        payload.pop('community_needs_selection')
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context.get('completed', False))
        self.assertEqual(response.context['initial_step'], 2)
        self.assertContains(response, 'Select at least one service to continue.')
        self.assertIsNone(self.user.profile.service_type)

    def test_missing_path_reopens_step_one(self):
        payload = self._payload()
        payload.pop('service_type')
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['initial_step'], 1)
        self.assertIsNone(self.user.profile.service_type)

    def test_missing_goal_reopens_step_three(self):
        payload = self._payload()
        payload.pop('project_description')
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['initial_step'], 3)
        self.assertIsNone(self.user.profile.service_type)

    def test_completed_onboarding_redirects_away(self):
        self.client.post(self.url, self._payload())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('users:dashboard'))

    def test_crm_customer_is_created(self):
        self.client.post(self.url, self._payload())
        from crm.models import Customer
        customer = Customer.objects.get(user=self.user)
        self.assertEqual(customer.email, 'ada@example.com')
        self.assertEqual(customer.name, 'Analytical Engines')
        self.assertEqual(customer.company_name, 'Analytical Engines')
        self.assertEqual(customer.industry, 'Technology')
        self.assertEqual(customer.website, 'https://example.com')
        self.assertEqual(customer.phone, '+1 555 000 1111')
        self.assertEqual(customer.customer_type, 'COMPANY')
        self.assertEqual(customer.source, 'Onboarding')

    def test_crm_sync_preserves_existing_values(self):
        from crm.models import Customer
        Customer.objects.create(
            user=self.user, email='ada@example.com',
            name='Curated Name', company_name='Curated Co',
            industry='Finance', source='Sales team',
        )
        self.client.post(self.url, self._payload())
        customer = Customer.objects.get(user=self.user)
        self.assertEqual(customer.name, 'Curated Name')
        self.assertEqual(customer.company_name, 'Curated Co')
        self.assertEqual(customer.industry, 'Finance')
        self.assertEqual(customer.source, 'Sales team')
        # Blank fields are filled from onboarding.
        self.assertEqual(customer.phone, '+1 555 000 1111')
        self.assertEqual(customer.website, 'https://example.com')

    def test_dashboard_shows_personalized_plan(self):
        self.client.post(self.url, self._payload())
        response = self.client.get(reverse('users:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your OnWebApp Plan')
        self.assertContains(response, 'Full Digital Platform')
        self.assertContains(response, 'Website Development')
        self.assertContains(response, 'Grow an Existing Business')
        self.assertContains(response, 'Within a Month')

    def test_profile_edit_persists_onboarding_details(self):
        self.client.post(self.url, self._payload())
        response = self.client.post(reverse('users:profile_edit'), {
            'display_name': 'Ada L.',
            'bio': 'Mathematician',
            'avatar': '',
            'company_name': 'Analytical Engines Ltd',
            'industry': 'Computing',
            'company_size': '51-200',
            'country': 'United Kingdom',
            'phone_number': '+44 20 0000 0000',
            'job_title': 'Chief Scientist',
            'city': 'Manchester',
            'website': 'https://ada.example.com',
            'business_address': '2 Engine Road',
        })
        self.assertEqual(response.status_code, 302)
        profile = self.user.profile
        self.assertEqual(profile.phone_number, '+44 20 0000 0000')
        self.assertEqual(profile.job_title, 'Chief Scientist')
        self.assertEqual(profile.city, 'Manchester')
        self.assertEqual(profile.website, 'https://ada.example.com')
        self.assertEqual(profile.business_address, '2 Engine Road')

    def test_profile_edit_syncs_customer_record(self):
        self.client.post(self.url, self._payload())
        self.client.post(reverse('users:profile_edit'), {
            'display_name': 'Ada L.',
            'bio': 'Mathematician',
            'avatar': '',
            'company_name': 'Analytical Engines Ltd',
            'industry': 'Computing',
            'company_size': '51-200',
            'country': 'United Kingdom',
            'phone_number': '+44 20 0000 0000',
            'job_title': 'Chief Scientist',
            'city': 'Manchester',
            'website': 'https://ada.example.com',
            'business_address': '2 Engine Road',
        })

        from crm.models import Customer
        customer = Customer.objects.get(user=self.user)
        self.assertEqual(customer.name, 'Analytical Engines Ltd')
        self.assertEqual(customer.phone, '+44 20 0000 0000')
        self.assertEqual(customer.company_name, 'Analytical Engines Ltd')
        self.assertEqual(customer.industry, 'Computing')
        self.assertEqual(customer.city, 'Manchester')
        self.assertEqual(customer.website, 'https://ada.example.com')
        self.assertEqual(customer.profile_sync_status, 'SYNCED')


