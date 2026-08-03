import os
import re

referenced_templates = set()
for root, dirs, files in os.walk('branding'):
    if '__pycache__' in root:
        continue
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            try:
                with open(path) as fh:
                    content = fh.read()
                    matches = re.findall(r'render\([^,]+,\s*[\'"]([^\'"]+\.html)[\'"]', content)
                    referenced_templates.update(matches)
            except: 
                pass

for t in sorted(referenced_templates):
    print(t)