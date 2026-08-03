from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from .forms import SignUpForm, OnboardingForm, NotificationPreferencesForm
from django.contrib.auth.models import User
from django.contrib.auth import logout as auth_logout
from django.utils import timezone
from .models import ActivityLog, UserProfile, UserSubscription, ServiceUsage, UserApiKey
from projects.models import Invoice
from payments.models import PaymentPlan, UserPaymentSelection
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.conf import settings
from home.models import WebsiteBuildRequest, ConsultationRequest
from services.decorators import DEFAULT_SERVICES
from django.views.decorators.http import require_POST
from .decorators import require_premium_plan
from django.utils.dateparse import parse_date
from django.db.models import Q
import hashlib
import secrets

# Password reset imports
from django.contrib.auth.views import PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from .password_forms import CustomPasswordResetForm, CustomSetPasswordForm


@login_required
def profile_dashboard(request):
    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    subscription = (
        UserSubscription.objects.filter(user=user)
        .order_by('-start_date', '-created_at')
        .first()
    )

    plan_label = subscription.plan_label if subscription else 'Free'
    subscription_status = subscription.status if subscription else 'Free'
    next_billing_date = subscription.next_billing_date if subscription else None
    billing_cycle_label = subscription.billing_cycle_label if subscription else 'N/A'
    is_premium = subscription.is_premium if subscription else False

    raw_services = ServiceUsage.objects.filter(
        user=user,
        service_name__in=list(DEFAULT_SERVICES.keys()),
    )
    services = []
    for usage in raw_services:
        label = DEFAULT_SERVICES.get(usage.service_name, usage.service_name)
        usage.service_name = label
        services.append(usage)

    invoices = Invoice.objects.filter(client=user).order_by('-issued_date')[:5]
    
    logs = ActivityLog.objects.filter(user=user).order_by('-timestamp')[:10]

    consultations = ConsultationRequest.objects.filter(user=user).order_by('-created_at')[:5]

    last_selection = (
        UserPaymentSelection.objects.filter(user=user, status='completed')
        .order_by('-selected_at')
        .first()
    )
    payment_method_label = "Not set"
    if last_selection and isinstance(last_selection.session_data, dict):
        brand = last_selection.session_data.get('card_brand')
        last4 = last_selection.session_data.get('card_last4')
        if brand and last4:
            payment_method_label = f"{brand.title()} •••• {last4}"
        else:
            payment_method_label = "Card on file"

    last_login_ip = None
    last_login_log = ActivityLog.objects.filter(user=user, action='login').order_by('-timestamp').first()
    if last_login_log and last_login_log.ip_address:
        last_login_ip = last_login_log.ip_address

    last_login = user.last_login

    email_verified = getattr(profile, "email_verified", False)
    two_factor_enabled = getattr(profile, "two_factor_enabled", False)

    plan_hint = ""
    if plan_label == "Free":
        plan_hint = "Best for testing the platform before starting a full project."
    elif plan_label == "Basic":
        plan_hint = "Perfect for small teams starting with automation and analytics."
    elif plan_label == "Premium":
        plan_hint = "Unlimited access to platform capabilities for growing organizations."
    
    context = {
        'profile': profile,
        'subscription': subscription,
        'services': services,
        'invoices': invoices,
        'logs': logs,
        'plan_label': plan_label,
        'subscription_status': subscription_status,
        'next_billing_date': next_billing_date,
        'billing_cycle_label': billing_cycle_label,
        'is_premium': is_premium,
        'payment_method_label': payment_method_label,
        'last_login': last_login,
        'last_login_ip': last_login_ip,
        'email_verified': email_verified,
        'two_factor_enabled': two_factor_enabled,
        'plan_hint': plan_hint,
        'consultations': consultations,
        'active_tab': 'overview'
    }
    return render(request, 'users/profile_dashboard.html', context)


