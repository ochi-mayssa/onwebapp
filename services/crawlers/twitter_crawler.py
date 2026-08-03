import requests
from .base_crawler import BaseCrawler

class TwitterCrawler(BaseCrawler):
    def __init__(self):
        super().__init__('twitter')
        self.base_url = "https://api.twitter.com/2"

    def crawl(self, username):
        """
        Crawls Twitter/X data using API v2.
        Requires TWITTER_API_KEY (Bearer Token).
        """
        headers = {
            'Authorization': f'Bearer {self.api_key}'
        }
        
        try:
            # 1. Get User ID
            user_url = f"{self.base_url}/users/by/username/{username}"
            params = {'user.fields': 'public_metrics'}
            
            resp = requests.get(user_url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            if 'data' not in data:
                print(f"User {username} not found")
                return []
                
            user_data = data['data']
            user_id = user_data['id']
            followers = user_data['public_metrics']['followers_count']
            
            # 2. Get Tweets
            tweets_url = f"{self.base_url}/users/{user_id}/tweets"
            tweet_params = {
                'tweet.fields': 'created_at,public_metrics',
                'max_results': 20
            }
            
            t_resp = requests.get(tweets_url, headers=headers, params=tweet_params)
            t_resp.raise_for_status()
            t_data = t_resp.json()
            
            posts = []
            for item in t_data.get('data', []):
                metrics = item['public_metrics']
                post = {
                    'platform': 'twitter',
                    'post_id': item['id'],
                    'post_url': f"https://twitter.com/{username}/status/{item['id']}",
                    'caption': item['text'],
                    'posted_at': item['created_at'],
                    'likes': metrics.get('like_count', 0),
                    'comments': metrics.get('reply_count', 0),
                    'shares': metrics.get('retweet_count', 0), # + quote_count
                    'views': metrics.get('impression_count', 0),
                    'user_data': {
                        'username': username,
                        'id': user_id,
                        'followers': followers
                    }
                }
                posts.append(post)
                
            return posts

        except requests.RequestException as e:
            print(f"Twitter Crawl Error: {e}")
            return []
