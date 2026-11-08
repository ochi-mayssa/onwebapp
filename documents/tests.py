"""Tests for the document generation and e-signature app."""
import shutil
import os
import tempfile
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.models import Customer
from projects.models import Invoice as LegacyInvoice, Project, ProjectPhase

from .models import (
    BillingProfile,
    BillingProfileLineItem,
    Document,
    DocumentEmail,
    DocumentEvent,
    DocumentLineItem,
    DocumentSettings,
    DocumentSignature,
    DocumentType,
)
from .services import (
    accept_document,
    advance_billing_date,
    apply_client_signature,
    create_invoice_from_profile,
    generate_document_pdf,
    reject_document,
    run_due_billing_profiles,
    send_document,
)
from .tokens import TokenExpired, TokenInvalid, make_token, read_token

User = get_user_model()

LOCMEM_EMAIL = 'django.core.mail.backends.locmem.EmailBackend'


class DocumentTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='docadmin', email='admin@example.com', password='secret123',
            is_staff=True,
        )
        cls.client_user = User.objects.create_user(
            username='docclient', email='client@example.com', password='secret123',
            first_name='Casey', last_name='Client',
        )
        cls.other_user = User.objects.create_user(
            username='otherclient', email='other@example.com', password='secret123',
        )
        cls.customer = Customer.objects.create(
            name='Acme Industries',
            email='client@example.com',
            company_name='Acme Industries Ltd',
            business_address='1 Market Street',
            city='London',
            country='United Kingdom',
            user=cls.client_user,
        )

    def setUp(self):
        self._media_root = tempfile.mkdtemp()
        self._media_override = override_settings(
            MEDIA_ROOT=self._media_root,
            PRIVATE_MEDIA_ROOT=os.path.join(self._media_root, 'private'),
        )
        self._media_override.enable()
        self.addCleanup(self._media_override.disable)
        self.addCleanup(shutil.rmtree, self._media_root, True)

    def make_document(self, code='invoice', *, status=Document.STATUS_DRAFT,
                      quantity='2', unit_price='100', discount='50', tax_rate='10'):
        doc_type = DocumentType.objects.get(code=code)
        document = Document(
            doc_type=doc_type,
            customer=self.customer,
            issue_date='2026-01-10',
            currency='USD',
            discount_amount=Decimal(discount),
            tax_rate=Decimal(tax_rate),
            tax_label='VAT',
            status=status,
        )
        document.apply_client_snapshot()
        document.save()
        DocumentLineItem.objects.create(
            document=document,
            description='Design and build',
            quantity=Decimal(quantity),
            unit_price=Decimal(unit_price),
        )
        document.recalculate()
        document.refresh_from_db()
        return document


class DocumentModelTests(DocumentTestBase):
    def test_reference_and_totals(self):
        document = self.make_document()

        self.assertTrue(document.reference.startswith('INV-'))
        self.assertEqual(document.subtotal, Decimal('200.00'))
        self.assertEqual(document.tax_amount, Decimal('15.00'))
        self.assertEqual(document.total, Decimal('165.00'))
        self.assertEqual(document.client_name, 'Acme Industries')
        self.assertEqual(document.client_email, 'client@example.com')
        self.assertEqual(document.client_company, 'Acme Industries Ltd')
        self.assertIn('1 Market Street', document.client_address)
        self.assertEqual(document.client_user_id, self.client_user.pk)

    def test_reference_numbers_increment(self):
        first = self.make_document()
        second = self.make_document()
        self.assertNotEqual(first.reference, second.reference)

    def test_settings_singleton(self):
        first = DocumentSettings.load()
        second = DocumentSettings.load()
        self.assertEqual(first.pk, 1)
        self.assertEqual(second.pk, 1)

        DocumentSettings(pk=9, company_name='Overridden').save()
        self.assertEqual(DocumentSettings.objects.count(), 1)
        self.assertEqual(DocumentSettings.load().company_name, 'Overridden')

    def test_document_visibility(self):
        document = self.make_document(status=Document.STATUS_SENT)
        self.assertTrue(document.is_visible_to(self.client_user))
        self.assertTrue(document.is_visible_to(self.admin))
        self.assertFalse(document.is_visible_to(self.other_user))
        self.assertFalse(document.is_visible_to(None))

    def test_overdue_only_for_unpaid_invoices(self):
        document = self.make_document(status=Document.STATUS_SENT)
        document.due_date = '2020-01-01'
        document.save(update_fields=['due_date'])
        document.refresh_from_db()
        self.assertTrue(document.is_overdue)
        self.assertEqual(document.display_status, Document.STATUS_OVERDUE)


