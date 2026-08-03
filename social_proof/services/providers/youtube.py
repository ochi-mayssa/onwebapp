import os
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

def fetch_latest_events(since_datetime):
    """
    Fetches latest comments from YouTube Data API.
    """
    api_key = os.environ.get('YOUTUBE_API_KEY')
    channel_id = os.environ.get('YOUTUBE_CHANNEL_ID')
    
    if not api_key or not channel_id:
        logger.warning("YouTube credentials missing. Skipping collection.")
        return []
        
    try:
        # Placeholder for actual API call
        # url = "https://www.googleapis.com/youtube/v3/commentThreads"
        # params = {
        #     'key': api_key,
        #     'part': 'snippet',
        #     'allThreadsRelatedToChannelId': channel_id,
        #     'order': 'time',
        #     'maxResults': 50
        # }
        # response = requests.get(url, params=params)
        # response.raise_for_status()
        
        return []
        
    except Exception as e:
        logger.error(f"Error fetching YouTube events: {e}")
        return []
