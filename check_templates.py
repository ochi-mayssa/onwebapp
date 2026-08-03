import os
import re

# Find all template files
template_dirs = []
for root, dirs, files in os.walk('templates'):
    for f in files:
        if f.endswith('.html'):
            template_dirs.append(os.path.join(root, f))

# Check which templates are referenced in views
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

print(f'Total templates found: {len(template_dirs)}')
print(f'Templates referenced in branding views: {len(referenced_templates)}')
print()

# Find unused templates in branding directory
branding_templates = [t for t in template_dirs if t.startswith('templates/branding/')]
for t in sorted(branding_templates):
    rel = t.replace('templates/', '')
    if rel not in referenced_templates:
        print(f'Potentially unused: {rel}')