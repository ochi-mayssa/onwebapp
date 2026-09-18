from django.shortcuts import render, redirect
from .forms import ConsultationForm, WebsiteBuildForm
from .models import WebsiteBuildRequest

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


def use_cases(request):
    """Marketing page highlighting key use cases."""
    return render(request, 'home/use_cases.html')


def testimonials(request):
    """Marketing page showcasing customer testimonials."""
    return render(request, 'home/testimonials.html')


def features(request):
    """Product features overview page."""
    return render(request, 'home/features.html')


def api_docs(request):
    """API documentation landing page."""
    return render(request, 'home/api_docs.html')

def about(request):
    return render(request, 'home/about.html')

def help_center(request):
    return render(request, 'home/help_center.html')

def privacy(request):
    return render(request, 'home/privacy.html')

def terms(request):
    return render(request, 'home/terms.html')

def security(request):
    return render(request, 'home/security.html')

def free_tools(request):
    return render(request, 'home/tools.html')

def demo_request(request):
    return render(request, 'home/demo_request.html')

def webinars(request):
    return render(request, 'home/webinars.html')

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

def design_system(request):
    """Render the design system verification page."""
    return render(request, 'design_system.html')

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
