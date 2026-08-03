from django.contrib import admin
from .models import (
    ForumCategory, ForumTag, ForumPost, ForumComment, ForumReaction,
    Bookmark, FollowCategory, FollowUser, ForumReport, ForumBadge,
    UserBadge, ForumEvent, ForumJob,
)


@admin.register(ForumCategory)
class ForumCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'order', 'is_active', 'post_count']
    list_editable = ['order', 'is_active']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(ForumTag)
class ForumTagAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'color']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}


class ForumCommentInline(admin.TabularInline):
    model = ForumComment
    extra = 0
    fields = ['author', 'content', 'is_solution', 'is_active']
    readonly_fields = ['author', 'content']


@admin.register(ForumPost)
class ForumPostAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'category', 'status', 'is_pinned', 'score', 'views_count', 'created_at']
    list_filter = ['status', 'is_pinned', 'is_locked', 'category', 'tags']
    search_fields = ['title', 'content', 'author__username']
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ['tags']
    actions = ['pin_posts', 'unpin_posts', 'lock_posts', 'unlock_posts']
    inlines = [ForumCommentInline]
    date_hierarchy = 'created_at'

    def pin_posts(self, request, queryset):
        queryset.update(is_pinned=True)
    pin_posts.short_description = 'Pin selected posts'

    def unpin_posts(self, request, queryset):
        queryset.update(is_pinned=False)
    unpin_posts.short_description = 'Unpin selected posts'

    def lock_posts(self, request, queryset):
        queryset.update(is_locked=True)
    lock_posts.short_description = 'Lock selected posts'

    def unlock_posts(self, request, queryset):
        queryset.update(is_locked=False)
    unlock_posts.short_description = 'Unlock selected posts'


@admin.register(ForumComment)
class ForumCommentAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'author', 'post', 'is_solution', 'is_active', 'created_at']
    list_filter = ['is_solution', 'is_active']
    search_fields = ['content', 'author__username']
    actions = ['mark_solution', 'toggle_active']

    def mark_solution(self, request, queryset):
        queryset.update(is_solution=True)
    mark_solution.short_description = 'Mark as solution'

    def toggle_active(self, request, queryset):
        for c in queryset:
            c.is_active = not c.is_active
            c.save()
    toggle_active.short_description = 'Toggle active status'


@admin.register(ForumReaction)
class ForumReactionAdmin(admin.ModelAdmin):
    list_display = ['user', 'reaction_type', 'post', 'comment', 'created_at']
    list_filter = ['reaction_type']
    search_fields = ['user__username']


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ['user', 'post', 'created_at']
    search_fields = ['user__username', 'post__title']


@admin.register(FollowCategory)
class FollowCategoryAdmin(admin.ModelAdmin):
    list_display = ['user', 'category', 'created_at']


@admin.register(FollowUser)
class FollowUserAdmin(admin.ModelAdmin):
    list_display = ['follower', 'following', 'created_at']


@admin.register(ForumReport)
class ForumReportAdmin(admin.ModelAdmin):
    list_display = ['reporter', 'reason', 'post', 'comment', 'is_resolved', 'created_at']
    list_filter = ['reason', 'is_resolved']
    actions = ['resolve_reports']

    def resolve_reports(self, request, queryset):
        from django.utils import timezone
        queryset.update(is_resolved=True, resolved_by=request.user, resolved_at=timezone.now())
    resolve_reports.short_description = 'Resolve selected reports'


@admin.register(ForumBadge)
class ForumBadgeAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'color']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ['user', 'badge', 'awarded_at']
    search_fields = ['user__username', 'badge__name']


@admin.register(ForumEvent)
class ForumEventAdmin(admin.ModelAdmin):
    list_display = ['title', 'event_type', 'start_date', 'end_date', 'is_published']
    list_filter = ['event_type', 'is_published']


@admin.register(ForumJob)
class ForumJobAdmin(admin.ModelAdmin):
    list_display = ['title', 'company', 'job_type', 'is_active', 'created_at']
    list_filter = ['job_type', 'is_active']
    search_fields = ['title', 'company', 'description']