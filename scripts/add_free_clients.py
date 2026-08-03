
import os
import django
from django.utils import timezone
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()

from django.contrib.auth import get_user_model
from payments.models import PaymentPlan
from users.models import UserSubscription, UserProfile
from crm.models import Customer

User = get_user_model()

def seed_free_plan_clients():
    print("Seeding Free Plan Clients...")

    # 1. Ensure Free Plan Exists
    free_plan, created = PaymentPlan.objects.get_or_create(
        name='Free',
        defaults={
            'plan_type': 'basic',
            'price': 0.00,
            'description': 'Free tier access',
            'features': ['basic_access'],
            'duration_days': 365,
            'is_active': True
        }
    )
    if created:
        print(f"Created PaymentPlan: {free_plan}")
    else:
        print(f"Found existing PaymentPlan: {free_plan}")

    # 2. Create Sample Users and Customers
    for i in range(1, 6):
        username = f"free_user_{i}"
        email = f"free_user_{i}@example.com"
        
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': email}
        )
        if created:
            user.set_password('password123')
            user.save()
            print(f"Created User: {username}")
            
            # Create UserProfile
            UserProfile.objects.create(user=user, display_name=f"Free User {i}")
        else:
            print(f"User {username} already exists")

        # 3. Create/Update Subscription
        sub, created = UserSubscription.objects.get_or_create(
            user=user,
            defaults={
                'plan': free_plan,
                'start_date': timezone.now(),
                'end_date': timezone.now() + timezone.timedelta(days=365),
                'is_active': True
            }
        )
        if not created and sub.plan != free_plan:
            sub.plan = free_plan
            sub.save()
            print(f"Updated subscription for {username} to Free Plan")
        
        # 4. Create/Update Customer Profile
        customer, created = Customer.objects.get_or_create(
            user=user,
            defaults={
                'name': f"Free User {i}",
                'email': email,
                'customer_type': 'INDIVIDUAL',
                'lifecycle_stage': 'ACTIVE_CLIENT',
                'source': 'Website Signup'
            }
        )
        if created:
            print(f"Created Customer profile for {username}")

    print("Seeding complete.")

if __name__ == '__main__':
    seed_free_plan_clients()
