from functools import wraps
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from django.urls import reverse
from users.models import UserSubscription, ServiceUsage, Plan, Service, PlanLimit
from payments.models import PaymentPlan


def get_free_tier_usage(user, feature_name):
    """
    Get the number of times a user has used a specific feature today.
    """
    if not user.is_authenticated:
        return 0
    
    from users.models import ActivityLog
    
    # Count queries for this feature in the current day
    now = timezone.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    count = ActivityLog.objects.filter(
        user=user,
        action=f'feature_used_{feature_name}',
        timestamp__gte=day_start
    ).count()
    
    return count


def record_feature_usage(user, feature_name):
    """Record that a user has used a feature."""
    # This function remains for backwards compatibility but we prefer
    # using record_feature_usage_dedupe which accepts a dedupe_key.
    if user.is_authenticated:
        from users.models import ActivityLog
        ActivityLog.objects.create(
            user=user,
            action=f'feature_used_{feature_name}',
            metadata={'feature': feature_name}
        )


def record_feature_usage_dedupe(user, feature_name, dedupe_key=None):
    """Record usage only if no existing ActivityLog with same dedupe_key exists for today.

    dedupe_key should be a string that uniquely identifies this logical usage attempt
    (eg. user+feature+date+request-hash). If None, behavior falls back to naive recording.
    """
    if not user.is_authenticated:
        return None

    from users.models import ActivityLog
    from django.utils import timezone

    now = timezone.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if dedupe_key:
        exists = ActivityLog.objects.filter(
            user=user,
            action=f'feature_used_{feature_name}',
            metadata__dedupe_key=dedupe_key,
            timestamp__gte=day_start,
        ).exists()
        if exists:
            return None

    # create a new entry, include dedupe_key in metadata when provided
    meta = {'feature': feature_name}
    if dedupe_key:
        meta['dedupe_key'] = dedupe_key

    return ActivityLog.objects.create(
        user=user,
        action=f'feature_used_{feature_name}',
        metadata=meta,
    )


def has_active_subscription(user):
    """Check if user has an active subscription."""
    if not user.is_authenticated:
        return False
    return UserSubscription.objects.filter(user=user, is_active=True).exists()


DEFAULT_PLANS = {
    'starter': {
        'name': 'Starter Plan',
        'description': 'Ideal for small businesses beginning their analytics journey.',
    },
    'growth': {
        'name': 'Growth Plan',
        'description': 'Scaled limits for growing companies needing more insights.',
    },
    'premium': {
        'name': 'Premium Plan',
        'description': 'All‑features unlimited access for enterprise customers.',
    },
    'free': {
        'name': 'Free Plan',
        'description': 'Try core tools with small usage limits.',
    },
    'basic': {
        'name': 'Basic Plan',
        'description': 'Limited usage of core analytics services.',
    },
    'seo_intelligence': {
        'name': 'SEO Intelligence Suite',
        'description': 'Complete SEO analysis suite including SEO Checker, URL Intelligence, and Link Intelligence.',
    },
}


DEFAULT_SERVICES = {
    'social_media_tracking': 'Social Media Tracking',
    'industrial_automation': 'Industrial Automation',
    'link_analyzer': 'Link Analyzer',
    'seo_analytics': 'SEO Analytics',
    'keyword_research': 'Keyword Research',
    'competitor_tracking': 'Competitor Tracking',
    'erp_integration': 'ERP Integration',
    'crm_integration': 'CRM Integration',
    'seo_analyzer': 'SEO Intelligence Suite',
}


DEFAULT_PLAN_LIMITS = {
    'free': {
        'social_media_tracking': 1,
        'industrial_automation': 1,
        'link_analyzer': 1,
        'competitor_tracking': 1,
        'erp_integration': 1,
        'crm_integration': 1,
        'seo_analyzer': 0,
    },
    'basic': {
        'social_media_tracking': 10,
        'industrial_automation': 5,
        'seo_analytics': 5,
        'keyword_research': 5,
        'erp_integration': 5,
        'crm_integration': 5,
        'seo_analyzer': 0,
    },
    'premium': {
        # Unlimited by default – no limits configured here
    },
    'seo_intelligence': {
        # Unlimited by default – no limits configured here
    },
}


