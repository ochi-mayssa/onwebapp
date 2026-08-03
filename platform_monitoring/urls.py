from django.urls import path
from . import views

app_name = 'platform_monitoring'

urlpatterns = [
    path('', views.hub_view, name='hub'),
    path('seo/', views.seo_view, name='seo'),
    path('seo/links/', views.seo_links_view, name='seo_links'),
    path('automation/', views.automation_view, name='automation'),
    path('iot/', views.iot_view, name='iot'),
    path('security/', views.security_view, name='security'),
    path('integrations/', views.integrations_view, name='integrations'),
    path('competitor/', views.standalone_view, {'section_id': 'competitor'}, name='competitor'),
    path('social/', views.standalone_view, {'section_id': 'social'}, name='social'),
    path('digital-presence/', views.standalone_view, {'section_id': 'digital'}, name='digital'),
]
