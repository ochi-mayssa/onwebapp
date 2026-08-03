"""
Rule-based estimation engine for the onboarding wizard.
Architecture is AI-ready: swap calculate() internals with an LLM call when ready.
"""

from decimal import Decimal


class EstimationResult:
    __slots__ = [
        'timeline_weeks', 'budget_min', 'budget_max', 'complexity',
        'team_size', 'recommended_package', 'technologies', 'breakdown',
    ]

    def __init__(self):
        self.timeline_weeks = 2
        self.budget_min = Decimal('499')
        self.budget_max = Decimal('999')
        self.complexity = 'Standard'
        self.team_size = 1
        self.recommended_package = 'basic_pkg'
        self.technologies = []
        self.breakdown = []

    @property
    def total_cost(self):
        return str(int((self.budget_min + self.budget_max) / 2))

    @property
    def total_days(self):
        return self.timeline_weeks * 7

    def to_dict(self):
        return {
            'timeline_weeks': self.timeline_weeks,
            'budget_min': float(self.budget_min),
            'budget_max': float(self.budget_max),
            'complexity': self.complexity,
            'team_size': self.team_size,
            'recommended_package': self.recommended_package,
            'technologies': self.technologies,
            'breakdown': self.breakdown,
            'total_cost': self.total_cost,
            'total_days': self.total_days,
        }


SERVICE_BASE_TIMELINE = {
    'web': 4,
    'brand': 2,
    'marketing': 3,
    'consulting': 1,
}

SERVICE_BASE_PRICE = {
    'web': Decimal('999'),
    'brand': Decimal('499'),
    'marketing': Decimal('699'),
    'consulting': Decimal('399'),
}

PAGE_COST = Decimal('75')
FEATURE_COST = Decimal('150')
ADDON_COST_MULTIPLIER = Decimal('1.0')

COMPLEXITY_FEATURES = {
    'booking_system': 3,
    'online_payments': 4,
    'customer_portal': 5,
    'admin_dashboard': 4,
    'inventory': 4,
    'appointment_system': 3,
    'membership': 3,
    'blog': 1,
    'newsletter': 1,
}

COMPLEXITY_INTEGRATIONS = {
    'payment_gateway': 3,
    'crm': 3,
    'email_marketing': 2,
    'multi_language': 2,
    'social_login': 2,
    'live_chat': 1,
    'whatsapp_chat': 1,
    'google_analytics': 1,
    'google_maps': 1,
    'seo': 1,
    'blog': 1,
    'newsletter': 1,
}


