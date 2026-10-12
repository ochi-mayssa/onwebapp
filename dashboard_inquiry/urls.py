from django.urls import path

from . import views

app_name = 'dashboard_inquiry'

urlpatterns = [
    path('', views.quote, name='quote'),
    path('success/', views.success, name='success'),
]
