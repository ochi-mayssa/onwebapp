from django.urls import path
from . import views
from .client_views import (
    client_tracking_portal,
    client_orders_view,
    client_invoices_view,
    client_projects_view,
    client_account_view,
    api_refresh_dashboard,
    export_invoice_pdf
)

app_name = 'crm'

urlpatterns = [
    # Admin/Staff views
    path('dashboard/', views.crm_dashboard, name='dashboard'),
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/<int:customer_id>/', views.customer_detail, name='customer_detail'),
    
    # Client-facing views
    path('my-dashboard/', client_tracking_portal, name='client_tracking_portal'),
    path('my-orders/', client_orders_view, name='client_orders_view'),
    path('my-invoices/', client_invoices_view, name='client_invoices_view'),
    path('my-projects/', client_projects_view, name='client_projects_view'),
    path('my-account/', client_account_view, name='client_account_view'),
    
    # API endpoints
    path('api/refresh-dashboard/', api_refresh_dashboard, name='api_refresh_dashboard'),
    path('api/export-invoice/<str:invoice_id>/', export_invoice_pdf, name='export_invoice_pdf'),
]
