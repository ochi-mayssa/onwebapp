import os
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

def fetch_latest_events(since_datetime):
    """
    Fetches latest events from Instagram Business API.
    """
    access_token = os.environ.get('INSTAGRAM_ACCESS_TOKEN')
    ig_user_id = os.environ.get('INSTAGRAM_USER_ID')
    
    if not access_token or not ig_user_id:
        logger.warning("Instagram credentials missing. Skipping collection.")
        return []
        
    try:
        # Placeholder for actual API call
        # url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media"
        # params = {
        #     'access_token': access_token, 
        #     'fields': 'id,caption,media_type,media_url,permalink,timestamp,comments_count,like_count',
        #     'since': int(since_datetime.timestamp()) if since_datetime else None
        # }
        # response = requests.get(url, params=params)
        # response.raise_for_status()
        
        return []
        
    except Exception as e:
        logger.error(f"Error fetching Instagram events: {e}")
        return []
