from django.urls import path
from . import views

app_name = 'home'

urlpatterns = [
    path('', views.index, name='home'),
    path('', views.index, name='index'),  # Alias for 'home' to fix "Reverse for 'index' not found"
    path('use-cases/', views.use_cases, name='use_cases'),
    path('testimonials/', views.testimonials, name='testimonials'),
    path('features/', views.features, name='features'),
    path('docs/', views.api_docs, name='api_docs'),
    path('about/', views.about, name='about'),
    path('help/', views.help_center, name='help_center'),
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
    path('security/', views.security, name='security'),
    path('tools/', views.free_tools, name='tools'),
    path('demo/', views.demo_request, name='demo_request'),
    path('events/', views.webinars, name='webinars'),
    path('build/', views.build_website, name='build_website'),
    path('design/ux/', views.ux_design, name='ux_design'),
    path('design/ui/', views.ui_design, name='ui_design'),
    path('software/', views.software_home, name='software_home'),
    path('software/web-development/', views.web_development, name='web_development'),
    path('software/mobile-development/', views.mobile_development, name='mobile_development'),
    path('software/ecommerce-development/', views.ecommerce_development, name='ecommerce_development'),
    path('design-system/', views.design_system, name='design_system'),
    path('overview/', views.video_explainer, name='video_explainer'),
]