@login_required
def notification_preferences(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = NotificationPreferencesForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Notification preferences updated.')
            return redirect('users:profile_dashboard')
    else:
        form = NotificationPreferencesForm(instance=profile)
    return render(request, 'users/notification_preferences.html', {'form': form})


@login_required
def delete_account(request):
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('users:profile_dashboard')
    user = request.user
    ActivityLog.objects.create(
        user=user,
        action='account_deleted',
        ip_address=_get_client_ip(request),
    )
    user.is_active = False
    user.save()
    auth_logout(request)
    messages.success(request, 'Your account has been deactivated.')
    return redirect('home')


@login_required
def two_factor_settings(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        enabled = request.POST.get('two_factor_enabled') == 'on'
        profile.two_factor_enabled = enabled
        profile.save()
        ActivityLog.objects.create(
            user=request.user,
            action='two_factor_enabled' if enabled else 'two_factor_disabled',
            ip_address=_get_client_ip(request),
        )
        messages.success(request, 'Two-factor authentication settings updated.')
        return redirect('users:profile_dashboard')
    return render(request, 'users/two_factor_settings.html', {'profile': profile})


@login_required
@require_premium_plan
def api_keys(request):
    qs = UserApiKey.objects.filter(user=request.user)
    active_keys = qs.filter(revoked_at__isnull=True)
    generated_key = None
    if request.method == 'POST':
        if 'create_key' in request.POST:
            name = request.POST.get('name') or 'API key'
            raw_key = secrets.token_urlsafe(32)
            key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
            prefix = raw_key[:10]
            UserApiKey.objects.create(
                user=request.user,
                name=name,
                key_prefix=prefix,
                key_hash=key_hash,
            )
            generated_key = raw_key
            ActivityLog.objects.create(
                user=request.user,
                action='api_key_created',
                ip_address=_get_client_ip(request),
                metadata={'name': name, 'prefix': prefix},
            )
        elif 'revoke_key' in request.POST:
            key_id = request.POST.get('key_id')
            key = qs.filter(id=key_id, revoked_at__isnull=True).first()
            if key:
                key.revoked_at = timezone.now()
                key.save()
                ActivityLog.objects.create(
                    user=request.user,
                    action='api_key_revoked',
                    ip_address=_get_client_ip(request),
                    metadata={'name': key.name, 'prefix': key.key_prefix},
                )
    context = {
        'active_keys': active_keys,
        'generated_key': generated_key,
    }
    return render(request, 'users/api_keys.html', context)


@login_required
def consultations_list(request):
    user = request.user
    qs = ConsultationRequest.objects.filter(user=user)

    topic = request.GET.get('topic') or ''
    search = request.GET.get('q') or ''
    date_from = request.GET.get('from') or ''
    date_to = request.GET.get('to') or ''

    if topic:
        qs = qs.filter(topic=topic)

    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(email__icontains=search)
            | Q(company__icontains=search)
            | Q(message__icontains=search)
        )

    if date_from:
        d_from = parse_date(date_from)
        if d_from:
            qs = qs.filter(created_at__date__gte=d_from)

    if date_to:
        d_to = parse_date(date_to)
        if d_to:
            qs = qs.filter(created_at__date__lte=d_to)

    qs = qs.order_by('-created_at')

    from django.core.paginator import Paginator

    paginator = Paginator(qs, 10)
    page_number = request.GET.get('page') or 1
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'topic': topic,
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'users/consultations_list.html', context)


@require_http_methods(["GET", "POST"])
def signup(request):
    """Handle user registration."""
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Start ERPNext Provisioning in background
            try:
                from .tasks import provision_erpnext_instance, send_verification_email
                provision_erpnext_instance.delay(user.id)
                
                # Async verification email
                from django.utils.http import urlsafe_base64_encode
                from django.utils.encoding import force_bytes
                from django.contrib.auth.tokens import default_token_generator
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                verify_url = request.build_absolute_uri(reverse('users:verify_email', args=[uid, token]))
                send_verification_email.delay(user.id, verify_url)
            except Exception:
                pass

            login(request, user)
            messages.success(request, 'Account created successfully! A verification email is being sent.')
            return redirect('users:onboarding')
        else:
            # Form has errors, re-render with errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            # Render the combined template with 'signup' active
            return render(request, 'registration/login.html', {'signup_form': form, 'active_panel': 'signup'})
    else:
        form = SignUpForm()
    
    return render(request, 'registration/login.html', {'signup_form': form, 'active_panel': 'signup'})


