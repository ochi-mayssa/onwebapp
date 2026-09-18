from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class ServiceType(models.Model):
    CATEGORY_CHOICES = [
        ('web', 'Website Development'),
        ('brand', 'Brand & Design'),
        ('marketing', 'Marketing & SEO'),
        ('consulting', 'Consulting'),
    ]
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    description = models.TextField()
    icon = models.CharField(max_length=50, default='fas fa-cube', help_text='Font Awesome icon class')
    estimated_duration = models.CharField(max_length=100, default='2-4 weeks')
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    complexity_weight = models.PositiveIntegerField(default=1, help_text='1-10 scale for estimation')
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class OnboardingSession(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('abandoned', 'Abandoned'),
    ]
    STEP_CHOICES = [
        (1, 'Welcome'),
        (2, 'Choose Package'),
        (3, 'Business & Project'),
        (4, 'Design Preferences'),
        (5, 'Features & Integrations'),
        (6, 'Estimate & Summary'),
        (7, 'Add-ons'),
        (8, 'Payment & Workspace'),
    ]

    PROJECT_TYPE_CHOICES = [
        ('startup', 'Startup Package'),
        ('essential', 'Basic Package'),
        ('enterprise', 'Enterprise Package'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='onboarding_sessions')
    session_key = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    current_step = models.PositiveIntegerField(default=1)
    completed_steps = models.JSONField(default=list, help_text='List of completed step numbers')
    package_type = models.CharField(max_length=20, choices=PROJECT_TYPE_CHOICES, blank=True, help_text='Startup Package or Basic Package')

    # Step 2: Service
    selected_services = models.ManyToManyField('ServiceType', blank=True, related_name='sessions')

    # Step 3: Business Discovery
    business_name = models.CharField(max_length=255, blank=True)
    industry = models.CharField(max_length=255, blank=True)
    business_description = models.TextField(blank=True)
    target_audience = models.TextField(blank=True)
    existing_website = models.URLField(blank=True)
    competitors = models.TextField(blank=True, help_text='One per line')
    country = models.CharField(max_length=100, blank=True)
    languages = models.CharField(max_length=255, blank=True, help_text='Comma-separated')
    business_goals = models.JSONField(default=list)
    social_media_links = models.JSONField(default=dict, help_text='Platform: URL mapping')

    # Step 4: Project Details
    project_name = models.CharField(max_length=255, blank=True)
    project_goals = models.TextField(blank=True)
    project_type = models.CharField(max_length=50, blank=True)
    budget_range = models.CharField(max_length=50, blank=True)
    target_launch_date = models.DateField(null=True, blank=True)
    additional_notes = models.TextField(blank=True)
    required_pages = models.JSONField(default=list)
    special_features = models.JSONField(default=list)

    # Step 5: Design Preferences
    design_style = models.CharField(max_length=100, blank=True)
    primary_color = models.CharField(max_length=20, blank=True, default='#6366f1')
    accent_color = models.CharField(max_length=20, blank=True, default='#8b5cf6')
    preferred_colors = models.CharField(max_length=255, blank=True)
    typography_style = models.CharField(max_length=100, blank=True)
    inspiration_sites = models.TextField(blank=True)
    reference_websites = models.TextField(blank=True)
    inspiration_images = models.JSONField(default=list)
    uploaded_logo = models.ImageField(upload_to='onboarding/logos/', blank=True, null=True)
    uploaded_brand_guide = models.FileField(upload_to='onboarding/brand_guides/', blank=True, null=True)

    # Step 6: Features & Integrations
    selected_features = models.JSONField(default=list)
    integrations = models.TextField(blank=True, help_text='Comma-separated third-party integrations')

    # Step 7: Estimation (stored after calculation)
    estimation_data = models.JSONField(default=dict, help_text='AI/rule-based estimation results')

    # Step 8: Package
    recommended_package = models.CharField(max_length=50, blank=True)
    selected_package = models.CharField(max_length=50, blank=True)

    @property
    def package(self):
        return self.selected_package

    # Step 9: Add-ons
    selected_addons = models.JSONField(default=list)
    addons_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Step 10-11: Summary & Proposal
    proposal_data = models.JSONField(default=dict)

    # Step 12: Payment
    payment_method = models.CharField(max_length=50, blank=True)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    promo_code = models.CharField(max_length=50, blank=True)
    payment_completed = models.BooleanField(default=False)
    linked_project = models.ForeignKey(
        'projects.Project', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='onboarding_sessions'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Onboarding {self.session_key} - {self.user.username} (Step {self.current_step})"

    def mark_step_complete(self, step_num):
        if step_num not in self.completed_steps:
            self.completed_steps = self.completed_steps + [step_num]
            self.save(update_fields=['completed_steps', 'updated_at'])

    def get_total_steps(self):
        if self.package_type == 'essential':
            return 6
        if self.package_type == 'enterprise':
            return 10
        return 8

    def get_progress_pct(self):
        total = self.get_total_steps()
        if self.package_type == 'essential':
            done = len([s for s in self.completed_steps if s in (2, 3, 4, 5, 6)])
        elif self.package_type == 'enterprise':
            done = len([s for s in self.completed_steps if s in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)])
        else:
            done = len([s for s in self.completed_steps if s in (1, 2, 3, 4, 5, 6, 7, 8)])
        return round((done / total) * 100)

    def get_step_name(self):
        for num, name in self.STEP_CHOICES:
            if num == self.current_step:
                return name
        return 'Unknown'

    def get_estimated_time_left(self):
        total = self.get_total_steps()
        if self.package_type == 'essential':
            done = len([s for s in self.completed_steps if s in (2, 3, 4, 5, 6)])
        elif self.package_type == 'enterprise':
            done = len([s for s in self.completed_steps if s in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)])
        else:
            done = len([s for s in self.completed_steps if s in (1, 2, 3, 4, 5, 6, 7, 8)])
        remaining = total - done
        return f"~{remaining * 2} min"

    def get_selected_services_list(self):
        return [s.name for s in self.selected_services.all()]

    def get_features_list(self):
        return [f.replace('-', ' ').title() for f in self.selected_features]

    def get_addons_list(self):
        result = []
        for a in self.selected_addons:
            if isinstance(a, dict):
                result.append(a.get('name', a.get('slug', '').replace('-', ' ').title()))
            else:
                result.append(str(a).replace('-', ' ').title())
        return result

    def get_package_display(self):
        return self.selected_package.replace('-', ' ').replace('_', ' ').title() if self.selected_package else '—'

    def get_design_style_display(self):
        return self.design_style.replace('-', ' ').title() if self.design_style else '—'

    def get_typography_style_display(self):
        return self.typography_style.replace('-', ' ').title() if self.typography_style else '—'

    def get_budget_range_display(self):
        return self.budget_range.replace('_', ' ').replace('k', 'K').title() if self.budget_range else '—'

    def complete(self):
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])


