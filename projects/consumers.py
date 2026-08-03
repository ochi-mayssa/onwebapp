import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        
        if self.user.is_anonymous:
            await self.close()
            return
            
        self.group_name = f"user_{self.user.id}"
        
        # Join user group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        # If admin, also join admins group
        if self.user.is_staff or self.user.is_superuser:
            await self.channel_layer.group_add(
                "admins",
                self.channel_name
            )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave user group
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
            
        if self.user.is_staff or self.user.is_superuser:
            await self.channel_layer.group_discard(
                "admins",
                self.channel_name
            )

    # Receive message from room group
    async def notification_message(self, event):
        message = event['message']
        notification_type = event.get('notification_type', 'INFO')
        
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': message,
            'type': notification_type
        }))

    async def dashboard_update(self, event):
        data = event['data']
        await self.send(text_data=json.dumps({
            'type': 'dashboard_stats',
            'data': data
        }))
