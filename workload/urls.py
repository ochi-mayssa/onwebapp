"""URL routing for the workload management workspace."""
from django.urls import path

from . import views

app_name = 'workload'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Work items
    path('items/', views.work_item_list, name='work_item_list'),
    path('items/new/', views.work_item_create, name='work_item_create'),
    path('items/<int:pk>/', views.work_item_detail, name='work_item_detail'),
    path('items/<int:pk>/edit/', views.work_item_edit, name='work_item_edit'),
    path('items/<int:pk>/delete/', views.work_item_delete, name='work_item_delete'),
    path('items/<int:pk>/status/', views.work_item_status, name='work_item_status'),
    path('items/<int:pk>/assign/', views.work_item_assign, name='work_item_assign'),
    path('items/<int:pk>/recommend/', views.work_item_recommend, name='work_item_recommend'),
    path(
        'items/<int:pk>/attachments/',
        views.attachment_upload,
        name='attachment_upload',
    ),
    path(
        'attachments/<int:pk>/download/',
        views.attachment_download,
        name='attachment_download',
    ),
    path(
        'recommendations/<int:pk>/<str:action>/',
        views.recommendation_action,
        name='recommendation_action',
    ),
    path('items/bulk/', views.work_item_bulk, name='work_item_bulk'),

    # Resources
    path('resources/', views.resource_list, name='resource_list'),
    path('resources/new/', views.resource_create, name='resource_create'),
    path('resources/<int:pk>/edit/', views.resource_edit, name='resource_edit'),

    # Teams
    path('teams/', views.team_list, name='team_list'),
    path('teams/new/', views.team_create, name='team_create'),
    path('teams/<int:pk>/edit/', views.team_edit, name='team_edit'),

    # Monitoring and alerts
    path('monitoring/', views.monitoring, name='monitoring'),
    path('monitoring/refresh/', views.refresh_monitoring, name='refresh_monitoring'),
    path('monitoring/sync/', views.sync_integrations_view, name='sync_integrations'),
    path('alerts/', views.alert_list, name='alert_list'),
    path('alerts/<int:pk>/<str:action>/', views.alert_action, name='alert_action'),

    # Policies
    path('policies/', views.policy_list, name='policy_list'),
    path('policies/new/', views.policy_create, name='policy_create'),
    path('policies/<int:pk>/edit/', views.policy_edit, name='policy_edit'),
]
