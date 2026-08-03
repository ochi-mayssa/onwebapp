
import os
import django
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()

from django.contrib.auth import get_user_model
from payments.models import PaymentPlan
from users.models import UserSubscription, UserProfile
from crm.models import Customer

User = get_user_model()

def add_specific_clients():
    clients = [
        {'email': 'ochimayssa@gmail.com', 'name': 'Ochi Mayssa', 'plan': 'Free'},
        {'email': 'ichrak@gmail.com', 'name': 'Ichrak', 'plan': 'Free'}
    ]

    # Ensure Free plan exists
    free_plan, _ = PaymentPlan.objects.get_or_create(
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

    for client_data in clients:
        email = client_data['email']
        username = email.split('@')[0]
        name = client_data['name']
        
        # 1. Create/Get User
        # We try to get by email first to avoid unique constraint errors if username varies
        try:
            user = User.objects.get(email=email)
            print(f"User already exists: {email}")
        except User.DoesNotExist:
            # Handle potential username collision if username exists but email is different
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}_{counter}"
                counter += 1
                
            user = User.objects.create_user(username=username, email=email, password='password123')
            print(f"Created User: {email} (username: {username})")

        # 2. UserProfile
        UserProfile.objects.get_or_create(user=user, defaults={'display_name': name})

        # 3. Subscription
        sub, created = UserSubscription.objects.get_or_create(
            user=user,
            defaults={
                'plan': free_plan,
                'start_date': timezone.now(),
                'end_date': timezone.now() + timezone.timedelta(days=365),
                'is_active': True
            }
        )
        if not created and not sub.is_active:
             sub.is_active = True
             sub.plan = free_plan
             sub.save()
             print(f"Re-activated subscription for {name}")

        
        # 4. CRM Customer Profile
        customer, created = Customer.objects.get_or_create(
            user=user,
            defaults={
                'name': name,
                'email': email,
                'customer_type': 'INDIVIDUAL',
                'lifecycle_stage': 'ACTIVE_CLIENT',
                'source': 'Manual Addition'
            }
        )
        if created:
            print(f"Created CRM Customer Profile for {name}")
        else:
            print(f"CRM Customer Profile already exists for {name}")

if __name__ == '__main__':
    add_specific_clients()
