from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='rpa_dashboard'),
    path('workflow/<str:wf_id>/', views.workflow_detail, name='workflow_detail'),
    path('workflow/<str:wf_id>/start/', views.start_workflow_run, name='start_workflow_run'),
    path('step/<int:step_id>/run/', views.run_step_api, name='run_step_api'),
    path('export/csv/<int:run_id>/', views.export_run_csv, name='export_run_csv'),
    path('export/pdf/<int:run_id>/', views.export_run_pdf, name='export_run_pdf'),
]
