from django import template
from django.db.models import Count, Q
from ..models import ForumPost, ForumCategory, ForumTag, ForumReaction

register = template.Library()


@register.simple_tag
def forum_stat(key):
    from ..services import get_community_stats
    stats = get_community_stats()
    return stats.get(key, 0)


@register.simple_tag
def forum_category_list():
    return ForumCategory.objects.filter(is_active=True).annotate(
        total_posts=Count('posts', filter=Q(posts__status='published'))
    ).order_by('order', 'name')


@register.simple_tag
def forum_tag_list(limit=20):
    return ForumTag.objects.annotate(
        post_count=Count('posts', filter=Q(posts__status='published'))
    ).order_by('-post_count')[:limit]


@register.simple_tag
def user_reputation(user):
    from ..permissions import get_user_reputation
    return get_user_reputation(user)


@register.simple_tag
def user_forum_badges(user):
    from ..models import UserBadge
    return UserBadge.objects.filter(user=user).select_related('badge')


@register.filter
def vote_percent(upvotes, downvotes):
    total = upvotes + downvotes
    if total == 0:
        return 0
    return round((upvotes / total) * 100)


@register.filter
def user_avatar(user):
    profile = getattr(user, 'profile', None)
    if profile and profile.avatar:
        return profile.avatar
    return f'https://ui-avatars.com/api/?name={user.username}&background=6366f1&color=fff'


@register.filter
def reading_time(text):
    wpm = 200
    words = len(text.split())
    return max(1, round(words / wpm))


@register.filter
def has_voted(post, user):
    if not user.is_authenticated:
        return None
    reaction = ForumReaction.objects.filter(user=user, post=post).first()
    return reaction.reaction_type if reaction else None


@register.filter
def is_bookmarked(post, user):
    if not user.is_authenticated:
        return False
    from ..models import Bookmark
    return Bookmark.objects.filter(user=user, post=post).exists()


@register.filter
def comment_depth(comment):
    return comment.get_depth


@register.filter
def indent_level(comment):
    depth = comment.get_depth
    return min(depth * 20, 120)