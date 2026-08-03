"""
Views for client-facing tracking portal
Allows customers to see their orders, invoices, and project status
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Sum, Q
from django.http import JsonResponse
from datetime import timedelta

from .models import Customer, Interaction, ClientTracking, OrderSnapshot
from projects.models import Project
from projects.models import Project, Invoice
from .erp_sync import (
    get_customer_dashboard_data,
    calculate_order_completion_rate,
    calculate_invoice_health,
    sync_customer_orders
)


@login_required
def client_tracking_portal(request):
    """
    Client-facing dashboard showing real-time ERP and CRM data.
    Displays: orders, invoices, projects, and account health.
    """
    
    # Verify user is a customer - create if doesn't exist
    customer, created = Customer.objects.get_or_create(
        user=request.user,
        defaults={
            'name': request.user.get_full_name() or request.user.username,
            'email': request.user.email,
            'customer_type': 'INDIVIDUAL',
            'lifecycle_stage': 'ACTIVE_CLIENT'
        }
    )
    if created:
        messages.info(request, "Welcome! Your customer profile has been created.")
    
    # Ensure user has tracking data - create if missing
    tracking, created = ClientTracking.objects.get_or_create(
        user=request.user,
        defaults={
            'erp_customer_id': customer.email,  # Use email as customer ID
            'erp_site_name': customer.erp_site_name or 'demo',
            'api_key': customer.erp_api_key or '',
            'api_secret': customer.erp_api_secret or '',
            'realtime_enabled': True
        }
    )
    
    # Check if user has any data, if not generate mock data
    if not OrderSnapshot.objects.filter(client=tracking).exists():
        # Generate mock data for this user
        # Temporarily disabled - will use existing mock data
        pass
    
    # Get unified dashboard data
    dashboard_data = get_customer_dashboard_data(request.user)
    
    if not dashboard_data:
        messages.error(request, "Unable to load your portal data.")
        return redirect('home:index')
    
    # Calculate metrics
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    
    # Order metrics
    order_completion_rate = calculate_order_completion_rate(request.user)
    
    # Invoice metrics
    invoice_health = calculate_invoice_health(request.user)
    
    # Project metrics
    user_projects = Project.objects.filter(client=request.user)
    active_projects = user_projects.exclude(current_status__in=['COMPLETED', 'CANCELLED']).count()
    completed_projects = user_projects.filter(current_status='COMPLETED').count()
    delayed_projects = user_projects.filter(current_status='DELAYED').count()
    
    # Activity feed
    recent_interactions = Interaction.objects.filter(
        customer=customer
    ).select_related('agent').order_by('-date')[:8]
    
    # Next milestones
    upcoming_projects = user_projects.filter(
        current_status__in=['IN_PROGRESS', 'ON_HOLD']
    ).order_by('expected_delivery_date')[:5]
    
    context = {
        'customer': customer,
        'page_title': f"Welcome, {customer.name}",
        
        # Orders & Production
        'orders': dashboard_data.get('orders', []),
        'order_completion_rate': order_completion_rate,
        'total_orders': len(dashboard_data.get('orders', [])),
        
        # Invoices & Billing
        'invoices': dashboard_data.get('invoices', []),
        'invoice_health': invoice_health,
        'total_due': invoice_health.get('total_due', 0),
        'overdue_amount': invoice_health.get('overdue', 0),
        'paid_on_time_percent': invoice_health.get('paid_on_time_percent', 0),
        
        # Resources
        'stock_allocation': dashboard_data.get('stock', []),
        
        # Projects
        'active_projects': active_projects,
        'completed_projects': completed_projects,
        'delayed_projects': delayed_projects,
        'upcoming_projects': upcoming_projects,
        
        # Health & Analytics
        'health_score': customer.current_health_score,
        'analytics': dashboard_data.get('analytics', {}),
        'last_sync': dashboard_data.get('last_sync'),
        
        # Activity
        'recent_interactions': recent_interactions,
    }
    
    return render(request, 'crm/client_tracking_portal.html', context)


@login_required
def client_orders_view(request):
    """
    Detailed orders view for customers
    """
    
    try:
        customer = Customer.objects.get(user=request.user)
    except Customer.DoesNotExist:
        messages.error(request, "Customer profile not found.")
        return redirect('home:index')
    
    # Get orders from cache/DB
    from .models import OrderSnapshot
    orders = OrderSnapshot.objects.filter(
        client=customer
    ).order_by('-last_updated')
    
    # Calculate statistics
    completed = orders.filter(status='COMPLETED').count()
    in_progress = orders.filter(status='IN_PROGRESS').count()
    pending = orders.filter(status='PENDING').count()
    
    context = {
        'orders': orders,
        'statistics': {
            'completed': completed,
            'in_progress': in_progress,
            'pending': pending,
            'total': orders.count()
        }
    }
    
    return render(request, 'crm/client_orders.html', context)


@login_required
def client_invoices_view(request):
    """
    Detailed invoices view for customers
    Shows all invoices with payment status
    """
    
    try:
        customer = Customer.objects.get(user=request.user)
    except Customer.DoesNotExist:
        messages.error(request, "Customer profile not found.")
        return redirect('home:index')
    
    # Get invoices
    from .erp_sync import ERPNextClient
    client = ERPNextClient(request.user)
    all_invoices = client.get_invoices()
    
    # Separate by status
    paid_invoices = [inv for inv in all_invoices if inv.get('status') == 'Paid']
    due_invoices = [inv for inv in all_invoices if inv.get('status') == 'Issued']
    overdue_invoices = [inv for inv in all_invoices if inv.get('status') == 'Overdue']
    
    # Calculate totals
    total_paid = sum(inv.get('grand_total', 0) for inv in paid_invoices)
    total_due = sum(inv.get('grand_total', 0) for inv in due_invoices)
    total_overdue = sum(inv.get('grand_total', 0) for inv in overdue_invoices)
    
    context = {
        'all_invoices': all_invoices,
        'paid_invoices': paid_invoices,
        'due_invoices': due_invoices,
        'overdue_invoices': overdue_invoices,
        'summary': {
            'total_paid': total_paid,
            'total_due': total_due,
            'total_overdue': total_overdue,
            'count_paid': len(paid_invoices),
            'count_due': len(due_invoices),
            'count_overdue': len(overdue_invoices)
        }
    }
    
    return render(request, 'crm/client_invoices.html', context)


@login_required
def client_projects_view(request):
    """
    View for customer's projects with real-time status
    """
    
    user_projects = Project.objects.filter(client=request.user).order_by('-created_at')
    
    # Statistics
    stats = {
        'total': user_projects.count(),
        'active': user_projects.exclude(current_status__in=['COMPLETED', 'CANCELLED']).count(),
        'completed': user_projects.filter(current_status='COMPLETED').count(),
        'delayed': user_projects.filter(current_status='DELAYED').count(),
    }
    
    context = {
        'projects': user_projects,
        'stats': stats
    }
    
    return render(request, 'crm/client_projects.html', context)


@login_required
def client_account_view(request):
    """
    Customer account overview with subscription, health, and settings
    """
    
    try:
        customer = Customer.objects.get(user=request.user)
    except Customer.DoesNotExist:
        messages.error(request, "Customer profile not found.")
        return redirect('home:index')
    
    # Get subscription info
    from users.models import UserSubscription
    try:
        subscription = UserSubscription.objects.get(user=request.user, is_active=True)
    except:
        subscription = None
    
    # Account health
    invoice_health = calculate_invoice_health(request.user)
    order_completion = calculate_order_completion_rate(request.user)
    
    context = {
        'customer': customer,
        'subscription': subscription,
        'health_score': customer.current_health_score,
        'invoice_health': invoice_health,
        'order_completion': order_completion,
        'renewal_date': customer.subscription_end_date if hasattr(customer, 'subscription_end_date') else None,
    }
    
    return render(request, 'crm/client_account.html', context)


@login_required
def api_refresh_dashboard(request):
    """
    API endpoint to manually refresh customer data
    Called by AJAX for real-time updates
    """
    
    try:
        customer = Customer.objects.get(user=request.user)
        
        # Sync orders from ERPNext
        sync_customer_orders(customer)
        
        # Return updated data
        dashboard_data = get_customer_dashboard_data(request.user)
        
        return JsonResponse({
            'status': 'success',
            'message': 'Dashboard refreshed successfully',
            'data': {
                'orders': dashboard_data.get('orders', []),
                'invoices': dashboard_data.get('invoices', []),
                'stock': dashboard_data.get('stock', []),
                'last_sync': str(dashboard_data.get('last_sync'))
            }
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@login_required
def export_invoice_pdf(request, invoice_id):
    """
    Export invoice as PDF
    """
    try:
        from .erp_sync import ERPNextClient
        client = ERPNextClient(request.user)
        
        # Would need to implement PDF generation
        # For now, redirect to payment processing
        return redirect('payments:invoice_detail', invoice_id=invoice_id)
    except Exception as e:
        messages.error(request, "Unable to export invoice.")
        return redirect('crm:client_invoices')