FREE_TIER_LIMITS = {
    'predictive_maintenance': {
        'max_queries_per_day': 1,
        'max_results': 1,
    },
    'industrial_automation': {
        'max_queries_per_day': 1,
        'max_results': 1,
    },
}


def _ensure_default_plan_limits():
    for code, meta in DEFAULT_PLANS.items():
        Plan.objects.get_or_create(
            code=code,
            defaults={
                'name': meta['name'],
                'description': meta['description'],
            },
        )

    for code, name in DEFAULT_SERVICES.items():
        Service.objects.get_or_create(
            code=code,
            defaults={'name': name},
        )

    for plan_code, service_limits in DEFAULT_PLAN_LIMITS.items():
        plan = Plan.objects.filter(code=plan_code).first()
        if not plan:
            continue
        for service_code, max_usage in service_limits.items():
            service = Service.objects.filter(code=service_code).first()
            if not service:
                continue
            PlanLimit.objects.get_or_create(
                plan=plan,
                service=service,
                defaults={'max_usage': max_usage},
            )


def _get_plan_code_for_user(user):
    sub = (
        UserSubscription.objects.filter(user=user, is_active=True)
        .order_by('-start_date', '-created_at')
        .first()
    )
    if not sub or not sub.plan:
        return 'free'
    label = (sub.plan_label or '').lower()
    if 'premium' in label:
        return 'premium'
    if 'basic' in label or 'starter' in label:
        return 'basic'
    return 'basic'


def require_plan_limit(service_code):
    """
    Enforce per-plan usage limits for a given service.

    - Free plan: very small limits (e.g. 1 use).
    - Basic plan: configurable limits per service.
    - Premium plan: unlimited.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                login_url = reverse('users:login_view')
                return redirect(f"{login_url}?next={request.path}")

            if request.method != 'POST':
                return view_func(request, *args, **kwargs)

            _ensure_default_plan_limits()

            plan_code = _get_plan_code_for_user(request.user)

            # Premium has unlimited access – still track usage but never block
            is_premium = plan_code == 'premium'

            plan = Plan.objects.filter(code=plan_code).first()
            service = Service.objects.filter(code=service_code).first()

            limit_obj = (
                PlanLimit.objects.filter(plan=plan, service=service).first()
                if plan and service
                else None
            )
            max_usage = limit_obj.max_usage if limit_obj is not None else None

            usage, _ = ServiceUsage.objects.get_or_create(
                user=request.user,
                service_name=service_code,
                defaults={'usage_count': 0},
            )
            old_limit = usage.limit
            display_limit = 0 if is_premium or max_usage is None else max_usage
            usage.limit = display_limit
            limit_changed = old_limit != display_limit

            limit_reached = (
                not is_premium
                and max_usage is not None
                and usage.usage_count >= max_usage
                and usage.usage_count > 0
            )

            if limit_reached:
                if limit_changed:
                    usage.save(update_fields=['limit'])
                recommended_code = 'premium' if plan_code == 'basic' else 'basic'
                recommended_plan = Plan.objects.filter(code=recommended_code).first()
                return render(
                    request,
                    'services/upgrade_required.html',
                    {
                        'service': service,
                        'plan': plan,
                        'plan_code': plan_code,
                        'current_usage': usage.usage_count,
                        'max_usage': max_usage,
                        'recommended_plan': recommended_plan,
                    },
                    status=402,
                )

            response = view_func(request, *args, **kwargs)

            try:
                status = getattr(response, 'status_code', 200)
            except Exception:
                status = 200

            if status < 400:
                usage.usage_count = (usage.usage_count or 0) + 1
                fields = ['usage_count']
                if limit_changed:
                    fields.append('limit')
                usage.save(update_fields=fields)
            elif limit_changed:
                usage.save(update_fields=['limit'])

            return response

        return wrapper

    return decorator


def has_seo_intelligence_access(user):
    """Bypass SEO subscription and paywall checks while preserving authentication."""
    if not user.is_authenticated:
        return False

    access_granted = True
    return access_granted


def require_seo_intelligence(view_func):
    """Allow authenticated users to access SEO Intelligence views without paywall checks."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            login_url = reverse('users:login_view')
            return redirect(f"{login_url}?next={request.path}")

        access_granted = has_seo_intelligence_access(request.user)
        if access_granted:
            return view_func(request, *args, **kwargs)

        return view_func(request, *args, **kwargs)

    return wrapper

