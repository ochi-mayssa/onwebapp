from django.urls import path
from . import views

app_name = 'services'
urlpatterns = [
    path('', views.services_index, name='index'),
    path('industrial-automation/', views.industrial_automation, name='industrial_automation'),
    path('smart-factory/', views.smart_factory, name='smart_factory'),
    path('iot-integration/', views.iot_integration, name='iot_integration'),
    path('predictive-maintenance/', views.predictive_maintenance, name='predictive_maintenance'),
    path('erp-integration/', views.erp_integration, name='erp_integration'),
    path('erpnext-cloud/', views.erpnext_dashboard, name='erpnext_dashboard'),
    path('crm-integration/', views.crm_integration, name='crm_integration'),
    path('export-invoice-pdf/', views.export_invoice_pdf, name='export_invoice_pdf'),
    # Case studies page removed
    path('competitor-tracking/', views.competitor_tracking, name='competitor_tracking'),
    path('market-analysis-tools/', views.market_analysis_tools, name='market_analysis_tools'),
    path('seo-analytics/', views.seo_analytics, name='seo_analytics'),
    path('seo-performance-dashboard/', views.seo_performance_dashboard, name='seo_performance_dashboard'),
    path('social-intelligence/', views.social_intelligence, name='social_intelligence'),
    path('social-media-tracking/', views.social_media_tracking, name='social_media_tracking'),
    path('social-tracking/', views.social_tracking, name='social_tracking'),
    path('link-analyzer/', views.link_analyzer, name='link_analyzer'),
    path('keyword-research/', views.keyword_research, name='keyword_research'),
    path('keyword-checker/', views.keyword_checker, name='keyword_checker'),
    path('engagement-analytics/', views.engagement_analytics, name='engagement_analytics'),
    path('social-media/dashboard/', views.social_dashboard_view, name='social_dashboard'),
    path('social-media/crawl/', views.run_social_crawl, name='run_social_crawl'),
    path('platform-monitoring/', views.platform_monitoring, name='platform_monitoring'),
    path('platform-links/', views.platform_links, name='platform_links'),
    path('detail/<slug:page>/', views.service_detail, name='detail'),
]
