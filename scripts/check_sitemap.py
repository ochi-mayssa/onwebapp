import urllib.request

url = 'http://127.0.0.1:8000/sitemap.xml'
try:
    with urllib.request.urlopen(url, timeout=8) as r:
        data = r.read()
        print('OK', r.getcode(), 'bytes=', len(data))
        print(data[:1000].decode(errors='replace'))
except Exception as e:
    print('ERROR', e)
