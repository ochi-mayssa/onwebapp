from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q, Sum, F
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from itertools import chain

from .models import Customer, Interaction, ServiceRequest
from projects.models import Project, Invoice, ProjectActivity
from users.models import UserSubscription
from .automation import calculate_health_score, get_business_insights

def is_admin_or_staff(user):
    return user.is_authenticated and (user.is_superuser or user.is_staff)

@login_required
@user_passes_test(is_admin_or_staff)
def crm_dashboard(request):
    """
    Main dashboard for CRM - Command Center.
    """
    # Time ranges
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)

    # --- 1. Role-Awareness & Scope ---
    # If superuser, show Global view. If staff, show My Portfolio.
    if request.user.is_superuser:
        all_customers = Customer.objects.all()
        view_scope = "Global View"
    else:
        all_customers = Customer.objects.filter(assigned_to=request.user)
        view_scope = "My Portfolio"

    total_clients = all_customers.count()
    
    active_clients_count = all_customers.filter(lifecycle_stage__in=['ACTIVE_CLIENT', 'RETAINED_CLIENT']).count()
    
    new_leads_30d = all_customers.filter(
        lifecycle_stage='LEAD', 
        created_at__gte=thirty_days_ago
    ).count()
    
    # MRR (Proxy: Revenue in last 30 days) - Filtered by relevant customers
    relevant_user_ids = all_customers.values_list('user_id', flat=True)
    
    revenue_30d = Invoice.objects.filter(
        client_id__in=relevant_user_ids,
        status='PAID',
        issued_date__gte=thirty_days_ago
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Plan Distribution
    plan_counts = UserSubscription.objects.filter(is_active=True, user__id__in=relevant_user_ids).values('plan__name').annotate(count=Count('id'))
    plan_stats = {item['plan__name']: item['count'] for item in plan_counts if item['plan__name']}
    free_plan_count = plan_stats.get('Free', 0)

    # Churn Rate (Churned / Total)
    churned_count = all_customers.filter(lifecycle_stage='CHURNED').count()
    churn_rate = (churned_count / total_clients * 100) if total_clients > 0 else 0

    # --- 2. Health Intelligence & Needs Attention ---
    # Cached scores used here. Heavy calculation happens in Celery tasks.
    clients_at_risk_count = 0
    healthy_clients_count = 0
    attention_clients_count = 0
    
    client_health_data = [] # List of dicts for the view
    needs_attention = [] # List of critical items
    
    for customer in all_customers:
        score = customer.current_health_score
        status_label = 'Healthy'
        if score < 50:
            status_label = 'At Risk'
            clients_at_risk_count += 1
        elif score < 75:
            status_label = 'Attention Needed'
            attention_clients_count += 1
        else:
            healthy_clients_count += 1
            
        client_health_data.append({
            'customer': customer,
            'score': score,
            'trend': customer.health_trend,
            'status': status_label,
            'issues': [] # Issues list would need a separate field or cached info
        })

        # Needs Attention Logic
        attention_reasons = []
        if score < 50:
            attention_reasons.append(f"Critical Health Score ({score})")
        
        if customer.user:
            overdue = Invoice.objects.filter(client=customer.user, status='ISSUED', due_date__lt=now.date()).count()
            if overdue > 0:
                attention_reasons.append(f"{overdue} Overdue Invoice(s)")
        
        stuck_requests = customer.service_requests.filter(status='NEW', created_at__lt=now - timedelta(days=3)).count()
        if stuck_requests > 0:
            attention_reasons.append(f"{stuck_requests} Stalled Request(s)")

        if attention_reasons:
            needs_attention.append({
                'customer': customer,
                'reasons': attention_reasons,
                'priority': 'High' if score < 40 else 'Medium'
            })

    # Sort by score (lowest first to show risks)
    client_health_data.sort(key=lambda x: x['score'])
    
    # Sort needs attention
    needs_attention.sort(key=lambda x: x['customer'].current_health_score)

    # --- 3. Business Intelligence Insights ---
    all_insights = get_business_insights()
    # Filter insights relevant to visible customers
    visible_customer_ids = set(all_customers.values_list('id', flat=True))
    insights = []
    for insight in all_insights:
        # crude extraction of ID from url /crm/customers/{id}/
        try:
            # Assumes format ends with /id/ or /id
            parts = insight['action_url'].strip('/').split('/')
            if parts and parts[-1].isdigit():
                cid = int(parts[-1])
                if cid in visible_customer_ids:
                    insights.append(insight)
            else:
                 # If no ID found or different URL structure, keep it (might be general)
                 insights.append(insight)
        except:
            insights.append(insight)

    # --- 4. Client Lifecycle Funnel (With Percentages) ---
    leads_count = all_customers.filter(lifecycle_stage='LEAD').count()
    qualified_count = all_customers.filter(lifecycle_stage='QUALIFIED_LEAD').count()
    active_count = all_customers.filter(lifecycle_stage='ACTIVE_CLIENT').count()
    retained_count = all_customers.filter(lifecycle_stage='RETAINED_CLIENT').count()
    
    # Max value for bar width calculation
    max_val = max(leads_count, qualified_count, active_count, retained_count, churned_count, 1) # avoid div/0

    funnel_data = {
        'leads': {'count': leads_count, 'pct': int(leads_count/max_val*100)},
        'qualified': {'count': qualified_count, 'pct': int(qualified_count/max_val*100)},
        'active': {'count': active_count, 'pct': int(active_count/max_val*100)},
        'retained': {'count': retained_count, 'pct': int(retained_count/max_val*100)},
        'churned': {'count': churned_count, 'pct': int(churned_count/max_val*100)}
    }

    # --- 5. Activity & Engagement Timeline ---
    # Filter interactions by relevant customers
    interactions = Interaction.objects.filter(customer__in=all_customers).select_related('customer', 'agent')
    
    recent_interactions = list(interactions.order_by('-date')[:15])
    
    # Filter projects by relevant customers (via User)
    recent_proj_activity = list(ProjectActivity.objects.filter(project__client__in=relevant_user_ids).select_related('project', 'project__client').order_by('-created_at')[:15])
    
    timeline = []
    for i in recent_interactions:
        timeline.append({
            'type': 'INTERACTION',
            'obj': i,
            'date': i.date,
            'customer_name': i.customer.name,
            'desc': f"{i.get_interaction_type_display()}: {i.summary}"
        })
    for p in recent_proj_activity:
        c_name = p.project.client.username
        if hasattr(p.project.client, 'crm_customer'):
            c_name = p.project.client.crm_customer.name
            
        timeline.append({
            'type': 'PROJECT',
            'obj': p,
            'date': p.created_at,
            'customer_name': c_name,
            'desc': f"Project Update: {p.content}"
        })
        
    timeline.sort(key=lambda x: x['date'], reverse=True)
    timeline = timeline[:15]

    # --- 6. Projects & Services Overview ---
    # Filter by relevant users
    projects_active = Project.objects.filter(client__in=relevant_user_ids).exclude(current_status__in=['COMPLETED', 'CANCELLED']).count()
    projects_delayed = Project.objects.filter(client__in=relevant_user_ids, current_status='DELAYED').count()
    
    services_active = ServiceRequest.objects.filter(customer__in=all_customers, status='ACCEPTED').values('service_type').annotate(count=Count('service_type'))

    # --- 7. Billing Health ---
    overdue_invoices_count = Invoice.objects.filter(client__in=relevant_user_ids, status='ISSUED', due_date__lt=now.date()).count()
    failed_payments = Invoice.objects.filter(client__in=relevant_user_ids, status='CANCELLED').count() 

    context = {
        'view_scope': view_scope,
        'needs_attention': needs_attention,
        
        # KPI
        'total_clients': total_clients,
        'active_clients': active_clients_count,
        'new_leads_30d': new_leads_30d,
        'clients_at_risk': clients_at_risk_count,
        'mrr': revenue_30d,
        'churn_rate': round(churn_rate, 1),
        'plan_stats': plan_stats,
        'free_plan_count': free_plan_count,
        
        # Lists
        'recent_interactions': recent_interactions,
        
        # Funnel
        'funnel_data': funnel_data,
        
        # Health & BI
        'client_health_list': client_health_data[:10],
        'health_stats': {
            'healthy': healthy_clients_count,
            'attention': attention_clients_count,
            'risk': clients_at_risk_count
        },
        'insights': insights,
        
        # Timeline
        'timeline': timeline,
        
        # Projects
        'projects_active': projects_active,
        'projects_delayed': projects_delayed,
        'services_active': services_active,
        
        # Billing
        'overdue_invoices_count': overdue_invoices_count,
        'failed_payments': failed_payments,
    }
    return render(request, 'crm/dashboard.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def customer_list(request):
    if request.user.is_superuser:
        customers = Customer.objects.all().order_by('-created_at')
    else:
        customers = Customer.objects.filter(assigned_to=request.user).order_by('-created_at')
    return render(request, 'crm/customer_list.html', {'customers': customers})

@login_required
@user_passes_test(is_admin_or_staff)
def customer_detail(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)
    
    # Access Control for Staff
    if not request.user.is_superuser and customer.assigned_to != request.user:
        messages.error(request, "You do not have permission to view this customer.")
        return redirect('crm:dashboard')

    interactions = customer.interactions.all().order_by('-date')
    service_requests = customer.service_requests.all().order_by('-created_at')
    
    projects = Project.objects.filter(client=customer.user) if customer.user else []

    if request.method == 'POST':
        summary = request.POST.get('summary')
        details = request.POST.get('details')
        if summary:
            Interaction.objects.create(
                customer=customer,
                agent=request.user,
                summary=summary,
                details=details,
                interaction_type='NOTE'
            )
            messages.success(request, 'Interaction logged successfully.')
            return redirect('crm:customer_detail', customer_id=customer.id)

    context = {
        'customer': customer,
        'interactions': interactions,
        'service_requests': service_requests,
        'projects': projects,
    }
    return render(request, 'crm/customer_detail.html', context)
