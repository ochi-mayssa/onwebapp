from django.urls import path
from . import views

app_name = 'home'

urlpatterns = [
    path('', views.index, name='home'),
    path('', views.index, name='index'),  # Alias for 'home' to fix "Reverse for 'index' not found"
    path('testimonials/', views.testimonials, name='testimonials'),
    path('docs/', views.api_docs, name='api_docs'),
    path('about/', views.about, name='about'),
    path('automation/', views.automation_home, name='automation_home'),
    path('automation/rpa-bpa/', views.rpa_bpa, name='rpa_bpa'),
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
    path('build/', views.build_website, name='build_website'),
    path('design/ux/', views.ux_design, name='ux_design'),
    path('design/ui/', views.ui_design, name='ui_design'),
    path('software/', views.software_home, name='software_home'),
    path('software/web-development/', views.web_development, name='web_development'),
    path('software/mobile-development/', views.mobile_development, name='mobile_development'),
    path('software/ecommerce-development/', views.ecommerce_development, name='ecommerce_development'),
    path('software/dashboard-development/', views.dashboard_development, name='dashboard_development'),
    path('software/browser-web-automation/', views.browser_web_automation, name='browser_web_automation'),
    path('services/erp/', views.erp_service, name='erp_service'),
    path('overview/', views.video_explainer, name='video_explainer'),
]