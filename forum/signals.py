from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import ForumPost, ForumComment, ForumReaction, ForumReport
from .services import check_and_award_badges

User = get_user_model()


@receiver(post_save, sender=ForumPost)
def handle_post_save(sender, instance, created, **kwargs):
    if created and instance.status == 'published':
        check_and_award_badges(instance.author)
        if instance.category:
            ForumCategory = sender.category.field.related_model
            ForumCategory.objects.filter(pk=instance.category_id).update(
                post_count=ForumPost.objects.filter(
                    category=instance.category, status='published'
                ).count()
            )


@receiver(post_save, sender=ForumReaction)
def handle_reaction(sender, instance, created, **kwargs):
    if instance.post:
        instance.post.update_vote_counts()
    if instance.comment:
        instance.comment.update_vote_counts()
    if created and instance.reaction_type in ('upvote', 'like', 'love', 'insightful'):
        target_user = None
        if instance.post:
            target_user = instance.post.author
        elif instance.comment:
            target_user = instance.comment.author
        if target_user and target_user != instance.user:
            pass


@receiver(post_save, sender=ForumComment)
def handle_comment_save(sender, instance, created, **kwargs):
    if created:
        check_and_award_badges(instance.author)


@receiver(post_save, sender=ForumReport)
def handle_report(sender, instance, created, **kwargs):
    if created:
        target = instance.post or instance.comment
        if target and hasattr(target, 'author'):
            reporter_profile = getattr(instance.reporter, 'profile', None)
            if reporter_profile:
                pass