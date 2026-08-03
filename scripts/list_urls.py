#!/usr/bin/env python3
import os
import re
import json
from glob import glob

ROOT = os.getcwd()

pattern = re.compile(r"path\(\s*['\"](?P<route>[^'\"]+)['\"]\s*,[\s\S]*?name\s*=\s*['\"](?P<name>[^'\"]+)['\"]\s*\)")
pattern_re = re.compile(r"re_path\(\s*r?['\"](?P<route>[^'\"]+)['\"]\s*,[\s\S]*?name\s*=\s*['\"](?P<name>[^'\"]+)['\"]\s*\)")

routes = []
for fp in glob('**/urls.py', recursive=True):
    try:
        with open(fp, 'r', encoding='utf-8') as f:
            txt = f.read()
        for m in pattern.finditer(txt):
            routes.append({'file': fp, 'type': 'path', 'pattern': m.group('route'), 'name': m.group('name')})
        for m in pattern_re.finditer(txt):
            routes.append({'file': fp, 'type': 're_path', 'pattern': m.group('route'), 'name': m.group('name')})
    except Exception:
        continue

# attempt Django resolution
resolutions = []
try:
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
    django.setup()
    from django.urls import reverse, NoReverseMatch
    from django.apps import apps
    models = list(apps.get_models())
    candidates = []
    for m in models:
        try:
            qs = m.objects.all()[:1]
            if qs:
                obj = list(qs)[0]
                candidates.append({'model': f'{m._meta.app_label}.{m._meta.model_name}', 'pk': getattr(obj, 'pk', None), 'slug': getattr(obj, 'slug', None)})
        except Exception:
            continue
    for r in routes:
        name = r['name']
        res = {'name': name, 'pattern': r['pattern'], 'file': r['file'], 'resolved': False, 'details': []}
        try:
            u = reverse(name)
            res['resolved'] = True
            res['url'] = u
        except Exception as e:
            res['details'].append({'method': 'reverse()', 'error': str(e)})
            for c in candidates:
                try:
                    if c.get('pk') is not None:
                        u = reverse(name, args=[c['pk']])
                        res['resolved'] = True
                        res['url'] = u
                        res['resolved_with'] = {'model': c['model'], 'pk': c['pk']}
                        break
                except Exception as e2:
                    res['details'].append({'method': f'reverse(args=[{c.get("pk")}])', 'error': str(e2), 'model': c['model']})
            if not res['resolved']:
                for c in candidates:
                    try:
                        if c.get('slug'):
                            u = reverse(name, kwargs={'slug': c['slug']})
                            res['resolved'] = True
                            res['url'] = u
                            res['resolved_with'] = {'model': c['model'], 'slug': c['slug']}
                            break
                    except Exception as e3:
                        res['details'].append({'method': "reverse(kwargs={'slug':...})", 'error': str(e3), 'model': c['model']})
        resolutions.append(res)
except Exception as e:
    resolutions = {'error': str(e)}

out = {'routes_found': len(routes), 'routes': routes, 'resolutions': resolutions}
with open('routes_list.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print('Wrote routes_list.json')
