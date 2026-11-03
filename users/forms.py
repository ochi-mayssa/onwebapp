from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import UserProfile


class SignUpForm(UserCreationForm):
    """Extended user creation form with email field."""
    email = forms.EmailField(
        max_length=254,
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': _('your@email.com')
        })
    )
    username = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('username')
        })
    )
    password1 = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': _('Enter password')
        })
    )
    password2 = forms.CharField(
        label=_('Confirm Password'),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': _('Confirm password')
        })
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def clean_email(self):
        """Validate that email is unique."""
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError(_('An account with this email already exists.'))
        return email

    def clean_username(self):
        """Validate username is unique."""
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise ValidationError(_('This username is already taken.'))
        return username

    def save(self, commit=True):
        """Save user with email."""
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class OnboardingForm(forms.ModelForm):
    """First-run onboarding: path, services, goal, timeline and profile details."""

    COMMUNITY_NEED_CHOICES = UserProfile.COMMUNITY_NEED_CHOICES

    # Stored manually into the JSONField so the model shape stays unchanged.
    community_needs_selection = forms.MultipleChoiceField(
        choices=UserProfile.COMMUNITY_NEED_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
        label=_("Which services do you need?"),
    )

    class Meta:
        model = UserProfile
        fields = [
            'service_type', 'community_needs_selection',
            'project_description', 'start_timeline',
            'display_name', 'phone_number', 'company_name', 'job_title',
            'country', 'city', 'website', 'industry', 'company_size',
            'business_address',
        ]
        widgets = {
            'service_type': forms.RadioSelect(attrs={'class': 'form-check-input'}),
            'project_description': forms.RadioSelect(attrs={'class': 'form-check-input'}),
            'start_timeline': forms.RadioSelect(attrs={'class': 'form-check-input'}),
            'display_name': forms.TextInput(attrs={
                'class': 'form-control', 'autocomplete': 'name',
                'placeholder': _('Your full name'),
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control', 'autocomplete': 'tel',
                'placeholder': _('+1 555 000 0000'),
            }),
            'company_name': forms.TextInput(attrs={
                'class': 'form-control', 'autocomplete': 'organization',
                'placeholder': _('Company or project name'),
            }),
            'job_title': forms.TextInput(attrs={
                'class': 'form-control', 'autocomplete': 'organization-title',
                'placeholder': _('e.g. Founder, Marketing Lead'),
            }),
            'country': forms.TextInput(attrs={
                'class': 'form-control', 'autocomplete': 'country-name',
                'placeholder': _('Country'),
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-control', 'autocomplete': 'address-level2',
                'placeholder': _('City'),
            }),
            'website': forms.URLInput(attrs={
                'class': 'form-control', 'autocomplete': 'url',
                'placeholder': _('https://your-website.com'),
            }),
            'industry': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('e.g. Technology, Retail, Healthcare'),
            }),
            'company_size': forms.Select(attrs={'class': 'form-select'}),
            'business_address': forms.TextInput(attrs={
                'class': 'form-control', 'autocomplete': 'street-address',
                'placeholder': _('Street, building, suite'),
            }),
        }
        labels = {
            'service_type': _('Which path fits you best?'),
            'project_description': _('What are you looking to achieve?'),
            'start_timeline': _('When are you planning to get started?'),
            'display_name': _('Full name'),
            'phone_number': _('Phone number'),
            'company_name': _('Company name'),
            'job_title': _('Job title'),
            'country': _('Country'),
            'city': _('City'),
            'website': _('Website'),
            'industry': _('Industry'),
            'company_size': _('Company size'),
            'business_address': _('Business address'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The model keeps these optional for legacy rows, but the wizard
        # requires a path and a goal before setup can be completed.
        self.fields['service_type'].required = True
        self.fields['project_description'].required = True
        # Model fields are blank=True, so Django inserts an empty choice.
        # The wizard renders these as cards and must not show a blank option.
        self.fields['service_type'].choices = UserProfile.SERVICE_TYPE_CHOICES
        self.fields['project_description'].choices = UserProfile.PROJECT_DESC_CHOICES
        self.fields['start_timeline'].choices = UserProfile.TIMELINE_CHOICES
        # Replace Django's "---------" blank option with a helpful prompt.
        size_choices = list(self.fields['company_size'].choices)
        if size_choices and size_choices[0][0] == '':
            size_choices[0] = ('', _('Select company size'))
            self.fields['company_size'].choices = size_choices

    def clean(self):
        cleaned_data = super().clean()
        community_needs = cleaned_data.get('community_needs_selection')

        if not community_needs:
            self.add_error(
                'community_needs_selection',
                _('Please select at least one service to continue.'),
            )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.community_needs = self.cleaned_data.get('community_needs_selection', [])
        if commit:
            instance.save()
        return instance


class NotificationPreferencesForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['phone_number', 'sms_notifications_enabled', 'email_notifications_enabled',
                  'marketing_emails_enabled']
        widgets = {
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
        }
