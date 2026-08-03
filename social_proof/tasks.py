from celery import shared_task
from django.utils import timezone
from .models import SocialProvider, SocialEvent
from .services.providers import facebook, instagram, tiktok, youtube, google_reviews
from .utils import analyze_sentiment
import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)

PROVIDER_MAP = {
    'facebook': facebook,
    'instagram': instagram,
    'tiktok': tiktok,
    'youtube': youtube,
    'google_reviews': google_reviews,
}

@shared_task
def collect_social_events():
    logger.info("Starting social event collection")
    
    # Get enabled providers from DB
    providers = SocialProvider.objects.filter(enabled=True)
    
    for provider in providers:
        if provider.name not in PROVIDER_MAP:
            logger.warning(f"No service module for provider {provider.name}")
            continue
            
        service = PROVIDER_MAP[provider.name]
        last_sync = provider.last_sync_at
        
        try:
            events_data = service.fetch_latest_events(last_sync)
            
            new_count = 0
            channel_layer = get_channel_layer()
            
            for event_data in events_data:
                external_id = event_data.get('external_id')
                if not external_id:
                    continue
                    
                # Deduplication
                if SocialEvent.objects.filter(provider=provider, external_id=external_id).exists():
                    continue
                
                # Sentiment Analysis
                text = event_data.get('text', '')
                sentiment_score = analyze_sentiment(text)
                
                # Auto-approve logic (default > 0.7)
                is_approved = sentiment_score >= 0.7
                
                event = SocialEvent.objects.create(
                    provider=provider,
                    event_type=event_data.get('event_type', 'post'),
                    external_id=external_id,
                    author_name=event_data.get('author_name', 'Anonymous'),
                    author_avatar_url=event_data.get('author_avatar_url'),
                    text=text,
                    url=event_data.get('url'),
                    sentiment_score=sentiment_score,
                    raw_json=event_data,
                    is_approved=is_approved,
                    occurred_at=event_data.get('created_at', timezone.now())
                )
                new_count += 1
                
                # Broadcast if approved
                if is_approved:
                    async_to_sync(channel_layer.group_send)(
                        "social_proof_live",
                        {
                            "type": "social_event_message",
                            "event": {
                                "id": event.id,
                                "provider": provider.name,
                                "author": event.author_name,
                                "text": event.text,
                                "sentiment": event.sentiment_score,
                                "created_at": event.created_at.isoformat()
                            }
                        }
                    )
            
            provider.last_sync_at = timezone.now()
            provider.save()
            
            if new_count > 0:
                logger.info(f"Collected {new_count} new events for {provider.name}")
                
        except Exception as e:
            logger.error(f"Error collecting events for {provider.name}: {e}")
            # Continue to next provider, do not crash
