from django import forms
from .models import OnboardingSession, WebsiteIntake, BrandProfile


class Step2ServiceForm(forms.Form):
    SERVICES_CHOICES = [
        ('website_dev', 'Website Development'),
        ('ecommerce', 'E-Commerce'),
        ('landing_page', 'Landing Page'),
        ('portfolio', 'Portfolio'),
        ('corporate', 'Corporate Website'),
        ('brand_identity', 'Brand Identity'),
        ('logo_design', 'Logo Design'),
        ('ui_ux', 'UI/UX Design'),
        ('seo', 'SEO'),
        ('maintenance', 'Website Maintenance'),
        ('consulting', 'Digital Consulting'),
    ]
    services = forms.MultipleChoiceField(
        choices=SERVICES_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )


class Step3BusinessForm(forms.Form):
    business_name = forms.CharField(max_length=255, widget=forms.TextInput(
        attrs={'class': 'wizard-input', 'placeholder': 'Your Business Name'}
    ))
    industry = forms.CharField(max_length=255, widget=forms.TextInput(
        attrs={'class': 'wizard-input', 'placeholder': 'e.g. Technology, Healthcare, Retail'}
    ))
    business_description = forms.CharField(widget=forms.Textarea(
        attrs={'class': 'wizard-input', 'rows': 3, 'placeholder': 'Briefly describe what your business does...'}
    ))
    target_audience = forms.CharField(widget=forms.Textarea(
        attrs={'class': 'wizard-input', 'rows': 2, 'placeholder': 'Who are your ideal customers?'}
    ))
    country = forms.CharField(max_length=100, widget=forms.TextInput(
        attrs={'class': 'wizard-input', 'placeholder': 'Country'}
    ))
    languages = forms.CharField(max_length=255, required=False, widget=forms.TextInput(
        attrs={'class': 'wizard-input', 'placeholder': 'e.g. English, French'}
    ))
    current_website = forms.URLField(required=False, widget=forms.TextInput(
        attrs={'class': 'wizard-input', 'placeholder': 'https://...'}
    ))
    competitors = forms.CharField(required=False, widget=forms.Textarea(
        attrs={'class': 'wizard-input', 'rows': 2, 'placeholder': 'One competitor per line'}
    ))


class Step4ProjectForm(forms.Form):
    PROJECT_TYPE_CHOICES = [
        ('showcase', 'Showcase / Portfolio'),
        ('ecommerce', 'E-commerce'),
        ('blog', 'Blog / Magazine'),
        ('webapp', 'Enterprise Web Application'),
        ('saas', 'SaaS Platform'),
        ('landing', 'Landing Page'),
    ]
    project_type = forms.ChoiceField(choices=PROJECT_TYPE_CHOICES, widget=forms.RadioSelect(
        attrs={'class': 'project-type-radio'}
    ))

    PAGES_CHOICES = [
        ('home', 'Home'),
        ('about', 'About'),
        ('services', 'Services'),
        ('contact', 'Contact'),
        ('blog', 'Blog'),
        ('pricing', 'Pricing'),
        ('faq', 'FAQ'),
        ('team', 'Team'),
        ('portfolio', 'Portfolio'),
        ('testimonials', 'Testimonials'),
        ('careers', 'Careers'),
        ('other', 'Other'),
    ]
    required_pages = forms.MultipleChoiceField(
        choices=PAGES_CHOICES, widget=forms.CheckboxSelectMultiple, required=False
    )

    FEATURES_CHOICES = [
        ('booking_system', 'Booking System'),
        ('blog', 'Blog'),
        ('online_payments', 'Online Payments'),
        ('customer_portal', 'Customer Portal'),
        ('admin_dashboard', 'Admin Dashboard'),
        ('inventory', 'Inventory Management'),
        ('appointment_system', 'Appointment System'),
        ('membership', 'Membership Area'),
        ('newsletter', 'Newsletter'),
    ]
    special_features = forms.MultipleChoiceField(
        choices=FEATURES_CHOICES, widget=forms.CheckboxSelectMultiple, required=False
    )


class Step5DesignForm(forms.Form):
    STYLE_CHOICES = [
        ('modern', 'Modern'),
        ('minimal', 'Minimal'),
        ('luxury', 'Luxury'),
        ('corporate', 'Corporate'),
        ('creative', 'Creative'),
        ('dark', 'Dark'),
        ('light', 'Light'),
        ('bold', 'Bold'),
        ('elegant', 'Elegant'),
    ]
    design_style = forms.ChoiceField(choices=STYLE_CHOICES, widget=forms.RadioSelect(
        attrs={'class': 'style-radio'}
    ))
    preferred_colors = forms.CharField(max_length=255, required=False, widget=forms.TextInput(
        attrs={'class': 'wizard-input', 'placeholder': 'e.g. Blue, White, #FF5733'}
    ))
    typography_style = forms.CharField(max_length=100, required=False, widget=forms.TextInput(
        attrs={'class': 'wizard-input', 'placeholder': 'e.g. Sans-serif, Elegant, Bold'}
    ))
    reference_websites = forms.CharField(required=False, widget=forms.Textarea(
        attrs={'class': 'wizard-input', 'rows': 3, 'placeholder': 'Paste URLs of websites you like...'}
    ))


