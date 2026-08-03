from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('plans/', views.plans, name='plans'),
    path('create-checkout/<int:plan_id>/', views.create_checkout, name='create_checkout'),
    path('pay-invoice/<int:invoice_id>/', views.pay_invoice, name='pay_invoice'),
    path('webhook/', views.webhook, name='webhook'),
]
