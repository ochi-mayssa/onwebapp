from django.urls import path
from . import views

app_name = 'integration'

urlpatterns = [
    path('', views.IntegrationHomepageView.as_view(), name='integration_homepage'),
    path('data/', views.DataIntegrationView.as_view(), name='data_integration'),
    path('b2b/', views.B2BIntegrationView.as_view(), name='b2b_integration'),
    path('system/', views.SystemIntegrationView.as_view(), name='system_integration'),
]
