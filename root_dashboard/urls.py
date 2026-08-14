"""URL configuration for Root Dashboard."""
from django.urls import path
from . import views

app_name = 'root_dashboard'

urlpatterns = [
    path('', views.command_center, name='command_center'),
    path('operations/', views.operations_center, name='operations_center'),
    path('health/', views.health_check, name='health_check'),
    path('api/health/', views.health_api, name='health_api'),
    path('api/infrastructure/', views.infrastructure_api, name='infrastructure_api'),
    path('api/search/', views.search_api, name='search_api'),
]
