from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from .forms import (
    ConsultationForm, WebsiteBuildForm, APIRequestForm, APIRequestAdminActionForm,
    RPAConsultationForm,
)
from .models import WebsiteBuildRequest, APIRequest, RPAConsultationRequest
from .notifications import notify_admins, notify_client_submitted
from .notifications import notify_rpa_admins, notify_rpa_client_submitted

# Create your views here.


def index(request):
    if request.method == 'POST':
        form = ConsultationForm(request.POST)
        if form.is_valid():
            consultation = form.save(commit=False)
            if request.user.is_authenticated:
                consultation.user = request.user
            consultation.save()
            return render(request, 'home/index.html', {'form': ConsultationForm(), 'consultation_success': True})
    else:
        initial = {}
        if request.user.is_authenticated:
            user = request.user
            full_name = user.get_full_name().strip() if user.get_full_name() else ''
            initial['name'] = full_name or user.username
            initial['email'] = user.email
            profile = getattr(user, 'profile', None)
            if profile and profile.company_name:
                initial['company'] = profile.company_name
        form = ConsultationForm(initial=initial)
    return render(request, 'home/index.html', {'form': form})


# Unregistered: these views rendered templates that were never created, so the
# routes returned HTTP 500. They are kept here for reference and can be restored
# together with their templates. See home/urls.py.


# def use_cases(request):
#     """Marketing page highlighting key use cases."""
#     return render(request, 'home/use_cases.html')


def testimonials(request):
    """Marketing page showcasing customer testimonials."""
    return render(request, 'home/testimonials.html')


# def features(request):
#     """Product features overview page."""
#     return render(request, 'home/features.html')


def api_docs(request):
    """API documentation landing page."""
    return render(request, 'home/api_docs.html')

def about(request):
    return render(request, 'home/about.html')

def rpa_bpa(request):
    return render(request, 'automation/RPA & BPA.html')


def rpa_solutions(request):
    """RPA solutions landing page with the consultation request form.

    The page and the form share one URL: a successful submission redirects
    back with the reference stashed in the session so the browser never
    re-posts on refresh.
    """
    reference = ''
    if request.method == 'POST':
        # Honeypot: real visitors never see or fill this field. Silently drop bots.
        if request.POST.get('website', ''):
            return redirect('home:rpa_solutions')

        form = RPAConsultationForm(request.POST)
        if form.is_valid():
            rpa_request = form.save(commit=False)
            if request.user.is_authenticated:
                rpa_request.user = request.user

            # Duplicate guard: one similar submission per email per 24 hours.
            duplicate = RPAConsultationRequest.objects.filter(
                business_email__iexact=rpa_request.business_email,
                process_to_automate__iexact=rpa_request.process_to_automate.strip(),
                created_at__gte=timezone.now() - timedelta(hours=24),
            ).exists()
            if duplicate:
                form.add_error(
                    None,
                    'A similar consultation request from this email was already '
                    'submitted in the last 24 hours. We are already reviewing it - '
                    'no need to resend.',
                )
            else:
                rpa_request.save()
                notify_rpa_admins(rpa_request)
                notify_rpa_client_submitted(rpa_request)
                request.session['rpa_reference'] = rpa_request.reference
                return redirect(f"{reverse('home:rpa_solutions')}#consultation")
    else:
        reference = request.session.pop('rpa_reference', '')
        form = RPAConsultationForm()
        if request.user.is_authenticated:
            user = request.user
            full_name = user.get_full_name().strip() if user.get_full_name() else ''
            if full_name or user.username:
                form.fields['full_name'].initial = full_name or user.username
            if user.email:
                form.fields['business_email'].initial = user.email
            profile = getattr(user, 'profile', None)
            if profile and getattr(profile, 'company_name', ''):
                form.fields['company_name'].initial = profile.company_name

    return render(request, 'automation/rpa_solutions.html', {
        'form': form,
        'rpa_reference': reference,
    })

def automation_home(request):
    return render(request, 'automation/automationhome.html')

# def help_center(request):
#     return render(request, 'home/help_center.html')