class PdfTests(DocumentTestBase):
    def test_generate_pdf(self):
        document = self.make_document()
        pdf_bytes = generate_document_pdf(document, actor=self.admin)
        document.refresh_from_db()

        self.assertTrue(pdf_bytes.startswith(b'%PDF'))
        self.assertEqual(len(document.pdf_sha256), 64)
        self.assertTrue(document.pdf_file.name.endswith('.pdf'))
        self.assertIn(os.path.join('private', 'documents', 'pdfs'), document.pdf_file.path)
        self.assertTrue(document.pdf_generated_at)
        self.assertTrue(
            document.events.filter(event=DocumentEvent.EVENT_GENERATED).exists()
        )
        with document.pdf_file.open('rb') as handle:
            self.assertEqual(handle.read(4), b'%PDF')


@override_settings(EMAIL_BACKEND=LOCMEM_EMAIL)
class SendTests(DocumentTestBase):
    def test_send_records_email_and_status(self):
        document = self.make_document()

        sent = send_document(document, actor=self.admin)
        document.refresh_from_db()

        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['client@example.com'])
        self.assertIn(document.reference, message.subject)

        attachment_names = [name for name, _content, _mime in message.attachments]
        self.assertIn(f'{document.reference}.pdf', attachment_names)
        pdf_attachment = next(
            content for name, content, _mime in message.attachments
            if name == f'{document.reference}.pdf'
        )
        self.assertTrue(bytes(pdf_attachment).startswith(b'%PDF'))

        record = DocumentEmail.objects.get(document=document)
        self.assertEqual(record.status, DocumentEmail.STATUS_SENT)
        self.assertEqual(record.to_email, 'client@example.com')
        self.assertEqual(document.status, Document.STATUS_SENT)
        self.assertIsNotNone(document.sent_at)
        self.assertTrue(
            document.events.filter(event=DocumentEvent.EVENT_SENT).exists()
        )

    def test_resend_is_flagged(self):
        document = self.make_document()
        send_document(document, actor=self.admin)
        send_document(document, actor=self.admin)

        self.assertEqual(document.emails.count(), 2)
        self.assertTrue(document.emails.order_by('created_at').last().is_resend)
        self.assertTrue(
            document.events.filter(event=DocumentEvent.EVENT_RESENT).exists()
        )


class ResponseTests(DocumentTestBase):
    def test_accept_quotation(self):
        document = self.make_document(code='quotation', status=Document.STATUS_SENT)

        accept_document(document, name='Casey Client')
        document.refresh_from_db()

        self.assertEqual(document.status, Document.STATUS_ACCEPTED)
        self.assertEqual(document.accepted_by_name, 'Casey Client')
        self.assertIsNotNone(document.accepted_at)
        self.assertTrue(
            document.events.filter(event=DocumentEvent.EVENT_ACCEPTED).exists()
        )

    def test_reject_quotation_records_reason(self):
        document = self.make_document(code='quotation', status=Document.STATUS_SENT)

        reject_document(document, reason='Budget too high')
        document.refresh_from_db()

        self.assertEqual(document.status, Document.STATUS_REJECTED)
        self.assertEqual(document.rejected_reason, 'Budget too high')
        event = document.events.get(event=DocumentEvent.EVENT_REJECTED)
        self.assertIn('Budget too high', event.note)

    def test_invoice_cannot_be_accepted(self):
        document = self.make_document(code='invoice', status=Document.STATUS_SENT)
        with self.assertRaises(ValueError):
            accept_document(document)

    def test_contract_signature_records_audit(self):
        document = self.make_document(code='contract', status=Document.STATUS_SENT)

        signature = apply_client_signature(
            document,
            signer_name='Casey Client',
            signer_email='client@example.com',
            signer_role='Director',
            typed_signature='Casey Client',
            consent_text='I agree that this is my electronic signature.',
        )
        document.refresh_from_db()
        signature.refresh_from_db()

        self.assertEqual(document.status, Document.STATUS_SIGNED)
        self.assertEqual(document.latest_signature.pk, signature.pk)
        self.assertEqual(signature.document_version, document.version)
        self.assertEqual(signature.signer_role, 'Director')
        self.assertEqual(len(signature.pdf_sha256), 64)
        self.assertEqual(signature.pdf_sha256, document.pdf_sha256)
        self.assertTrue(
            document.events.filter(event=DocumentEvent.EVENT_SIGNED).exists()
        )

    def test_company_signature_alone_does_not_mark_signed(self):
        document = self.make_document(code='contract', status=Document.STATUS_SENT)
        generate_document_pdf(document)
        document.refresh_from_db()

        self.assertEqual(document.status, Document.STATUS_SENT)
        self.assertFalse(document.is_client_signed)
        self.assertFalse(DocumentSignature.objects.filter(document=document).exists())


