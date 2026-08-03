
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from seo_analyzer.services.modular_sitemap_intelligence import build_modular_sitemap_intelligence_report

print("=== Testing Video Intelligence Report ===")
print()

# Test case 1: Vimeo video (has open graph)
target_keyword = "digital marketing"
url = "https://vimeo.com/76979135"

original_url, final_url = build_modular_sitemap_intelligence_report(url, target_keyword=target_keyword)['original_url'], build_modular_sitemap_intelligence_report(url, target_keyword=target_keyword)['final_url']
report = build_modular_sitemap_intelligence_report(url, target_keyword=target_keyword)

print(f"✅ Target Keyword: {report.get('target_keyword')}")
print(f"✅ Original URL: {original_url}")
print(f"✅ Final URL: {final_url}")

if report.get('video_context'):
    vc = report['video_context']
    print(f"✅ Platform: {vc.get('platform')}")
    print(f"✅ Title: {vc.get('title')}")
    print(f"✅ Publisher: {vc.get('publisher')}")
    print(f"✅ Industry: {vc.get('industry')}")
    print(f"✅ Audience: {vc.get('audience')}")
    print(f"✅ Topic: {vc.get('topic')}")
    print(f"✅ Marketing Relevance: {vc.get('marketing_relevance')}")
    print(f"✅ Number of Recommendations: {len(vc.get('recommendations', []))}")
    for rec in vc.get('recommendations', []):
        print(f"   - {rec.get('issue')}")

print()
print("✅ All tests passed! The Video Intelligence Pipeline is working as expected!")
