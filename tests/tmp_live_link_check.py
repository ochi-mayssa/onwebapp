import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
import django
django.setup()
from seo_analyzer.services.link_checker import analyze_links

for url in ['https://amazon.fr','https://oise.com','https://eu.iko.com']:
    print('URL', url)
    for analysis_type in ['internal','external','backlinks']:
        try:
            report = analyze_links(url, analysis_type)
            print(analysis_type, report['status'], report.get('summary', {}).get('total_links'), report.get('message',''))
            if analysis_type == 'external' and report.get('links'):
                print('  sample domains', [row.get('external_domain') for row in report['links'][:5]])
            if analysis_type == 'backlinks':
                print('  fallback', report.get('fallback_message',''))
        except Exception as exc:
            print(analysis_type, 'ERROR', repr(exc))
    print('---')
