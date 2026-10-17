from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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
