import json
import logging
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.conf import settings as django_settings
from django.core.mail import send_mail
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.utils import timezone
from users.models import UserProfile, ActivityLog, UserSubscription
from payments.models import UserPaymentSelection, PaymentPlan
from projects.models import Project, ProjectPhase, PhaseTask
from crm.models import Customer
from .models import WebsiteIntake, OnboardingSession, ServiceType, OnboardingAddon, BrandProfile
from .forms import (
    WebsiteIntakeForm, Step2ServiceForm, Step3BusinessForm,
    Step4ProjectForm, Step5DesignForm, Step6FeaturesForm,
    Step9AddonsForm, Step12PaymentForm, BrandAssistForm,
)
from .services import calculate, get_package_comparison

logger = logging.getLogger(__name__)


def is_community_user(user):
    return user.is_authenticated and hasattr(user, 'profile') and user.profile.service_type == 'community'


DESIGN_STYLES = [
    ('modern', 'Modern'),
    ('minimalist', 'Minimalist'),
    ('bold', 'Bold'),
    ('elegant', 'Elegant'),
    ('playful', 'Playful'),
    ('corporate', 'Corporate'),
]

TYPOGRAPHY_STYLES = [
    ('sans-serif', 'Sans Serif'),
    ('serif', 'Serif'),
    ('display', 'Display'),
    ('mono', 'Monospace'),
]

FEATURES = [
    ('ecommerce', 'E-Commerce'),
    ('blog', 'Blog / CMS'),
    ('analytics', 'Analytics Dashboard'),
    ('social', 'Social Integration'),
    ('membership', 'Membership / Gated'),
    ('booking', 'Booking System'),
    ('chat', 'Live Chat'),
    ('multilingual', 'Multi-language'),
]

PACKAGES = [
    {
        'slug': 'basic_pkg', 'name': 'Starter', 'price': 499,
        'description': 'Perfect for simple landing pages and small sites.',
        'features': ['1-3 Pages', 'Responsive Design', 'Basic SEO', 'Contact Form', '1 Revision Round'],
        'timeline': '2-3 weeks', 'recommended': False,
    },
    {
        'slug': 'standard_pkg', 'name': 'Growth', 'price': 999,
        'description': 'Ideal for growing businesses that need more pages and features.',
        'features': ['5-8 Pages', 'Custom Design', 'Advanced SEO', 'CMS / Blog', 'Analytics', '3 Revision Rounds'],
        'timeline': '4-6 weeks', 'recommended': True,
    },
    {
        'slug': 'advanced_pkg', 'name': 'Enterprise', 'price': 1999,
        'description': 'Full-featured solution for complex projects with custom needs.',
        'features': ['Unlimited Pages', 'Premium Design', 'Full SEO Suite', 'E-Commerce', 'Admin Panel', 'API Access', '90-Day Support'],
        'timeline': '6-10 weeks', 'recommended': False,
    },
]


# ---------------------------------------------------------------------------
# Seed data helpers
# ---------------------------------------------------------------------------

