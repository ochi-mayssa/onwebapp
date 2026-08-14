"""Global search service for the Root Dashboard.

Searches across multiple entities: Users, Customers, Projects, Branding,
ERP, Payments, Subscriptions. Returns compact results with links.
"""
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

MAX_RESULTS_PER_CATEGORY = 5


def search_users(query):
    """Search users by email, username, or name."""
    results = []
    try:
        qs = User.objects.filter(
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        ).distinct()[:MAX_RESULTS_PER_CATEGORY]
        for u in qs:
            results.append({
                'type': 'user',
                'title': u.get_full_name() or u.username,
                'subtitle': u.email,
                'url': '/admin/auth/user/{}/change/'.format(u.pk),
                'icon': 'fas fa-user',
                'color': '#6366f1',
            })
    except Exception:
        pass
    return results


def search_customers(query):
    """Search CRM customers."""
    results = []
    try:
        from crm.models import Customer
        qs = Customer.objects.filter(
            Q(name__icontains=query) |
            Q(email__icontains=query) |
            Q(company_name__icontains=query)
        ).distinct()[:MAX_RESULTS_PER_CATEGORY]
        for c in qs:
            results.append({
                'type': 'customer',
                'title': c.name,
                'subtitle': c.company_name or c.email or '',
                'url': '/crm/customers/{}/'.format(c.pk),
                'icon': 'fas fa-user-tie',
                'color': '#0ea5e9',
            })
    except (ImportError, Exception):
        pass
    return results


def search_projects(query):
    """Search projects."""
    results = []
    try:
        from projects.models import Project
        qs = Project.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        ).distinct()[:MAX_RESULTS_PER_CATEGORY]
        for p in qs:
            results.append({
                'type': 'project',
                'title': p.name,
                'subtitle': getattr(p, 'current_status', ''),
                'url': '/projects/{}/'.format(p.pk),
                'icon': 'fas fa-project-diagram',
                'color': '#6366f1',
            })
    except (ImportError, Exception):
        pass
    return results


def search_branding(query):
    """Search branding requests."""
    results = []
    try:
        from branding.models import BrandingRequest
        qs = BrandingRequest.objects.filter(
            Q(project_name__icontains=query) |
            Q(client_name__icontains=query)
        ).distinct()[:MAX_RESULTS_PER_CATEGORY]
        for b in qs:
            results.append({
                'type': 'branding',
                'title': b.project_name,
                'subtitle': getattr(b, 'client_name', ''),
                'url': '/branding/dashboard/',
                'icon': 'fas fa-palette',
                'color': '#8b5cf6',
            })
    except (ImportError, Exception):
        pass
    return results


def search_erp(query):
    """Search ERP clients."""
    results = []
    try:
        from users.models import UserERP
        qs = UserERP.objects.filter(
            Q(client_name__icontains=query) |
            Q(client_code__icontains=query)
        ).distinct()[:MAX_RESULTS_PER_CATEGORY]
        for e in qs:
            results.append({
                'type': 'erp',
                'title': e.client_name,
                'subtitle': getattr(e, 'client_code', ''),
                'url': '/services/erp-integration/',
                'icon': 'fas fa-industry',
                'color': '#f97316',
            })
    except (ImportError, Exception):
        pass
    return results


def search_payments(query):
    """Search payments."""
    results = []
    try:
        from payments.models import Payment
        qs = Payment.objects.filter(
            Q(stripe_payment_id__icontains=query) |
            Q(customer_email__icontains=query)
        ).distinct()[:MAX_RESULTS_PER_CATEGORY]
        for p in qs:
            results.append({
                'type': 'payment',
                'title': p.stripe_payment_id or 'Payment #{}'.format(p.pk),
                'subtitle': getattr(p, 'customer_email', ''),
                'url': '/payments/plans/',
                'icon': 'fas fa-credit-card',
                'color': '#10b981',
            })
    except (ImportError, Exception):
        pass
    return results


def global_search(query):
    """
    Search across all entities and return aggregated results.
    Returns a dict with results grouped by type and total count.
    """
    if not query or len(query.strip()) < 2:
        return {'results': {}, 'total': 0, 'query': query}

    query = query.strip()
    all_results = {}

    searchers = [
        ('users', search_users),
        ('customers', search_customers),
        ('projects', search_projects),
        ('branding', search_branding),
        ('erp', search_erp),
        ('payments', search_payments),
    ]

    for category, searcher in searchers:
        try:
            results = searcher(query)
            if results:
                all_results[category] = results
        except Exception:
            pass

    total = sum(len(r) for r in all_results.values())

    return {
        'results': all_results,
        'total': total,
        'query': query,
    }
