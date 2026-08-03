#!/usr/bin/env python3
import json
import csv
import re
from pathlib import Path

root = Path.cwd()
links_json = root / 'links_report.json'
routes_json = root / 'routes_list.json'
out_csv = root / 'links_report.csv'

with open(links_json, 'r', encoding='utf-8') as f:
    data = json.load(f)
links = data.get('links', [])

routes_map = {}
if routes_json.exists():
    with open(routes_json, 'r', encoding='utf-8') as f:
        rdata = json.load(f)
    for r in rdata.get('routes', []):
        routes_map[r.get('name')] = r.get('pattern')

# helper to extract django url name
dj_re = re.compile(r"\{\%\s*url\s+['\"]([^'\"]+)['\"]")

with open(out_csv, 'w', newline='', encoding='utf-8') as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=['type','url','source','attr','django_route_name','route_pattern'])
    writer.writeheader()
    for l in links:
        raw = l.get('url') or ''
        route_name = ''
        m = dj_re.search(raw)
        if m:
            route_name = m.group(1)
        # also handle django_url_tag entries where raw is like 'app:name'
        if l.get('attr') == 'django_url_tag' and not route_name:
            route_name = raw.strip()
        pattern = routes_map.get(route_name, '')
        writer.writerow({
            'type': l.get('type',''),
            'url': raw,
            'source': l.get('source',''),
            'attr': l.get('attr',''),
            'django_route_name': route_name,
            'route_pattern': pattern,
        })

print('Wrote', out_csv)