@require_http_methods(["GET", "POST"])
def login_view(request):
    """Simple email+password login view."""
    signup_form = SignUpForm() # Always provide signup form for the combined view
    
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        user = None
        if email and password:
            try:
                user_obj = User.objects.get(email__iexact=email)
                user = authenticate(request, username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None

        if user:
            login(request, user)
            # log activity
            ActivityLog.objects.create(user=user, action='login', ip_address=_get_client_ip(request), metadata={'method': 'email'})
            
            # Branding role redirects (priority: specific roles first)
            if user.groups.filter(name='Designers').exists():
                return redirect('branding:designer_dashboard')
            if user.groups.filter(name='Supervisors').exists():
                return redirect('branding:supervisor_dashboard')
            if user.is_staff or user.is_superuser:
                return redirect('branding:unified_dashboard')

            # Client: check if they have branding requests
            from branding.models import BrandingRequest
            if BrandingRequest.objects.filter(user=user).exists():
                return redirect('branding:my_requests')

            # Check profile for direct redirection
            try:
                profile, created = UserProfile.objects.get_or_create(user=user)
                if profile.service_type:
                    return redirect('services:index')
                else:
                    return redirect('users:onboarding')
            except Exception:
                pass
                
            # Default to onboarding if no profile/service type found
            return redirect('users:onboarding')
        else:
            messages.error(request, 'Invalid email or password')
            return render(request, 'registration/login.html', {'signup_form': signup_form, 'active_panel': 'login'})
    
    return render(request, 'registration/login.html', {'signup_form': signup_form, 'active_panel': 'login'})


def _get_client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


@require_http_methods(["GET"])
def verify_email(request, uidb64, token):
    from django.utils.http import urlsafe_base64_decode
    from django.utils.encoding import force_str
    from django.contrib.auth.tokens import default_token_generator
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except Exception:
        user = None

    if user and default_token_generator.check_token(user, token):
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.email_verified = True
        profile.save()
        ActivityLog.objects.create(user=user, action='email_verified', ip_address=_get_client_ip(request))
        messages.success(request, 'Email verified successfully.')
        return redirect('users:dashboard')
    messages.error(request, 'Invalid or expired verification link.')
    return redirect('home')


def _get_community_redirect(profile):
    """Helper to determine community redirect URL based on needs."""
    return redirect('community:home')


@login_required
def onboarding(request):
    """Handle user onboarding and service selection."""
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    # If service type is already selected, redirect to appropriate dashboard
    if profile.service_type:
        if profile.service_type == 'community':
            return _get_community_redirect(profile)
        return redirect('users:dashboard')

    if request.method == 'POST':
        form = OnboardingForm(request.POST, instance=profile)
        if form.is_valid():
            profile = form.save()
            # Log the onboarding action
            ActivityLog.objects.create(
                user=request.user, 
                action='onboarding_completed', 
                ip_address=_get_client_ip(request),
                metadata={
                    'service_type': profile.service_type,
                    'community_needs': profile.community_needs,
                    'project_desc': profile.project_description
                }
            )
            
            if profile.service_type == 'community':
                messages.success(request, 'Welcome to Community Services!')
                return _get_community_redirect(profile)
            
            messages.success(request, 'Welcome to the Full Platform!')
            return redirect('users:dashboard')
    else:
        form = OnboardingForm(instance=profile)
    
    return render(request, 'registration/onboarding.html', {'form': form})


@login_required
def dashboard(request):
    """User dashboard: profile, subscription, activity."""
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    # Ensure user has completed onboarding
    if not profile.service_type:
        return redirect('users:onboarding')
    
    # Redirect community users to their specific dashboard
    if profile.service_type == 'community':
        return redirect('community:dashboard')

    # get active subscription if any
    active_sub = UserSubscription.objects.filter(user=user, is_active=True).order_by('-start_date').first()
    # fallback: check latest UserPaymentSelection
    last_selection = None
    try:
        last_selection = UserPaymentSelection.objects.filter(user=user, status='completed').order_by('-selected_at').first()
    except Exception:
        last_selection = None

    # Get all activities, paginated
    from django.core.paginator import Paginator
    activities_list = ActivityLog.objects.filter(user=user).order_by('-timestamp')
    paginator = Paginator(activities_list, 25)  # 25 activities per page
    page_number = request.GET.get('page', 1)
    activities = paginator.get_page(page_number)

    # Team assignments (for staff or team members)
    from projects.models import ProjectPhase, PhaseTask, Project
    assigned_phases = ProjectPhase.objects.filter(assignee=user).select_related('project').order_by('project__title', 'id')
    assigned_tasks = PhaseTask.objects.filter(assigned_to=user).select_related('phase', 'phase__project').order_by('-completed_at', 'id')[:25]

    # Client Projects (for non-staff users)
    projects = []
    blocked_tasks = []
    delayed_phases = []
    
    # New queries for requests
    website_requests = WebsiteBuildRequest.objects.filter(user=user).order_by('-created_at')
    consultation_requests = ConsultationRequest.objects.filter(user=user).order_by('-created_at')
    
    if not user.is_staff:
        projects = Project.objects.filter(client=user).prefetch_related('phases').order_by('-updated_at')
        
        # Alerts for Full Platform Users
        delayed_phases = ProjectPhase.objects.filter(
            project__client=user, 
            status='DELAYED'
        ).select_related('project')
        
        blocked_tasks = PhaseTask.objects.filter(
            phase__project__client=user,
            status='BLOCKED'
        ).select_related('phase', 'phase__project')

    context = {
        'profile': profile,
        'subscription': active_sub,
        'last_selection': last_selection,
        'activities': activities,
        'assigned_phases': assigned_phases,
        'assigned_tasks': assigned_tasks,
        'projects': projects,
        'delayed_phases': delayed_phases,
        'blocked_tasks': blocked_tasks,
        'website_requests': website_requests,
        'consultation_requests': consultation_requests,
    }
    return render(request, 'users/dashboard.html', context)


@login_required
def profile_edit(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if request.method == 'POST':
        display_name = request.POST.get('display_name', '')
        bio = request.POST.get('bio', '')
        avatar = request.POST.get('avatar', '')
        company_name = request.POST.get('company_name', '')
        industry = request.POST.get('industry', '')
        company_size = request.POST.get('company_size', '')
        country = request.POST.get('country', '')
        profile.display_name = display_name
        profile.bio = bio
        profile.avatar = avatar
        profile.company_name = company_name
        profile.industry = industry
        profile.company_size = company_size
        profile.country = country
        profile.save()
        ActivityLog.objects.create(user=user, action='profile_update', ip_address=_get_client_ip(request))
        messages.success(request, 'Profile updated')
        return redirect('users:profile_dashboard')
    return render(request, 'users/profile_edit.html', {'profile': profile})


@login_required
def logout_view(request):
    ActivityLog.objects.create(user=request.user, action='logout', ip_address=_get_client_ip(request))
    auth_logout(request)
    return redirect('/')


# Password reset views (class-based, using custom forms and templates)
class UserPasswordResetView(PasswordResetView):
    template_name = 'registration/password_reset_form.html'
    email_template_name = 'emails/password_reset_email.html'
    subject_template_name = 'emails/password_reset_subject.txt'
    form_class = CustomPasswordResetForm
    success_url = '/users/password-reset/done/'

class UserPasswordResetDoneView(PasswordResetDoneView):
    template_name = 'registration/password_reset_done.html'

class UserPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'registration/password_reset_confirm.html'
    form_class = CustomSetPasswordForm
    success_url = '/users/password-reset/complete/'

class UserPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = 'registration/password_reset_complete.html'
