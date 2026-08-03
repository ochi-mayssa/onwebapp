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
    """Form for user onboarding to select service type."""
    
    COMMUNITY_NEED_CHOICES = [
        ('website', 'Custom Website'),
        ('branding', 'Brand Identity'),
        ('social', 'Social Media Growth'),
        ('content', 'Content Strategy'),
    ]
    
    # We use a MultipleChoiceField but store it manually into the JSONField
    community_needs_selection = forms.MultipleChoiceField(
        choices=COMMUNITY_NEED_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
        label=_("If you selected Community Services, what do you need?")
    )

    class Meta:
        model = UserProfile
        fields = ['service_type', 'project_description', 'start_timeline']
        widgets = {
            'service_type': forms.RadioSelect(attrs={'class': 'form-check-input'}),
            'project_description': forms.RadioSelect(attrs={'class': 'form-check-input'}),
            'start_timeline': forms.RadioSelect(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'service_type': _('What type of service are you looking for?'),
            'project_description': _('What best describes your project?'),
            'start_timeline': _('When would you like to get started?'),
        }

    def clean(self):
        cleaned_data = super().clean()
        service_type = cleaned_data.get('service_type')
        community_needs = cleaned_data.get('community_needs_selection')

        if service_type == 'community' and not community_needs:
            self.add_error('community_needs_selection', _('Please select at least one community service need.'))
        
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
        fields = ['phone_number', 'sms_notifications_enabled', 'email_notifications_enabled']
        widgets = {
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
        }
