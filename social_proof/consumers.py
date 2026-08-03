import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import SocialStreamConfig

class SocialProofConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        
        if self.user.is_anonymous:
            await self.close()
            return
            
        # Join global social proof group
        # We will filter messages in the handler
        self.group_name = "social_proof_live"
        
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def social_event_message(self, event):
        """
        Handler for social_event_message type sent from Celery task.
        """
        event_data = event['event']
        provider_name = event_data.get('provider')
        
        # Check permissions
        if await self.can_see_event(provider_name):
            await self.send(text_data=json.dumps({
                'type': 'social_event',
                'data': event_data
            }))

    @database_sync_to_async
    def can_see_event(self, provider_name):
        user = self.user
        if not user.is_authenticated:
            return False
        if user.is_staff:
            return True
            
        # Check if user has a config with this provider enabled
        return SocialStreamConfig.objects.filter(
            project__client=user,
            enabled_providers__name=provider_name
        ).exists()