def _ensure_services_exist():
    services_data = [
        {'name': 'Website Development', 'slug': 'website-dev', 'category': 'web',
         'description': 'Custom-built websites tailored to your brand and business needs.',
         'icon': 'fas fa-code', 'estimated_duration': '3-6 weeks', 'base_price': 999,
         'complexity_weight': 5, 'order': 1},
        {'name': 'E-Commerce', 'slug': 'ecommerce', 'category': 'web',
         'description': 'Full-featured online stores with payment processing and inventory.',
         'icon': 'fas fa-shopping-cart', 'estimated_duration': '4-8 weeks', 'base_price': 1499,
         'complexity_weight': 7, 'order': 2},
        {'name': 'Landing Page', 'slug': 'landing-page', 'category': 'web',
         'description': 'High-converting single-page designs for campaigns and launches.',
         'icon': 'fas fa-rocket', 'estimated_duration': '1-2 weeks', 'base_price': 499,
         'complexity_weight': 2, 'order': 3},
        {'name': 'Portfolio', 'slug': 'portfolio', 'category': 'web',
         'description': 'Showcase your work with stunning visual presentations.',
         'icon': 'fas fa-briefcase', 'estimated_duration': '2-3 weeks', 'base_price': 699,
         'complexity_weight': 3, 'order': 4},
        {'name': 'Corporate Website', 'slug': 'corporate', 'category': 'web',
         'description': 'Professional enterprise-grade websites with advanced functionality.',
         'icon': 'fas fa-building', 'estimated_duration': '4-8 weeks', 'base_price': 1999,
         'complexity_weight': 6, 'order': 5},
        {'name': 'Brand Identity', 'slug': 'brand-identity', 'category': 'brand',
         'description': 'Complete brand systems including logo, colors, typography, and guidelines.',
         'icon': 'fas fa-palette', 'estimated_duration': '2-4 weeks', 'base_price': 899,
         'complexity_weight': 4, 'order': 6},
        {'name': 'Logo Design', 'slug': 'logo-design', 'category': 'brand',
         'description': 'Professional logo creation with multiple concepts and revisions.',
         'icon': 'fas fa-pen-nib', 'estimated_duration': '1-2 weeks', 'base_price': 399,
         'complexity_weight': 2, 'order': 7},
        {'name': 'UI/UX Design', 'slug': 'ui-ux', 'category': 'brand',
         'description': 'User-centered design with wireframes, prototypes, and testing.',
         'icon': 'fas fa-layer-group', 'estimated_duration': '3-5 weeks', 'base_price': 1299,
         'complexity_weight': 5, 'order': 8},
        {'name': 'SEO', 'slug': 'seo', 'category': 'marketing',
         'description': 'Search engine optimization to boost your organic visibility.',
         'icon': 'fas fa-search', 'estimated_duration': 'Ongoing', 'base_price': 599,
         'complexity_weight': 3, 'order': 9},
        {'name': 'Website Maintenance', 'slug': 'maintenance', 'category': 'consulting',
         'description': 'Regular updates, security patches, and performance monitoring.',
         'icon': 'fas fa-tools', 'estimated_duration': 'Monthly', 'base_price': 199,
         'complexity_weight': 1, 'order': 10},
        {'name': 'Digital Consulting', 'slug': 'consulting', 'category': 'consulting',
         'description': 'Strategic guidance for your digital transformation journey.',
         'icon': 'fas fa-lightbulb', 'estimated_duration': '1-2 weeks', 'base_price': 499,
         'complexity_weight': 2, 'order': 11},
    ]
    for data in services_data:
        ServiceType.objects.get_or_create(slug=data['slug'], defaults=data)


def _ensure_addons_exist():
    addons_data = [
        {'name': 'Hosting Setup', 'slug': 'hosting', 'description': '1 year premium hosting included', 'icon': 'fas fa-server', 'price': 149, 'order': 1},
        {'name': 'Domain Registration', 'slug': 'domain', 'description': '1 year domain registration', 'icon': 'fas fa-globe', 'price': 29, 'order': 2},
        {'name': 'Website Maintenance', 'slug': 'maint-3m', 'description': '3 months maintenance & support', 'icon': 'fas fa-shield-alt', 'price': 299, 'order': 3},
        {'name': 'Monthly SEO', 'slug': 'seo-monthly', 'description': '3 months SEO optimization', 'icon': 'fas fa-chart-line', 'price': 449, 'order': 4},
        {'name': 'Content Writing', 'slug': 'content', 'description': 'Professional copywriting for 5 pages', 'icon': 'fas fa-pen-fancy', 'price': 349, 'order': 5},
        {'name': 'Logo Design', 'slug': 'logo-addon', 'description': 'Professional logo with 3 concepts', 'icon': 'fas fa-pen-nib', 'price': 299, 'order': 6},
        {'name': 'Brand Identity', 'slug': 'brand-addon', 'description': 'Complete brand guidelines package', 'icon': 'fas fa-palette', 'price': 599, 'order': 7},
        {'name': 'Social Media Kit', 'slug': 'social-kit', 'description': 'Templates for 5 platforms', 'icon': 'fas fa-share-alt', 'price': 199, 'order': 8},
        {'name': 'Email Setup', 'slug': 'email-setup', 'description': 'Professional email configuration', 'icon': 'fas fa-envelope', 'price': 79, 'order': 9},
        {'name': 'Training Session', 'slug': 'training', 'description': '2-hour platform training', 'icon': 'fas fa-graduation-cap', 'price': 149, 'order': 10},
        {'name': 'Priority Support', 'slug': 'priority-support', 'description': '3 months priority support', 'icon': 'fas fa-headset', 'price': 249, 'order': 11},
    ]
    for data in addons_data:
        OnboardingAddon.objects.get_or_create(slug=data['slug'], defaults=data)