class PermissionAndViewTests(DocumentTestBase):
    def test_client_can_view_own_document(self):
        document = self.make_document(status=Document.STATUS_SENT)
        self.client.force_login(self.client_user)

        response = self.client.get(reverse('documents:client_detail', args=[document.pk]))
        self.assertEqual(response.status_code, 200)
        document.refresh_from_db()
        self.assertEqual(document.status, Document.STATUS_VIEWED)

    def test_client_cannot_view_another_document(self):
        document = self.make_document(status=Document.STATUS_SENT)
        self.client.force_login(self.other_user)

        response = self.client.get(reverse('documents:client_detail', args=[document.pk]))
        self.assertEqual(response.status_code, 403)

    def test_client_cannot_view_draft_document(self):
        document = self.make_document(status=Document.STATUS_DRAFT)
        self.client.force_login(self.client_user)

        response = self.client.get(reverse('documents:client_detail', args=[document.pk]))
        self.assertEqual(response.status_code, 403)

    def test_non_admin_cannot_open_admin_list(self):
        self.client.force_login(self.client_user)
        response = self.client.get(reverse('documents:admin_list'))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_open_admin_list(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('documents:admin_list'))
        self.assertEqual(response.status_code, 200)

    def test_admin_pages_render(self):
        document = self.make_document(status=Document.STATUS_SENT)
        self.client.force_login(self.admin)
        pages = [
            ('admin_list', []),
            ('admin_create', []),
            ('admin_detail', [document.pk]),
            ('admin_edit', [document.pk]),
            ('admin_preview', [document.pk]),
            ('settings', []),
        ]
        for name, args in pages:
            with self.subTest(page=name):
                response = self.client.get(reverse(f'documents:{name}', args=args))
                self.assertEqual(response.status_code, 200)

    def test_sign_and_public_pages_render(self):
        contract = self.make_document(code='contract', status=Document.STATUS_SENT)
        self.client.force_login(self.client_user)
        response = self.client.get(reverse('documents:client_sign', args=[contract.pk]))
        self.assertEqual(response.status_code, 200)

        token = make_token(contract)
        self.client.logout()
        response = self.client.get(reverse('documents:public_sign', args=[token]))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('documents:public_view', args=[token]))
        self.assertEqual(response.status_code, 200)

    def test_invalid_link_shows_error_page(self):
        response = self.client.get(reverse('documents:public_view', args=['invalid-token']))
        self.assertEqual(response.status_code, 410)
        self.assertContains(response, 'This link cannot be used', status_code=410)

    def test_admin_create_document_via_form(self):
        self.client.force_login(self.admin)
        invoice_type = DocumentType.objects.get(code='invoice')
        data = {
            'doc_type': invoice_type.pk,
            'customer': self.customer.pk,
            'issue_date': '2026-02-01',
            'currency': 'USD',
            'tax_label': 'VAT',
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-description': 'Consulting',
            'items-0-details': '',
            'items-0-quantity': '3',
            'items-0-unit_price': '125.00',
        }
        response = self.client.post(reverse('documents:admin_create'), data)
        self.assertEqual(response.status_code, 302)

        document = Document.objects.latest('pk')
        self.assertEqual(document.total, Decimal('375.00'))
        self.assertEqual(document.client_email, 'client@example.com')

    def test_public_token_view_marks_viewed(self):
        document = self.make_document(status=Document.STATUS_SENT)
        token = make_token(document)

        response = self.client.get(reverse('documents:public_view', args=[token]))
        self.assertEqual(response.status_code, 200)
        document.refresh_from_db()
        self.assertEqual(document.status, Document.STATUS_VIEWED)

    def test_public_download_returns_pdf(self):
        document = self.make_document(status=Document.STATUS_SENT)
        token = make_token(document)

        response = self.client.get(reverse('documents:public_download', args=[token]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))


