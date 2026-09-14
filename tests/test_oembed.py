import requests
from urllib.parse import quote


def test_youtube_oembed(url):
    """Test YouTube oEmbed API for a given video URL"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    
    print(f"Testing YouTube oEmbed for URL: {url}")
    print("-" * 80)
    
    try:
        oembed_url = f"https://www.youtube.com/oembed?url={quote(url)}&format=json"
        print(f"Calling oEmbed URL: {oembed_url}")
        
        response = session.get(oembed_url, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("\nSuccess! oEmbed data:")
            print(f"  Title: {data.get('title')}")
            print(f"  Author: {data.get('author_name')}")
            print(f"  Author URL: {data.get('author_url')}")
            print(f"  Provider: {data.get('provider_name')}")
            print(f"  Type: {data.get('type')}")
            print(f"  Height: {data.get('height')}")
            print(f"  Width: {data.get('width')}")
            print(f"  Thumbnail URL: {data.get('thumbnail_url')}")
            print(f"  Thumbnail Width: {data.get('thumbnail_width')}")
            print(f"  Thumbnail Height: {data.get('thumbnail_height')}")
            print(f"  HTML: {data.get('html')[:100]}...")
            return data
        else:
            print(f"Error: Received status code {response.status_code}")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None


if __name__ == "__main__":
    test_urls = [
        "https://www.youtube.com/watch?v=Jhzc54fxQWM",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ]
    
    for url in test_urls:
        test_youtube_oembed(url)
        print("\n" + "=" * 80 + "\n")
