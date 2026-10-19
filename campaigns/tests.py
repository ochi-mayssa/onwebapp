"""Tests for the admin email-campaign feature."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail, signing
from django.test import TestCase, override_settings
from django.urls import reverse

from users.models import UserProfile

from .audience import eligible_client_queryset, resolve_recipients, resolved_email_map
from .delivery import (
    deliver_campaign,
    start_send,
    unsubscribe_url_for,
    verify_unsubscribe_token,
)
from .models import Campaign, CampaignRecipient
from .sanitizer import sanitize_campaign_html

User = get_user_model()


def _client_user(username, email, **profile_kwargs):
    user = User.objects.create_user(username, email, 'Str0ng-Passw0rd!2026')
    if profile_kwargs:
        profile, _ = UserProfile.objects.get_or_create(user=user)
        for key, value in profile_kwargs.items():
            setattr(profile, key, value)
        profile.save()
    return user


def _compose_payload(**overrides):
    data = {
        'name': 'Spring update',
        'subject': 'What is new on OnWebApp',
        'body_text': 'Hello! We have new features.',
        'body_html': '<p>Hello! <strong>We have</strong> new features.</p>',
        'audience': Campaign.AUDIENCE_ALL,
    }
    data.update(overrides)
    return data


class SanitizerTests(TestCase):
    def test_allows_basic_tags(self):
        html = '<p>Hello <strong>world</strong></p>'
        self.assertEqual(sanitize_campaign_html(html), html)

    def test_strips_script_entirely(self):
        out = sanitize_campaign_html('<p>Hi</p><script>alert(1)</script><p>Bye</p>')
        self.assertNotIn('script', out)
        self.assertNotIn('alert(1)', out)
        self.assertIn('<p>Hi</p>', out)
        self.assertIn('<p>Bye</p>', out)

    def test_strips_event_handlers_and_javascript_href(self):
        out = sanitize_campaign_html('<a href="javascript:alert(1)" onclick="x()">click</a>')
        self.assertNotIn('javascript:', out)
        self.assertNotIn('onclick', out)
        self.assertIn('>click</a>', out)

    def test_keeps_safe_href(self):
        out = sanitize_campaign_html('<a href="https://onwebapp.com/x">go</a>')
        self.assertIn('href="https://onwebapp.com/x"', out)

    def test_escapes_unknown_tag_content_as_text(self):
        out = sanitize_campaign_html('<div><iframe src="http://evil"></iframe>text</div>')
        self.assertNotIn('iframe', out)
        self.assertIn('text', out)


class AudienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client1 = _client_user('ada', 'ada@example.com')
        cls.client2 = _client_user('grace', 'grace@example.com')
        cls.opted_out = _client_user('linus', 'linus@example.com',
                                     marketing_emails_enabled=False)
        cls.staff = User.objects.create_user('worker', 'worker@example.com', 'Str0ng-Passw0rd!2026')
        cls.staff.is_staff = True
        cls.staff.save(update_fields=['is_staff'])
        cls.superuser = User.objects.create_superuser('root', 'root@example.com', 'Str0ng-Passw0rd!2026')
        cls.inactive = _client_user('boom', 'boom@example.com')
        cls.inactive.is_active = False
        cls.inactive.save(update_fields=['is_active'])
        cls.no_email = User.objects.create_user('noemail', '', 'Str0ng-Passw0rd!2026')

    def _campaign(self, audience, selected=None):
        campaign = Campaign.objects.create(
            name='C', subject='S', body_text='B', audience=audience,
        )
        if selected is not None:
            campaign.selected_users.set(selected)
        return campaign

    def test_all_excludes_staff_superusers_inactive_optouts_and_blank_emails(self):
        emails = set(resolved_email_map(
            self._campaign(Campaign.AUDIENCE_ALL),
        ).values())
        self.assertEqual(emails, {'ada@example.com', 'grace@example.com'})

    def test_selected_audience_only_chosen_clients(self):
        campaign = self._campaign(Campaign.AUDIENCE_SELECTED, selected=[self.client2])
        emails = set(resolved_email_map(campaign).values())
        self.assertEqual(emails, {'grace@example.com'})

    def test_subscriber_groups_use_existing_subscription_model(self):
        from users.models import UserSubscription
        UserSubscription.objects.create(user=self.client1, is_active=True)
        UserSubscription.objects.create(user=self.client2, is_active=False)

        subs = set(resolved_email_map(
            self._campaign(Campaign.AUDIENCE_SUBSCRIBERS),
        ).values())
        self.assertEqual(subs, {'ada@example.com'})

        non_subs = set(resolved_email_map(
            self._campaign(Campaign.AUDIENCE_NON_SUBSCRIBERS),
        ).values())
        self.assertIn('grace@example.com', non_subs)
        self.assertNotIn('ada@example.com', non_subs)


class CampaignAuthorizationTests(TestCase):
    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('campaigns:compose'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_staff_user_redirected_away(self):
        user = User.objects.create_user('worker', 'worker@example.com', 'Str0ng-Passw0rd!2026')
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        self.client.login(username='worker', password='Str0ng-Passw0rd!2026')
        for url in (reverse('campaigns:compose'), reverse('campaigns:history')):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)

    def test_superuser_can_open_pages(self):
        User.objects.create_superuser('root', 'root@example.com', 'Str0ng-Passw0rd!2026')
        self.client.login(username='root', password='Str0ng-Passw0rd!2026')
        self.assertEqual(self.client.get(reverse('campaigns:compose')).status_code, 200)
        self.assertEqual(self.client.get(reverse('campaigns:history')).status_code, 200)

    def test_navbar_contains_campaigns_link_for_superuser(self):
        User.objects.create_superuser('root', 'root@example.com', 'Str0ng-Passw0rd!2026')
        self.client.login(username='root', password='Str0ng-Passw0rd!2026')
        response = self.client.get(reverse('home:home'))
        self.assertContains(response, reverse('campaigns:history'))


class CampaignWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser('root', 'root@example.com', 'Str0ng-Passw0rd!2026')
        cls.client1 = _client_user('ada', 'ada@example.com')
        cls.client2 = _client_user('grace', 'grace@example.com')

    def setUp(self):
        self.client.login(username='root', password='Str0ng-Passw0rd!2026')

    def _compose(self, **overrides):
        return self.client.post(reverse('campaigns:compose'), _compose_payload(**overrides))

    def test_compose_creates_draft_and_redirects_to_confirm(self):
        response = self._compose()
        campaign = Campaign.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('campaigns:confirm', args=[campaign.pk]))
        self.assertEqual(campaign.status, Campaign.STATUS_DRAFT)
        self.assertEqual(campaign.created_by, self.root)
        self.assertTrue(campaign.reference.startswith('CMP-'))
        # HTML is stored sanitized.
        self.assertNotIn('<script', campaign.body_html)

    def test_compose_sanitizes_html_body(self):
        self._compose(body_html='<p>ok</p><script>alert(1)</script>')
        campaign = Campaign.objects.get()
        self.assertIn('<p>ok</p>', campaign.body_html)
        self.assertNotIn('script', campaign.body_html)
        self.assertNotIn('alert(1)', campaign.body_html)

    def test_selected_audience_requires_selection(self):
        response = self._compose(audience=Campaign.AUDIENCE_SELECTED)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'], 'selected_users',
            'Pick at least one client for a selected audience.',
        )
        self.assertEqual(Campaign.objects.count(), 0)

    def test_confirm_page_shows_count_and_preview(self):
        self._compose()
        campaign = Campaign.objects.get()
        response = self.client.get(reverse('campaigns:confirm', args=[campaign.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['recipient_count'], 2)
        self.assertContains(response, 'Spring update')
        self.assertContains(response, 'We have')

    def test_confirm_post_starts_send_and_delivers(self):
        self._compose()
        campaign = Campaign.objects.get()
        mail.outbox.clear()
        with mock.patch('campaigns.delivery._spawn') as spawn:
            response = self.client.post(reverse('campaigns:confirm', args=[campaign.pk]))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(spawn.called)
            # Run delivery synchronously for the test.
            deliver_campaign(campaign.pk, sleep=lambda s: None)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.STATUS_SENT)
        self.assertEqual(campaign.sent_count, 2)
        self.assertEqual(campaign.failed_count, 0)
        self.assertEqual(campaign.pending_count, 0)
        # One individual message per recipient; no shared To/CC leakage.
        self.assertEqual(len(mail.outbox), 2)
        for message in mail.outbox:
            self.assertEqual(len(message.to), 1)
            self.assertFalse(message.cc)
            self.assertFalse(message.bcc)
        recipients = {m.to[0] for m in mail.outbox}
        self.assertEqual(recipients, {'ada@example.com', 'grace@example.com'})
        # Marketing email carries the unsubscribe footer link.
        body = mail.outbox[0].body
        self.assertIn('/campaigns/unsubscribe/', body)

    def test_duplicate_send_is_refused(self):
        self._compose()
        campaign = Campaign.objects.get()
        with mock.patch('campaigns.delivery._spawn'):
            start_send(campaign)
        # Second start must fail (status is no longer draft).
        ok, error = start_send(campaign)
        self.assertFalse(ok)
        self.assertEqual(error, 'not_draft')
        # Even a direct confirm POST cannot restart it.
        response = self.client.post(reverse('campaigns:confirm', args=[campaign.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('campaigns:detail', args=[campaign.pk]))

    def test_failed_delivery_is_recorded_and_campaign_marks_failed(self):
        self._compose()
        campaign = Campaign.objects.get()
        with mock.patch('campaigns.delivery._spawn'):
            self.assertTrue(start_send(campaign)[0])
        with mock.patch(
            'campaigns.delivery.send_notification_email', return_value=False,
        ):
            deliver_campaign(campaign.pk, sleep=lambda s: None)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.STATUS_FAILED)
        self.assertEqual(campaign.failed_count, 2)
        self.assertEqual(campaign.sent_count, 0)
        row = campaign.recipients.first()
        self.assertEqual(row.status, CampaignRecipient.STATUS_FAILED)
        self.assertEqual(row.attempts, 1)
        self.assertIn('Delivery failed', row.last_error)

    def test_partial_failure_keeps_sent_status_with_counts(self):
        self._compose()
        campaign = Campaign.objects.get()
        with mock.patch('campaigns.delivery._spawn'):
            self.assertTrue(start_send(campaign)[0])
        real = mock.Mock(side_effect=lambda **kw: kw['recipients'] != ['ada@example.com'])
        with mock.patch('campaigns.delivery.send_notification_email', real):
            deliver_campaign(campaign.pk, sleep=lambda s: None)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.STATUS_SENT)
        self.assertEqual(campaign.sent_count, 1)
        self.assertEqual(campaign.failed_count, 1)

    def test_batching_processes_everything_with_counters_accurate(self):
        self._compose()
        campaign = Campaign.objects.get()
        delays = []
        with mock.patch('campaigns.delivery._spawn'):
            start_send(campaign)
        # 2 recipients, batch size 1 -> two batches, one delay between them.
        campaign.batch_size = 1
        campaign.batch_delay_seconds = 0.5
        campaign.save(update_fields=['batch_size', 'batch_delay_seconds'])
        deliver_campaign(campaign.pk, sleep=delays.append)
        campaign.refresh_from_db()
        self.assertEqual(campaign.sent_count, 2)
        self.assertEqual(campaign.pending_count, 0)
        self.assertEqual(len(delays), 1)

    def test_interrupted_campaign_resumes_pending_only(self):
        self._compose()
        campaign = Campaign.objects.get()
        # Simulate an interrupted send: two rows exist, one delivered, one pending.
        CampaignRecipient.objects.bulk_create([
            CampaignRecipient(campaign=campaign, user=self.client1,
                              email='ada@example.com',
                              status=CampaignRecipient.STATUS_SENT, attempts=1),
            CampaignRecipient(campaign=campaign, user=self.client2,
                              email='grace@example.com'),
        ])
        campaign.status = Campaign.STATUS_SENDING
        campaign.sent_count = 1
        campaign.pending_count = 1
        campaign.total_recipients = 2
        campaign.save(update_fields=['status', 'sent_count', 'pending_count', 'total_recipients'])
        mail.outbox.clear()
        deliver_campaign(campaign.pk, sleep=lambda s: None)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.STATUS_SENT)
        self.assertEqual(campaign.sent_count, 2)
        self.assertEqual(campaign.pending_count, 0)
        # Only the pending recipient was mailed.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['grace@example.com'])

    def test_opted_out_user_is_excluded_from_new_campaigns(self):
        _client_user('linus', 'linus@example.com', marketing_emails_enabled=False)
        self._compose()
        campaign = Campaign.objects.get()
        with mock.patch('campaigns.delivery._spawn'):
            start_send(campaign)
        emails = set(campaign.recipients.values_list('email', flat=True))
        self.assertEqual(emails, {'ada@example.com', 'grace@example.com'})

    def test_cancel_draft(self):
        self._compose()
        campaign = Campaign.objects.get()
        response = self.client.post(reverse('campaigns:cancel', args=[campaign.pk]))
        self.assertEqual(response.status_code, 302)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.STATUS_CANCELED)

    def test_history_and_detail_show_counts_and_recipients(self):
        self._compose()
        campaign = Campaign.objects.get()
        with mock.patch('campaigns.delivery._spawn'):
            start_send(campaign)
        deliver_campaign(campaign.pk, sleep=lambda s: None)
        campaign.refresh_from_db()

        history = self.client.get(reverse('campaigns:history'))
        self.assertContains(history, campaign.reference)
        self.assertContains(history, 'Spring update')

        detail = self.client.get(reverse('campaigns:detail', args=[campaign.pk]))
        self.assertContains(detail, 'ada@example.com')
        self.assertContains(detail, 'grace@example.com')
        self.assertContains(detail, campaign.get_status_display())

class UnsubscribeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _client_user('ada', 'ada@example.com')

    def test_token_roundtrip(self):
        token = unsubscribe_url_for(self.user).rsplit('/', 2)[-2]
        self.assertEqual(verify_unsubscribe_token(token), self.user.pk)

    def test_tampered_token_rejected(self):
        self.assertIsNone(verify_unsubscribe_token('bogus:token'))
        token = unsubscribe_url_for(self.user).rsplit('/', 2)[-2]
        self.assertIsNone(verify_unsubscribe_token(token + 'x'))

    def test_get_shows_confirmation_and_post_opts_out(self):
        token = unsubscribe_url_for(self.user).rsplit('/', 2)[-2]
        url = reverse('campaigns:unsubscribe', args=[token])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Unsubscribe')

        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.profile = UserProfile.objects.get(user=self.user)
        self.assertFalse(self.profile.marketing_emails_enabled)

        # Already unsubscribed on next GET.
        response = self.client.get(url)
        self.assertContains(response, 'Already unsubscribed')

    def test_invalid_token_returns_400(self):
        response = self.client.get(reverse('campaigns:unsubscribe', args=['bad:token']))
        self.assertEqual(response.status_code, 400)


class SettingsLimitsTests(TestCase):
    def test_max_recipients_limit_is_enforced(self):
        root = User.objects.create_superuser('root', 'root@example.com', 'Str0ng-Passw0rd!2026')
        for i in range(3):
            _client_user(f'u{i}', f'u{i}@example.com')
        campaign = Campaign.objects.create(
            name='Big', subject='S', body_text='B', audience=Campaign.AUDIENCE_ALL,
        )
        with override_settings(CAMPAIGN_MAX_RECIPIENTS=2):
            ok, error = start_send(campaign)
        self.assertFalse(ok)
        self.assertEqual(error, 'too_many_recipients')
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.STATUS_DRAFT)
        self.assertEqual(CampaignRecipient.objects.count(), 0)
