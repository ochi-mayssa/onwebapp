"""
Mock data generator for testing ERP tracking without full ERPNext server
Creates sample orders, invoices, and stock data for demo purposes
"""

import os
import sys
import django
from datetime import datetime, timedelta
from decimal import Decimal
import random

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()

from django.utils import timezone
from crm.models import ClientTracking, OrderSnapshot, InvoiceSnapshot, StockAllocation

def create_mock_orders(client_tracking):
    """Create sample orders for testing"""

    print(f"📦 Creating mock orders for {client_tracking.user.username}...")

    # Clear existing orders
    OrderSnapshot.objects.filter(client=client_tracking).delete()

    orders_data = [
        {
            'erp_order_id': 'ORD-2026-001',
            'product': 'Website Development Package',
            'qty': 1,
            'status': 'IN_PROGRESS',
            'progress_percent': 75,
            'target_date': timezone.now().date() + timedelta(days=5),
        },
        {
            'erp_order_id': 'ORD-2026-002',
            'product': 'Mobile App Development',
            'qty': 1,
            'status': 'PENDING',
            'progress_percent': 10,
            'target_date': timezone.now().date() + timedelta(days=30),
        },
        {
            'erp_order_id': 'ORD-2026-003',
            'product': 'SEO Optimization Service',
            'qty': 3,
            'status': 'COMPLETED',
            'progress_percent': 100,
            'target_date': timezone.now().date() - timedelta(days=10),
            'actual_completion_date': timezone.now().date() - timedelta(days=8),
        },
        {
            'erp_order_id': 'ORD-2026-004',
            'product': 'Cloud Hosting Setup',
            'qty': 1,
            'status': 'IN_PROGRESS',
            'progress_percent': 45,
            'target_date': timezone.now().date() + timedelta(days=15),
        },
    ]

    for order_data in orders_data:
        OrderSnapshot.objects.create(
            client=client_tracking,
            **order_data
        )

    print(f"✅ Created {len(orders_data)} mock orders")

def create_mock_invoices(client_tracking):
    """Create sample invoices for testing"""

    print(f"💰 Creating mock invoices for {client_tracking.user.username}...")

    # Clear existing invoices
    InvoiceSnapshot.objects.filter(client=client_tracking).delete()

    invoices_data = [
        {
            'erp_invoice_id': 'INV-2026-001',
            'amount': Decimal('2500.00'),
            'status': 'PAID',
            'issue_date': timezone.now().date() - timedelta(days=30),
            'due_date': timezone.now().date() - timedelta(days=15),
            'payment_date': timezone.now().date() - timedelta(days=20),
        },
        {
            'erp_invoice_id': 'INV-2026-002',
            'amount': Decimal('1800.00'),
            'status': 'ISSUED',
            'issue_date': timezone.now().date() - timedelta(days=10),
            'due_date': timezone.now().date() + timedelta(days=20),
        },
        {
            'erp_invoice_id': 'INV-2026-003',
            'amount': Decimal('950.00'),
            'status': 'OVERDUE',
            'issue_date': timezone.now().date() - timedelta(days=45),
            'due_date': timezone.now().date() - timedelta(days=15),
        },
        {
            'erp_invoice_id': 'INV-2026-004',
            'amount': Decimal('3200.00'),
            'status': 'PAID',
            'issue_date': timezone.now().date() - timedelta(days=60),
            'due_date': timezone.now().date() - timedelta(days=30),
            'payment_date': timezone.now().date() - timedelta(days=35),
        },
    ]

    for invoice_data in invoices_data:
        InvoiceSnapshot.objects.create(
            client=client_tracking,
            **invoice_data
        )

    print(f"✅ Created {len(invoices_data)} mock invoices")

def create_mock_stock(client_tracking):
    """Create sample stock allocations for testing"""

    print(f"📦 Creating mock stock allocations for {client_tracking.user.username}...")

    # Clear existing stock
    StockAllocation.objects.filter(client=client_tracking).delete()

    stock_data = [
        {
            'item_code': 'WEB-HOST-001',
            'item_name': 'Premium Web Hosting',
            'allocated_qty': 2,
            'available_qty': 10,
            'unit_rate': Decimal('99.99'),
        },
        {
            'item_code': 'SSL-CERT-001',
            'item_name': 'SSL Certificate',
            'allocated_qty': 1,
            'available_qty': 50,
            'unit_rate': Decimal('49.99'),
        },
        {
            'item_code': 'BACKUP-001',
            'item_name': 'Automated Backup Service',
            'allocated_qty': 3,
            'available_qty': 25,
            'unit_rate': Decimal('29.99'),
        },
        {
            'item_code': 'CDN-001',
            'item_name': 'Content Delivery Network',
            'allocated_qty': 1,
            'available_qty': 15,
            'unit_rate': Decimal('79.99'),
        },
    ]

    for stock_item in stock_data:
        StockAllocation.objects.create(
            client=client_tracking,
            **stock_item
        )

    print(f"✅ Created {len(stock_data)} mock stock allocations")

def generate_mock_data_for_user(user, client_tracking):
    """Generate mock data for a specific user"""
    try:
        create_mock_orders(client_tracking)
        create_mock_invoices(client_tracking)
        create_mock_stock(client_tracking)
        print(f"✅ Generated mock data for {user.username}")
    except Exception as e:
        print(f"❌ Error generating mock data for {user.username}: {str(e)}")


def generate_mock_data():
    """Generate mock data for all clients with tracking setup"""

    print("🎭 Generating mock ERP data for testing...")

    # Get all clients with tracking
    clients = ClientTracking.objects.all()

    if not clients.exists():
        print("❌ No clients with tracking setup found. Run setup_erp_tracking.py first.")
        return

    print(f"📋 Found {clients.count()} clients to populate with mock data:")

    for client in clients:
        print(f"\n🔄 Processing {client.user.username}...")
        try:
            create_mock_orders(client)
            create_mock_invoices(client)
            create_mock_stock(client)
            print(f"✅ Completed mock data for {client.user.username}")
        except Exception as e:
            print(f"❌ Error creating mock data for {client.user.username}: {str(e)}")

    print("\n🎉 Mock data generation complete!")
    print("\n📊 Summary:")
    total_orders = OrderSnapshot.objects.count()
    total_invoices = InvoiceSnapshot.objects.count()
    total_stock = StockAllocation.objects.count()

    print(f"   • Orders: {total_orders}")
    print(f"   • Invoices: {total_invoices}")
    print(f"   • Stock Items: {total_stock}")

    print("\n🚀 Ready to test! Visit: http://localhost:8000/crm/my-dashboard/")
    print("   Login as: demo_customer / demo123")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--help':
        print("Mock Data Generator for ERP Tracking")
        print("Usage: python generate_mock_data.py")
        print("This will populate all clients with tracking setup with sample data.")
    else:
        generate_mock_data()