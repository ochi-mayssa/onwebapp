
import os
import django
from pprint import pprint

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()

from django.test import RequestFactory
from seo_analyzer.views import sitemap_view
from seo_analyzer.forms import SitemapIntelligenceForm
from seo_analyzer.services.modular_sitemap_intelligence import build_modular_sitemap_intelligence_report

# Build report first
report = build_modular_sitemap_intelligence_report(
    url="https://www.sitemaps.org/protocol.html",
    target_keyword="digital marketing"
)

# Create POST request with proper host
factory = RequestFactory()
request = factory.post(
    '/seo/sitemap/', 
    {
        'url': "https://www.sitemaps.org/protocol.html",
        'target_keyword': "digital marketing"
    },
    HTTP_HOST='127.0.0.1:8000'
)

# Render the template manually to see what's in there
from django.template import loader
template = loader.get_template('seo_analyzer/sitemap.html')
context = {
    'form': SitemapIntelligenceForm(),
    'report': report,
    'topic_intelligence': report['topic_intelligence']
}
rendered = template.render(context, request)

# Save the rendered HTML to a file so we can look at it!
with open("test_rendered.html", "w", encoding="utf-8") as f:
    f.write(rendered)

print("=== Saved rendered HTML to test_rendered.html ===")
print("\n=== report.executive_summary keys ===")
pprint(list(report['executive_summary'].keys()))
print("\n=== report.executive_summary.target_keyword ===")
print(report['executive_summary']['target_keyword'])
print("\n=== report.content_alignment ===")
pprint(report['content_alignment'])
