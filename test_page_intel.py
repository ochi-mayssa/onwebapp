
from seo_analyzer.services.modular_sitemap_intelligence import PageIntelligencePipeline
from seo_analyzer.services.topic_intelligence import build_topic_intelligence_from_url

url = "https://yoast.com/what-is-seo/"
target_keyword = "digital marketing"

print("=== Building topic intelligence ===")
topic_intel = build_topic_intelligence_from_url(url)
print("Topic intel keys:", list(topic_intel.keys()))
print("Primary keyword:", topic_intel.get('primary_keyword'))
print("Detected topic:", topic_intel.get('detected_topic'))
print("Secondary keywords:", topic_intel.get('secondary_keywords'))
print("Semantic keywords:", topic_intel.get('semantic_keywords'))
print("Search intent:", topic_intel.get('search_intent'))
print("Content category:", topic_intel.get('content_category'))
print("Topic cluster:", topic_intel.get('topic_cluster'))
print("Target audience:", topic_intel.get('target_audience'))
print("Page title:", topic_intel.get('page_title'))
print("Meta description:", topic_intel.get('meta_description'))
print("H1:", topic_intel.get('primary_h1'))
print("H2 headings:", topic_intel.get('primary_h2'))
print("Keyword coverage:", topic_intel.get('keyword_coverage_pct'))
print("Semantic relevance:", topic_intel.get('semantic_relevance_pct'))

print("\n=== Analyzing topic and keywords ===")
analysis = PageIntelligencePipeline.analyze_topic_and_keywords(topic_intel)
print("Analysis:", analysis)

print("\n=== Calculating scores ===")
scores = PageIntelligencePipeline.calculate_scores(topic_intel, analysis, target_keyword)
print("Scores:", scores)

print("\n=== Building page context ===")
page_context = PageIntelligencePipeline.build_page_context(url, url, target_keyword)
print("Page context keys:", list(page_context.keys()))
print("Topic:", page_context.get('topic'))
print("Primary keyword:", page_context.get('primary_keyword'))
print("Marketing alignment score:", page_context.get('marketing_alignment_score'))
print("Marketing relevance:", page_context.get('marketing_relevance'))
