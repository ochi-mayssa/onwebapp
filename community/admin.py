from django.contrib import admin
from .models import ServiceType, OnboardingSession, OnboardingAddon, BrandProfile, WebsiteIntake


@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'base_price', 'estimated_duration', 'is_active')
    list_filter = ('is_active',)
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('name',)


@admin.register(OnboardingAddon)
class OnboardingAddonAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'price', 'is_active')
    list_filter = ('is_active',)
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('name',)


@admin.register(OnboardingSession)
class OnboardingSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'business_name', 'current_step', 'status', 'selected_package', 'created_at')
    list_filter = ('status', 'current_step')
    search_fields = ('user__username', 'business_name', 'project_name')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    fieldsets = (
        ('User', {'fields': ('user', 'status', 'current_step')}),
        ('Business', {'fields': ('business_name', 'industry', 'business_description', 'target_audience', 'existing_website', 'competitors')}),
        ('Project', {'fields': ('project_name', 'project_goals', 'budget_range', 'target_launch_date', 'additional_notes')}),
        ('Design', {'fields': ('design_style', 'primary_color', 'accent_color', 'typography_style', 'inspiration_sites')}),
        ('Selections', {'fields': ('selected_services', 'selected_features', 'selected_addons', 'selected_package')}),
        ('AI Estimation', {'fields': ('estimation_data',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(BrandProfile)
class BrandProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'industry', 'personality', 'payment_status', 'addons_total', 'created_at')
    list_filter = ('personality', 'brand_voice', 'payment_status')
    search_fields = ('name', 'user__username', 'industry')
    ordering = ('-created_at',)
    readonly_fields = ('generated_palette', 'generated_typography', 'generated_voice_examples', 'created_at', 'updated_at', 'paid_at')
    fieldsets = (
        ('Brand', {'fields': ('user', 'name', 'industry', 'tagline', 'description', 'target_audience')}),
        ('Design inputs', {'fields': ('personality', 'brand_voice', 'primary_color', 'secondary_color', 'accent_color', 'typography_preference', 'logo_description')}),
        ('Payment (pay add-ons total to unlock download)', {'fields': ('payment_status', 'selected_addons', 'addons_total', 'stripe_session_id', 'paid_at')}),
        ('Deliverables (staff upload — only downloadable when Paid)', {'fields': ('logo_final', 'guidelines_file')}),
        ('Generated kit', {'fields': ('generated_palette', 'generated_typography', 'generated_voice_examples')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(WebsiteIntake)
class WebsiteIntakeAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'company_name', 'email', 'project_type', 'created_at')
    list_filter = ('project_type',)
    search_fields = ('full_name', 'company_name', 'email')
    readonly_fields = ('created_at',)
    def has_add_permission(self, request):
        return False
