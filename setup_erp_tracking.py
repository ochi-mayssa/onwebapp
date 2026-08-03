"""
Setup script for configuring ERP tracking for existing clients
Run this to set up demo/test data for the ERP tracking system
"""

import os
import sys
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()

from django.contrib.auth.models import User
from crm.models import Customer, ClientTracking, ClientNotification

def setup_client_tracking():
    """Set up ERP tracking for existing customers"""

    print("🔧 Setting up ERP Client Tracking...")

    # Get all customers with user accounts
    customers = Customer.objects.filter(user__isnull=False).exclude(user__is_superuser=True)

    if not customers.exists():
        print("❌ No customers found with user accounts. Please create some customers first.")
        return

    print(f"📋 Found {customers.count()} customers to configure:")

    configured_count = 0

    for customer in customers:
        try:
            # Check if tracking already exists
            tracking, created = ClientTracking.objects.get_or_create(
                user=customer.user,
                defaults={
                    'erp_customer_id': f"CUST-{customer.user.id:04d}",
                    'erp_site_name': f"{customer.user.username}.onwebapp.com",
                    'api_key': f"demo_api_key_{customer.user.id}",
                    'api_secret': f"demo_api_secret_{customer.user.id}",
                    'notification_email': customer.email,
                }
            )

            if created:
                print(f"✅ Created tracking for {customer.name} ({customer.user.username})")
            else:
                print(f"⏭️  Tracking already exists for {customer.name} ({customer.user.username})")

            # Set up default notifications
            notification_types = [
                'ORDER_STATUS',
                'INVOICE_DUE',
                'PAYMENT_RECEIVED',
                'DELIVERY_UPDATE',
                'SYSTEM_MAINTENANCE'
            ]

            for notification_type in notification_types:
                ClientNotification.objects.get_or_create(
                    client=tracking,
                    notification_type=notification_type,
                    defaults={
                        'email_enabled': True,
                        'sms_enabled': False,
                        'in_app_enabled': True,
                        'frequency': 'immediate'
                    }
                )

            configured_count += 1

        except Exception as e:
            print(f"❌ Error setting up {customer.name}: {str(e)}")

    print(f"\n🎉 Successfully configured {configured_count} clients for ERP tracking!")
    print("\n📝 Next steps:")
    print("1. Run: python manage.py sync_erp_data")
    print("2. Start the ERP gateway server: cd erpnext_integration/backend && node server.js")
    print("3. Visit: http://localhost:8000/crm/my-dashboard/ (as a customer)")

def create_demo_customer():
    """Create a demo customer for testing"""

    print("👤 Creating demo customer...")

    # Create user
    user, created = User.objects.get_or_create(
        username='demo_customer',
        defaults={
            'email': 'demo@customer.com',
            'first_name': 'Demo',
            'last_name': 'Customer',
            'is_active': True
        }
    )

    if created:
        user.set_password('demo123')
        user.save()
        print("✅ Created demo user: demo_customer / demo123")

    # Create customer
    customer, created = Customer.objects.get_or_create(
        user=user,
        defaults={
            'name': 'Demo Customer',
            'email': 'demo@customer.com',
            'customer_type': 'INDIVIDUAL',
            'lifecycle_stage': 'ACTIVE_CLIENT',
            'phone': '+1234567890',
            'industry': 'Technology',
            'source': 'Demo Setup'
        }
    )

    if created:
        print("✅ Created demo customer profile")

    # Set up tracking
    tracking, created = ClientTracking.objects.get_or_create(
        user=user,
        defaults={
            'erp_customer_id': 'DEMO-CUST-001',
            'erp_site_name': 'demo.onwebapp.com',
            'api_key': 'demo_api_key_12345',
            'api_secret': 'demo_api_secret_67890',
            'notification_email': 'demo@customer.com',
        }
    )

    if created:
        print("✅ Created demo ERP tracking")

    # Set up notifications
    notification_types = ['ORDER_STATUS', 'INVOICE_DUE', 'PAYMENT_RECEIVED']
    for notification_type in notification_types:
        ClientNotification.objects.get_or_create(
            client=tracking,
            notification_type=notification_type,
            defaults={
                'email_enabled': True,
                'in_app_enabled': True,
                'frequency': 'immediate'
            }
        )

    print("🎉 Demo customer setup complete!")
    print("Login credentials: demo_customer / demo123")
    print("Dashboard URL: http://localhost:8000/crm/my-dashboard/")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--demo':
        create_demo_customer()
    else:
        setup_client_tracking()