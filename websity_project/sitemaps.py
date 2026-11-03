from django.contrib.sitemaps import Sitemap
from django.urls import reverse, NoReverseMatch
import logging

logger = logging.getLogger(__name__)


class StaticViewSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.6

    # Public marketing/SEO pages only. Auth-gated pages (e.g. /platform/,
    # /platform-monitoring/) are deliberately excluded: they 302 to the login
    # screen, which would send search crawlers to a noindex page.
    _url_names = [
        'home:home',
        'home:about',
        'home:testimonials',
        'home:privacy',
        'home:terms',
        'home:automation_home',
        'home:rpa_bpa',
        'home:rpa_solutions',
        'home:website_automation',
        'home:enterprise_automation',
        'home:ux_design',
        'home:ui_design',
        'home:software_home',
        'home:web_development',
        'home:mobile_development',
        'home:ecommerce_development',
        'home:dashboard_development',
        'home:api_solutions',
        'home:browser_web_automation',
        'home:request_api',
        'home:api_docs',
        'home:video_explainer',
        'home:build_website',
        'services:index',
        'services:industrial_automation',
        'integration:integration_homepage',
        'integration:system_integration',
        'integration:data_integration',
        'integration:b2b_integration',
        'branding:landing',
        'community:home',
        'blog:index',
        'blog:articles',
        'seo_analyzer:index',
        'contact:contact',
    ]

    def items(self):
        # Only emit names that actually reverse. A name that fails to reverse
        # would otherwise fall back to '/' and duplicate the homepage entry.
        valid = []
        for name in self._url_names:
            try:
                reverse(name)
            except NoReverseMatch:
                logger.debug('Skipping non-reversible sitemap item: %s', name)
                continue
            valid.append(name)
        return valid

    def location(self, item):
        try:
            return reverse(item)
        except NoReverseMatch:
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
