#!/usr/bin/env python3
"""
Simple site audit script: crawls a site (limited depth/pages), collects internal/external links,
checks HTTP status codes, and fetches sitemap.xml and robots.txt.

Usage:
  python scripts/site_audit.py http://127.0.0.1:8000 --max-pages 200 --output report.json

This script uses only the standard library plus `requests` if available; it will
fall back to urllib if requests is not installed.
"""
import sys
import argparse
import json
import time
from urllib.parse import urljoin, urlparse

try:
    import requests
    _HAS_REQUESTS = True
except Exception:
    import urllib.request as _urllib_request
    _HAS_REQUESTS = False

from html.parser import HTMLParser


class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and 'href' in attrs:
            self.links.add(attrs['href'])
        if tag in ('img', 'script') and 'src' in attrs:
            self.links.add(attrs['src'])
        if tag == 'link' and attrs.get('rel') in ('canonical', 'alternate') and 'href' in attrs:
            self.links.add(attrs['href'])


def fetch_url(url, timeout=8):
    if _HAS_REQUESTS:
        try:
            r = requests.get(url, timeout=timeout)
            return r.status_code, r.text
        except Exception as e:
            return None, str(e)
    else:
        try:
            with _urllib_request.urlopen(url, timeout=timeout) as r:
                return r.getcode(), r.read().decode(errors='replace')
        except Exception as e:
            return None, str(e)


def is_same_host(u1, base_netloc):
    try:
        p = urlparse(u1)
        return (p.netloc == '' or p.netloc == base_netloc)
    except Exception:
        return False


def normalize_link(href, base):
    if not href:
        return None
    href = href.strip()
    if href.startswith('mailto:') or href.startswith('tel:') or href.startswith('javascript:'):
        return None
    return urljoin(base, href)


def crawl(base_url, max_pages=200):
    parsed = urlparse(base_url)
    base_netloc = parsed.netloc
    to_visit = [base_url]
    visited = set()
    results = {'pages': {}, 'broken_links': [], 'external_links': set(), 'sitemaps': {}, 'robots': None}

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)
        status, body = fetch_url(url)
        results['pages'][url] = {'status': status}
        if status is None or (isinstance(status, int) and status >= 400):
            results['broken_links'].append({'url': url, 'status': status})
            continue

        le = LinkExtractor()
        try:
            le.feed(body)
        except Exception:
            pass

        for href in le.links:
            full = normalize_link(href, url)
            if not full:
                continue
            p = urlparse(full)
            if is_same_host(full, base_netloc):
                if full not in visited and full not in to_visit:
                    to_visit.append(full)
            else:
                results['external_links'].add(full)
                # optionally check external link status lightly
    # fetch sitemap and robots
    for candidate in ('/sitemap.xml', '/sitemap_index.xml'):
        u = urljoin(base_url, candidate)
        st, body = fetch_url(u)
        results['sitemaps'][candidate] = {'status': st, 'present': st == 200}

    rt, rb = fetch_url(urljoin(base_url, '/robots.txt'))
    results['robots'] = {'status': rt, 'body': rb if rt == 200 else None}

    # finalize sets
    results['external_links'] = sorted(list(results['external_links']))
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument('base_url')
    p.add_argument('--max-pages', type=int, default=200)
    p.add_argument('--output', default='site_audit_report.json')
    args = p.parse_args()

    start = time.time()
    report = crawl(args.base_url, max_pages=args.max_pages)
    report['meta'] = {'base_url': args.base_url, 'duration_seconds': time.time() - start}

    with open(args.output, 'w', encoding='utf-8') as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print('Audit complete — report written to', args.output)


if __name__ == '__main__':
    main()
