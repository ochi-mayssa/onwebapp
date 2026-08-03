from django import forms


class SampleForm(forms.Form):
    name = forms.CharField(max_length=100, required=True)


from .models import Link


class LinkForm(forms.ModelForm):
    class Meta:
        model = Link
        fields = ['title', 'url', 'link_type', 'description']