class OnboardingAddon(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default='fas fa-plus-circle')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.name} (${self.price})"


class WebsiteIntake(models.Model):
    """
    .. deprecated::
        Use OnboardingSession instead. This model is kept for backward compatibility
        with the legacy website_building view and will be removed in a future release.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField()
    phone_number = models.CharField(max_length=50)
    country = models.CharField(max_length=100)
    PROJECT_TYPES = [
        ('personal', 'Personal website'),
        ('business', 'Business website'),
        ('startup', 'Startup / SaaS'),
        ('store', 'Online store'),
        ('portfolio', 'Portfolio'),
        ('other', 'Other'),
    ]
    project_type = models.CharField(max_length=20, choices=PROJECT_TYPES)
    website_goals = models.JSONField(default=list, help_text="List of selected goals")
    required_pages = models.JSONField(default=list, help_text="List of required pages")
    style_preference = models.CharField(max_length=100, blank=True)
    color_preference = models.CharField(max_length=100, blank=True)
    reference_websites = models.TextField(blank=True)
    future_vision = models.JSONField(default=list, help_text="List of future vision items")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Intake for {self.company_name or self.full_name} ({self.created_at.date()})"


class BrandProfile(models.Model):
    PERSONALITY_CHOICES = [
        ('professional', 'Professional & Corporate'),
        ('playful', 'Playful & Creative'),
        ('luxurious', 'Luxurious & Premium'),
        ('minimal', 'Minimal & Clean'),
        ('edgy', 'Edgy & Bold'),
        ('friendly', 'Friendly & Approachable'),
        ('innovative', 'Innovative & Tech-forward'),
    ]
    VOICE_CHOICES = [
        ('formal', 'Formal & Authoritative'),
        ('conversational', 'Conversational & Friendly'),
        ('humorous', 'Humorous & Witty'),
        ('inspirational', 'Inspirational & Motivating'),
        ('direct', 'Direct & Professional'),
        ('storytelling', 'Storytelling & Narrative'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='brand_profiles')
    name = models.CharField(max_length=200, verbose_name='Brand/Business Name')
    industry = models.CharField(max_length=200, blank=True)
    tagline = models.CharField(max_length=300, blank=True, verbose_name='Tagline or Slogan')
    description = models.TextField(blank=True, verbose_name='Brand Description')
    target_audience = models.TextField(blank=True)
    personality = models.CharField(max_length=30, choices=PERSONALITY_CHOICES, default='professional')
    brand_voice = models.CharField(max_length=30, choices=VOICE_CHOICES, default='professional', verbose_name='Brand Voice')
    primary_color = models.CharField(max_length=7, default='#6366f1')
    secondary_color = models.CharField(max_length=7, default='#8b5cf6')
    accent_color = models.CharField(max_length=7, default='#10b981')
    typography_preference = models.CharField(max_length=100, blank=True)
    logo_description = models.TextField(blank=True, help_text='Describe your ideal logo')

    generated_palette = models.JSONField(default=dict, blank=True, help_text='Generated color palette')
    generated_typography = models.JSONField(default=dict, blank=True, help_text='Generated typography suggestions')
    generated_voice_examples = models.JSONField(default=list, blank=True, help_text='Brand voice examples')

    # --- Branding payment (pay add-ons total to unlock download) ---
    PAYMENT_STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('pending', 'Payment Pending'),
        ('paid', 'Paid'),
    ]
    selected_addons = models.JSONField(default=list, blank=True, help_text='List of OnboardingAddon slugs e.g. ["logo-addon", "brand-addon"]')
    addons_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='unpaid')
    stripe_session_id = models.CharField(max_length=255, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    # Final deliverables uploaded by staff (logo files, guidelines PDF)
    logo_final = models.FileField(upload_to='branding/deliverables/', blank=True, null=True)
    guidelines_file = models.FileField(upload_to='branding/deliverables/', blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_paid(self):
        return self.payment_status == 'paid'

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Brand Profile'
        verbose_name_plural = 'Brand Profiles'

    def __str__(self):
        return f"{self.name} — {self.user.username}"
