from django.urls import path

from . import views

app_name = 'documents'

urlpatterns = [
    # Administration
    path('', views.admin_list, name='admin_list'),
    path('new/', views.admin_create, name='admin_create'),
    path('settings/', views.settings_view, name='settings'),

    # Billing automation (staff only)
    path('billing/', views.billing_list, name='billing_list'),
    path('billing/new/', views.billing_create, name='billing_create'),
    path('billing/run-due/', views.billing_run_due, name='billing_run_due'),
    path('billing/<int:pk>/edit/', views.billing_edit, name='billing_edit'),
    path('billing/<int:pk>/toggle/', views.billing_toggle, name='billing_toggle'),
    path('billing/<int:pk>/generate/', views.billing_generate, name='billing_generate'),

    # Client dashboard (authenticated)
    path('mine/', views.client_list, name='client_list'),
    path('mine/<int:pk>/', views.client_detail, name='client_detail'),
    path('mine/<int:pk>/download/', views.client_download, name='client_download'),
    path('mine/<int:pk>/accept/', views.client_accept, name='client_accept'),
    path('mine/<int:pk>/reject/', views.client_reject, name='client_reject'),
    path('mine/<int:pk>/sign/', views.client_sign, name='client_sign'),

    # Tokenised links used in emails (view / download / respond / sign)
    path('d/<str:token>/', views.public_view, name='public_view'),
    path('d/<str:token>/download/', views.public_download, name='public_download'),
    path('d/<str:token>/accept/', views.public_accept, name='public_accept'),
    path('d/<str:token>/reject/', views.public_reject, name='public_reject'),
    path('d/<str:token>/sign/', views.public_sign, name='public_sign'),

    # Admin document actions
    path('<int:pk>/', views.admin_detail, name='admin_detail'),
    path('<int:pk>/edit/', views.admin_edit, name='admin_edit'),
    path('<int:pk>/preview/', views.admin_preview, name='admin_preview'),
    path('<int:pk>/download/', views.admin_download, name='admin_download'),
    path('<int:pk>/regenerate/', views.admin_regenerate, name='admin_regenerate'),
    path('<int:pk>/send/', views.admin_send, name='admin_send'),
    path('<int:pk>/mark-paid/', views.admin_mark_paid, name='admin_mark_paid'),
    path('<int:pk>/cancel/', views.admin_cancel, name='admin_cancel'),
]
