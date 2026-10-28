from django import forms

from .models import AutomationRequest


class AutomationRequestForm(forms.ModelForm):
    class Meta:
        model = AutomationRequest
        fields = ['title', 'description', 'requirement_notes', 'config']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'requirement_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'config': forms.HiddenInput(),
        }

    def save(self, commit=True, *, customer=None, requested_by=None):
        instance = super().save(commit=False)
        if customer is not None:
            instance.customer = customer
        if requested_by is not None:
            instance.requested_by = requested_by
        if commit:
            instance.save()
        return instance