def _ensure_plans_exist():
    plans_data = [
        {'plan_type': 'basic_pkg', 'name': 'Basic Package', 'price': 499.00,
         'description': 'Simple websites, 1-3 pages, quick turnaround.',
         'features': ['1-3 Pages', 'Responsive Design', 'Basic SEO', 'Contact Form']},
        {'plan_type': 'standard_pkg', 'name': 'Standard Package', 'price': 999.00,
         'description': 'Growing business sites, multiple pages, CMS.',
         'features': ['5-8 Pages', 'Custom Design', 'Advanced SEO', 'CMS', 'Blog']},
        {'plan_type': 'advanced_pkg', 'name': 'Advanced Package', 'price': 1999.00,
         'description': 'Complex projects, scalable architecture.',
         'features': ['Unlimited Pages', 'Premium Design', 'Full SEO', 'E-commerce', 'Admin Panel']},
        {'plan_type': 'enterprise_pkg', 'name': 'Enterprise Package', 'price': 4999.00,
         'description': 'Complete digital solution with dedicated team.',
         'features': ['Everything in Advanced', 'Dedicated PM', 'Custom Dev', 'API', '90-Day Support']},
    ]
    for p in plans_data:
        PaymentPlan.objects.get_or_create(plan_type=p['plan_type'], defaults={
            'name': p['name'], 'price': p['price'], 'description': p['description'],
            'features': p['features'], 'duration_days': 365, 'payment_mode': 'payment', 'is_active': True,
        })


# ---------------------------------------------------------------------------
# Classic views (kept for backward compat)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_community_user, login_url='users:onboarding', redirect_field_name=None)
def home(request):
    _ensure_services_exist()
    _ensure_addons_exist()
    active_sessions = OnboardingSession.objects.filter(
        user=request.user, status__in=['draft', 'in_progress']
    ).order_by('-updated_at')
    completed_count = OnboardingSession.objects.filter(
        user=request.user, status='completed'
    ).count()
    return render(request, 'community/home.html', {
        'active_sessions': active_sessions,
        'completed_count': completed_count,
    })


@login_required
@user_passes_test(is_community_user, login_url='users:onboarding', redirect_field_name=None)
def dashboard(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    active_sub = UserSubscription.objects.filter(user=user, is_active=True).order_by('-start_date').first()
    last_selection = None
    try:
        last_selection = UserPaymentSelection.objects.filter(user=user, status='completed').order_by('-selected_at').first()
    except Exception:
        pass
    activities_list = ActivityLog.objects.filter(user=user).order_by('-timestamp')
    paginator = Paginator(activities_list, 25)
    activities = paginator.get_page(request.GET.get('page', 1))
    recent_activities = activities_list[:10]
    projects = Project.objects.filter(client=user).order_by('-updated_at')
    pending_approvals = ProjectPhase.objects.filter(
        project__client=user, approval_status='AWAITING_CLIENT'
    ).select_related('project')
    delayed_phases = ProjectPhase.objects.filter(
        project__client=user, status='DELAYED'
    ).select_related('project')
    active_session = OnboardingSession.objects.filter(
        user=user, status__in=['draft', 'in_progress']
    ).order_by('-updated_at').first()
    forum_posts_count = 0
    forum_comments_count = 0
    badges_count = 0
    try:
        forum_posts_count = user.forum_posts.filter(status='published').count()
    except Exception:
        pass
    try:
        from forum.models import ForumComment
        forum_comments_count = ForumComment.objects.filter(author=user).count()
    except Exception:
        pass
    badges_count = 0
    try:
        from forum.models import UserBadge
        badges_count = UserBadge.objects.filter(user=user).count()
    except Exception:
        pass
    stats = {
        'projects_count': projects.count(),
        'forum_posts_count': forum_posts_count,
        'forum_comments_count': forum_comments_count,
        'badges_count': badges_count,
    }
    return render(request, 'community/dashboard.html', {
        'profile': profile, 'subscription': active_sub, 'last_selection': last_selection,
        'activities': activities, 'projects': projects,
        'pending_approvals': pending_approvals, 'delayed_phases': delayed_phases,
        'recent_activities': recent_activities, 'active_session': active_session, 'stats': stats,
    })


# ---------------------------------------------------------------------------
# Onboarding Wizard
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_community_user, login_url='users:onboarding', redirect_field_name=None)
def wizard_start(request):
    _ensure_services_exist()
    _ensure_addons_exist()
    _ensure_plans_exist()

    existing = OnboardingSession.objects.filter(
        user=request.user, status__in=['draft', 'in_progress']
    ).order_by('-updated_at').first()

    force_new = request.GET.get('new') == '1' or request.POST.get('new') == '1'

    if existing and existing.current_step > 1 and not force_new:
        return redirect('community:wizard_step', step=existing.current_step)

    if request.method == 'POST':
        if force_new and existing:
            existing.status = 'cancelled'
            existing.save(update_fields=['status', 'updated_at'])
            session = OnboardingSession.objects.create(
                user=request.user, current_step=2, status='in_progress'
            )
        elif existing:
            session = existing
            session.current_step = 2
            session.status = 'in_progress'
            session.save(update_fields=['current_step', 'status', 'updated_at'])
        else:
            session = OnboardingSession.objects.create(
                user=request.user, current_step=2, status='in_progress'
            )
            ActivityLog.objects.create(
                user=request.user, action="Started onboarding wizard.",
            )
        return redirect('community:wizard_step', step=2)

    return render(request, 'community/wizard/step_01_welcome.html', {
        'session': None if force_new else existing,
        'force_new': force_new,
    })


