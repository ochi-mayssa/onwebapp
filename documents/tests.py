"""Tests for the document generation and e-signature app."""
import shutil
import os
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.models import Customer

from .models import (
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
    apply_client_signature,
    generate_document_pdf,
    reject_document,
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
