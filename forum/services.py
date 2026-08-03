import re
from django.db import models
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.text import slugify
from .models import (
    ForumPost, ForumComment, ForumReaction, ForumBadge, UserBadge,
    Bookmark, FollowUser, FollowCategory,
)


def create_notification(user, action, metadata=None):
    from users.models import ActivityLog
    ActivityLog.objects.create(
        user=user,
        action=action,
        metadata=metadata or {},
    )


def get_trending_posts(limit=10):
    week_ago = timezone.now() - timezone.timedelta(days=7)
    return ForumPost.objects.published().filter(
        created_at__gte=week_ago
    ).order_by('-score', '-views_count')[:limit]


def get_latest_discussions(limit=20):
    return ForumPost.objects.with_counts().order_by('-created_at')[:limit]


def get_top_contributors(period='week', limit=10):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    now = timezone.now()
    if period == 'week':
        since = now - timezone.timedelta(days=7)
    elif period == 'month':
        since = now - timezone.timedelta(days=30)
    else:
        since = None

    filters = {'forum_posts__status': 'published', 'forum_posts__is_hidden': False}
    if since:
        filters['forum_posts__created_at__gte'] = since

    user_filters = Q(forum_posts__status='published', forum_posts__is_hidden=False)
    if since:
        user_filters &= Q(forum_posts__created_at__gte=since)

    return User.objects.filter(**filters).annotate(
        post_count=Count('forum_posts', filter=user_filters),
        total_upvotes=Sum('forum_posts__upvotes', filter=user_filters),
    ).order_by('-post_count')[:limit]


def get_community_stats():
    return {
        'total_posts': ForumPost.objects.published().count(),
        'total_comments': ForumComment.objects.filter(is_active=True).count(),
        'total_members': ForumPost.objects.published().values('author').distinct().count(),
        'total_categories': ForumPost.objects.published().values('category').distinct().count(),
        'total_solutions': ForumComment.objects.filter(is_solution=True).count(),
    }


def check_and_award_badges(user):
    awarded = []
    badges_to_check = ForumBadge.objects.all()
    existing = UserBadge.objects.filter(user=user).values_list('badge_id', flat=True)

    for badge in badges_to_check:
        if badge.pk in existing:
            continue

        earned = _check_badge_criteria(user, badge)
        if earned:
            UserBadge.objects.create(user=user, badge=badge)
            awarded.append(badge)
    return awarded


def _check_badge_criteria(user, badge):
    slug = badge.slug
    if slug == 'first-post':
        return ForumPost.objects.filter(author=user, status='published').exists()
    elif slug == '100-upvotes':
        total = ForumPost.objects.filter(author=user).aggregate(
            total=Sum('upvotes')
        )['total'] or 0
        return total >= 100
    elif slug == 'top-contributor':
        count = ForumPost.objects.filter(author=user, status='published').count()
        return count >= 50
    elif slug == 'helpful-member':
        solutions = ForumComment.objects.filter(author=user, is_solution=True).count()
        return solutions >= 10
    elif slug == 'early-member':
        first = ForumPost.objects.filter(author=user).order_by('created_at').first()
        if first and first.created_at:
            return first.created_at < timezone.now() - timezone.timedelta(days=90)
        return False
    elif slug == 'django-expert':
        return ForumPost.objects.filter(
            author=user, status='published', tags__slug='django'
        ).count() >= 10
    elif slug == 'ui-designer':
        return ForumPost.objects.filter(
            author=user, status='published', tags__slug__in=['ui', 'ux', 'design']
        ).count() >= 10
    return False


def get_duplicate_posts(content, user, threshold=0.8):
    from difflib import SequenceMatcher
    recent = ForumPost.objects.filter(author=user).order_by('-created_at')[:5]
    for post in recent:
        ratio = SequenceMatcher(None, content.lower(), post.content.lower()).ratio()
        if ratio >= threshold:
            return post
    return None


PROFANITY_LIST = [
    r'\bspam\b', r'\bscam\b',
]


def contains_profanity(text):
    text_lower = text.lower()
    for pattern in PROFANITY_LIST:
        if re.search(pattern, text_lower):
            return True
    return False


def clean_html(text):
    import html
    return html.escape(text)


def get_reading_time(text):
    wpm = 200
    words = len(text.split())
    return max(1, round(words / wpm))


def toggle_bookmark(user, post):
    bookmark, created = Bookmark.objects.get_or_create(user=user, post=post)
    if not created:
        bookmark.delete()
        ForumPost.objects.filter(pk=post.pk).update(bookmarks_count=models.F('bookmarks_count') - 1)
        return False
    ForumPost.objects.filter(pk=post.pk).update(bookmarks_count=models.F('bookmarks_count') + 1)
    return True


def toggle_follow_user(follower, following):
    if follower == following:
        return None
    follow, created = FollowUser.objects.get_or_create(
        follower=follower, following=following
    )
    if not created:
        follow.delete()
        return False
    return True


def toggle_follow_category(user, category):
    follow, created = FollowCategory.objects.get_or_create(
        user=user, category=category
    )
    if not created:
        follow.delete()
        return False
    return True


def get_sitemap_posts():
    return ForumPost.objects.filter(status='published').only('slug', 'updated_at')