def require_subscription_with_limit(feature_name):
    """
    Decorator that allows free users to access the feature with limitations.
    Authenticated free users can make limited queries. When they reach the limit,
    they see a paywall modal but can still view the page.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Get all available plans
            plans = PaymentPlan.objects.filter(is_active=True).order_by('price')
            
            # Check if user is authenticated
            if request.user.is_authenticated:
                # Check if user has active subscription
                has_subscription = has_active_subscription(request.user)
                
                if has_subscription:
                    # User has subscription, allow full access
                    response = view_func(request, *args, **kwargs)
                    if hasattr(response, 'context_data'):
                        response.context_data['has_subscription'] = True
                        response.context_data['is_free_tier'] = False
                    return response
                
                # User is authenticated but on free tier
                # Check if they've reached their daily limit
                usage_limit = FREE_TIER_LIMITS.get(feature_name, {})
                max_queries = usage_limit.get('max_queries_per_day', 1)
                
                current_usage = get_free_tier_usage(request.user, feature_name)

                # Call the view first, then record usage only if the view succeeded
                response = view_func(request, *args, **kwargs)

                # compute whether to record usage: only if response indicates success
                try:
                    status = getattr(response, 'status_code', 200)
                except Exception:
                    status = 200

                # Build a dedupe key based on user, feature and request signature to avoid
                # double-counting on refresh. We keep it conservative: user_id+feature+date+path+method+body
                dedupe_key = None
                try:
                    import hashlib
                    sig = f"{request.user.id}:{feature_name}:{timezone.now().date()}:{request.path}:{request.method}"
                    # include POST body for more uniqueness when available
                    if request.method in ('POST', 'PUT'):
                        body = (request.body or b'')
                        sig = sig + ':' + hashlib.sha256(body).hexdigest()
                    dedupe_key = hashlib.sha256(sig.encode('utf-8')).hexdigest()
                except Exception:
                    dedupe_key = None

                # Only record when response was successful (status < 400)
                if status < 400:
                    try:
                        # Use dedupe-aware recorder
                        record_feature_usage_dedupe(request.user, feature_name, dedupe_key=dedupe_key)
                    except Exception:
                        # swallow errors to avoid breaking the feature
                        pass

                # If they've exceeded the limit, show paywall modal
                # Recompute usage after possibly creating the log
                current_usage = get_free_tier_usage(request.user, feature_name)
                reached_limit = current_usage >= max_queries
                
                # If it's a TemplateResponse, add context
                if hasattr(response, 'context_data'):
                    response.context_data['has_subscription'] = False
                    response.context_data['is_free_tier'] = True
                    response.context_data['feature_name'] = feature_name
                    response.context_data['plans'] = plans
                    response.context_data['reached_limit'] = reached_limit
                    response.context_data['current_usage'] = current_usage
                    response.context_data['max_queries'] = max_queries
                    # expose max_results so templates can limit visible content
                    response.context_data['max_results'] = usage_limit.get('max_results', 1)
                    response.context_data['usage_remaining'] = max(0, max_queries - current_usage)
                    response.context_data['requires_payment'] = reached_limit
                
                return response
            
            # User is not authenticated
            # If it's an AJAX request, return JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'requires_auth': True,
                    'message': 'Please log in to access this feature',
                })
            
            # For non-AJAX requests, let the view render but show a login prompt
            response = view_func(request, *args, **kwargs)
            if hasattr(response, 'context_data'):
                response.context_data['requires_auth'] = True
                response.context_data['plans'] = plans
            return response
        
        return wrapper
    return decorator

