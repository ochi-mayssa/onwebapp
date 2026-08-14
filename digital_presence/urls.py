"""URL configuration for Digital Presence app."""
from django.urls import path
from . import views

app_name = 'digital_presence'

urlpatterns = [
    path('', views.overview, name='overview'),
    path('social-media/', views.social_media, name='social_media'),
    path('social-media/chart/', views.social_chart_data, name='social_chart_data'),
    path('seo/', views.seo, name='seo'),
    path('seo/chart/', views.seo_chart_data, name='seo_chart_data'),
    path('keywords/', views.keywords, name='keywords'),
    path('keywords/chart/', views.keyword_chart_data, name='keyword_chart_data'),
    path('content/', views.content, name='content'),
    path('reports/', views.reports, name='reports'),
    path('api/overview/', views.api_overview, name='api_overview'),
]