@login_required
@user_passes_test(is_community_user, login_url='users:onboarding', redirect_field_name=None)
def wizard_step(request, step):
    step = int(step)
    if step < 1 or step > 13:
        return redirect('community:wizard_start')

    session = OnboardingSession.objects.filter(
        user=request.user, status__in=['draft', 'in_progress']
    ).order_by('-updated_at').first()

    if not session:
        return redirect('community:wizard_start')

    if step > session.current_step + 1:
        return redirect('community:wizard_step', step=session.current_step)

    step_handlers = {
        2: _handle_step2,
        3: _handle_step3,
        4: _handle_step4,
        5: _handle_step5,
        6: _handle_step6,
        7: _handle_step7,
        8: _handle_step8,
        9: _handle_step9,
        10: _handle_step10,
        11: _handle_step11,
        12: _handle_step12,
        13: _handle_step13,
    }

    handler = step_handlers.get(step)
    if handler:
        return handler(request, session)

    return redirect('community:wizard_start')


def _handle_step2(request, session):
    services = ServiceType.objects.filter(is_active=True)

    if request.method == 'POST':
        selected_slugs = request.POST.getlist('services')
        session.selected_services.set(ServiceType.objects.filter(slug__in=selected_slugs))
        session.mark_step_complete(2)
        session.current_step = 3
        session.save(update_fields=['current_step', 'updated_at'])
        return redirect('community:wizard_step', step=3)

    selected_slugs = [s.slug for s in session.selected_services.all()]

    return render(request, 'community/wizard/step_02_service.html', {
        'session': session, 'services': services, 'selected_slugs': selected_slugs,
    })


def _handle_step3(request, session):
    if request.method == 'POST':
        session.business_name = request.POST.get('business_name', '')
        session.industry = request.POST.get('industry', '')
        session.business_description = request.POST.get('business_description', '')
        session.target_audience = request.POST.get('target_audience', '')
        session.existing_website = request.POST.get('existing_website', '')
        session.competitors = request.POST.get('competitors', '')
        session.mark_step_complete(3)
        session.current_step = 4
        session.save()
        return redirect('community:wizard_step', step=4)

    return render(request, 'community/wizard/step_03_business.html', {
        'session': session,
    })


def _handle_step4(request, session):
    if request.method == 'POST':
        session.project_name = request.POST.get('project_name', '')
        session.project_goals = request.POST.get('project_goals', '')
        session.budget_range = request.POST.get('budget_range', '')
        launch = request.POST.get('target_launch_date', '')
        if launch:
            try:
                session.target_launch_date = launch
            except Exception:
                pass
        session.additional_notes = request.POST.get('additional_notes', '')
        session.mark_step_complete(4)
        session.current_step = 5
        session.save()
        return redirect('community:wizard_step', step=5)

    return render(request, 'community/wizard/step_04_project.html', {
        'session': session,
    })


