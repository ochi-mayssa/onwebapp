from django.contrib import admin
from .models import PaymentPlan, UserPaymentSelection, Payment


@admin.register(PaymentPlan)
class PaymentPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'plan_type', 'price', 'payment_mode', 'is_active', 'created_at')
    list_filter = ('plan_type', 'payment_mode', 'is_active')
    search_fields = ('name', 'description')


@admin.register(UserPaymentSelection)
class UserPaymentSelectionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'selected_at', 'completed_at')
    list_filter = ('status',)
    search_fields = ('user__email', 'user__username')
    raw_id_fields = ('user', 'plan')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'amount', 'status', 'transaction_id', 'date')
    list_filter = ('status',)
    search_fields = ('user_id', 'transaction_id')
    readonly_fields = ('date',)
