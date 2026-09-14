import requests
from urllib.parse import quote

url = "https://www.youtube.com/watch?v=Jhzc54fxQWM"  # Digital Marketing Full Course
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

try:
    oembed_url = f"https://www.youtube.com/oembed?url={quote(url)}&format=json"
    print(f"Calling oEmbed: {oembed_url}")
    oembed_response = session.get(oembed_url, timeout=10)
    print(f"oEmbed status: {oembed_response.status_code}")
    if oembed_response.status_code == 200:
        print(oembed_response.json())
except Exception as e:
    print(f"Error: {e}")