def _handle_step5(request, session):
    if request.method == 'POST':
        session.design_style = request.POST.get('design_style', '')
        session.primary_color = request.POST.get('primary_color', '#6366f1')
        session.accent_color = request.POST.get('accent_color', '#8b5cf6')
        session.typography_style = request.POST.get('typography_style', '')
        session.inspiration_sites = request.POST.get('inspiration_sites', '')
        session.mark_step_complete(5)
        session.current_step = 6
        session.save()
        return redirect('community:wizard_step', step=6)

    return render(request, 'community/wizard/step_05_design.html', {
        'session': session,
        'design_styles': DESIGN_STYLES,
        'typography_styles': TYPOGRAPHY_STYLES,
    })


def _handle_step6(request, session):
    if request.method == 'POST':
        session.selected_features = request.POST.getlist('features')
        session.integrations = request.POST.get('integrations', '')
        session.mark_step_complete(6)
        session.current_step = 7
        session.save()
        return redirect('community:wizard_step', step=7)

    selected_features = session.selected_features or []

    return render(request, 'community/wizard/step_06_features.html', {
        'session': session,
        'features': FEATURES,
        'selected_features': selected_features,
    })


def _handle_step7(request, session):
    estimation = calculate(session)
    session.estimation_data = estimation.to_dict()
    session.save(update_fields=['estimation_data', 'updated_at'])

    if request.method == 'POST':
        session.mark_step_complete(7)
        session.current_step = 8
        session.save()
        return redirect('community:wizard_step', step=8)

    return render(request, 'community/wizard/step_07_estimate.html', {
        'session': session, 'estimation': estimation,
    })


def _handle_step8(request, session):
    comparison = get_package_comparison(session)

    if request.method == 'POST':
        selected = request.POST.get('package', '')
        if selected:
            session.selected_package = selected
            session.recommended_package = comparison.get('recommended', '')
            session.mark_step_complete(8)
            session.current_step = 9
            session.save()
            return redirect('community:wizard_step', step=9)

    return render(request, 'community/wizard/step_08_package.html', {
        'session': session, 'packages': PACKAGES,
    })


def _handle_step9(request, session):
    addons = OnboardingAddon.objects.filter(is_active=True)

    if request.method == 'POST':
        selected_slugs = request.POST.getlist('addons')
        addon_list = []
        total = Decimal('0')
        for addon in addons:
            if addon.slug in selected_slugs:
                addon_list.append({'slug': addon.slug, 'name': addon.name, 'price': float(addon.price)})
                total += addon.price
        session.selected_addons = addon_list
        session.addons_total = total
        session.mark_step_complete(9)
        session.current_step = 10
        session.save()
        return redirect('community:wizard_step', step=10)

    selected_addons = [a['slug'] for a in session.selected_addons] if session.selected_addons else []

    return render(request, 'community/wizard/step_09_addons.html', {
        'session': session, 'addons': addons, 'selected_addons': selected_addons,
    })


def _handle_step10(request, session):
    estimation = calculate(session)

    if request.method == 'POST':
        if not session.estimation_data:
            session.estimation_data = estimation.to_dict()
        session.mark_step_complete(10)
        session.current_step = 11
        session.save()
        return redirect('community:wizard_step', step=11)

    return render(request, 'community/wizard/step_10_summary.html', {
        'session': session, 'estimation': estimation,
    })


def _handle_step11(request, session):
    if session.estimation_data:
        estimation = calculate(session)
    else:
        estimation = calculate(session)
        session.estimation_data = estimation.to_dict()

    if request.method == 'POST':
        if not session.estimation_data:
            session.estimation_data = estimation.to_dict()
        session.selected_package = estimation.recommended_package
        session.mark_step_complete(11)
        session.current_step = 12
        session.save()
        return redirect('community:wizard_step', step=12)

    return render(request, 'community/wizard/step_11_proposal.html', {
        'session': session, 'estimation': estimation,
    })


