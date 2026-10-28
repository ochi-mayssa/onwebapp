from django import forms
from django.contrib.auth import get_user_model
from .models import ConsultationRequest, WebsiteBuildRequest, APIRequest, RPAConsultationRequest

User = get_user_model()

class ConsultationForm(forms.ModelForm):
    class Meta:
        model = ConsultationRequest
        fields = ['name', 'email', 'company', 'topic', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Your Email'}),
            'company': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company Name (Optional)'}),
            'topic': forms.Select(attrs={'class': 'form-select'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'How can we help you?'}),
        }

class WebsiteBuildForm(forms.ModelForm):
    class Meta:
        model = WebsiteBuildRequest
        fields = ['name', 'email', 'company', 'website_type', 'features', 'budget', 'timeline', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'company': forms.TextInput(attrs={'class': 'form-control'}),
            'website_type': forms.Select(attrs={'class': 'form-select'}),
            'features': forms.CheckboxSelectMultiple(),
            'budget': forms.Select(attrs={'class': 'form-select'}),
            'timeline': forms.Select(attrs={'class': 'form-select'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }


class APIRequestForm(forms.ModelForm):
    class Meta:
        model = APIRequest
        fields = [
            'full_name', 'business_email', 'company_name', 'request_type',
            'api_name_or_category', 'use_case', 'required_features',
            'expected_usage', 'budget_range', 'additional_requirements',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Full Name',
                'autocomplete': 'name', 'autofocus': True,
            }),
            'business_email': forms.EmailInput(attrs={
                'class': 'form-control', 'placeholder': 'you@company.com',
                'autocomplete': 'email',
                'aria-describedby': 'id_business_email-help',
            }),
            'company_name': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Company Name (Optional)',
                'autocomplete': 'organization',
            }),
            'request_type': forms.Select(attrs={
                'class': 'form-select',
                'aria-describedby': 'id_request_type-help',
            }),
            'api_name_or_category': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Payments API, SEO data, custom invoicing API',
                'aria-describedby': 'id_api_name_or_category-help id_api_name_or_category-hint3p',
            }),
            'use_case': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 4,
                'placeholder': 'What do you want to achieve with this API?',
                'aria-describedby': 'id_use_case-help id_use_case-counter',
            }),
            'required_features': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Describe the functionality you need',
                'aria-describedby': 'id_required_features-help id_required_features-counter',
            }),
            'expected_usage': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. ~10,000 requests/day (Optional)',
                'aria-describedby': 'id_expected_usage-help',
            }),
            'budget_range': forms.Select(attrs={
                'class': 'form-select',
                'aria-describedby': 'id_budget_range-help',
            }),
            'additional_requirements': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Any other requirements? (Optional)',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['budget_range'].choices = [('', 'Prefer not to say')] + list(APIRequest.BUDGET_CHOICES)
        # Mark errored fields for styling and assistive tech.
        for name, field in self.fields.items():
            if self.errors.get(name):
                css = field.widget.attrs.get('class', '')
                if 'is-invalid' not in css:
                    field.widget.attrs['class'] = f'{css} is-invalid'.strip()
                field.widget.attrs['aria-invalid'] = 'true'


class APIRequestAdminActionForm(forms.ModelForm):
    """Staff-only management form used on the custom admin API requests page."""

    class Meta:
        model = APIRequest
        fields = ['status', 'assigned_to', 'internal_notes', 'is_archived']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'internal_notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Staff-only notes — never shown to the client.',
            }),
            'is_archived': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = User.objects.filter(
            is_staff=True, is_active=True,
        ).order_by('username')
        self.fields['assigned_to'].required = False
        self.fields['assigned_to'].empty_label = '— Unassigned —'


class RPAConsultationForm(forms.ModelForm):
    """Public consultation form for the RPA solutions landing page."""

    class Meta:
        model = RPAConsultationRequest
        fields = [
            'full_name', 'business_email', 'company_name', 'current_tools',
            'process_to_automate', 'task_frequency', 'time_spent',
            'additional_requirements',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'rpaf-control', 'placeholder': 'Full Name',
                'autocomplete': 'name', 'autofocus': True,
            }),
            'business_email': forms.EmailInput(attrs={
                'class': 'rpaf-control', 'placeholder': 'you@company.com',
                'autocomplete': 'email',
            }),
            'company_name': forms.TextInput(attrs={
                'class': 'rpaf-control', 'placeholder': 'Company Name (Optional)',
                'autocomplete': 'organization',
            }),
            'current_tools': forms.TextInput(attrs={
                'class': 'rpaf-control',
                'placeholder': 'e.g. Excel, SAP, an internal web portal',
            }),
            'process_to_automate': forms.Textarea(attrs={
                'class': 'rpaf-control', 'rows': 4,
                'placeholder': 'Describe the repetitive process you want automated',
            }),
            'task_frequency': forms.Select(attrs={'class': 'rpaf-control'}),
            'time_spent': forms.TextInput(attrs={
                'class': 'rpaf-control',
                'placeholder': 'e.g. about 6 hours a week (Optional)',
            }),
            'additional_requirements': forms.Textarea(attrs={
                'class': 'rpaf-control', 'rows': 3,
                'placeholder': 'Any other requirements? (Optional)',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company_name'].required = False
        self.fields['task_frequency'].required = False
        self.fields['task_frequency'].choices = [('', 'Select how often…')] + list(
            RPAConsultationRequest.FREQUENCY_CHOICES
        )
        self.fields['time_spent'].required = False
        self.fields['additional_requirements'].required = False
        # Mark errored fields for styling and assistive tech.
        for name, field in self.fields.items():
            if self.errors.get(name):
                css = field.widget.attrs.get('class', '')
                if 'is-invalid' not in css:
                    field.widget.attrs['class'] = f'{css} is-invalid'.strip()
                field.widget.attrs['aria-invalid'] = 'true'

    def clean_business_email(self):
        return (self.cleaned_data.get('business_email') or '').strip().lower()

    def clean_current_tools(self):
        return (self.cleaned_data.get('current_tools') or '').strip()

    def clean_process_to_automate(self):
        value = (self.cleaned_data.get('process_to_automate') or '').strip()
        if len(value) < 15:
            raise forms.ValidationError(
                'Please describe the process in a little more detail (at least 15 characters).'
            )
        return value
