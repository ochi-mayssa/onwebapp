from django.urls import path
from . import views

app_name = 'community'

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # Onboarding Wizard
    path('onboarding/', views.wizard_start, name='wizard_start'),
    path('onboarding/step/<int:step>/', views.wizard_step, name='wizard_step'),
    path('onboarding/autosave/', views.wizard_autosave, name='wizard_autosave'),

    # Legacy (kept for backward compat)
    path('website-building/', views.website_building, name='website_building'),
    path('website-building/packages/', views.package_selection, name='package_selection'),
    path('brand-assist/', views.brand_assist, name='brand_assist'),
]
