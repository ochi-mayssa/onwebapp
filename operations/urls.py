from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.ops_dashboard, name='ops_dashboard'),
    path('leave/submit/', views.submit_leave, name='submit_leave'),
    path('leave/<int:leave_id>/<str:action>/', views.approve_leave, name='approve_leave'),
    path('incident/report/', views.report_incident, name='report_incident'),
    path('onboard/', views.onboard_employee, name='onboard_employee'),
]
