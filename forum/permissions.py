from django.contrib.auth import get_user_model
from django.db.models import Count, Q

User = get_user_model()


def can_create_post(user):
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    return True


def can_edit_post(user, post):
    return user == post.author or user.is_staff or user.is_superuser


def can_delete_post(user, post):
    return user == post.author or user.is_staff or user.is_superuser


def can_moderate(user):
    return user.is_staff or user.is_superuser or user.groups.filter(name='Moderators').exists()


def can_pin_post(user):
    return user.is_staff or user.is_superuser or user.groups.filter(name='Moderators').exists()


def can_lock_post(user):
    return user.is_staff or user.is_superuser or user.groups.filter(name='Moderators').exists()


def can_comment(user, post):
    if not user.is_authenticated:
        return False
    if post.is_locked:
        return user.is_staff or user.is_superuser
    return True


def can_vote(user):
    return user.is_authenticated


def can_report(user):
    return user.is_authenticated


def get_user_reputation(user):
    from .models import ForumPost, ForumComment
    post_upvotes = ForumPost.objects.filter(author=user).aggregate(
        total=Count('reactions', filter=Q(reactions__reaction_type='upvote'))
    )['total'] or 0
    comment_upvotes = ForumComment.objects.filter(author=user).aggregate(
        total=Count('reactions', filter=Q(reactions__reaction_type='upvote'))
    )['total'] or 0
    solutions = ForumComment.objects.filter(author=user, is_solution=True).count()
    posts_count = ForumPost.objects.filter(author=user, status='published').count()
    return (post_upvotes * 5) + (comment_upvotes * 3) + (solutions * 25) + (posts_count * 10)


class ForumPermissions:
    def __init__(self, user):
        self.user = user

    @property
    def can_post(self):
        return can_create_post(self.user)

    @property
    def can_comment(self):
        return self.user.is_authenticated

    @property
    def can_vote(self):
        return self.user.is_authenticated

    @property
    def can_report(self):
        return self.user.is_authenticated

    @property
    def is_moderator(self):
        return can_moderate(self.user)