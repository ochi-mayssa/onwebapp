from django.contrib import admin

from .models import Campaign, CampaignRecipient


class CampaignRecipientInline(admin.TabularInline):
    model = CampaignRecipient
    extra = 0
    readonly_fields = ('email', 'user', 'status', 'attempts', 'last_error', 'sent_at')
    can_delete = False


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('reference', 'name', 'subject', 'status', 'total_recipients',
                    'sent_count', 'failed_count', 'pending_count', 'created_by', 'created_at')
    list_filter = ('status', 'audience')
    search_fields = ('reference', 'name', 'subject')
    readonly_fields = ('reference', 'total_recipients', 'sent_count', 'failed_count',
                       'pending_count', 'started_at', 'finished_at', 'created_at', 'updated_at')
    inlines = [CampaignRecipientInline]
    actions = ['delete_selected']


@admin.register(CampaignRecipient)
class CampaignRecipientAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'email', 'status', 'attempts', 'sent_at', 'last_error')
    list_filter = ('status',)
    search_fields = ('email', 'campaign__reference', 'campaign__name')
    readonly_fields = ('campaign', 'user', 'email', 'status', 'attempts', 'last_error', 'sent_at')
