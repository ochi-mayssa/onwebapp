from django.contrib import admin
from .models import ServiceType, OnboardingSession, OnboardingAddon, BrandProfile


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
    list_display = ('name', 'user', 'industry', 'personality', 'created_at')
    list_filter = ('personality', 'brand_voice')
    search_fields = ('name', 'user__username', 'industry')
    ordering = ('-created_at',)
