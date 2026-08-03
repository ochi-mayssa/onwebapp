import os
from abc import ABC, abstractmethod

class BaseCrawler(ABC):
    def __init__(self, platform_name):
        self.platform_name = platform_name
        self.api_key = self._get_api_key()

    def _get_api_key(self):
        # Maps platform name to env var
        env_var_map = {
            'instagram': 'INSTAGRAM_API_KEY',
            'tiktok': 'TIKTOK_API_KEY',
            'youtube': 'YOUTUBE_API_KEY',
            'twitter': 'TWITTER_API_KEY'
        }
        
        env_var = env_var_map.get(self.platform_name)
        if not env_var:
            raise ValueError(f"Unknown platform: {self.platform_name}")
            
        api_key = os.environ.get(env_var)
        
        # Strict security check as requested
        if not api_key:
            raise ValueError(f"Social Media API not accessible – API keys required for {self.platform_name}")
            
        return api_key

    @abstractmethod
    def crawl(self, target):
        """
        Crawl data for the target (username or hashtag).
        Must return a list of dicts with standardized keys.
        """
        pass
