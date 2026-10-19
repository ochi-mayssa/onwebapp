"""Forms for the admin email-campaign workflow."""
from django import forms

from .audience import eligible_client_queryset
from .models import Campaign
from .sanitizer import sanitize_campaign_html


class CampaignComposeForm(forms.ModelForm):
    audience = forms.ChoiceField(
        choices=Campaign.AUDIENCE_CHOICES,
        initial=Campaign.AUDIENCE_ALL,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    selected_users = forms.ModelMultipleChoiceField(
        queryset=eligible_client_queryset().order_by('email'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Selected clients',
    )

    class Meta:
        model = Campaign
        fields = ['name', 'subject', 'body_text', 'body_html']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Campaign name (internal)',
            }),
            'subject': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Email subject line',
            }),
            'body_text': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 8,
                'placeholder': 'Plain-text version of the email',
            }),
            'body_html': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 12,
                'placeholder': 'Optional HTML version (basic tags only; scripts are stripped)',
            }),
        }

    def clean_body_html(self):
        return sanitize_campaign_html(self.cleaned_data.get('body_html', ''))

    def clean(self):
        cleaned = super().clean()
        audience = cleaned.get('audience')
        selected = cleaned.get('selected_users')
        if audience == Campaign.AUDIENCE_SELECTED and not selected:
            self.add_error('selected_users', 'Pick at least one client for a selected audience.')
        body_text = (cleaned.get('body_text') or '').strip()
        if not body_text and not (cleaned.get('body_html') or '').strip():
            self.add_error('body_text', 'Provide a plain-text or HTML body.')
        return cleaned
