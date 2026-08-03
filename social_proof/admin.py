from django.contrib import admin
from .models import SocialProvider, SocialEvent, SocialStreamConfig

@admin.register(SocialProvider)
class SocialProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'enabled', 'last_sync_at')
    list_filter = ('enabled', 'name')
    readonly_fields = ('last_sync_at',)

@admin.register(SocialStreamConfig)
class SocialStreamConfigAdmin(admin.ModelAdmin):
    list_display = ('project', 'min_sentiment_score', 'auto_approve', 'updated_at')
    search_fields = ('project__title', 'project__client__email')
    filter_horizontal = ('enabled_providers',)

@admin.register(SocialEvent)
class SocialEventAdmin(admin.ModelAdmin):
    list_display = ('provider', 'author_name', 'sentiment_score', 'is_approved', 'created_at')
    list_filter = ('provider', 'is_approved', 'event_type')
    search_fields = ('text', 'author_name', 'external_id')
    readonly_fields = ('created_at', 'raw_json')
