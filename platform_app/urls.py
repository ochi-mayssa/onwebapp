from django.urls import path
from . import views

app_name = 'platform'

urlpatterns = [
    path('', views.index, name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('links/', views.link_list, name='links'),
    path('links/add/', views.link_create, name='links_add'),
    path('links/<int:pk>/', views.link_detail, name='links_detail'),
]
