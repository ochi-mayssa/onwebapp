from django import forms
from .models import ConsultationRequest, WebsiteBuildRequest

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
