"""DRF serializers for the Branding Service API."""
from django.contrib.auth import get_user_model
from rest_framework import serializers

from ..models import (
    ASSET_TYPES,
    BRAND_VALUES,
    COLLECTION_CATEGORIES,
    CURRENT_BRANDING_CHOICES,
    INDUSTRY_CHOICES,
    PREFERRED_COLORS,
    PRIORITY_CHOICES,
    STATUS_CHOICES,
    WEBHOOK_EVENT_TYPES,
    BrandCollection,
    BrandingAsset,
    BrandingAssetVersion,
    BrandingClientProfile,
    BrandingFeedback,
    BrandingMessage,
    BrandingNotification,
    BrandingRequest,
    BrandingTimeline,
    BrandingWebhook,
    ConsentRecord,
    DataExportRequest,
    PrivacyAcceptance,
    WebhookDelivery,
)

User = get_user_model()


# ── User (minimal) ────────────────────────────────────────────────────────

class UserSummarySerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'email', 'is_staff']

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


# ── Brand Collection ──────────────────────────────────────────────────────

class BrandCollectionListSerializer(serializers.ModelSerializer):
    preview_items_count = serializers.IntegerField(source='preview_items_count', read_only=True, default=0)

    class Meta:
        model = BrandCollection
        fields = [
            'id', 'name', 'slug', 'category', 'industry', 'description',
            'style_tags', 'preview_image', 'accent_color', 'is_active',
            'sort_order', 'created_at',
        ]


class BrandCollectionDetailSerializer(serializers.ModelSerializer):
    preview_items = serializers.SerializerMethodField()

    class Meta:
        model = BrandCollection
        fields = [
            'id', 'name', 'slug', 'category', 'industry', 'description',
            'style_tags', 'examples', 'preview_image', 'accent_color',
            'is_active', 'sort_order', 'created_at', 'updated_at',
            'hero_image', 'logo_image', 'typography_image', 'business_card_image',
            'presentation_image', 'letterhead_image', 'email_signature_image',
            'social_media_image', 'brand_guidelines_image',
            'color_palette', 'fonts', 'preview_items',
        ]

    def get_preview_items(self, obj):
        return [
            {'key': key, 'label': label, 'icon': icon, 'url': image.url if image else None}
            for key, label, icon, image in obj.preview_items
        ]


# ── Branding Request ─────────────────────────────────────────────────────

class BrandingRequestListSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer(read_only=True)
    designer = UserSummarySerializer(read_only=True)
    collection_name = serializers.CharField(source='collection.name', read_only=True, default=None)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    industry_display = serializers.CharField(source='get_industry_display', read_only=True)

    class Meta:
        model = BrandingRequest
        fields = [
            'id', 'request_number', 'user', 'status', 'status_display',
            'priority', 'priority_display', 'current_step',
            'company_name', 'industry', 'industry_display', 'website', 'country',
            'collection', 'collection_name', 'designer',
            'estimated_delivery_date', 'completed_at',
            'created_at', 'updated_at',
        ]


class BrandingRequestDetailSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer(read_only=True)
    designer = UserSummarySerializer(read_only=True)
    collection = BrandCollectionListSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    industry_display = serializers.CharField(source='get_industry_display', read_only=True)
    completion_time = serializers.CharField(source='completion_time_display', read_only=True)
    assets = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    timeline_count = serializers.SerializerMethodField()

    class Meta:
        model = BrandingRequest
        fields = [
            'id', 'request_number', 'user', 'status', 'status_display',
            'priority', 'priority_display', 'current_step',
            'company_name', 'industry', 'industry_display', 'website', 'country',
            'business_description', 'company_description', 'target_audience',
            'brand_values', 'preferred_colors', 'current_branding',
            'additional_notes', 'collection', 'designer',
            'estimated_delivery_date', 'completed_at', 'completion_time',
            'internal_notes', 'assets', 'timeline_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['request_number', 'completed_at']

    def get_timeline_count(self, obj):
        return obj.timeline_entries.count()


class BrandingRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandingRequest
        fields = [
            'company_name', 'industry', 'website', 'country',
            'business_description', 'company_description', 'target_audience',
            'brand_values', 'preferred_colors', 'current_branding',
            'additional_notes', 'collection', 'priority',
        ]


# ── Branding Asset ────────────────────────────────────────────────────────

class BrandingAssetVersionSerializer(serializers.ModelSerializer):
    uploaded_by = UserSummarySerializer(read_only=True)
    size_display = serializers.CharField(read_only=True)

    class Meta:
        model = BrandingAssetVersion
        fields = [
            'id', 'file', 'version_number', 'original_name',
            'content_type', 'size', 'size_display', 'note',
            'uploaded_by', 'created_at',
        ]


class BrandingAssetListSerializer(serializers.ModelSerializer):
    asset_type_display = serializers.CharField(source='get_asset_type_display', read_only=True)
    size_display = serializers.CharField(read_only=True)
    scan_display = serializers.CharField(read_only=True)

    class Meta:
        model = BrandingAsset
        fields = [
            'id', 'file', 'asset_type', 'asset_type_display',
            'original_name', 'sanitized_name', 'content_type', 'detected_mime',
            'file_hash', 'size', 'size_display',
            'scan_status', 'scan_display', 'uploaded_at',
        ]


class BrandingAssetDetailSerializer(serializers.ModelSerializer):
    asset_type_display = serializers.CharField(source='get_asset_type_display', read_only=True)
    size_display = serializers.CharField(read_only=True)
    scan_display = serializers.CharField(read_only=True)
    versions = BrandingAssetVersionSerializer(many=True, read_only=True)

    class Meta:
        model = BrandingAsset
        fields = [
            'id', 'request', 'file', 'asset_type', 'asset_type_display',
            'original_name', 'sanitized_name', 'content_type', 'detected_mime',
            'file_hash', 'size', 'size_display',
            'scan_status', 'scan_display', 'scan_result',
            'versions', 'uploaded_at',
        ]


# ── Branding Notification ─────────────────────────────────────────────────

class BrandingNotificationSerializer(serializers.ModelSerializer):
    notification_type_display = serializers.CharField(source='get_notification_type_display', read_only=True)

    class Meta:
        model = BrandingNotification
        fields = [
            'id', 'request', 'notification_type', 'notification_type_display',
            'message', 'url', 'is_read', 'created_at',
        ]
        read_only_fields = ['is_read']


# ── Branding Message ──────────────────────────────────────────────────────

class BrandingMessageSerializer(serializers.ModelSerializer):
    sender = UserSummarySerializer(read_only=True)
    sender_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='sender', write_only=True, required=False,
    )
    replies = serializers.SerializerMethodField()

    class Meta:
        model = BrandingMessage
        fields = [
            'id', 'request', 'sender', 'sender_id', 'parent',
            'content', 'is_read_by_client', 'is_read_by_staff',
            'replies', 'created_at', 'updated_at',
        ]
        read_only_fields = ['is_read_by_client', 'is_read_by_staff']

    def get_replies(self, obj):
        if obj.parent_id is not None:
            return []
        replies = obj.replies.select_related('sender').all()
        return BrandingMessageSerializer(replies, many=True, context=self.context).data


# ── Branding Timeline ─────────────────────────────────────────────────────

class BrandingTimelineSerializer(serializers.ModelSerializer):
    actor = UserSummarySerializer(read_only=True)
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)

    class Meta:
        model = BrandingTimeline
        fields = [
            'id', 'request', 'event_type', 'event_type_display',
            'action', 'description', 'actor', 'created_at',
        ]


# ── Branding Feedback ─────────────────────────────────────────────────────

class BrandingFeedbackSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    rating_percentage = serializers.FloatField(read_only=True)

    class Meta:
        model = BrandingFeedback
        fields = [
            'id', 'request', 'rating', 'rating_percentage',
            'comment', 'would_recommend',
            'staff_response', 'responded_by', 'responded_at',
            'user', 'created_at', 'updated_at',
        ]
        read_only_fields = ['staff_response', 'responded_by', 'responded_at']

    def get_user(self, obj):
        return {
            'id': obj.request.user_id,
            'username': obj.request.user.username,
            'full_name': obj.request.user.get_full_name() or obj.request.user.username,
        }


# ── Client Profile ────────────────────────────────────────────────────────

class BrandingClientProfileSerializer(serializers.ModelSerializer):
    favorite_collections = BrandCollectionListSerializer(many=True, read_only=True)

    class Meta:
        model = BrandingClientProfile
        fields = [
            'id', 'default_industry', 'default_country',
            'favorite_collections', 'notification_preferences',
            'saved_briefs', 'created_at', 'updated_at',
        ]


# ── Webhooks ──────────────────────────────────────────────────────────────

class WebhookDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookDelivery
        fields = [
            'id', 'webhook', 'event_type', 'payload', 'status',
            'status_code', 'response_body', 'attempt',
            'created_at', 'completed_at',
        ]
        read_only_fields = fields


class BrandingWebhookSerializer(serializers.ModelSerializer):
    delivery_count = serializers.SerializerMethodField()
    last_delivery = serializers.SerializerMethodField()

    class Meta:
        model = BrandingWebhook
        fields = [
            'id', 'name', 'url', 'events', 'secret', 'is_active',
            'last_triggered_at', 'failure_count',
            'delivery_count', 'last_delivery',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['last_triggered_at', 'failure_count', 'created_at', 'updated_at']

    def get_delivery_count(self, obj):
        return obj.deliveries.count()

    def get_last_delivery(self, obj):
        last = obj.deliveries.order_by('-created_at').first()
        if not last:
            return None
        return WebhookDeliverySerializer(last).data


class BrandingWebhookCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandingWebhook
        fields = ['name', 'url', 'events', 'secret', 'is_active']


# ── GDPR Serializers ─────────────────────────────────────────────────────

class ConsentRecordSerializer(serializers.ModelSerializer):
    consent_type_display = serializers.CharField(source='get_consent_type_display', read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = ConsentRecord
        fields = [
            'id', 'consent_type', 'consent_type_display',
            'action', 'action_display',
            'ip_address', 'created_at',
        ]
        read_only_fields = fields


class DataExportRequestSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    format_display = serializers.CharField(source='get_export_format_display', read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = DataExportRequest
        fields = [
            'id', 'status', 'status_display',
            'export_format', 'format_display',
            'file', 'download_url',
            'expires_at', 'error_message',
            'requested_at', 'completed_at',
        ]
        read_only_fields = [
            'status', 'file', 'expires_at', 'error_message',
            'requested_at', 'completed_at',
        ]

    def get_download_url(self, obj):
        if obj.status == DataExportRequest.STATUS_READY and obj.file:
            return f'/api/branding/gdpr/exports/{obj.pk}/download/'
        return None


class DataExportRequestCreateSerializer(serializers.Serializer):
    export_format = serializers.ChoiceField(
        choices=DataExportRequest.FORMAT_CHOICES,
        default='json',
    )


class PrivacyAcceptanceSerializer(serializers.ModelSerializer):
    page_display = serializers.CharField(source='get_page_display', read_only=True)

    class Meta:
        model = PrivacyAcceptance
        fields = [
            'id', 'page', 'page_display', 'version', 'accepted',
            'ip_address', 'created_at',
        ]
        read_only_fields = ['ip_address', 'created_at']


class UserConsentStatusSerializer(serializers.Serializer):
    """Serializes the current consent status for all types."""
    data_processing = serializers.DictField()
    marketing = serializers.DictField()
    analytics = serializers.DictField()
    third_party = serializers.DictField()


class UserPrivacyStatusSerializer(serializers.Serializer):
    """Serializes the current privacy acceptance status."""
    privacy_policy = serializers.DictField(required=False)
    terms_of_service = serializers.DictField(required=False)
    cookie_policy = serializers.DictField(required=False)
