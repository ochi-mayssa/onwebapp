#!/usr/bin/env python3
import sys
import os
import json

project_root = r"c:\Users\PC-HP\Documents\version final\OnWebAppFinal\OnWebApp v6"
sys.path.append(project_root)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "websity_project.settings")
import django
django.setup()

from seo_analyzer.services.modular_sitemap_intelligence import VideoIntelligencePipeline

url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
metadata = VideoIntelligencePipeline.extract_video_metadata(url, url)
print("=== METADATA ===")
print(json.dumps(metadata, ensure_ascii=True, indent=2))

analysis = VideoIntelligencePipeline.analyze_topic_and_keywords(metadata)
print("\n=== ANALYSIS ===")
print(json.dumps(analysis, ensure_ascii=True, indent=2))

video_context = VideoIntelligencePipeline.build_video_context(url, url, "digital marketing")
print("\n=== VIDEO CONTEXT ===")
print(f"Industry: {video_context.get('industry')}")
print(f"Audience: {video_context.get('audience')}")
print(f"Topic: {video_context.get('topic')}")
print(f"Title: {video_context.get('title')}")
print(f"Channel: {video_context.get('channel')}")
