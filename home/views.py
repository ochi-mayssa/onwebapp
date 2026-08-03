from django.shortcuts import render
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
        form = WebsiteBuildForm(request.POST)
        if form.is_valid():
            website_request = form.save(commit=False)
            if request.user.is_authenticated:
                website_request.user = request.user
            website_request.save()
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


def api_status(request):
    """Simple API status endpoint to respond to health checks."""
    from django.http import JsonResponse
    return JsonResponse({
        'status': 'ok',
        'service': 'OnWebApp API',
        'version': '1.0',
        'timestamp': '2026-04-12T18:00:00Z'  # Current date
    })
