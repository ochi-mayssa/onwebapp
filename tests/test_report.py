
import os
import django
from pprint import pprint
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
django.setup()
from seo_analyzer.services.modular_sitemap_intelligence import build_modular_sitemap_intelligence_report
report = build_modular_sitemap_intelligence_report(
    url="https://www.linternaute.fr/dictionnaire/fr/definition/cu/",
    target_keyword="digital marketing"
)
print("=== report['target_keyword']")
pprint(report['target_keyword'])
print("\n=== report['topic_intelligence']['detected_topic']")
pprint(report['topic_intelligence']['detected_topic'])
print("\n=== report['executive_summary']['detected_topic']")
pprint(report['executive_summary']['detected_topic'])
print("\n=== report['content_alignment']['detected_topic']")
pprint(report['content_alignment']['detected_topic'])
print("\n=== report['module_results'].keys()")
pprint(report['module_results'].keys())
print("\n=== report['module_results']")
pprint(report['module_results'])
print("\n=== report['all_recommendations']['High']")
pprint(report['all_recommendations']['High'])