def _handle_step12(request, session):
    package_prices = {'basic_pkg': 499, 'standard_pkg': 999, 'advanced_pkg': 1999, 'enterprise_pkg': 4999}
    package_price = package_prices.get(session.selected_package, 999)
    addons_cost = session.addons_total or Decimal('0')
    total = Decimal(str(package_price)) + addons_cost

    if request.method == 'POST':
        session.payment_method = 'stripe'
        session.deposit_amount = total / 2
        session.total_amount = total
        session.mark_step_complete(12)
        session.current_step = 13
        session.payment_completed = True
        session.save()
        _generate_workspace(session)
        return redirect('community:wizard_step', step=13)

    return render(request, 'community/wizard/step_12_payment.html', {
        'session': session,
        'services_cost': str(int(package_price)),
        'addon_cost': str(int(addons_cost)),
        'total_due': str(int(total)),
        'payment_schedule': '50% upfront, 50% on completion',
    })


def _handle_step13(request, session):
    if request.method == 'POST':
        session.complete()
        return redirect('community:dashboard')

    project = session.linked_project
    return render(request, 'community/wizard/step_13_workspace.html', {
        'session': session, 'project': project,
    })


# ---------------------------------------------------------------------------
# Workspace Generation
# ---------------------------------------------------------------------------

def _generate_workspace(session):
    services_text = ', '.join([s.name for s in session.selected_services.all()]) or 'Web Project'
    project = Project.objects.create(
        client=session.user,
        title=f"{session.business_name or 'Project'} - {services_text}",
        description=(
            f"Industry: {session.industry}\n"
            f"Description: {session.business_description}\n"
            f"Target: {session.target_audience}\n"
            f"Style: {session.design_style}"
        ),
        project_type='WEBSITE',
        current_status='PLANNING',
        current_phase='PLANNING',
        brand_color=session.primary_color or '#000000',
    )
    session.linked_project = project
    session.save(update_fields=['linked_project'])

    phases_data = [
        ('PLANNING', 'Planning & Requirements'),
        ('DESIGN', 'Design Drafts'),
        ('DEVELOPMENT', 'Development'),
        ('TESTING', 'Testing & QA'),
        ('LAUNCH', 'Launch'),
    ]
    for ptype, _ in phases_data:
        ProjectPhase.objects.create(
            project=project, phase_type=ptype, status='NOT_STARTED',
            is_locked=True, client_visible_notes=f'{ptype} phase'
        )

    planning_phase = project.phases.filter(phase_type='PLANNING').first()
    if planning_phase:
        tasks = [
            'Review project requirements',
            'Finalize sitemap and page structure',
            'Set up development environment',
            'Create initial wireframes',
        ]
        for task_name in tasks:
            PhaseTask.objects.create(
                phase=planning_phase, name=task_name,
                priority='HIGH', status='TODO'
            )

    if session.user.email:
        Customer.objects.get_or_create(
            email=session.user.email,
            defaults={
                'user': session.user,
                'name': session.user.get_full_name() or session.user.username,
                'lifecycle_stage': 'LEAD',
                'company_name': session.business_name or '',
                'industry': session.industry or '',
                'source': 'Onboarding Wizard',
            }
        )

    ActivityLog.objects.create(
        user=session.user,
        action=f"Onboarding completed. Project '{project.title}' created.",
    )

    _send_completion_email(session, project)


def _send_completion_email(session, project):
    if not session.user.email:
        return
    services = ', '.join([s.name for s in session.selected_services.all()]) or 'Web Project'
    budget = session.estimation_data.get('budget_high', 'N/A') if session.estimation_data else 'N/A'
    timeline = session.estimation_data.get('timeline_weeks', 'N/A') if session.estimation_data else 'N/A'

    subject = f"Project Created: {project.title}"
    plain = (
        f"Hi {session.user.get_full_name() or session.user.username},\n\n"
        f"Your onboarding is complete and your project has been created!\n\n"
        f"Project: {project.title}\n"
        f"Package: {session.get_package_display()}\n"
        f"Services: {services}\n"
        f"Estimated Budget: ${budget}\n"
        f"Timeline: {timeline} weeks\n\n"
        f"Your project team will reach out within 24 hours.\n\n"
        f"- The OnWebApp Team"
    )
    html = (
        f"<h2>Your project is ready!</h2>"
        f"<p>Hi <strong>{session.user.get_full_name() or session.user.username}</strong>,</p>"
        f"<p>Your onboarding is complete and your project has been created.</p>"
        f"<table style='border-collapse:collapse;width:100%;max-width:480px;'>"
        f"<tr><td style='padding:8px 12px;font-weight:600;'>Project</td><td style='padding:8px 12px;'>{project.title}</td></tr>"
        f"<tr><td style='padding:8px 12px;font-weight:600;'>Package</td><td style='padding:8px 12px;'>{session.get_package_display()}</td></tr>"
        f"<tr><td style='padding:8px 12px;font-weight:600;'>Services</td><td style='padding:8px 12px;'>{services}</td></tr>"
        f"<tr><td style='padding:8px 12px;font-weight:600;'>Budget</td><td style='padding:8px 12px;'>${budget}</td></tr>"
        f"<tr><td style='padding:8px 12px;font-weight:600;'>Timeline</td><td style='padding:8px 12px;'>{timeline} weeks</td></tr>"
        f"</table>"
        f"<p style='margin-top:20px;'>Your project team will reach out within <strong>24 hours</strong>.</p>"
        f"<p>- The OnWebApp Team</p>"
    )
    try:
        send_mail(
            subject, plain, django_settings.DEFAULT_FROM_EMAIL,
            [session.user.email], html_message=html, fail_silently=True,
        )
        logger.info("Onboarding email sent to %s for project %s", session.user.email, project.id)
    except Exception:
        logger.exception("Failed to send onboarding email to %s", session.user.email)


