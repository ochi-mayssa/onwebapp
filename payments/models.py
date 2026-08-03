from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class PaymentPlan(models.Model):
    """Model for different payment plans available"""
    PLAN_TYPES = [
        ('starter', 'Starter Package'),
        ('growth', 'Growth Package'),
        ('enterprise', 'Enterprise Package'),
        ('seo_intelligence', 'SEO Intelligence Suite'),
    ]
    
    name = models.CharField(max_length=100)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPES)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField()
    features = models.JSONField(default=list)  # List of features included
    duration_days = models.IntegerField(default=30)  # Plan duration in days
    payment_mode = models.CharField(max_length=20, default='subscription', choices=[('subscription', 'Subscription'), ('payment', 'One-time Payment')])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} - ${self.price}"

class UserPaymentSelection(models.Model):
    """Model to store user's payment plan selections"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('selected', 'Selected'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_selections')
    plan = models.ForeignKey(PaymentPlan, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    selected_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    session_data = models.JSONField(default=dict)  # Store additional session data
    
    class Meta:
        ordering = ['-selected_at']
        
    def __str__(self):
        return f"{self.user.email} - {self.plan.name}"

class Payment(models.Model):
    """Existing payment model (kept for backward compatibility)"""
    user_id = models.CharField(max_length=128, db_index=True)
    amount = models.IntegerField(help_text="Amount in cents")
    status = models.CharField(max_length=32)
    transaction_id = models.CharField(max_length=128, blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date']
        
    def __str__(self):
        return f"{self.user_id} - {self.amount} - {self.status}"
