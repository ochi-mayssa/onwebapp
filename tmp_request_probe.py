import requests
from bs4 import BeautifulSoup
urls = ['https://amazon.fr','https://oise.com','https://eu.iko.com']
for url in urls:
    print('URL', url)
    try:
        r = requests.get(url, timeout=15, headers={'User-Agent':'Mozilla/5.0'}, allow_redirects=True)
        print('status', r.status_code)
        print('final', r.url)
        print('content-type', r.headers.get('Content-Type'))
        print('len', len(r.content))
        soup = BeautifulSoup(r.content, 'html.parser')
        anchors = soup.find_all('a', href=True)
        print('anchors', len(anchors))
        for a in anchors[:10]:
            href = a.get('href')
            if href:
                print(' ', href[:120])
        print('---')
    except Exception as e:
        print('ERR', repr(e))
        print('---')
