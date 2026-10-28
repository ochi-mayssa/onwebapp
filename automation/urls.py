from django.urls import path

from . import views

app_name = 'automation'

urlpatterns = [
    path('', views.automation_overview, name='overview'),
    path('request/', views.automation_request_form, name='request_form'),
    path('request/<int:pk>/', views.request_detail, name='request_detail'),
    path('my-automations/', views.my_automations, name='my_automations'),
    path('workflow/<int:pk>/', views.automation_detail, name='automation_detail'),
    path('workflow/<int:pk>/trigger/', views.workflow_trigger, name='workflow_trigger'),
    path('execution/<int:pk>/', views.execution_status, name='execution_status'),
    path('billing/', views.billing_dashboard, name='billing_dashboard'),
    path('billing/checkout/', views.billing_checkout, name='billing_checkout'),
    path('billing/success/', views.billing_success, name='billing_success'),
    path('billing/cancel/', views.billing_cancel, name='billing_cancel'),
    path('billing/webhook/stripe/', views.stripe_webhook, name='stripe_webhook'),
    path('history/<int:pk>/', views.record_execution, name='execution_history'),
    path('admin/queue/', views.admin_queue, name='admin_queue'),
    path('admin/queue/<int:pk>/approve/', views.approve_request, name='approve_request'),
]
