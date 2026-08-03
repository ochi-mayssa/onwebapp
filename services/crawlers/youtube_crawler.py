import requests
from .base_crawler import BaseCrawler

class YouTubeCrawler(BaseCrawler):
    def __init__(self):
        super().__init__('youtube')
        self.base_url = "https://www.googleapis.com/youtube/v3"

    def crawl(self, channel_name):
        """
        Crawls YouTube channel data.
        Requires YOUTUBE_API_KEY.
        """
        try:
            # 1. Get Channel ID
            search_url = f"{self.base_url}/search"
            search_params = {
                'part': 'snippet',
                'q': channel_name,
                'type': 'channel',
                'key': self.api_key
            }
            
            resp = requests.get(search_url, params=search_params)
            resp.raise_for_status()
            search_data = resp.json()
            
            if not search_data.get('items'):
                print(f"Channel {channel_name} not found")
                return []
                
            channel_id = search_data['items'][0]['snippet']['channelId']
            
            # 2. Get Channel Stats (Followers)
            channel_url = f"{self.base_url}/channels"
            channel_params = {
                'part': 'statistics',
                'id': channel_id,
                'key': self.api_key
            }
            c_resp = requests.get(channel_url, params=channel_params)
            c_data = c_resp.json()
            stats = c_data['items'][0]['statistics']
            subscriber_count = stats.get('subscriberCount', 0)
            
            # 3. Get Recent Videos
            # First get Uploads Playlist ID (usually related to channel ID)
            # Or just search for videos by channel ID
            video_search_url = f"{self.base_url}/search"
            vid_params = {
                'part': 'snippet',
                'channelId': channel_id,
                'order': 'date',
                'maxResults': 20,
                'key': self.api_key
            }
            
            v_resp = requests.get(video_search_url, params=vid_params)
            v_data = v_resp.json()
            
            posts = []
            for item in v_data.get('items', []):
                if item['id']['kind'] == 'youtube#video':
                    video_id = item['id']['videoId']
                    
                    # Need extra call for stats (views, likes)
                    stats_url = f"{self.base_url}/videos"
                    s_params = {
                        'part': 'statistics',
                        'id': video_id,
                        'key': self.api_key
                    }
                    s_resp = requests.get(stats_url, params=s_params)
                    s_data = s_resp.json()
                    vid_stats = s_data['items'][0]['statistics']
                    
                    post = {
                        'platform': 'youtube',
                        'post_id': video_id,
                        'post_url': f"https://www.youtube.com/watch?v={video_id}",
                        'caption': item['snippet']['title'], # Use title as caption
                        'posted_at': item['snippet']['publishedAt'],
                        'likes': vid_stats.get('likeCount', 0),
                        'comments': vid_stats.get('commentCount', 0),
                        'views': vid_stats.get('viewCount', 0),
                        'shares': 0, # Not provided by API
                        'user_data': {
                            'username': channel_name,
                            'id': channel_id,
                            'followers': subscriber_count
                        }
                    }
                    posts.append(post)
            
            return posts

        except requests.RequestException as e:
            print(f"YouTube Crawl Error: {e}")
            return []
