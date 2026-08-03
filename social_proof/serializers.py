from rest_framework import serializers
from .models import SocialEvent, SocialProvider, SocialStreamConfig

class SocialProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialProvider
        fields = ['id', 'name', 'enabled', 'last_sync_at']

class SocialEventSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source='provider.name', read_only=True)
    
    class Meta:
        model = SocialEvent
        fields = ['id', 'provider_name', 'event_type', 'author_name', 'author_avatar_url', 
                  'text', 'url', 'sentiment_score', 'created_at', 'occurred_at']

class SocialStreamConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialStreamConfig
        fields = ['id', 'project', 'enabled_providers', 'min_sentiment_score', 'auto_approve']
