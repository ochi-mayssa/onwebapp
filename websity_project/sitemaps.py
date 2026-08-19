from django.contrib.sitemaps import Sitemap
from django.urls import reverse
import logging

logger = logging.getLogger(__name__)


class StaticViewSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.6

    def items(self):
        return [
            'home:home',
            'services:index',
            'integration:integration_homepage',
            'integration:system_integration',
            'integration:data_integration',
            'integration:b2b_integration',
            'branding:landing',
            'community:home',
            'blog:index',
            'blog:article_list',
            'seo_analyzer:index',
            'platform:index',
            'platform_monitoring:hub',
            'contact:contact',
        ]

    def location(self, item):
        try:
            return reverse(item)
        except Exception:
            logger.debug('Failed to reverse sitemap item: %s', item)
            return '/'


try:
    from projects.models import Project


    class ProjectSitemap(Sitemap):
        changefreq = 'monthly'
        priority = 0.5

        def items(self):
            return Project.objects.all()

        def lastmod(self, obj):
            return getattr(obj, 'updated_at', None)

        def location(self, obj):
            # Prefer preview_url if present; otherwise try get_absolute_url
            if getattr(obj, 'preview_url', None):
                return obj.preview_url
            if hasattr(obj, 'get_absolute_url'):
                return obj.get_absolute_url()
            # Fallback: try to build a detail path if app exposes one
            try:
                return reverse('projects:project_detail', args=[obj.pk])
            except Exception:
                return '/'

except Exception:
    # Projects app or model not available; skip ProjectSitemap
    ProjectSitemap = None
