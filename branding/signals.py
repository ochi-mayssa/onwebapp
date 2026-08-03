"""Branding app signals — feedback notifications."""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import BrandingFeedback, BrandingNotification

User = get_user_model()


@receiver(post_save, sender=BrandingFeedback)
def notify_staff_on_feedback(sender, instance, created, **kwargs):
    """When a client submits feedback, notify all staff."""
    if not created:
        return
    for staff in User.objects.filter(is_staff=True):
        BrandingNotification.objects.create(
            recipient=staff,
            request=instance.request,
            notification_type='SYSTEM',
            message=(
                f"New {instance.rating}/5 feedback from "
                f"{instance.request.user.username} on {instance.request.request_number}."
            ),
            url=f"/branding/requests/{instance.request.pk}/",
        )
