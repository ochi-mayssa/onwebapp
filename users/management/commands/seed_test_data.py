from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from payments.models import PaymentPlan
from users.models import UserProfile, UserSubscription, ActivityLog
from django.utils import timezone

User = get_user_model()

class Command(BaseCommand):
    help = 'Seed test data: payment plans, test users, subscriptions, and activity logs.'

    def handle(self, *args, **options):
        self.stdout.write('Seeding PaymentPlan entries...')
        plans = [
            {'name': 'Free', 'plan_type': 'basic', 'price': 0.00, 'description': 'Free tier', 'features': ['basic_access'], 'duration_days': 365},
            {'name': 'Basic', 'plan_type': 'basic', 'price': 19.00, 'description': 'Basic plan (monthly)', 'features': ['basic_analytics', 'email_support'], 'duration_days': 30},
            {'name': 'Premium', 'plan_type': 'premium', 'price': 49.00, 'description': 'Premium plan (monthly)', 'features': ['advanced_analytics', 'priority_support'], 'duration_days': 30},
        ]
        for p in plans:
            obj, created = PaymentPlan.objects.get_or_create(name=p['name'], defaults={
                'plan_type': p['plan_type'],
                'price': p['price'],
                'description': p['description'],
                'features': p['features'],
                'duration_days': p['duration_days'],
                'is_active': True,
            })
            if created:
                self.stdout.write(f"Created plan {obj.name}")
            else:
                self.stdout.write(f"Plan {obj.name} already exists")

        # Create a test user
        self.stdout.write('Creating test users...')
        if not User.objects.filter(email='test@local').exists():
            u = User.objects.create_user(username='testuser', email='test@local', password='password123')
            UserProfile.objects.create(user=u, display_name='Test User')
            # create subscription record
            premium = PaymentPlan.objects.filter(name='Premium').first()
            if premium:
                UserSubscription.objects.create(user=u, plan=premium, start_date=timezone.now(), end_date=timezone.now() + timezone.timedelta(days=premium.duration_days), is_active=True)
            ActivityLog.objects.create(user=u, action='seed_created_user', metadata={'note': 'created by seed script'})
            self.stdout.write('Created test user test@local / password123')
        else:
            self.stdout.write('Test user already exists')

        self.stdout.write('Seeding complete.')
