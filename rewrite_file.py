with open(r"c:\Users\PC-HP\Documents\version final\OnWebAppFinal\OnWebApp v6\seo_analyzer\services\modular_sitemap_intelligence.py", "r", encoding="utf-8") as f:
    lines = f.read().splitlines()

# Now build the new line list!
new_lines = []

# Part 1: Lines 0-43 (VideoIntelligencePipeline class variables, up to just before PageIntelligencePipeline
new_lines += lines[0:44]

# Part 2: Lines 313-929 (VideoIntelligencePipeline methods)
new_lines += lines[313:930]

# Part 3: Lines 44-312 (PageIntelligencePipeline class and its methods)
new_lines += lines[44:313]

# Part4: The rest of the file
new_lines += lines[930:]

# Now write to the file!
with open(r"c:\Users\PC-HP\Documents\version final\OnWebAppFinal\OnWebApp v6\seo_analyzer\services\modular_sitemap_intelligence.py", "w", encoding="utf-8") as f:
    for line in new_lines:
        f.write(line + "\n")

print("File rewritten successfully!")
