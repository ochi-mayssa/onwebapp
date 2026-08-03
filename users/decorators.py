from functools import wraps

from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone

from .models import UserSubscription


def require_active_subscription(view_func):
    """
    Ensure the user has an active subscription.

    If no active subscription is found, redirect to the pricing/plans page.
    """

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('users:login_view')}?next={request.path}")

        now = timezone.now()
        sub = (
            UserSubscription.objects.filter(user=request.user)
            .order_by('-start_date')
            .first()
        )
        if not sub or not sub.plan:
            messages.info(request, "You need a subscription plan to access this feature.")
            return redirect('payments:plans')

        if not sub.is_active or (sub.end_date and sub.end_date < now):
            messages.warning(request, "Your subscription is not active. Please update your plan.")
            return redirect('payments:plans')

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def require_premium_plan(view_func):
    """
    Restrict access to Premium-only features.

    Uses UserSubscription.is_premium helper to decide.
    """

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('users:login_view')}?next={request.path}")

        sub = (
            UserSubscription.objects.filter(user=request.user, is_active=True)
            .order_by('-start_date')
            .first()
        )
        if not sub or not sub.is_premium:
            messages.warning(request, "This feature is available on the Premium plan.")
            return redirect('payments:plans')

        return view_func(request, *args, **kwargs)

    return _wrapped_view

