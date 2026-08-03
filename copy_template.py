
import shutil
import os

source = r"c:\Users\PC-HP\Documents\version final\OnWebAppFinal\OnWebApp v6\seo_analyzer\templates\seo_analyzer\sitemap.html"
destination = r"c:\Users\PC-HP\Documents\version final\OnWebAppFinal\OnWebApp v6\OnWebApp v6\seo_analyzer\templates\seo_analyzer\sitemap.html"

os.makedirs(os.path.dirname(destination), exist_ok=True)
shutil.copyfile(source, destination)
print("File copied successfully!")
