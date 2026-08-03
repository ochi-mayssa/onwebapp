
import sys
import os

# Add the seo_analyzer directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from seo_analyzer.services.topic_intelligence import (
    _analyze_image_intelligence,
    _analyze_video_intelligence,
    _analyze_text_intelligence,
    _analyze_google_discovery,
    _analyze_digital_marketing_intelligence,
)

print("Testing individual functions...")

# Test image intelligence
print("\n1. Testing _analyze_image_intelligence:")
img_result = _analyze_image_intelligence(
    all_images=[],
    target_keyword="digital marketing"
)
print(f"Success: {img_result.get('image_seo_score')}")

# Test video intelligence
print("\n2. Testing _analyze_video_intelligence:")
vid_result = _analyze_video_intelligence(
    all_videos=[],
    has_video_schema=False,
    target_keyword="digital marketing",
    page_text="Some test page text"
)
print(f"Success: {vid_result.get('video_seo_score')}")

# Test text intelligence (mocked topic_intel)
print("\n3. Testing _analyze_text_intelligence:")
mock_topic_intel = {
    "primary_keyword": "islamic audio",
    "secondary_keywords": ["audio", "religion"],
    "semantic_relevance_pct": 5,
    "search_intent": "informational"
}
text_result = _analyze_text_intelligence(
    topic_intel=mock_topic_intel,
    target_keyword="digital marketing",
    page_text="Some islamic audio content"
)
alignment = text_result.get("content_alignment")
print(f"Success: {alignment.get('topic_match')}% topic match")
print(f"   Marketing relevance: {alignment.get('marketing_relevance')}")

# Test google discovery
print("\n4. Testing _analyze_google_discovery:")
disc_result = _analyze_google_discovery(
    xml_found=True,
    image_score=70,
    video_score=60,
    mobile_score=85,
    keyword_score=50
)
print(f"Success: {disc_result.get('discovery_score')}")

# Test digital marketing
print("\n5. Testing _analyze_digital_marketing_intelligence:")
dm_result = _analyze_digital_marketing_intelligence(
    text_intel=text_result,
    image_intel=img_result,
    video_intel=vid_result,
    target_keyword="digital marketing"
)
print(f"Success: {dm_result.get('primary_marketing_keyword')}")

print("\nAll functions tested successfully!")

