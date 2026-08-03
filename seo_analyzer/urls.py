from django.urls import path
from . import views

app_name = "seo_analyzer"

urlpatterns = [
    path("", views.SEOHomeView.as_view(), name="index"),
    path("free-check/", views.free_website_pre_check_view, name="free_pre_check"),
    path("checker/", views.checker_view, name="checker"),
    path("url-intelligence/", views.url_intelligence_view, name="url_intelligence"),
    path(
        "url-intelligence/results/<int:task_id>/",
        views.url_intelligence_results_view,
        name="url_intelligence_results",
    ),
    path("link/", views.link_checker_view, name="link_checker"),
    path("link/progress/<uuid:task_id>/", views.link_progress_view, name="link_progress"),
    path("link/results/<uuid:task_id>/", views.link_results, name="link_results"),
    path("monitoring/", views.monitoring_view, name="monitoring"),
    path("monitoring/export/<str:export_format>/", views.monitoring_export_view, name="monitoring_export"),
    path("sitemap/", views.sitemap_view, name="sitemap"),
    path("dashboard/<int:task_id>/", views.DashboardView.as_view(), name="dashboard"),
    path(
        "report/<str:report_type>/<str:task_id>/download/",
        views.download_report,
        name="download_report",
    ),
    path("backlinks/", views.backlink_view, name="backlinks"),
    path("executive-kpi-dashboard/", views.executive_kpi_dashboard, name="executive_kpi_dashboard"),
]
