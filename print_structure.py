with open(r"c:\Users\PC-HP\Documents\version final\OnWebAppFinal\OnWebApp v6\seo_analyzer\services\modular_sitemap_intelligence.py", "r", encoding="utf-8") as f:
    lines = f.read().splitlines()

for i in range(len(lines)):
    stripped_line = lines[i].strip()
    if stripped_line.startswith("class "):
        print(f"{i} ({i+1}): {stripped_line}")
    if stripped_line.startswith("@staticmethod"):
        if (i+1) < len(lines):
            print(f"  {i} ({i+1}): {stripped_line}")
            print(f"  {i+1} ({i+2}): {lines[i+1].strip()}")