class Step6FeaturesForm(forms.Form):
    INTEGRATIONS_CHOICES = [
        ('whatsapp_chat', 'WhatsApp Chat'),
        ('live_chat', 'Live Chat'),
        ('newsletter', 'Newsletter'),
        ('google_analytics', 'Google Analytics'),
        ('google_maps', 'Google Maps'),
        ('seo', 'SEO Tools'),
        ('blog', 'Blog'),
        ('multi_language', 'Multi-language'),
        ('payment_gateway', 'Payment Gateway'),
        ('email_marketing', 'Email Marketing'),
        ('crm', 'CRM'),
        ('social_login', 'Social Login'),
    ]
    selected_features = forms.MultipleChoiceField(
        choices=INTEGRATIONS_CHOICES, widget=forms.CheckboxSelectMultiple, required=False
    )


class Step9AddonsForm(forms.Form):
    pass  # Dynamically built from OnboardingAddon model


class Step12PaymentForm(forms.Form):
    PAYMENT_CHOICES = [
        ('deposit', 'Pay 50% Deposit'),
        ('full', 'Pay Full Amount'),
    ]
    payment_method = forms.ChoiceField(choices=PAYMENT_CHOICES, widget=forms.RadioSelect)
    promo_code = forms.CharField(max_length=50, required=False, widget=forms.TextInput(
        attrs={'class': 'wizard-input', 'placeholder': 'Promo code (optional)'}
    ))


class WebsiteIntakeForm(forms.ModelForm):
    WEBSITE_GOALS_CHOICES = [
        ('presence', 'Online presence'),
        ('lead_gen', 'Lead generation'),
        ('sales', 'Sell products or services'),
        ('branding', 'Brand awareness'),
        ('expansion', 'Prepare for future expansion'),
    ]
    REQUIRED_PAGES_CHOICES = [
        ('home', 'Home'),
        ('about', 'About'),
        ('services', 'Services'),
        ('contact', 'Contact'),
        ('blog', 'Blog'),
        ('other', 'Other'),
    ]
    FUTURE_VISION_CHOICES = [
        ('features', 'Add new features later'),
        ('automation', 'Automation'),
        ('dashboard', 'Dashboard / Admin panel'),
        ('integrations', 'Integrations (payments, email, APIs)'),
        ('not_sure', 'Not sure yet (we help you plan it)'),
    ]

    website_goals = forms.MultipleChoiceField(
        choices=WEBSITE_GOALS_CHOICES, widget=forms.CheckboxSelectMultiple, required=False
    )
    required_pages = forms.MultipleChoiceField(
        choices=REQUIRED_PAGES_CHOICES, widget=forms.CheckboxSelectMultiple, required=False
    )
    future_vision = forms.MultipleChoiceField(
        choices=FUTURE_VISION_CHOICES, widget=forms.CheckboxSelectMultiple, required=False
    )

    class Meta:
        model = WebsiteIntake
        fields = [
            'full_name', 'company_name', 'email', 'phone_number', 'country',
            'project_type', 'website_goals', 'required_pages',
            'style_preference', 'color_preference', 'reference_websites',
            'future_vision'
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name'}),
            'company_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company / Project Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'country': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Country'}),
            'project_type': forms.Select(attrs={'class': 'form-select'}),
            'style_preference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Modern, Minimal, Corporate'}),
            'color_preference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Blue and White'}),
            'reference_websites': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional: Links to websites you like'}),
        }


class BrandAssistForm(forms.ModelForm):
    class Meta:
        model = BrandProfile
        fields = [
            'name', 'industry', 'tagline', 'description', 'target_audience',
            'personality', 'brand_voice', 'primary_color', 'secondary_color',
            'accent_color', 'typography_preference', 'logo_description',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your brand or business name'}),
            'industry': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Technology, Fashion, Healthcare'}),
            'tagline': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'A short tagline or slogan'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe your brand in a few sentences...'}),
            'target_audience': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Who are your ideal customers?'}),
            'personality': forms.Select(attrs={'class': 'form-select'}),
            'brand_voice': forms.Select(attrs={'class': 'form-select'}),
            'primary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color', 'style': 'height: 48px; padding: 4px;'}),
            'secondary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color', 'style': 'height: 48px; padding: 4px;'}),
            'accent_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color', 'style': 'height: 48px; padding: 4px;'}),
            'typography_preference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Sans-serif, Serif, Montserrat'}),
            'logo_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Describe your ideal logo (style, symbols, colors...)'}),
        }