# ---------------------------------------------------------------------------
# Autosave endpoint (AJAX)
# ---------------------------------------------------------------------------

@login_required
def wizard_autosave(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    session = OnboardingSession.objects.filter(
        user=request.user, status__in=['draft', 'in_progress']
    ).order_by('-updated_at').first()

    if not session:
        return JsonResponse({'error': 'No active session'}, status=404)

    step = data.get('step', session.current_step)
    field_updates = data.get('data', {})

    field_map = {
        3: ['business_name', 'industry', 'business_description', 'target_audience', 'existing_website', 'competitors'],
        4: ['project_name', 'project_goals', 'budget_range', 'additional_notes'],
        5: ['design_style', 'primary_color', 'accent_color', 'typography_style', 'inspiration_sites'],
        6: ['selected_features', 'integrations'],
    }

    allowed = field_map.get(step, [])
    for key, value in field_updates.items():
        if key in allowed:
            setattr(session, key, value)

    session.save()
    return JsonResponse({'status': 'saved', 'step': step})


# ---------------------------------------------------------------------------
# Legacy views (kept for backward compat)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_community_user, login_url='users:onboarding', redirect_field_name=None)
def website_building(request):
    if request.method == 'POST':
        form = WebsiteIntakeForm(request.POST)
        if form.is_valid():
            intake = form.save(commit=False)
            intake.user = request.user
            intake.save()
            request.session['website_intake_id'] = intake.id
            Project.objects.create(
                client=request.user,
                title=f"Website Project - {intake.company_name or intake.full_name}",
                description=f"Project Type: {intake.get_project_type_display()}\nGoals: {', '.join(intake.website_goals)}",
                current_status='PLANNING',
                project_type='WEBSITE'
            )
            return redirect('community:package_selection')
    else:
        form = WebsiteIntakeForm(initial={
            'full_name': f"{request.user.first_name} {request.user.last_name}",
            'email': request.user.email,
        })
    return render(request, 'community/website_intake.html', {'form': form})


@login_required
@user_passes_test(is_community_user, login_url='users:onboarding', redirect_field_name=None)
def package_selection(request):
    _ensure_plans_exist()
    basic_plan = PaymentPlan.objects.get(plan_type='basic_pkg')
    standard_plan = PaymentPlan.objects.get(plan_type='standard_pkg')
    advanced_plan = PaymentPlan.objects.get(plan_type='advanced_pkg')
    return render(request, 'community/package_selection.html', {
        'basic_plan': basic_plan, 'standard_plan': standard_plan, 'advanced_plan': advanced_plan,
    })


@login_required
def brand_assist(request):
    is_staff = request.user.is_staff
    target_user = request.user

    if is_staff:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        client_id = request.GET.get('client') or request.POST.get('client_user')
        if client_id:
            target_user = get_object_or_404(User, id=client_id)
        else:
            first_client = User.objects.filter(is_staff=False).exclude(brand_profiles=None).first()
            if first_client:
                target_user = first_client

    profiles = BrandProfile.objects.filter(user=target_user)
    active_profile = None
    form = BrandAssistForm()

    profile_id = request.GET.get('profile')
    if profile_id:
        active_profile = get_object_or_404(BrandProfile, id=profile_id, user=target_user)
        form = BrandAssistForm(instance=active_profile)

    if request.method == 'POST':
        if request.POST.get('delete'):
            BrandProfile.objects.filter(id=request.POST['delete'], user=target_user).delete()
            messages.success(request, 'Brand profile deleted.')
            return redirect(f"{reverse('community:brand_assist')}?client={target_user.id}" if is_staff else 'community:brand_assist')
        form = BrandAssistForm(request.POST)
        edit_id = request.POST.get('profile_id')
        if edit_id:
            instance = get_object_or_404(BrandProfile, id=edit_id, user=target_user)
            form = BrandAssistForm(request.POST, instance=instance)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = target_user
            _generate_brand_kit(profile)
            profile.save()
            messages.success(request, 'Brand profile saved and kit generated.')
            url = f"{reverse('community:brand_assist')}?profile={profile.id}"
            if is_staff:
                url += f"&client={target_user.id}"
            return redirect(url)
        else:
            messages.error(request, 'Please correct the errors below.')

    ctx = {
        'form': form,
        'profiles': profiles,
        'active_profile': active_profile,
    }
    if is_staff:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        clients = User.objects.filter(is_staff=False).order_by('username')
        ctx['clients'] = clients
        ctx['selected_client'] = target_user
        ctx['is_staff'] = True

    return render(request, 'community/brand_assist.html', ctx)


def _generate_brand_kit(profile):
    personality = profile.personality
    primary = profile.primary_color
    secondary = profile.secondary_color
    accent = profile.accent_color

    palette = {
        'primary': primary,
        'secondary': secondary,
        'accent': accent,
        'background': '#ffffff',
        'text': '#1a1a2e',
        'muted': '#6b7280',
    }
    if personality == 'luxurious':
        palette.update({'background': '#0a0a0a', 'text': '#f5f0e8', 'muted': '#a09080'})
    elif personality == 'playful':
        palette.update({'background': '#fff9f0', 'accent': '#f59e0b'})
    elif personality == 'minimal':
        palette.update({'background': '#fafafa', 'text': '#333333', 'muted': '#999999'})
    elif personality == 'edgy':
        palette.update({'background': '#0d0d0d', 'text': '#e0e0e0', 'accent': '#ef4444'})
    elif personality == 'friendly':
        palette.update({'background': '#fef9ef', 'accent': '#ec4899'})
    elif personality == 'innovative':
        palette.update({'background': '#f0f9ff', 'accent': '#06b6d4'})

    typography_map = {
        'professional': {'headings': 'Playfair Display', 'body': 'Inter', 'style': 'Serif headings, sans-serif body'},
        'playful': {'headings': 'Fredoka One', 'body': 'Nunito', 'style': 'Rounded, friendly'},
        'luxurious': {'headings': 'Cormorant Garamond', 'body': 'Lato', 'style': 'Elegant serif, clean sans'},
        'minimal': {'headings': 'Helvetica Neue', 'body': 'Open Sans', 'style': 'Clean, neutral'},
        'edgy': {'headings': 'Bebas Neue', 'body': 'Roboto Condensed', 'style': 'Bold, condensed'},
        'friendly': {'headings': 'Quicksand', 'body': 'Source Sans Pro', 'style': 'Soft, approachable'},
        'innovative': {'headings': 'Space Grotesk', 'body': 'DM Sans', 'style': 'Modern, geometric'},
    }
    typography = typography_map.get(personality, typography_map['professional'])

    voice_map = {
        'formal': ['We are committed to delivering exceptional value.', 'Our solutions meet the highest industry standards.'],
        'conversational': ['Hey there! Let us help you build something amazing.', "We've got your back every step of the way."],
        'humorous': ["Let's make your website so good, your competitors will cry.", "We code so you can put your feet up."],
        'inspirational': ['Empower your vision. Build your legacy.', 'Dream big. We will build it together.'],
        'direct': ['We build websites that work. Period.', 'No fluff. Just results-driven development.'],
        'storytelling': ['Every brand has a story. Let us tell yours.', 'From a simple idea to a digital masterpiece.'],
    }
    voice_examples = voice_map.get(profile.brand_voice, voice_map['formal'])

    profile.generated_palette = palette
    profile.generated_typography = typography
    profile.generated_voice_examples = voice_examples
