#!/usr/bin/env python3
"""
Lightweight SEO audit crawler
Usage: python scripts/seo_audit.py https://example.com --max-pages 50 --output audit_report.json

Notes:
- This script uses requests + BeautifulSoup to collect HTTP-accessible data.
- It cannot measure real Core Web Vitals (requires a browser/Lighthouse / field data).
- Backlink data from external domains requires external APIs (Ahrefs/SEMrush) and is not available here.
"""
import argparse
import json
import time
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


HEADERS = {"User-Agent": "OnWebApp-SEO-Audit/1.0 (+https://example.com)"}


def is_same_domain(base_netloc, url):
    try:
        return urlparse(url).netloc == base_netloc or urlparse(url).netloc == ''
    except Exception:
        return False


def norm_url(base, link):
    try:
        return urljoin(base, link)
    except Exception:
        return None


def extract_text(soup):
    for s in soup(['script', 'style', 'noscript']):
        s.extract()
    text = soup.get_text(separator=' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def analyze_page(url, base_netloc, session):
    rec = {'url': url, 'status': None, 'final_url': None, 'response_time': None, 'size_bytes': None,
           'title': None, 'meta_description': None, 'canonical': None, 'h1': [], 'h2': [],
           'internal_links': [], 'external_links': [], 'images': [], 'scripts': [], 'word_count': 0,
           'top_words': [], 'issues': []}
    try:
        start = time.time()
        r = session.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        elapsed = time.time() - start
        rec['status'] = r.status_code
        rec['final_url'] = r.url
        rec['response_time'] = elapsed
        rec['size_bytes'] = len(r.content)

        if r.status_code >= 400:
            rec['issues'].append(f'HTTP {r.status_code}')

        ct = r.headers.get('content-type','')
        if 'text/html' not in ct:
            rec['issues'].append('Non-HTML content')
            return rec

        soup = BeautifulSoup(r.text, 'html.parser')
        title = (soup.title.string.strip() if soup.title and soup.title.string else None)
        rec['title'] = title
        md = soup.find('meta', attrs={'name':'description'}) or soup.find('meta', attrs={'property':'og:description'})
        if md and md.get('content'):
            rec['meta_description'] = md.get('content').strip()
        can = soup.find('link', rel='canonical')
        if can and can.get('href'):
            rec['canonical'] = urljoin(r.url, can.get('href'))

        h1s = soup.find_all('h1')
        rec['h1'] = [h.get_text(strip=True) for h in h1s]
        rec['h2'] = [h.get_text(strip=True) for h in soup.find_all('h2')]

        # links
        for a in soup.find_all('a', href=True):
            href = urljoin(r.url, a['href'])
            if href.startswith('mailto:') or href.startswith('tel:'):
                continue
            if is_same_domain(base_netloc, href):
                rec['internal_links'].append(href)
            else:
                rec['external_links'].append(href)

        # images
        for img in soup.find_all('img'):
            src = img.get('src')
            if not src:
                continue
            src = urljoin(r.url, src)
            alt = img.get('alt') or ''
            rec['images'].append({'src': src, 'alt': alt})

        # scripts
        for s in soup.find_all('script'):
            src = s.get('src')
            rec['scripts'].append(src if src else 'inline')

        # text & keyword frequency
        text = extract_text(soup)
        words = re.findall(r"[A-Za-zÀ-ÿ0-9\-']{2,}", text.lower())
        rec['word_count'] = len(words)
        freq = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        top = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:30]
        rec['top_words'] = [{'word': w, 'count': c, 'density': round(100*c/rec['word_count'],2) if rec['word_count'] else 0} for w,c in top]

        # basic SEO issues
        if not title:
            rec['issues'].append('Missing <title>')
        else:
            if len(title) < 30:
                rec['issues'].append('Short title')
            if len(title) > 80:
                rec['issues'].append('Long title')
        if not rec['meta_description']:
            rec['issues'].append('Missing meta description')
        else:
            if len(rec['meta_description']) < 50:
                rec['issues'].append('Short meta description')
            if len(rec['meta_description']) > 320:
                rec['issues'].append('Long meta description')
        if not rec['h1']:
            rec['issues'].append('Missing H1')
        if not rec['canonical']:
            rec['issues'].append('Missing canonical')

    except Exception as e:
        rec['issues'].append(f'Exception: {e}')
    return rec


def fetch_sitemap(root_url, session):
    # try /sitemap.xml and robots.txt
    parsed = urlparse(root_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    res = {'found': False, 'url': None, 'entries': [], 'error': None}
    candidates = [urljoin(base, '/sitemap.xml'), urljoin(base, '/sitemap_index.xml')]
    # parse robots for sitemap
    try:
        r = session.get(urljoin(base, '/robots.txt'), headers=HEADERS, timeout=8)
        if r.status_code == 200:
            m = re.findall(r'^Sitemap:\s*(.+)$', r.text, flags=re.IGNORECASE | re.MULTILINE)
            for s in m:
                candidates.append(s.strip())
    except Exception:
        pass

    for c in candidates:
        try:
            r = session.get(c, headers=HEADERS, timeout=10)
            if r.status_code == 200 and 'xml' in r.headers.get('content-type',''):
                res['found'] = True
                res['url'] = c
                # very small xml parsing to extract <loc>
                locs = re.findall(r'<loc>([^<]+)</loc>', r.text)
                res['entries'] = locs
                return res
        except Exception:
            continue
    return res


def crawl(root_url, max_pages=50):
    session = requests.Session()
    parsed = urlparse(root_url)
    base_netloc = parsed.netloc
    queue = [root_url]
    seen = set()
    results = []
    broken = []
    redirects = []

    sitemap = fetch_sitemap(root_url, session)

    while queue and len(results) < max_pages:
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        rec = analyze_page(u, base_netloc, session)
        results.append(rec)
        # handle discovered internal links
        for link in rec.get('internal_links', []):
            if link not in seen and link not in queue and urlparse(link).netloc == base_netloc:
                queue.append(link)
        if rec.get('status') and 400 <= rec['status'] < 600:
            broken.append({'url': u, 'status': rec.get('status')})
        if rec.get('final_url') and urlparse(rec['final_url']).netloc != base_netloc:
            redirects.append({'from': u, 'to': rec.get('final_url')})

    # orphan pages: sitemap entries not internally linked
    orphan_pages = []
    if sitemap['found']:
        sitemap_urls = set(sitemap['entries'])
        crawled = set([r['url'] for r in results])
        for s in sitemap_urls:
            if s not in crawled:
                orphan_pages.append(s)

    report = {
        'root': root_url,
        'base_netloc': base_netloc,
        'pages_scanned': len(results),
        'pages': results,
        'sitemap': sitemap,
        'broken_links': broken,
        'redirects': redirects,
        'orphan_pages': orphan_pages,
        'notes': {
            'core_web_vitals': 'Not measured: field/lab data (use Lighthouse / PageSpeed Insights). Only server-side response times provided.',
            'backlinks': 'Not available without external API (Ahrefs/SEMrush).'
        }
    }
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument('root')
    p.add_argument('--max-pages', type=int, default=50)
    p.add_argument('--output', default='audit_report.json')
    args = p.parse_args()

    report = crawl(args.root, max_pages=args.max_pages)

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print('Wrote', args.output)


if __name__ == '__main__':
    main()
