"""Tests for the Branding Service (wizard, dashboard, workflow)."""
import json

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import (
    BrandCollection,
    BrandingAsset,
    BrandingNotification,
    BrandingRequest,
    BrandingTimeline,
)


def make_collection(name='CloudPulse', category='saas'):
    return BrandCollection.objects.create(
        name=name,
        slug=name.lower().replace(' ', '-'),
        category=category,
        industry='SaaS Platform',
        description='A modern identity system.',
        style_tags=['Modern', 'Minimal'],
        examples=['Logo suite', 'Website'],
    )


def make_user(username='client', staff=False):
    return User.objects.create_user(username=username, password='pass1234', is_staff=staff)


class WizardTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.collection = make_collection()
        self.client.force_login(self.user)

    def test_landing_public(self):
        resp = self.client.get(reverse('branding:landing'))
        self.assertEqual(resp.status_code, 200)

    def test_wizard_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('branding:wizard'))
        self.assertEqual(resp.status_code, 302)

    def test_wizard_creates_draft(self):
        resp = self.client.get(reverse('branding:wizard'))
        self.assertRedirects(resp, reverse('branding:wizard_step', args=[1]))
        draft = BrandingRequest.objects.filter(user=self.user, status='DRAFT').first()
        self.assertIsNotNone(draft)
        self.assertEqual(draft.request_number[:3], 'BR-')

    def _submit_step(self, step, data, action='next'):
        return self.client.post(reverse('branding:wizard_step', args=[step]), {**data, 'action': action})

    def test_full_wizard_flow(self):
        # Step 1
        resp = self._submit_step(1, {
            'company_name': 'Nova Manufacturing',
            'industry': 'manufacturing',
            'website': 'https://nova.example.com',
            'country': 'United States',
            'business_description': 'We build precision parts.',
        })
        self.assertRedirects(resp, reverse('branding:wizard_step', args=[2]))

        # Step 1 validation
        resp = self._submit_step(1, {'company_name': '', 'industry': ''})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Company name is required.')

        # Step 2
        resp = self._submit_step(2, {
            'company_description': 'Precision manufacturing.',
            'target_audience': 'Industrial buyers',
            'brand_values': ['modern', 'bold'],
            'preferred_colors': ['blue', 'black'],
            'current_branding': ['logo', 'website'],
        })
        self.assertRedirects(resp, reverse('branding:wizard_step', args=[3]))

        # Step 3 (no files, just notes)
        resp = self._submit_step(3, {'additional_notes': 'Please include a favicon.'})
        self.assertRedirects(resp, reverse('branding:wizard_step', args=[4]))

        # Step 4 select collection (clamps back to step 4 as max)
        resp = self._submit_step(4, {'collection': str(self.collection.pk)})
        self.assertRedirects(resp, reverse('branding:wizard_step', args=[4]))
        resp = self.client.get(reverse('branding:wizard_step', args=[4]))
        self.assertContains(resp, self.collection.name)

        # Submit
        resp = self._submit_step(4, {'collection': str(self.collection.pk)}, action='submit')
        if resp.status_code != 302:
            body = resp.content.decode('utf-8')
            msgs = [m for m in ['Company name is required.', 'Please select an industry.', 'Please choose a brand collection to continue.'] if m in body]
            self.fail('submit not a redirect: %s errs=%r' % (resp.status_code, msgs))
        req = BrandingRequest.objects.get(user=self.user)
        self.assertEqual(req.status, 'PENDING_REVIEW')
        self.assertEqual(req.collection, self.collection)
        self.assertEqual(req.company_name, 'Nova Manufacturing')
        self.assertEqual(req.brand_values, ['modern', 'bold'])
        self.assertRedirects(resp, reverse('branding:submitted', args=[req.request_number]))

        # Submitted page shows request number, collection, status
        resp = self.client.get(reverse('branding:submitted', args=[req.request_number]))
        self.assertContains(resp, req.request_number)
        self.assertContains(resp, 'Pending Review')
        self.assertContains(resp, self.collection.name)

    def test_submit_requires_collection_and_company(self):
        # Missing company name -> error
        resp = self._submit_step(1, {'company_name': '', 'industry': ''}, action='submit')
        self.assertContains(resp, 'Company name is required.')

        draft = BrandingRequest.objects.create(user=self.user, status='DRAFT')
        draft.company_name = 'Nova'
        draft.industry = 'manufacturing'
        draft.save()
        resp = self.client.post(
            reverse('branding:wizard_step', args=[1]), {'action': 'submit'}
        )
        self.assertContains(resp, 'Please choose a brand collection')

    def test_prev_navigation(self):
        self._submit_step(1, {'company_name': 'Nova', 'industry': 'saas'})
        resp = self.client.post(
            reverse('branding:wizard_step', args=[2]),
            {'action': 'prev', 'company_description': 'x'},
        )
        self.assertRedirects(resp, reverse('branding:wizard_step', args=[1]))

    def test_back_navigation_preserves_data(self):
        """Going back must not wipe fields entered on earlier steps."""
        self._submit_step(1, {'company_name': 'Nova', 'industry': 'saas'})
        self.client.post(
            reverse('branding:wizard_step', args=[2]),
            {'action': 'next', 'company_description': 'We build tools.'},
        )
        self.client.post(
            reverse('branding:wizard_step', args=[3]),
            {'action': 'next', 'additional_notes': 'Brand refresh'},
        )
        resp = self.client.post(
            reverse('branding:wizard_step', args=[4]),
            {'action': 'prev'},
        )
        self.assertRedirects(resp, reverse('branding:wizard_step', args=[3]))
        draft = BrandingRequest.objects.get(user=self.user)
        self.assertEqual(draft.company_name, 'Nova')
        self.assertEqual(draft.company_description, 'We build tools.')
        self.assertEqual(draft.additional_notes, 'Brand refresh')

    def test_ajax_back_navigation(self):
        """AJAX back (what the swapped-in Back button sends) must work."""
        self._submit_step(1, {'company_name': 'Nova', 'industry': 'saas'})
        resp = self.client.post(
            reverse('branding:wizard_step', args=[2]),
            {'action': 'prev'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['ok'], True)
        self.assertEqual(resp.json()['redirect_url'], reverse('branding:wizard_step', args=[1]))

    def test_autosave(self):
        self.client.get(reverse('branding:wizard'))  # creates the draft
        draft = BrandingRequest.objects.get(user=self.user)
        resp = self.client.post(
            reverse('branding:wizard_autosave'),
            data=json.dumps({'step': 1, 'data': {'company_name': 'Auto Corp', 'industry': 'saas'}}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        draft.refresh_from_db()
        self.assertEqual(draft.company_name, 'Auto Corp')

    def test_upload_and_delete_asset(self):
        upload = SimpleUploadedFile(
            'logo.png', b'\x89PNG\r\n\x1a\n' + b'0' * 64, content_type='image/png'
        )
        resp = self.client.post(reverse('branding:upload_file'), {'file': upload})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['ok'])
        asset = BrandingAsset.objects.get(pk=data['id'])
        self.assertEqual(asset.asset_type, 'logo')

        # asset appears on step 3
        resp = self.client.get(reverse('branding:wizard_step', args=[3]))
        self.assertContains(resp, 'logo.png')

        resp = self.client.post(reverse('branding:delete_asset', args=[asset.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(BrandingAsset.objects.filter(pk=asset.pk).exists())

    def test_oversized_upload_rejected(self):
        big = SimpleUploadedFile('big.zip', b'0' * (51 * 1024 * 1024), content_type='application/zip')
        resp = self.client.post(reverse('branding:upload_file'), {'file': big})
        self.assertEqual(resp.status_code, 400)


class DashboardTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.staff = make_user('staff', staff=True)
        self.collection = make_collection()
        self.client.force_login(self.staff)
        self.req = BrandingRequest.objects.create(
            user=self.user,
            status='PENDING_REVIEW',
            company_name='Acme Corp',
            industry='finance',
            collection=self.collection,
        )

    def test_dashboard_requires_staff(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('branding:dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_dashboard_lists_requests(self):
        resp = self.client.get(reverse('branding:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Acme Corp')
        self.assertContains(resp, 'PENDING_REVIEW')

    def test_dashboard_status_filter(self):
        BrandingRequest.objects.create(
            user=self.user, status='COMPLETED', company_name='Done Co', industry='saas'
        )
        resp = self.client.get(reverse('branding:dashboard'), {'status': 'COMPLETED'})
        self.assertContains(resp, 'Done Co')
        self.assertNotContains(resp, 'Acme Corp')

    def test_detail_shows_tabs(self):
        resp = self.client.get(reverse('branding:request_detail', args=[self.req.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Company Information')
        self.assertContains(resp, 'Status History')

    def test_assign_designer_and_status(self):
        designer = make_user('designer', staff=True)
        resp = self.client.post(reverse('branding:assign_designer', args=[self.req.pk]), {'designer': designer.pk})
        self.assertRedirects(resp, reverse('branding:request_detail', args=[self.req.pk]))
        self.req.refresh_from_db()
        self.assertEqual(self.req.designer, designer)
        self.assertEqual(self.req.status, 'ASSIGNED')

        resp = self.client.post(reverse('branding:update_status', args=[self.req.pk]), {'status': 'DESIGNING'})
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'DESIGNING')

    def test_add_note_creates_timeline(self):
        self.client.post(reverse('branding:add_note', args=[self.req.pk]), {'note': 'Waiting on client'})
        self.assertTrue(
            BrandingTimeline.objects.filter(request=self.req, event_type='NOTE', action='Waiting on client').exists()
        )

    def test_archive(self):
        resp = self.client.post(reverse('branding:archive_request', args=[self.req.pk]))
        self.assertRedirects(resp, reverse('branding:dashboard'))
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'ARCHIVED')

    def test_edit_form(self):
        resp = self.client.post(
            reverse('branding:edit_request', args=[self.req.pk]),
            {
                'company_name': 'Acme Corp v2',
                'industry': 'saas',
                'website': '',
                'country': 'France',
                'business_description': 'Updated',
                'company_description': '',
                'target_audience': '',
                'brand_values': ['premium'],
                'preferred_colors': [],
                'current_branding': [],
                'additional_notes': '',
                'collection': str(self.collection.pk),
                'status': 'IN_REVIEW',
                'designer': '',
                'internal_notes': '',
            },
        )
        self.assertRedirects(resp, reverse('branding:request_detail', args=[self.req.pk]))
        self.req.refresh_from_db()
        self.assertEqual(self.req.company_name, 'Acme Corp v2')
        self.assertEqual(self.req.status, 'IN_REVIEW')

    def test_kanban_lists_columns(self):
        resp = self.client.get(reverse('branding:kanban'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Pending')
        self.assertContains(resp, 'Completed')

    def test_kanban_update_moves_status(self):
        resp = self.client.post(
            reverse('branding:kanban_update'),
            data=json.dumps({'request_id': self.req.pk, 'status': 'DESIGNING'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'DESIGNING')

    def test_kanban_update_rejects_bad_status(self):
        resp = self.client.post(
            reverse('branding:kanban_update'),
            data=json.dumps({'request_id': self.req.pk, 'status': 'NOT_A_STATUS'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_update_priority(self):
        resp = self.client.post(
            reverse('branding:update_priority', args=[self.req.pk]), {'priority': 'URGENT'}
        )
        self.assertRedirects(resp, reverse('branding:request_detail', args=[self.req.pk]))
        self.req.refresh_from_db()
        self.assertEqual(self.req.priority, 'URGENT')

    def test_update_delivery(self):
        resp = self.client.post(
            reverse('branding:update_delivery', args=[self.req.pk]),
            {'estimated_delivery_date': '2026-09-30'},
        )
        self.assertRedirects(resp, reverse('branding:request_detail', args=[self.req.pk]))
        self.req.refresh_from_db()
        self.assertEqual(self.req.estimated_delivery_date.isoformat(), '2026-09-30')

    def test_dashboard_priority_filter(self):
        resp = self.client.get(reverse('branding:dashboard'), {'priority': 'URGENT'})
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'Acme Corp')

    def test_notifications_and_mark_read(self):
        BrandingNotification.objects.create(
            recipient=self.staff,
            request=self.req,
            notification_type='NEW_REQUEST',
            message='Acme Corp submitted a request.',
        )
        resp = self.client.get(reverse('branding:notifications'))
        self.assertContains(resp, 'Acme Corp submitted a request.')

        note = BrandingNotification.objects.get(recipient=self.staff)
        resp = self.client.post(reverse('branding:mark_notification_read', args=[note.pk]))
        self.assertEqual(resp.status_code, 200)
        note.refresh_from_db()
        self.assertTrue(note.is_read)

    def test_replace_asset_snapshots_version_and_redirects(self):
        upload = SimpleUploadedFile(
            'logo.png', b'\x89PNG\r\n\x1a\n' + b'0' * 64, content_type='image/png'
        )
        asset = BrandingAsset.objects.create(
            request=self.req, file=upload, asset_type='logo', original_name='logo.png'
        )
        new_file = SimpleUploadedFile(
            'logo2.png', b'\x89PNG\r\n\x1a\n' + b'1' * 64, content_type='image/png'
        )
        resp = self.client.post(reverse('branding:replace_asset', args=[asset.pk]), {'file': new_file})
        self.assertRedirects(resp, reverse('branding:request_detail', args=[self.req.pk]))
        asset.refresh_from_db()
        self.assertEqual(asset.original_name, 'logo2.png')
        self.assertEqual(asset.versions.count(), 1)
        self.assertEqual(asset.versions.first().version_number, 1)
