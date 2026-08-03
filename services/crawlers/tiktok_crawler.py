import requests
from .base_crawler import BaseCrawler

class TikTokCrawler(BaseCrawler):
    def __init__(self):
        super().__init__('tiktok')
        self.base_url = "https://open.tiktokapis.com/v2"

    def crawl(self, username):
        """
        Crawls TikTok data using Official API.
        Requires TIKTOK_API_KEY.
        """
        # This implementation assumes the use of Client Credentials flow or similar
        # to fetch public data if allowed, or specific research endpoints.
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        # Example endpoint for video list (research API or display API)
        # Note: Actual endpoints vary by permission scope.
        url = f"{self.base_url}/research/video/query/"
        
        payload = {
            "query": {
                "and": [{"operation": "EQ", "field_name": "username", "field_values": [username]}]
            },
            "max_count": 20
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            posts = []
            for item in data.get('data', {}).get('videos', []):
                post = {
                    'platform': 'tiktok',
                    'post_id': item['id'],
                    'post_url': item.get('video_url', ''), # Or construct from ID
                    'caption': item.get('video_description', ''),
                    'posted_at': item.get('create_time'),
                    'likes': item.get('like_count', 0),
                    'comments': item.get('comment_count', 0),
                    'shares': item.get('share_count', 0),
                    'views': item.get('view_count', 0),
                    'user_data': {
                        'username': username,
                        'id': item.get('author_id', '') # Often hidden/hashed
                    }
                }
                posts.append(post)
            
            return posts
            
        except requests.RequestException as e:
            print(f"TikTok Crawl Error: {e}")
            return []
