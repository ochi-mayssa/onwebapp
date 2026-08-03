#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

url = "https://www.youtube.com/watch?v=7g0Kb_1dFp0"
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Accept-Language": "en-US,en;q=0.5"
})
response = session.get(url, timeout=15, allow_redirects=True)
print("Response status:", response.status_code)
print("-" * 80)

soup = BeautifulSoup(response.content, "html.parser")

# Print OpenGraph tags
print("OpenGraph tags found:")
for og in soup.find_all("meta", property=lambda x: x and x.startswith("og:")):
    print(f"  {og.get('property')}: {og.get('content')[:200]}")
print("-" * 80)

# Print <title> tag
title_tag = soup.find("title")
print("<title> tag:", title_tag.get_text(strip=True) if title_tag else None)
print("-" * 80)

# Print JSON-LD scripts
print("JSON-LD scripts:")
for script in soup.find_all("script", type="application/ld+json"):
    try:
        import json
        data = json.loads(script.string)
        print(json.dumps(data, indent=2)[:2000])
    except Exception as e:
        print(f"  Error parsing JSON-LD: {e}")
        print(f"  Script content (first 500 chars): {script.string[:500] if script.string else None}")
    print("-" * 40)
