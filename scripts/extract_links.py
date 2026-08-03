#!/usr/bin/env python3
"""
Extract URL patterns and links across the Django project.
Generates `links_report.json` with:
- all named routes (from URL resolver)
- all templates with href/src/form action and `{% url %}` occurrences
- classification internal/external
- attempt to resolve named routes using DB objects (tries reverse(), then reverse with a model instance pk)

Usage: python scripts/extract_links.py --output links_report.json
"""
import os
import re
import json
import argparse
from glob import glob
from urllib.parse import urlparse

OUTPUT_DEFAULT = 'links_report.json'


def find_templates(root):
    patterns = [os.path.join(root, '**', '*.html')]
    files = []
    for p in patterns:
        files.extend(glob(p, recursive=True))
    return sorted(files)


def extract_from_template(path):
    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read()
    results = []
    # find href/src/action occurrences
    for m in re.finditer(r'(href|src|action)\s*=\s*"([^"]+)"', txt):
        attr, url = m.group(1), m.group(2)
        results.append({'attr': attr, 'raw': url})
    for m in re.finditer(r"(href|src|action)\s*=\s*'([^']+)'", txt):
        attr, url = m.group(1), m.group(2)
        results.append({'attr': attr, 'raw': url})
    # find {% url 'name' ... %}
    for m in re.finditer(r"\{\%\s*url\s+(['\"])([^'\"]+)\1([\s\S]*?)\%\}", txt):
        name = m.group(2).strip()
        results.append({'attr': 'django_url_tag', 'raw': name})
    return results


def classify_link(raw):
    # django url tag
    if raw.startswith('{%') or raw.startswith('{%'):
        return 'internal'
    if raw.startswith('http://') or raw.startswith('https://') or raw.startswith('//'):
        return 'external'
    if raw.startswith('/'):
        return 'internal'
    return 'internal'


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', default=OUTPUT_DEFAULT)
    args = p.parse_args()

    root = os.getcwd()

    # 1. Collect named URL patterns via Django resolver
    routes = []
    try:
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'websity_project.settings')
        django.setup()
        from django.urls import get_resolver, reverse
        resolver = get_resolver()

        def walk_patterns(patterns, prefix=''):
            for pat in patterns:
                name = getattr(pat, 'name', None)
                pattern_str = None
                try:
                    pattern_str = getattr(pat.pattern, '_route', getattr(pat.pattern, 'regex', None))
                except Exception:
                    pattern_str = None
                if name:
                    routes.append({'name': name, 'pattern': str(pattern_str)})
                # descend into included resolvers
                if hasattr(pat, 'url_patterns'):
                    walk_patterns(pat.url_patterns, prefix=prefix)
        walk_patterns(resolver.url_patterns)
    except Exception as e:
        routes = []
        resolver_error = str(e)
    # 2. Scan templates
    templates = find_templates(root)
    links = []
    for t in templates:
        items = extract_from_template(t)
        for it in items:
            url_raw = it['raw']
            typ = 'external' if url_raw.startswith('http') or url_raw.startswith('//') else 'internal'
            links.append({'type': typ, 'url': url_raw, 'source': os.path.relpath(t, root), 'attr': it['attr']})

    report = {'routes': routes, 'templates_scanned': len(templates), 'links': links}

    # 3. Attempt to resolve named routes using Django reverse and DB objects
    resolutions = []
    try:
        from django.apps import apps
        from django.core.exceptions import NoReverseMatch
        model_list = apps.get_models()
        # build simple candidates: for each model get first object's pk and slug if present
        candidates = []
        for m in model_list:
            try:
                qs = m.objects.all()[:1]
                if qs:
                    obj = list(qs)[0]
                    pk = getattr(obj, 'pk', None)
                    slug = getattr(obj, 'slug', None)
                    candidates.append({'model': f'{m._meta.app_label}.{m._meta.model_name}', 'pk': pk, 'slug': slug})
            except Exception:
                continue
        for r in routes:
            name = r['name']
            res = {'name': name, 'pattern': r.get('pattern'), 'resolved': False, 'tried': []}
            try:
                url = reverse(name)
                res['resolved'] = True
                res['url'] = url
            except Exception as e:
                res['tried'].append({'method': 'reverse()', 'error': str(e)})
                # try with candidate pks
                for c in candidates:
                    try:
                        if c['pk'] is not None:
                            url = reverse(name, args=[c['pk']])
                            res['resolved'] = True
                            res['url'] = url
                            res['resolved_with'] = {'model': c['model'], 'pk': c['pk']}
                            break
                    except Exception as e2:
                        res['tried'].append({'method': f'reverse(args=[{c.get("pk")}])', 'error': str(e2), 'model': c['model']})
                        continue
                # try kwargs slug
                if not res['resolved']:
                    for c in candidates:
                        try:
                            if c.get('slug'):
                                url = reverse(name, kwargs={'slug': c['slug']})
                                res['resolved'] = True
                                res['url'] = url
                                res['resolved_with'] = {'model': c['model'], 'slug': c['slug']}
                                break
                        except Exception as e3:
                            res['tried'].append({'method': f"reverse(kwargs={{'slug':...}})", 'error': str(e3), 'model': c['model']})
            resolutions.append(res)
    except Exception as e:
        resolutions = {'error': str(e)}

    report['route_resolutions'] = resolutions

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('Wrote', args.output)
