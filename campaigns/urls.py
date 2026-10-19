from django.urls import path

from . import views

app_name = 'campaigns'

urlpatterns = [
    path('', views.compose, name='compose'),
    path('history/', views.history, name='history'),
    path('<int:pk>/confirm/', views.confirm, name='confirm'),
    path('<int:pk>/detail/', views.detail, name='detail'),
    path('<int:pk>/resume/', views.resume, name='resume'),
    path('<int:pk>/cancel/', views.cancel, name='cancel'),
    path('unsubscribe/<str:token>/', views.unsubscribe, name='unsubscribe'),
]
