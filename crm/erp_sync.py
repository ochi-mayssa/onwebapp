"""
ERP/CRM Synchronization Module
Bridges OnWebApp CRM with ERPNext for real-time data access
"""

import requests
import json
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from .models import Customer, OrderSnapshot, ClientTracking, InvoiceSnapshot, StockAllocation
import logging

logger = logging.getLogger(__name__)

class ERPNextClient:
    """
    Client to communicate with ERPNext API via backend gateway
    """
    
    def __init__(self, user):
        self.user = user
        self.api_url = getattr(settings, 'ERP_GATEWAY_URL', 'http://localhost:3000')
        self.token = self._get_api_token()
    
    def _get_api_token(self):
        """Generate JWT token for authenticated requests"""
        import jwt
        from datetime import datetime, timedelta
        
        # Get customer ERP credentials
        try:
            customer = Customer.objects.get(user=self.user)
            erp_credentials = {
                'siteName': customer.erp_site_name or 'demo',
                'apiKey': customer.erp_api_key or '',
                'apiSecret': customer.erp_api_secret or ''
            }
        except Customer.DoesNotExist:
            erp_credentials = {
                'siteName': 'demo',
                'apiKey': '',
                'apiSecret': ''
            }
        
        payload = {
            'user_id': self.user.id,
            'username': self.user.username,
            'site': erp_credentials['siteName'],
            'api_key': erp_credentials['apiKey'],
            'api_secret': erp_credentials['apiSecret'],
            'exp': datetime.utcnow() + timedelta(hours=1)
        }
        secret = getattr(settings, 'SECRET_KEY', 'default-secret')
        return jwt.encode(payload, secret, algorithm='HS256')
    
    def get_customer_data(self):
        """
        Fetch all customer-related data from ERPNext
        Returns: {orders, invoices, stock_items, customer_info}
        """
        try:
            response = requests.get(
                f'{self.api_url}/customer-dashboard/{self.user.id}',
                headers={'Authorization': f'Bearer {self.token}'},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching customer data: {str(e)}")
            return {
                'orders': [],
                'invoices': [],
                'stock_items': [],
                'customer_info': None,
                'error': str(e)
            }
    
    def get_orders(self, limit=20):
        """Fetch customer's orders/work orders"""
        cache_key = f'erp_orders_{self.user.id}'
        cached = cache.get(cache_key)
        
        if cached:
            return cached
        
        try:
            response = requests.get(
                f'{self.api_url}/orders',
                headers={'Authorization': f'Bearer {self.token}'},
                params={'limit': limit},
                timeout=10
            )
            response.raise_for_status()
            orders = response.json()
            
            # Cache for 5 minutes
            cache.set(cache_key, orders, 300)
            return orders
        except Exception as e:
            logger.error(f"Error fetching orders: {str(e)}")
            return []
    
    def get_invoices(self, status=None, limit=20):
        """Fetch customer's invoices"""
        try:
            params = {'limit': limit}
            if status:
                params['status'] = status
                
            response = requests.get(
                f'{self.api_url}/invoices',
                headers={'Authorization': f'Bearer {self.token}'},
                params=params,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching invoices: {str(e)}")
            return []
    
    def get_stock_allocation(self, limit=10):
        """Fetch allocated stock/resources"""
        try:
            response = requests.get(
                f'{self.api_url}/stock',
                headers={'Authorization': f'Bearer {self.token}'},
                params={'limit': limit},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching stock: {str(e)}")
            return []
    
    def get_analytics(self):
        """Fetch aggregated analytics"""
        try:
            response = requests.get(
                f'{self.api_url}/analytics',
                headers={'Authorization': f'Bearer {self.token}'},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching analytics: {str(e)}")
            return {}


def sync_customer_orders(customer):
    """
    Sync orders from ERPNext and cache locally for faster access
    """
    try:
        if not customer.user:
            return
        
        client = ERPNextClient(customer.user)
        orders = client.get_orders()
        
        # Clear old snapshots
        OrderSnapshot.objects.filter(client__user=customer.user).delete()
        
        # Create new snapshots
        for order in orders:
            OrderSnapshot.objects.create(
                client=customer,
                erp_order_id=order.get('name'),
                product=order.get('item_name', 'Unknown'),
                qty=order.get('qty', 0),
                status=order.get('status', 'PENDING'),
                progress_percent=int((order.get('produced_qty', 0) / max(order.get('qty', 1), 1)) * 100),
                target_date=order.get('planned_start_date')
            )
        
        logger.info(f"Synced {len(orders)} orders for customer {customer.name}")
        return True
    except Exception as e:
        logger.error(f"Error syncing customer orders: {str(e)}")
        return False


def get_customer_dashboard_data(user):
    """
    Unified function to gather all customer dashboard data
    Used by views to populate client tracking portal
    """
    
    try:
        customer = Customer.objects.get(user=user)
        tracking = ClientTracking.objects.get(user=user)
    except (Customer.DoesNotExist, ClientTracking.DoesNotExist):
        return None
    
    # Fetch all data from local cache first
    orders = OrderSnapshot.objects.filter(client=tracking).order_by('-last_updated')[:10]
    invoices = InvoiceSnapshot.objects.filter(client=tracking).order_by('-issue_date')[:10]
    stock = StockAllocation.objects.filter(client=tracking)
    
    # Get analytics (mock for now)
    analytics = {
        'revenue_forecast': 12500.00,
        'stock_value': 8750.00,
        'total_sales': 15200.00,
        'efficiency_score': '94%',
        'customer_retention': '88%'
    }
    
    return {
        'customer': customer,
        'orders': list(orders.values()),
        'invoices': list(invoices.values()),
        'stock': list(stock.values()),
        'analytics': analytics,
        'health_score': customer.current_health_score,
        'last_sync': timezone.now()
    }


def calculate_order_completion_rate(user):
    """Calculate order completion percentage for customer"""
    try:
        snapshots = OrderSnapshot.objects.filter(client__user=user)
        
        if not snapshots.exists():
            return 0
        
        completed = snapshots.filter(status__in=['COMPLETED', 'FINISHED']).count()
        total = snapshots.count()
        
        return int((completed / total) * 100) if total > 0 else 0
    except Exception as e:
        logger.error(f"Error calculating completion rate: {str(e)}")
        return 0


def calculate_invoice_health(user):
    """
    Calculate invoice payment health
    Returns: {total_due, overdue, paid_on_time_percent}
    """
    try:
        client = ERPNextClient(user)
        invoices = client.get_invoices()
        
        if not invoices:
            return {'total_due': 0, 'overdue': 0, 'paid_on_time_percent': 0}
        
        total_due = sum(inv.get('grand_total', 0) for inv in invoices if inv.get('status') == 'Issued')
        overdue = sum(inv.get('grand_total', 0) for inv in invoices 
                     if inv.get('status') == 'Overdue')
        paid = len([inv for inv in invoices if inv.get('status') == 'Paid'])
        
        paid_on_time_percent = int((paid / len(invoices)) * 100) if invoices else 0
        
        return {
            'total_due': total_due,
            'overdue': overdue,
            'paid_on_time_percent': paid_on_time_percent
        }
    except Exception as e:
        logger.error(f"Error calculating invoice health: {str(e)}")
        return {'total_due': 0, 'overdue': 0, 'paid_on_time_percent': 0}