class TokenTests(DocumentTestBase):
    def test_round_trip(self):
        document = self.make_document()
        token = make_token(document)
        self.assertEqual(read_token(token).pk, document.pk)

    def test_invalid_token(self):
        with self.assertRaises(TokenInvalid):
            read_token('not-a-real-token')

    def test_expired_token(self):
        document = self.make_document()
        token = make_token(document)
        with override_settings(DOCUMENT_LINK_MAX_AGE=-1):
            with self.assertRaises(TokenExpired):
                read_token(token)

    def test_token_bound_to_version(self):
        document = self.make_document()
        token = make_token(document)
        document.version += 1
        document.save(update_fields=['version'])
        with self.assertRaises(TokenInvalid):
            read_token(token)


class InvoiceAutomationTests(DocumentTestBase):
    def make_profile(self, **overrides):
        invoice_type = DocumentType.objects.get(code='invoice')
        values = {
            'name': 'Standard billing',
            'customer': self.customer,
            'doc_type': invoice_type,
            'trigger': BillingProfile.TRIGGER_PROJECT_CREATED,
            'frequency': BillingProfile.FREQUENCY_ONE_OFF,
            'pricing_mode': BillingProfile.PRICING_FIXED,
            'default_description': 'Professional services',
            'default_amount': Decimal('500.00'),
            'currency': 'USD',
            'due_days': 14,
        }
        values.update(overrides)
        return BillingProfile.objects.create(**values)

    def make_project(self, title='Website build'):
        return Project.objects.create(
            client=self.client_user,
            title=title,
            description='Build a website',
        )

    def make_phase(self, project, phase_type='DESIGN', status='NOT_STARTED'):
        return ProjectPhase.objects.create(
            project=project,
            phase_type=phase_type,
            status=status,
            approval_status='NOT_REQUIRED',
        )

    def test_create_invoice_from_profile_is_idempotent(self):
        profile = self.make_profile(trigger=BillingProfile.TRIGGER_RECURRING)
        BillingProfileLineItem.objects.create(
            profile=profile,
            description='Hosting',
            quantity=Decimal('2'),
            unit_price=Decimal('25.00'),
        )

        document, created = create_invoice_from_profile(
            profile, automation_key='test-key-1',
        )
        duplicate, created_again = create_invoice_from_profile(
            profile, automation_key='test-key-1',
        )

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(document.pk, duplicate.pk)
        self.assertEqual(document.status, Document.STATUS_DRAFT)
        self.assertEqual(document.subtotal, Decimal('50.00'))
        self.assertEqual(document.total, Decimal('50.00'))
        self.assertEqual(document.items.count(), 1)
        self.assertEqual(document.billing_profile, profile)
        self.assertTrue(
            document.events.filter(event=DocumentEvent.EVENT_CREATED).exists()
        )
        profile.refresh_from_db()
        self.assertEqual(profile.last_document_id, document.pk)

    def test_advance_billing_date_clamps_month_end(self):
        self.assertEqual(advance_billing_date(date(2026, 1, 31), 'MONTHLY'), date(2026, 2, 28))
        self.assertEqual(advance_billing_date(date(2026, 1, 31), 'QUARTERLY'), date(2026, 4, 30))
        self.assertEqual(advance_billing_date(date(2024, 2, 29), 'YEARLY'), date(2025, 2, 28))

    def test_project_created_signal_creates_one_draft(self):
        profile = self.make_profile()
        with self.captureOnCommitCallbacks(execute=True):
            project = self.make_project()

        document = Document.objects.get(billing_profile=profile)
        self.assertEqual(document.status, Document.STATUS_DRAFT)
        self.assertEqual(document.project_id, project.pk)
        self.assertEqual(document.total, Decimal('500.00'))
        self.assertEqual(document.automation_key, f'project-created:{project.pk}:{profile.pk}')
        self.assertIn(project.title, document.title)

        # A second save of the same project must not create another invoice.
        with self.captureOnCommitCallbacks(execute=True):
            project.title = 'Website build (renamed)'
            project.save(update_fields=['title'])
        self.assertEqual(Document.objects.filter(billing_profile=profile).count(), 1)

    def test_project_completed_signal_triggers_once(self):
        profile = self.make_profile(trigger=BillingProfile.TRIGGER_PROJECT_COMPLETED)
        with self.captureOnCommitCallbacks(execute=True):
            project = self.make_project()
        self.assertFalse(Document.objects.filter(billing_profile=profile).exists())

        with self.captureOnCommitCallbacks(execute=True):
            project.current_status = 'COMPLETED'
            project.save(update_fields=['current_status'])

        document = Document.objects.get(billing_profile=profile)
        self.assertEqual(document.project_id, project.pk)
        self.assertEqual(document.automation_key, f'project-completed:{project.pk}:{profile.pk}')

        with self.captureOnCommitCallbacks(execute=True):
            project.current_status = 'COMPLETED'
            project.save(update_fields=['current_status'])
        self.assertEqual(Document.objects.filter(billing_profile=profile).count(), 1)

    def test_phase_completed_signal_respects_phase_type(self):
        profile = self.make_profile(
            trigger=BillingProfile.TRIGGER_PHASE_COMPLETED,
            phase_type='DESIGN',
        )
        with self.captureOnCommitCallbacks(execute=True):
            project = self.make_project()
            other_phase = self.make_phase(project, phase_type='DEVELOPMENT')
        self.assertFalse(Document.objects.filter(billing_profile=profile).exists())

        with self.captureOnCommitCallbacks(execute=True):
            other_phase.status = 'COMPLETED'
            other_phase.save(update_fields=['status'])
        self.assertFalse(Document.objects.filter(billing_profile=profile).exists())

        with self.captureOnCommitCallbacks(execute=True):
            design_phase = self.make_phase(project, phase_type='DESIGN', status='COMPLETED')
        self.assertTrue(Document.objects.filter(billing_profile=profile).exists())

        with self.captureOnCommitCallbacks(execute=True):
            design_phase.approval_status = 'APPROVED'
            design_phase.save(update_fields=['approval_status'])
        self.assertEqual(Document.objects.filter(billing_profile=profile).count(), 1)

    def test_recurring_run_creates_and_advances(self):
        profile = self.make_profile(
            trigger=BillingProfile.TRIGGER_RECURRING,
            frequency=BillingProfile.FREQUENCY_MONTHLY,
            next_invoice_date=date(2026, 1, 1),
        )

        summary = run_due_billing_profiles(today=date(2026, 1, 15))
        self.assertEqual(summary['created'], 1)
        document = Document.objects.get(billing_profile=profile)
        self.assertEqual(document.billing_period_start, date(2026, 1, 1))
        self.assertEqual(document.billing_period_end, date(2026, 1, 31))
        self.assertEqual(document.automation_key, f'recurring:{profile.pk}:2026-01-01')

        profile.refresh_from_db()
        self.assertEqual(profile.next_invoice_date, date(2026, 2, 1))

        # Running again before the next period is due is a no-op.
        summary = run_due_billing_profiles(today=date(2026, 1, 20))
        self.assertEqual(summary['created'], 0)
        self.assertEqual(Document.objects.filter(billing_profile=profile).count(), 1)

        # The next period creates a second invoice with its own key.
        summary = run_due_billing_profiles(today=date(2026, 2, 2))
        self.assertEqual(summary['created'], 1)
        self.assertEqual(Document.objects.filter(billing_profile=profile).count(), 2)

    def test_recurring_skips_customer_without_email_and_advances(self):
        profile = self.make_profile(
            trigger=BillingProfile.TRIGGER_RECURRING,
            frequency=BillingProfile.FREQUENCY_MONTHLY,
            next_invoice_date=date(2026, 1, 1),
        )
        self.customer.email = ''
        self.customer.save(update_fields=['email'])

        summary = run_due_billing_profiles(today=date(2026, 1, 5))

        self.assertEqual(summary['failed'], 1)
        self.assertFalse(Document.objects.filter(billing_profile=profile).exists())
        profile.refresh_from_db()
        self.assertEqual(profile.next_invoice_date, date(2026, 2, 1))

    @override_settings(EMAIL_BACKEND=LOCMEM_EMAIL)
    def test_auto_send_emails_invoice(self):
        profile = self.make_profile(auto_send=True)

        document, created = create_invoice_from_profile(profile)

        self.assertTrue(created)
        document.refresh_from_db()
        self.assertEqual(document.status, Document.STATUS_SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['client@example.com'])
        self.assertEqual(document.emails.get().status, DocumentEmail.STATUS_SENT)

    def test_legacy_project_invoice_signal_is_disabled(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.make_project()

        self.assertFalse(LegacyInvoice.objects.exists())

    def test_billing_ui_permissions_and_manual_generation(self):
        profile = self.make_profile()

        self.client.force_login(self.client_user)
        response = self.client.get(reverse('documents:billing_list'))
        self.assertEqual(response.status_code, 403)
        self.client.logout()

        self.client.force_login(self.admin)
        response = self.client.get(reverse('documents:billing_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invoice automation')
        response = self.client.get(reverse('documents:billing_create'))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('documents:billing_generate', args=[profile.pk]))
        self.assertEqual(response.status_code, 302)
        document = Document.objects.get(billing_profile=profile)
        self.assertEqual(document.status, Document.STATUS_DRAFT)

    def test_billing_rule_created_through_form(self):
        self.client.force_login(self.admin)
        invoice_type = DocumentType.objects.get(code='invoice')
        data = {
            'name': 'Monthly retainer',
            'customer': self.customer.pk,
            'project': '',
            'doc_type': invoice_type.pk,
            'trigger': BillingProfile.TRIGGER_RECURRING,
            'frequency': BillingProfile.FREQUENCY_MONTHLY,
            'phase_type': '',
            'pricing_mode': BillingProfile.PRICING_ITEMIZED,
            'default_description': 'Retainer',
            'default_amount': '0.00',
            'title_template': 'Invoice for {project}',
            'currency': 'usd',
            'discount_amount': '0.00',
            'tax_rate': '0.00',
            'tax_label': 'VAT',
            'due_days': '14',
            'notes': '',
            'terms': '',
            'is_active': 'on',
            'next_invoice_date': '2026-01-01',
            'line_items-TOTAL_FORMS': '1',
            'line_items-INITIAL_FORMS': '0',
            'line_items-MIN_NUM_FORMS': '0',
            'line_items-MAX_NUM_FORMS': '1000',
            'line_items-0-description': 'Retainer',
            'line_items-0-details': '',
            'line_items-0-quantity': '1',
            'line_items-0-unit_price': '750.00',
        }
        response = self.client.post(reverse('documents:billing_create'), data)
        self.assertEqual(response.status_code, 302)

        profile = BillingProfile.objects.get(name='Monthly retainer')
        self.assertEqual(profile.currency, 'USD')
        self.assertEqual(profile.line_items.count(), 1)
        self.assertEqual(profile.next_invoice_date, date(2026, 1, 1))

    def test_management_command_creates_due_invoice(self):
        profile = self.make_profile(
            trigger=BillingProfile.TRIGGER_RECURRING,
            frequency=BillingProfile.FREQUENCY_MONTHLY,
            next_invoice_date=date(2026, 1, 1),
        )

        call_command('generate_due_invoices', date='2026-01-15', verbosity=0)

        self.assertTrue(Document.objects.filter(billing_profile=profile).exists())
        profile.refresh_from_db()
        self.assertEqual(profile.next_invoice_date, date(2026, 2, 1))
