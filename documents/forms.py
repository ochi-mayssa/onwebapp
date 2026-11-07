"""Forms for creating documents and configuring company signature assets."""
from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.utils import timezone
from decimal import Decimal

from crm.models import Customer

from .models import Document, DocumentLineItem, DocumentSettings, DocumentSignature

TEXT_INPUT = {'class': 'form-control'}
SELECT = {'class': 'form-select'}


def _validate_png(upload):
    if not upload:
        return upload
    name = getattr(upload, 'name', '')
    if not name.lower().endswith('.png'):
        raise ValidationError('Upload a PNG file (transparent background recommended).')
    if upload.size > 2 * 1024 * 1024:
        raise ValidationError('The image must be smaller than 2 MB.')
    try:
        from PIL import Image
        Image.open(upload).verify()
    except Exception as exc:
        raise ValidationError('This file is not a readable image.') from exc
    finally:
        try:
            upload.seek(0)
        except Exception:
            pass
    return upload


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = [
            'doc_type', 'customer', 'project', 'source_invoice', 'title',
            'issue_date', 'due_date', 'valid_until', 'currency',
            'discount_amount', 'tax_rate', 'tax_label', 'notes', 'terms',
        ]
        widgets = {
            'issue_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'valid_until': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'terms': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 3}),
            'discount_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'tax_label': forms.TextInput(attrs={'class': 'form-control'}),
            'doc_type': forms.Select(attrs=SELECT),
            'customer': forms.Select(attrs=SELECT),
            'project': forms.Select(attrs=SELECT),
            'source_invoice': forms.Select(attrs=SELECT),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.select_related('user').order_by('name')
        self.fields['customer'].empty_label = 'Select a CRM customer'
        self.fields['customer'].required = True
        self.fields['customer'].help_text = 'Client name, company and email are copied from the CRM profile.'
        self.fields['project'].required = False
        self.fields['source_invoice'].required = False
        self.fields['due_date'].required = False
        self.fields['valid_until'].required = False
        self.fields['discount_amount'].required = False
        self.fields['tax_rate'].required = False
        if not self.instance.pk:
            cfg = DocumentSettings.load()
            if not self.initial.get('terms'):
                self.initial['terms'] = cfg.default_payment_terms
            if not self.initial.get('issue_date'):
                self.initial['issue_date'] = timezone.localdate()

    def clean(self):
        cleaned = super().clean()
        issue = cleaned.get('issue_date')
        due = cleaned.get('due_date')
        valid = cleaned.get('valid_until')
        if issue and due and due < issue:
            self.add_error('due_date', 'The due date cannot be earlier than the issue date.')
        if issue and valid and valid < issue:
            self.add_error('valid_until', 'The validity date cannot be earlier than the issue date.')
        currency = (cleaned.get('currency') or '').upper()
        if currency:
            cleaned['currency'] = currency
        for field in ('discount_amount', 'tax_rate'):
            if cleaned.get(field) is None:
                cleaned[field] = Decimal('0.00')
        return cleaned


class DocumentLineItemForm(forms.ModelForm):
    class Meta:
        model = DocumentLineItem
        fields = ['description', 'details', 'quantity', 'unit_price']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Service or product'}),
            'details': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional detail'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        }


DocumentLineItemFormSet = inlineformset_factory(
    Document,
    DocumentLineItem,
    form=DocumentLineItemForm,
    extra=3,
    can_delete=True,
    min_num=0,
    validate_min=False,
)


class DocumentSettingsForm(forms.ModelForm):
    class Meta:
        model = DocumentSettings
        fields = [
            'company_name', 'company_legal_name', 'company_address', 'company_email',
            'company_phone', 'company_website', 'company_tax_id', 'registration_note',
            'signatory_name', 'signatory_position', 'signature_image', 'stamp_image',
            'accent_color', 'default_payment_terms', 'default_validity_days',
            'bank_details', 'footer_note',
        ]
        widgets = {
            'company_address': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'default_payment_terms': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'bank_details': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'accent_color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color'}),
            'signature_image': forms.ClearableFileInput(attrs={'accept': 'image/png', 'class': 'form-control'}),
            'stamp_image': forms.ClearableFileInput(attrs={'accept': 'image/png', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name in {'signature_image', 'stamp_image', 'accent_color'}:
                continue
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault('class', 'form-select')
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', 'form-check-input')
            else:
                field.widget.attrs.setdefault('class', 'form-control')

    def clean_signature_image(self):
        return _validate_png(self.cleaned_data.get('signature_image'))

    def clean_stamp_image(self):
        return _validate_png(self.cleaned_data.get('stamp_image'))


class ClientSignatureForm(forms.Form):
    signer_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your full legal name'}),
    )
    signer_email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
    )
    signer_role = forms.CharField(
        max_length=120, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Director'}),
    )
    typed_signature = forms.CharField(
        max_length=200, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Type your name as your signature'}),
    )
    signature_image = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={'accept': 'image/png', 'class': 'form-control'}),
    )
    consent = forms.BooleanField(
        label='I agree that my typed name and uploaded image constitute my electronic signature.',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def clean_signature_image(self):
        return _validate_png(self.cleaned_data.get('signature_image'))

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('typed_signature') and not cleaned.get('signature_image'):
            raise ValidationError('Type your name or upload a signature image to sign.')
        return cleaned
