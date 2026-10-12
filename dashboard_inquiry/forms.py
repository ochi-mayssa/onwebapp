from django import forms

from .models import DashboardInquiry


class DashboardInquiryForm(forms.ModelForm):
    class Meta:
        model = DashboardInquiry
        fields = [
            'name', 'email', 'company', 'phone', 'package',
            'data_sources', 'budget', 'timeline', 'message',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Your Name',
                'autocomplete': 'name', 'autofocus': True,
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control', 'placeholder': 'you@company.com',
                'autocomplete': 'email',
            }),
            'company': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Company Name (Optional)',
                'autocomplete': 'organization',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Phone (Optional)',
                'autocomplete': 'tel', 'inputmode': 'tel',
            }),
            'package': forms.Select(attrs={'class': 'form-select'}),
            'data_sources': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g. SQL, ERP, Excel, Shopify',
            }),
            'budget': forms.Select(attrs={'class': 'form-select'}),
            'timeline': forms.Select(attrs={'class': 'form-select'}),
            'message': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 4,
                'placeholder': 'What do you want the dashboard to show?',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Mark errored fields for styling and assistive tech.
        for name, field in self.fields.items():
            if self.errors.get(name):
                css = field.widget.attrs.get('class', '')
                if 'is-invalid' not in css:
                    field.widget.attrs['class'] = f'{css} is-invalid'.strip()
                field.widget.attrs['aria-invalid'] = 'true'
