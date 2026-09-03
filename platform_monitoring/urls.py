from django.urls import path
from . import views

app_name = 'platform_monitoring'

urlpatterns = [
    path('', views.hub_view, name='hub'),
    path('seo/', views.seo_view, name='seo'),
    path('seo/links/', views.seo_links_view, name='seo_links'),
    path('automation/', views.automation_view, name='automation'),
    path(
    'automation/status/',
    views.automation_status_view,
    name='automation_status'
     ),
    path('iot/', views.iot_view, name='iot'),
    path('security/', views.security_view, name='security'),
    path('integrations/', views.integrations_view, name='integrations'),
    path('competitor/', views.standalone_view, {'section_id': 'competitor'}, name='competitor'),
    path('social/', views.standalone_view, {'section_id': 'social'}, name='social'),
    path('digital-presence/', views.standalone_view, {'section_id': 'digital'}, name='digital'),
    path('automation/scheduler/', views.task_scheduler_view, name='task_scheduler'),
    path('automation/logs/', views.execution_logs_view, name='execution_logs'),
    path('kpi-test/', views.kpi_test_view, name='kpi_test'),
    path('ga4/connect/', views.ga4_connect_view, name='ga4_connect'),
    path('ga4/callback/', views.ga4_callback_view, name='ga4_callback'),
    path('ga4/disconnect/<int:property_id>/', views.ga4_disconnect_view, name='ga4_disconnect'),
    path('ga4/fetch/', views.ga4_fetch_view, name='ga4_fetch'),
]