def privacy(request):
    return render(request, 'home/privacy.html')

def terms(request):
    return render(request, 'home/terms.html')

# def security(request):
#     return render(request, 'home/security.html')

# def free_tools(request):
#     return render(request, 'home/tools.html')

# def demo_request(request):
#     return render(request, 'home/demo_request.html')

# def webinars(request):
#     return render(request, 'home/webinars.html')

def build_website(request):
    """Handle website build requests using proper Django Forms."""
    features_list = ["SEO", "Payments", "CMS", "Chatbot", "Automation", "Social"]
    if request.method == 'POST':
        name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip()
        company = request.POST.get('company', '')
        website_type = request.POST.get('project_type', '')
        budget = request.POST.get('budget', '')
        timeline = request.POST.get('timeline', '')
        message = request.POST.get('description', '')
        features = request.POST.getlist('features', [])

        if name and email:
            WebsiteBuildRequest.objects.create(
                user=request.user if request.user.is_authenticated else None,
                name=name,
                email=email,
                company=company,
                website_type=website_type,
                budget=budget,
                timeline=timeline,
                message=message,
                features=features,
            )
            if request.user.is_authenticated:
                return redirect('crm:client_tracking_portal')
            return render(request, 'home/index.html', {'submitted': True})
    else:
        form = WebsiteBuildForm()
    return render(request, 'home/build_request.html', {
        'form': form,
        'features_list': features_list
    })

# def design_system(request):
#     """Render the design system verification page."""
#     return render(request, 'design_system.html')

def video_explainer(request):
    """Render the video explainer page for users who prefer watching over reading."""
    return render(request, 'home/video_explainer.html')


def ux_design(request):
    """Marketing page for UX design services."""
    return render(request, 'Design/UX Design.html')


def ui_design(request):
    """Marketing page for UI design services."""
    return render(request, 'Design/UI Design.html')


def software_home(request):
    """Software development services landing page."""
    return render(request, 'software/home.html')


def web_development(request):
    """Web development services page."""
    return render(request, 'software/web_development.html')


def mobile_development(request):
    """Mobile app development services page."""
    return render(request, 'software/mobile_development.html')


def ecommerce_development(request):
    """eCommerce development services page."""
    return render(request, 'software/ecommerce_development.html')


def dashboard_development(request):
    """Dashboard development services page."""
    return render(request, 'software/dashboard_development.html')


def api_solutions(request):
    """API Solutions landing page."""
    return render(request, 'services/API.html')


def browser_web_automation(request):
    """Browser and web automation services page."""
    return render(request, 'software/browser_web_automation.html')


def erp_service(request):
    """ERP integration and implementation services page."""
    return render(request, 'services/erp-service.html')


def api_status(request):
    """Simple API status endpoint to respond to health checks."""
    from django.http import JsonResponse
    from django.utils import timezone
    return JsonResponse({
        'status': 'ok',
        'service': 'OnWebApp API',
        'version': '1.0',
        'timestamp': timezone.now().isoformat(),
    })


def request_api(request):
    """Render and process the public 'Request an API' form."""
    if request.method == 'POST':
        # Honeypot: real users never see or fill this field. Silently drop bots.
        if request.POST.get('website', ''):
            return redirect('home:request_api_success')

        form = APIRequestForm(request.POST)
        if form.is_valid():
            api_request = form.save(commit=False)
            if request.user.is_authenticated:
                api_request.user = request.user

            # Duplicate guard: one similar submission per email per 24 hours.
            duplicate = APIRequest.objects.filter(
                business_email__iexact=api_request.business_email.strip(),
                api_name_or_category__iexact=api_request.api_name_or_category.strip(),
                created_at__gte=timezone.now() - timedelta(hours=24),
            ).exists()
            if duplicate:
                form.add_error(
                    None,
                    'A similar request from this email was already submitted in the '
                    'last 24 hours. We are already reviewing it - no need to resend.',
                )
            else:
                api_request.save()
                notify_admins(api_request)
                notify_client_submitted(api_request)
                request.session['api_request_reference'] = api_request.reference
                return redirect('home:request_api_success')
    else:
        initial = {}
        if request.user.is_authenticated:
            user = request.user
            full_name = user.get_full_name().strip() if user.get_full_name() else ''
            initial['full_name'] = full_name or user.username
            initial['business_email'] = user.email
            profile = getattr(user, 'profile', None)
            if profile and getattr(profile, 'company_name', ''):
                initial['company_name'] = profile.company_name
        form = APIRequestForm(initial=initial)

    return render(request, 'services/api_request.html', {'form': form})


