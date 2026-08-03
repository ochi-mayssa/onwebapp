from django import forms
from .models import SEOTask
from .services.url_intelligence_utils import safe_normalize_url


class FreeWebsitePreCheckForm(forms.Form):
    url = forms.URLField(
        widget=forms.URLInput(attrs={
            "class": "form-control",
            "placeholder": "https://example.com",
            "required": "required"
        })
    )


class SEOTaskForm(forms.ModelForm):
    url = forms.URLField(
        widget=forms.URLInput(attrs={
            "class": "form-control",
            "placeholder": "https://example.com",
            "required": "required"
        })
    )
    max_pages = forms.IntegerField(
        initial=50,
        min_value=1,
        max_value=100,
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )

    class Meta:
        model = SEOTask
        fields = ["url", "max_pages"]


class LinkCheckerForm(forms.Form):
    ANALYSIS_CHOICES = [
        ("internal", "Internal Links"),
        ("external", "External Links"),
        ("backlinks", "Backlinks"),
    ]

    url = forms.URLField(
        widget=forms.URLInput(
            attrs={
                "class": "form-control",
                "placeholder": "https://example.com",
                "required": "required",
            }
        )
    )
    analysis_type = forms.ChoiceField(
        choices=ANALYSIS_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
        initial="internal",
    )


class SitemapIntelligenceForm(forms.Form):
    url = forms.URLField(
        widget=forms.URLInput(
            attrs={
                "class": "form-control",
                "placeholder": "https://example.com",
                "required": "required",
            }
        )
    )
    target_keyword = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "digital marketing (optional)",
            }
        )
    )
    sitemap_url = forms.URLField(
        required=False,
        widget=forms.URLInput(
            attrs={
                "class": "form-control",
                "placeholder": "https://example.com/sitemap.xml (optional)",
            }
        )
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'


class URLIntelligenceForm(forms.Form):
    url = forms.URLField(
        widget=forms.URLInput(
            attrs={
                "class": "form-control",
                "placeholder": "https://example.com/Product_Page?id=123&utm_source=google",
                "required": "required",
            }
        )
    )
    target_keyword = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "digital marketing (optional)",
            }
        ),
    )

    def clean_url(self):
        return safe_normalize_url(self.cleaned_data["url"])


class SEOMonitoringFilterForm(forms.Form):
    RANGE_CHOICES = [
        ("7d", "Last 7 Days"),
        ("30d", "Last 30 Days"),
        ("90d", "Last 90 Days"),
        ("365d", "Last Year"),
        ("custom", "Custom Range"),
    ]
    ANALYSIS_CHOICES = [
        ("all", "All Analyses"),
        ("website", "Website Checker"),
        ("internal", "Internal Links"),
        ("external", "External Links"),
        ("backlinks", "Backlinks"),
    ]

    website = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "example.com or https://example.com",
            }
        ),
    )
    analysis_type = forms.ChoiceField(
        required=False,
        choices=ANALYSIS_CHOICES,
        initial="all",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    range_key = forms.ChoiceField(
        required=False,
        choices=RANGE_CHOICES,
        initial="30d",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