def calculate(session):
    """
    Calculate estimation from an OnboardingSession instance.
    Returns an EstimationResult.

    To integrate AI later, replace this function body with:
        response = ai_client.complete(prompt_from_session(session))
        return parse_ai_response(response)
    """
    result = EstimationResult()
    breakdown = []

    # 1. Service-based base
    total_timeline = 0
    total_base = Decimal('0')
    services = session.selected_services.all()

    if services.exists():
        for svc in services:
            t = SERVICE_BASE_TIMELINE.get(svc.category, 2)
            p = SERVICE_BASE_PRICE.get(svc.category, Decimal('499'))
            total_timeline += t
            total_base += p
            breakdown.append({
                'item': svc.name,
                'type': 'service',
                'timeline_weeks': t,
                'cost': float(p),
            })
    else:
        total_timeline = 3
        total_base = Decimal('799')
        breakdown.append({
            'item': 'Default Web Project',
            'type': 'service',
            'timeline_weeks': 3,
            'cost': 799,
        })

    # 2. Pages
    pages = session.required_pages or []
    page_cost = PAGE_COST * len(pages)
    if pages:
        total_timeline += max(1, len(pages) // 3)
        total_base += page_cost
        breakdown.append({
            'item': f'{len(pages)} Pages',
            'type': 'pages',
            'timeline_weeks': max(1, len(pages) // 3),
            'cost': float(page_cost),
        })

    # 3. Features (from selected_features — wizard step 6 saves here)
    features = session.selected_features or []
    special = session.special_features or []
    all_features = features + special
    feature_cost = Decimal('0')
    complexity_score = 0
    for feat in all_features:
        cost = FEATURE_COST
        feature_cost += cost
        complexity_score += COMPLEXITY_FEATURES.get(feat, 2)
    if all_features:
        extra_weeks = max(1, len(all_features) // 2)
        total_timeline += extra_weeks
        total_base += feature_cost
        breakdown.append({
            'item': f'{len(all_features)} Features',
            'type': 'features',
            'timeline_weeks': extra_weeks,
            'cost': float(feature_cost),
        })

    # 4. Integrations
    integrations = session.selected_features or []
    integration_cost = Decimal('0')
    for integ in integrations:
        score = COMPLEXITY_INTEGRATIONS.get(integ, 1)
        complexity_score += score
        integration_cost += Decimal(str(score * 100))
    if integrations:
        total_timeline += max(1, len(integrations) // 3)
        total_base += integration_cost
        breakdown.append({
            'item': f'{len(integrations)} Integrations',
            'type': 'integrations',
            'timeline_weeks': max(1, len(integrations) // 3),
            'cost': float(integration_cost),
        })

    # 5. Design style multiplier
    style_multipliers = {
        'modern': 1.0,
        'minimal': 0.9,
        'luxury': 1.3,
        'corporate': 1.1,
        'creative': 1.4,
        'dark': 1.0,
        'light': 1.0,
        'bold': 1.2,
        'elegant': 1.2,
    }
    style = (session.design_style or '').lower()
    multiplier = style_multipliers.get(style, 1.0)
    total_base = total_base * Decimal(str(multiplier))

    # 6. Determine complexity
    if complexity_score <= 5:
        complexity = 'Simple'
        team_size = 1
    elif complexity_score <= 12:
        complexity = 'Standard'
        team_size = 2
    elif complexity_score <= 20:
        complexity = 'Complex'
        team_size = 3
    else:
        complexity = 'Enterprise'
        team_size = 4

    # 7. Determine recommended package
    if total_base <= Decimal('600'):
        recommended = 'basic_pkg'
    elif total_base <= Decimal('1500'):
        recommended = 'standard_pkg'
    elif total_base <= Decimal('3000'):
        recommended = 'advanced_pkg'
    else:
        recommended = 'enterprise_pkg'

    # 8. Technologies
    technologies = ['HTML5', 'CSS3', 'JavaScript']
    if 'online_payments' in features or 'payment_gateway' in integrations:
        technologies.append('Stripe/PayPal')
    if 'blog' in features or 'blog' in integrations:
        technologies.append('CMS')
    if 'crm' in integrations:
        technologies.append('CRM Integration')
    if 'seo' in integrations:
        technologies.append('SEO Tools')
    if 'multi_language' in integrations:
        technologies.append('i18n Framework')
    if len(pages) > 5:
        technologies.append('React/Vue')

    # 9. Timeline cap
    total_timeline = max(2, min(total_timeline, 24))

    result.timeline_weeks = total_timeline
    result.budget_min = total_base * Decimal('0.85')
    result.budget_max = total_base * Decimal('1.15')
    result.complexity = complexity
    result.team_size = team_size
    result.recommended_package = recommended
    result.technologies = technologies
    result.breakdown = breakdown

    return result


def get_package_comparison(session):
    """Return comparison data for all packages."""
    estimation = calculate(session)
    base = float(estimation.budget_min)

    return {
        'basic': {
            'name': 'Basic',
            'price': 499,
            'deposit': 250,
            'description': 'Perfect for simple websites and quick launches.',
            'features': ['1-3 Pages', 'Responsive Design', 'Basic SEO', 'Contact Form', '1 Revision Round'],
            'timeline': '1-2 weeks',
            'fits': base <= 600,
        },
        'standard': {
            'name': 'Standard',
            'price': 999,
            'deposit': 500,
            'description': 'Ideal for growing businesses needing more features.',
            'features': ['5-8 Pages', 'Custom Design', 'Advanced SEO', 'CMS Integration', 'Blog Setup', '3 Revision Rounds', 'Analytics'],
            'timeline': '2-4 weeks',
            'fits': 600 < base <= 1500,
        },
        'advanced': {
            'name': 'Advanced',
            'price': 1999,
            'deposit': 1000,
            'description': 'For complex projects requiring scalable architecture.',
            'features': ['Unlimited Pages', 'Premium Design', 'Full SEO Suite', 'E-commerce Ready', 'Custom Integrations', 'Admin Dashboard', 'Unlimited Revisions', 'Priority Support'],
            'timeline': '4-8 weeks',
            'fits': 1500 < base <= 3000,
        },
        'enterprise': {
            'name': 'Enterprise',
            'price': 4999,
            'deposit': 2000,
            'description': 'Complete digital solution with dedicated team.',
            'features': ['Everything in Advanced', 'Dedicated Project Manager', 'Custom Development', 'API Integrations', 'Performance Optimization', 'Security Audit', '90-Day Support', 'Monthly Retainer Available'],
            'timeline': '8-16 weeks',
            'fits': base > 3000,
        },
        'recommended': estimation.recommended_package,
    }
