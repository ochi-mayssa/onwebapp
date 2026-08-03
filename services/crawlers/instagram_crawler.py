import requests
from .base_crawler import BaseCrawler
from datetime import datetime

class InstagramCrawler(BaseCrawler):
    def __init__(self):
        super().__init__('instagram')
        self.base_url = "https://graph.instagram.com/v12.0"

    def crawl(self, username):
        """
        Crawls Instagram public data using Graph API.
        Requires INSTAGRAM_API_KEY (Access Token).
        """
        # 1. Get User ID
        user_url = f"{self.base_url}/users/search"
        params = {
            'q': username,
            'access_token': self.api_key,
            'fields': 'id,username,followers_count,media_count'
        }
        
        try:
            # Real API call
            response = requests.get(user_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if not data.get('data'):
                print(f"User {username} not found")
                return []
                
            user_data = data['data'][0]
            user_id = user_data['id']
            
            # 2. Get Media
            media_url = f"{self.base_url}/{user_id}/media"
            media_params = {
                'access_token': self.api_key,
                'fields': 'id,caption,media_type,media_url,permalink,thumbnail_url,timestamp,like_count,comments_count'
            }
            
            media_response = requests.get(media_url, params=media_params)
            media_response.raise_for_status()
            media_data = media_response.json()
            
            posts = []
            for item in media_data.get('data', []):
                post = {
                    'platform': 'instagram',
                    'post_id': item['id'],
                    'post_url': item['permalink'],
                    'caption': item.get('caption', ''),
                    'posted_at': item['timestamp'], # Needs parsing
                    'likes': item.get('like_count', 0),
                    'comments': item.get('comments_count', 0),
                    'media_type': item['media_type'],
                    'user_data': {
                        'username': user_data['username'],
                        'id': user_data['id'],
                        'followers': user_data.get('followers_count', 0)
                    }
                }
                posts.append(post)
                
            return posts

        except requests.RequestException as e:
            print(f"Instagram Crawl Error: {e}")
            return []