def request_api_success(request):
    """Confirmation page after a successful API request submission."""
    return render(request, 'services/api_request_success.html', {
        'reference': request.session.get('api_request_reference', ''),
    })


# ── Admin: API requests management ────────────────────────────────────────


superuser_required = user_passes_test(lambda u: u.is_active and u.is_superuser)


@superuser_required
def admin_api_requests(request):
    """Custom admin page listing all API requests (superusers only)."""
    qs = APIRequest.objects.select_related('assigned_to', 'user')

    show_archived = request.GET.get('archived') == '1'
    if not show_archived:
        qs = qs.filter(is_archived=False)

    status_filter = request.GET.get('status') or ''
    type_filter = request.GET.get('type') or ''
    search = (request.GET.get('q') or '').strip()

    if status_filter and dict(APIRequest.STATUS_CHOICES).get(status_filter):
        qs = qs.filter(status=status_filter)
    if type_filter and dict(APIRequest.REQUEST_TYPE_CHOICES).get(type_filter):
        qs = qs.filter(request_type=type_filter)
    if search:
        from django.db.models import Q
        qs = qs.filter(
            Q(reference__icontains=search)
            | Q(full_name__icontains=search)
            | Q(business_email__icontains=search)
            | Q(company_name__icontains=search)
            | Q(api_name_or_category__icontains=search)
        )

    base = APIRequest.objects.all()
    stats = {
        'total': base.filter(is_archived=False).count(),
        'pending': base.filter(is_archived=False, status='pending').count(),
        'under_review': base.filter(is_archived=False, status='under_review').count(),
        'in_progress': base.filter(is_archived=False, status='in_progress').count(),
        'completed': base.filter(is_archived=False, status='completed').count(),
        'rejected': base.filter(is_archived=False, status='rejected').count(),
        'archived': base.filter(is_archived=True).count(),
    }

    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'stats': stats,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'search': search,
        'show_archived': show_archived,
        'status_choices': APIRequest.STATUS_CHOICES,
        'type_choices': APIRequest.REQUEST_TYPE_CHOICES,
    }
    return render(request, 'services/admin_api_requests.html', context)


@superuser_required
def admin_api_request_detail(request, pk):
    """Manage a single API request: status, assignment, notes, history."""
    api_request = get_object_or_404(
        APIRequest.objects.select_related('assigned_to', 'user'), pk=pk,
    )

    if request.method == 'POST':
        # Capture BEFORE validation: ModelForm._post_clean() writes cleaned
        # data onto the instance during is_valid(), so reading it after would
        # already show the new status.
        old_status = api_request.status
        form = APIRequestAdminActionForm(request.POST, instance=api_request)
        if form.is_valid():
            new_status = form.cleaned_data['status']
            # Save everything except the status, then let change_status()
            # apply the transition (so the log + client email always fire).
            api_request = form.save(commit=False)
            api_request.status = old_status
            api_request.save()
            if api_request.change_status(new_status, changed_by=request.user):
                messages.success(
                    request,
                    f'{api_request.reference} moved to '
                    f'{api_request.get_status_display()} — the client was notified.',
                )
            else:
                messages.success(request, f'{api_request.reference} updated.')
            return redirect('home:admin_api_request_detail', pk=pk)
    else:
        form = APIRequestAdminActionForm(instance=api_request)

    history = api_request.status_logs.select_related('changed_by').order_by('-created_at')
    context = {
        'api_request': api_request,
        'form': form,
        'history': history,
    }
    return render(request, 'services/admin_api_request_detail.html', context)
