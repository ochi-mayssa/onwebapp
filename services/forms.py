from django import forms

class MachineForm(forms.Form):
    identifier = forms.CharField(
        label='Machine ID or API',
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter machine ID or API key'}),
    )
    email = forms.EmailField(
        label='Email (optional)',
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@example.com'}),
    )

class CompanyForm(forms.Form):
    company = forms.CharField(
        label='Company or Factory Name',
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter company or factory name'}),
    )
    email = forms.EmailField(
        label='Email (optional)',
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@example.com'}),
    )

class UrlInputForm(forms.Form):
    url = forms.URLField(
        label='URL',
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com'}),
    )
    email = forms.EmailField(
        label='Email (optional)',
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@example.com'}),
    )


class KeywordForm(forms.Form):
    query = forms.CharField(
        label='Keyword or Phrase',
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., industrial automation sensors'}),
    )
    email = forms.EmailField(
        label='Email (optional)',
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@example.com'}),
    )


class SocialTrackingForm(forms.Form):
    handle = forms.CharField(
        label='Social Media Profile URL or @Handle',
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'https://instagram.com/onwebapp  or  @onwebapp',
            'autocomplete': 'off',
        }),
        help_text='Supported: Instagram, Facebook, LinkedIn, TikTok, YouTube and X',
    )
    email = forms.EmailField(
        label='Alert Email (optional)',
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@example.com'}),
    )
    PLATFORMS = [
        ('twitter', 'X / Twitter'),
        ('instagram', 'Instagram'),
        ('tiktok', 'TikTok'),
        ('facebook', 'Facebook'),
        ('linkedin', 'LinkedIn'),
        ('youtube', 'YouTube'),
    ]
    platforms = forms.MultipleChoiceField(
        label='Platforms (optional)',
        choices=PLATFORMS,
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        initial=[p[0] for p in PLATFORMS],
        help_text='Platform is auto-detected from profile URLs.',
    )
    days = forms.IntegerField(
        label='Days Range',
        required=False,
        initial=30,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 7, 'max': 365})
    )

    def clean_handle(self):
        value = (self.cleaned_data.get('handle') or '').strip()
        if not value:
            raise forms.ValidationError('Enter a supported social media profile URL or @handle.')
        return value
