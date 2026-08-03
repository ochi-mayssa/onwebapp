"""
URL configuration for websity_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.sitemaps.views import sitemap
from django.views.generic.base import RedirectView
from .sitemaps import StaticViewSitemap, ProjectSitemap
from django.conf import settings
from django.conf.urls.static import static
from home.views import api_status
from django.urls import reverse_lazy
import rest_framework_simplejwt.views
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from branding.admin_site import branding_admin_site

urlpatterns = [
    path('admin/', admin.site.urls),
    path('admin/branding-dashboard/', branding_admin_site.urls),
    path('api/status/', api_status, name='api_status'),
    path('chatbot/', include('chatbot.urls', namespace='chatbot')),
    path('services/', include('services.urls', namespace='services')),
    path('services-old-redirect/', RedirectView.as_view(url=reverse_lazy('platform_monitoring:hub'), permanent=False), name='services_index_redirect'),
    path('platform/redirect/', RedirectView.as_view(url=reverse_lazy('platform_monitoring:hub'), permanent=False), name='platform_redirect'),
    path('contact/', include('contact.urls', namespace='contact')),
    path('blog/', include('blog.urls', namespace='blog')),
    path('payments/', include('payments.urls', namespace='payments')),
    path('seo/', include('seo_analyzer.urls', namespace='seo_analyzer')),
    path('projects/', include('projects.urls')),
    path('platform/', include('platform_app.urls', namespace='platform')),
    path('platform-monitoring/', include('platform_monitoring.urls', namespace='platform_monitoring')),
    path('operations/', include('operations.urls')),
    path('rpa/', include('rpa_dashboard.urls')),
    path('crm/', include('crm.urls')),
    path('i18n/', include('django.conf.urls.i18n')),
    path('users/', include('users.urls', namespace='users')),
    path('community/', include('community.urls')),
    path('forum/', include('forum.urls', namespace='forum')),
    path('social-proof/', include('social_proof.urls')),
    path('branding/', include('branding.urls', namespace='branding')),

    # Branding REST API
    path('api/branding/', include('branding.api.urls', namespace='branding-api')),
    path('api/branding/auth/token/', rest_framework_simplejwt.views.TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/branding/auth/token/refresh/', rest_framework_simplejwt.views.TokenRefreshView.as_view(), name='token_refresh'),
    path('api/branding/auth/token/verify/', rest_framework_simplejwt.views.TokenVerifyView.as_view(), name='token_verify'),

    # API schema documentation
    path('api/branding/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/branding/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('home.urls', namespace='home')),
    path('sitemap.xml', sitemap, {'sitemaps': {'static': StaticViewSitemap(), 'projects': ProjectSitemap() if ProjectSitemap else None}}, name='sitemap'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
