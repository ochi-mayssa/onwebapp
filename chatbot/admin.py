from django.contrib import admin

from .models import CallRequest, ChatLead, ChatMessage, ChatSession


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    fields = ('sender', 'content', 'timestamp')
    readonly_fields = ('sender', 'content', 'timestamp')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('short_id', 'user', 'lead_summary_present', 'message_count',
                    'created_at', 'updated_at')
    search_fields = ('session_id', 'user__username', 'user__email')
    list_select_related = ('user',)
    readonly_fields = ('session_id', 'state', 'created_at', 'updated_at')
    inlines = [ChatMessageInline]

    @admin.display(description='Session')
    def short_id(self, obj):
        return obj.session_id[:8]

    @admin.display(description='Lead')
    def lead_summary_present(self, obj):
        return 'Yes' if getattr(obj, 'lead', None) else ''

    @admin.display(description='Messages')
    def message_count(self, obj):
        return obj.messages.count()


@admin.register(ChatLead)
class ChatLeadAdmin(admin.ModelAdmin):
    list_display = ('solution', 'intent', 'contact', 'status',
                    'created_at', 'session_link')
    list_filter = ('status', 'intent')
    search_fields = ('solution', 'summary', 'contact', 'session__session_id')
    readonly_fields = ('session', 'intent', 'solution', 'summary', 'data',
                       'contact', 'created_at', 'updated_at')
    list_select_related = ('session',)

    @admin.display(description='Session')
    def session_link(self, obj):
        return obj.session.session_id[:8]


@admin.register(CallRequest)
class CallRequestAdmin(admin.ModelAdmin):
    list_display = ('visitor', 'status', 'channel', 'reason', 'assigned_to',
                    'escalated_at', 'priority_label')
    list_filter = ('status', 'channel')
    search_fields = ('reason', 'notes', 'session__session_id',
                     'requested_by__username')
    readonly_fields = ('session', 'requested_by', 'reason', 'channel',
                       'escalated_at', 'created_at', 'updated_at')
    list_select_related = ('session', 'requested_by', 'assigned_to')

    @admin.display(description='Visitor')
    def visitor(self, obj):
        return obj.requested_by or obj.session.session_id[:8]


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'short_session', 'preview', 'timestamp')
    list_filter = ('sender',)
    search_fields = ('content', 'session__session_id')
    readonly_fields = ('session', 'sender', 'agent', 'content', 'timestamp')
    list_select_related = ('session', 'agent')

    @admin.display(description='Session')
    def short_session(self, obj):
        return obj.session.session_id[:8]

    @admin.display(description='Content')
    def preview(self, obj):
        return obj.content[:80]
