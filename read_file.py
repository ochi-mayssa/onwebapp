with open(r"c:\Users\PC-HP\Documents\version final\OnWebAppFinal\OnWebApp v6\seo_analyzer\services\modular_sitemap_intelligence.py", "r", encoding="utf-8") as f:
    content = f.read()
    lines = content.splitlines()
    print(f"Total lines: {len(lines)}")

    # Find where VideoIntelligencePipeline starts
    vip_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("class VideoIntelligencePipeline:"):
            vip_start = i
            break
    print(f"VideoIntelligencePipeline starts at line {vip_start}")

    # Find where PageIntelligencePipeline starts
    pip_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("class PageIntelligencePipeline:"):
            pip_start = i
            break
    print(f"PageIntelligencePipeline starts at line {pip_start}")

    # Find where extract_video_metadata starts
    evm_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("@staticmethod") and "extract_video_metadata" in lines[i+1]:
            evm_start = i
            break
    print(f"extract_video_metadata starts at line {evm_start}")

    # Now let's build the correct file!
    part1 = lines[0:44]  # lines 0-43: imports + VideoIntelligencePipeline class variables (wait no, line 44 is PIP start)
    # Let's adjust!
    # Part 1: from start to line 43 (before PIP)
    part1 = lines[0:44]
    # Part 2: lines from evm_start to line where PIP was supposed to end (but instead let's take the rest after PIP's methods!)
    # Wait let's look at what's after line 928!
    print("\nLines 920-940:")
    for i in range(920, 940):
        print(f"{i+1}: {lines[i]}")
