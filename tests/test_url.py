
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from seo_analyzer.services.pre_check import perform_free_website_pre_check

print("Testing https://example.com/...")
results_example = perform_free_website_pre_check("https://example.com/")
print(f"Status: {results_example['status_label']}")
print(f"Health score: {results_example['health_score']}")
print("Checks:")
for c in results_example['checks']:
    print(f"  - {c['name']}: {c['status']} ({c['finding']})")
print("\nTesting https://www.seo.fr/definition/seo-definition...")
results_seo = perform_free_website_pre_check("https://www.seo.fr/definition/seo-definition")
print(f"Status: {results_seo['status_label']}")
print(f"Health score: {results_seo['health_score']}")
print("Checks:")
for c in results_seo['checks']:
    print(f"  - {c['name']}: {c['status']} ({c['finding']})")

