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
