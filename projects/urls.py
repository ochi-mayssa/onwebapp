from django.urls import path
from . import views

app_name = 'projects'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
     path('<int:project_id>/', views.project_detail, name='project_detail'),
     path('<int:project_id>/team/', views.project_team, name='project_team'),
     path('<int:project_id>/phase/<int:phase_id>/feedback/client/', views.add_client_phase_feedback, name='add_client_phase_feedback'),
     path('<int:project_id>/feedback/general/', views.add_client_general_feedback, name='add_client_general_feedback'),
     path('client/<int:project_id>/assets/upload/', views.add_client_asset, name='add_client_asset'),
     path('admin/<int:project_id>/phase/<int:phase_id>/deliverables/new/', views.add_deliverable, name='add_deliverable'),
     path('team/task/<int:task_id>/update/', views.update_task_status, name='update_task_status'),
     path('team/<str:username>/', views.team_member_projects, name='team_member_projects'),
    path('<int:project_id>/cancel/', views.cancel_project, name='cancel_project'),
    path('admin/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/consultations/', views.admin_consultations, name='admin_consultations'),
    path('admin/team-management/', views.admin_team_management, name='admin_team_management'),
    path('admin/<int:project_id>/team/add/', views.add_team_assignment, name='add_team_assignment'),
    path('admin/team/assignment/<int:assignment_id>/remove/', views.remove_team_assignment, name='remove_team_assignment'),
    path('admin/kanban/', views.admin_kanban, name='admin_kanban'),
    path('admin/platform-dashboard/', views.platform_dashboard, name='platform_dashboard'),
    path('admin/kanban/update-phase/', views.update_project_phase, name='update_project_phase'),
    path('admin/<int:project_id>/delete/', views.delete_project, name='delete_project'),
    path('admin/<int:project_id>/hold/', views.hold_project, name='hold_project'),
    path('admin/<int:project_id>/', views.admin_project_detail, name='admin_project_detail'),
     path('admin/<int:project_id>/update/', views.update_project_meta, name='update_project_meta'),
     path('admin/<int:project_id>/phase/<int:phase_id>/tasks/add/', views.add_phase_task, name='add_phase_task'),
    path('admin/<int:project_id>/tasks/<int:task_id>/toggle/', views.toggle_phase_task, name='toggle_phase_task'),
     path('admin/<int:project_id>/tasks/<int:task_id>/assign/', views.assign_phase_task, name='assign_phase_task'),
      path('admin/<int:project_id>/preview/client/', views.admin_preview_client_project, name='admin_preview_client_project'),
    path('admin/<int:project_id>/export/phases/', views.export_project_phases_csv, name='export_project_phases_csv'),
    path('admin/<int:project_id>/export/messages/', views.export_project_messages_csv, name='export_project_messages_csv'),
    path('admin/export.csv', views.export_projects_csv, name='export_projects_csv'),
    path('admin/bulk/', views.bulk_projects_action, name='bulk_projects_action'),
    path('admin/<int:project_id>/phase/<int:phase_id>/update/', views.update_phase_meta, name='update_phase_meta'),
    path('admin/<int:project_id>/phase/add/', views.add_phase, name='add_phase'),
    path('admin/<int:project_id>/deliverable/<int:deliverable_id>/toggle/', views.toggle_deliverable_visibility, name='toggle_deliverable_visibility'),
    path('admin/<int:project_id>/phase/<int:phase_id>/feedback/', views.add_phase_feedback, name='add_phase_feedback'),
    path('admin/<int:project_id>/phase/<int:phase_id>/force-approve/', views.force_approve_phase, name='force_approve_phase'),
    path('<int:project_id>/phase/<int:phase_id>/ready/', views.mark_phase_ready, name='mark_phase_ready'),
    path('<int:project_id>/phase/<int:phase_id>/approve/', views.approve_phase, name='approve_phase'),
    path('<int:project_id>/phase/<int:phase_id>/changes/', views.request_changes_phase, name='request_changes_phase'),
    path('admin/<int:project_id>/phase/<int:phase_id>/lock/', views.lock_phase, name='lock_phase'),
    path('admin/<int:project_id>/phase/<int:phase_id>/unlock/', views.unlock_phase, name='unlock_phase'),
    path('admin/<int:project_id>/feedback/response/', views.add_admin_response, name='add_admin_response'),
    path('admin/<int:project_id>/phase/<int:phase_id>/reopen/', views.reopen_phase, name='reopen_phase'),
    
    # Agile Plan Management
    path('admin/<int:project_id>/agile/upload/', views.upload_agile_plan, name='upload_agile_plan'),
    path('<int:project_id>/agile/review/', views.review_agile_plan, name='review_agile_plan'),
    path('admin/<int:project_id>/phase/bulk-assign/', views.bulk_assign_phase, name='bulk_assign_phase'),
    
    # Notifications & Deadlines
    path('admin/deadlines/check/', views.check_deadlines, name='check_deadlines'),
    
    # Team Member Actions
    path('team/<int:project_id>/phase/<int:phase_id>/upload/', views.team_upload_deliverable, name='team_upload_deliverable'),

    # Workflow Automation URLs
    path('workflow/dashboard/', views.workflow_dashboard_client, name='workflow_dashboard_client'),
    path('workflow/admin/dashboard/', views.workflow_dashboard_admin, name='workflow_dashboard_admin'),
    path('api/notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),
    
    # Billing / Invoices
    path('invoices/<int:invoice_id>/', views.invoice_detail, name='invoice_detail'),
    
    # Analytics Export
    path('admin/analytics/export/kpi/', views.export_kpi_history_csv, name='export_kpi_history_csv'),
    
    # Website Requests
    path('admin/requests/<int:request_id>/accept/', views.accept_website_request, name='accept_website_request'),
    path('admin/requests/<int:request_id>/reject/', views.reject_website_request, name='reject_website_request'),
]
