import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'onwebapp.settings')
import django
django.setup()
from seo_analyzer.services.link_checker import analyze_links

for analysis_type in ['internal', 'external', 'backlinks']:
    result = analyze_links('https://amazon.fr', analysis_type)
    links = result.get('links', [])
    print(analysis_type, 'status=', result.get('status'))
    print('summary=', result.get('summary'))
    print('links_len=', len(links))
    if links:
        print('first=', links[0])
    print('---')
