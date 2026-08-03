"""
Test script to verify the ERP tracking dashboard is working
Makes programmatic requests to test the functionality
"""

import os
import sys
import django
import requests
from django.test import Client as DjangoClient
from django.contrib.auth import authenticate

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()

from django.contrib.auth.models import User
from crm.models import Customer, ClientTracking, OrderSnapshot, InvoiceSnapshot

def test_dashboard_access():
    """Test that the dashboard is accessible"""

    print("🧪 Testing ERP Tracking Dashboard...")

    # Create Django test client
    client = DjangoClient(HTTP_HOST='localhost')

    # Try to login as demo customer
    user = authenticate(username='demo_customer', password='demo123')
    if not user:
        print("❌ Demo user authentication failed")
        return False

    # Login
    login_success = client.login(username='demo_customer', password='demo123')
    if not login_success:
        print("❌ Login failed")
        return False

    print("✅ Successfully logged in as demo_customer")

    # Test dashboard access
    response = client.get('/crm/my-dashboard/', HTTP_HOST='localhost')
    if response.status_code != 200:
        print(f"❌ Dashboard access failed: HTTP {response.status_code}")
        print(f"Response: {response.content[:500]}")
        return False

    print("✅ Dashboard page accessible")

    # Check for expected content
    content = response.content.decode('utf-8')
    if 'Welcome, Demo Customer' not in content:
        print("❌ Welcome message not found")
        return False

    if 'Your Active Orders' not in content:
        print("❌ Orders section not found")
        return False

    if 'Your Invoices' not in content:
        print("❌ Invoices section not found")
        return False

    print("✅ Dashboard content verified")

    return True

def test_data_population():
    """Test that mock data was created correctly"""

    print("📊 Testing data population...")

    # Check demo customer exists
    try:
        customer = Customer.objects.get(user__username='demo_customer')
        print("✅ Demo customer exists")
    except Customer.DoesNotExist:
        print("❌ Demo customer not found")
        return False

    # Check tracking setup
    try:
        tracking = ClientTracking.objects.get(user__username='demo_customer')
        print("✅ Client tracking configured")
    except ClientTracking.DoesNotExist:
        print("❌ Client tracking not configured")
        return False

    # Check orders
    orders = OrderSnapshot.objects.filter(client=tracking)
    if orders.count() == 0:
        print("❌ No orders found")
        return False
    print(f"✅ {orders.count()} orders created")

    # Check invoices
    invoices = InvoiceSnapshot.objects.filter(client=tracking)
    if invoices.count() == 0:
        print("❌ No invoices found")
        return False
    print(f"✅ {invoices.count()} invoices created")

    # Check stock
    from crm.models import StockAllocation
    stock = StockAllocation.objects.filter(client=tracking)
    if stock.count() == 0:
        print("❌ No stock allocations found")
        return False
    print(f"✅ {stock.count()} stock items allocated")

    return True

def test_api_endpoints():
    """Test API endpoints for data refresh"""

    print("🔌 Testing API endpoints...")

    client = DjangoClient(HTTP_HOST='localhost')
    client.login(username='demo_customer', password='demo123')

    # Test refresh endpoint
    response = client.get('/crm/api/refresh-dashboard/', HTTP_HOST='localhost')
    if response.status_code != 200:
        print(f"❌ API refresh failed: HTTP {response.status_code}")
        print(f"Response: {response.content[:500]}")
        return False

    try:
        data = response.json()
        if data.get('status') != 'success':
            print(f"❌ API returned error: {data.get('message')}")
            return False
    except:
        print("❌ API returned invalid JSON")
        return False

    print("✅ API refresh endpoint working")

    return True

def run_all_tests():
    """Run all tests"""

    print("🚀 Running ERP Tracking Tests\n")

    tests = [
        ("Data Population", test_data_population),
        ("Dashboard Access", test_dashboard_access),
        ("API Endpoints", test_api_endpoints),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"Running: {test_name}")
        print('='*50)

        try:
            if test_func():
                print(f"✅ {test_name}: PASSED")
                passed += 1
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {str(e)}")

    print(f"\n{'='*50}")
    print(f"Test Results: {passed}/{total} tests passed")
    print('='*50)

    if passed == total:
        print("🎉 All tests passed! ERP tracking is working correctly.")
        print("\n📋 Next steps:")
        print("1. Visit: http://localhost:8000/crm/my-dashboard/")
        print("2. Login: demo_customer / demo123")
        print("3. Explore the real-time tracking features")
        print("4. Test with real ERPNext by configuring API credentials")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")

if __name__ == '__main__':
    run_all_tests()