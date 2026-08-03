"""DRF ViewSets for the Branding Service API."""
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import (
    BrandCollection,
    BrandingAsset,
    BrandingFeedback,
    BrandingMessage,
    BrandingNotification,
    BrandingRequest,
    BrandingTimeline,
    BrandingWebhook,
    WebhookDelivery,
    STATUS_CHOICES,
)
from .exceptions import custom_exception_handler
from .permissions import IsStaffUser, IsOwnerOrStaff, IsRequestOwnerOrStaff
from .serializers import (
    BrandCollectionListSerializer,
    BrandCollectionDetailSerializer,
    BrandingRequestListSerializer,
    BrandingRequestDetailSerializer,
    BrandingRequestCreateSerializer,
    BrandingAssetListSerializer,
    BrandingAssetDetailSerializer,
    BrandingNotificationSerializer,
    BrandingMessageSerializer,
    BrandingTimelineSerializer,
    BrandingFeedbackSerializer,
    BrandingWebhookSerializer,
    BrandingWebhookCreateSerializer,
    WebhookDeliverySerializer,
)


# ── Brand Collection ──────────────────────────────────────────────────────

class BrandCollectionViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve brand collections.

    - **list**: Public, returns active collections only.
    - **retrieve**: Public, returns full detail with preview items.
    """
    queryset = BrandCollection.objects.filter(is_active=True).order_by('category', 'sort_order', 'name')
    lookup_field = 'slug'
    filterset_fields = ['category', 'industry']
    search_fields = ['name', 'description', 'style_tags']
    ordering_fields = ['name', 'category', 'sort_order', 'created_at']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return BrandCollectionDetailSerializer
        return BrandCollectionListSerializer

    def get_permissions(self):
        return [IsAuthenticated()]


# ── Branding Request ─────────────────────────────────────────────────────

class BrandingRequestViewSet(viewsets.ModelViewSet):
    """CRUD for branding requests.

    - **Clients** can create, list, and retrieve their own requests.
    - **Staff** can list all, update status/designer/notes, and retrieve any.
    - **Filtering**: by `status`, `industry`, `designer`, `priority`, `collection`.
    - **Search**: `company_name`, `request_number`, `user__username`.
    """
    filterset_fields = ['status', 'industry', 'designer', 'priority', 'collection']
    search_fields = ['company_name', 'request_number', 'user__username', 'user__email']
    ordering_fields = ['created_at', 'updated_at', 'priority', 'company_name']

    def get_queryset(self):
        qs = BrandingRequest.objects.select_related('user', 'collection', 'designer')
        if self.request.user.is_staff:
            return qs.exclude(status='DRAFT')
        return qs.filter(user=self.request.user).exclude(status='DRAFT')

    def get_serializer_class(self):
        if self.action == 'create':
            return BrandingRequestCreateSerializer
        if self.action == 'retrieve':
            return BrandingRequestDetailSerializer
        return BrandingRequestListSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAuthenticated()]
        if self.action == 'create':
            return [IsAuthenticated()]
        return [IsStaffUser()]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, status='DRAFT')

    # ── Custom actions ────────────────────────────────────────────────

    @action(detail=True, methods=['post'], permission_classes=[IsStaffUser])
    def assign_designer(self, request, pk=None):
        """Assign a designer to a request."""
        req = self.get_object()
        designer_id = request.data.get('designer')
        if not designer_id:
            return Response({'error': 'designer is required'}, status=400)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        designer = User.objects.filter(pk=designer_id, is_staff=True).first()
        if not designer:
            return Response({'error': 'Invalid designer'}, status=400)
        req.designer = designer
        if req.status in ('PENDING_REVIEW', 'IN_REVIEW'):
            req.status = 'ASSIGNED'
        req.save(update_fields=['designer', 'status', 'updated_at'])
        req.log('ASSIGNMENT', f'Assigned to {designer.get_full_name() or designer.username}', actor=request.user)
        return Response(branding_request_to_dict(req))

    @action(detail=True, methods=['post'], permission_classes=[IsStaffUser])
    def update_status(self, request, pk=None):
        """Change the status of a request."""
        req = self.get_object()
        new_status = request.data.get('status', '')
        valid = {code for code, _ in STATUS_CHOICES if code != 'DRAFT'}
        if new_status not in valid:
            return Response({'error': 'Invalid status'}, status=400)
        from ..views import _set_status
        _set_status(req, new_status, request.user)
        return Response(branding_request_to_dict(req))

    @action(detail=True, methods=['get'])
    def timeline(self, request, pk=None):
        """Get the timeline for a request."""
        req = self.get_object()
        entries = req.timeline_entries.select_related('actor').order_by('created_at')
        page = self.paginate_queryset(entries)
        if page is not None:
            return self.get_paginated_response(BrandingTimelineSerializer(page, many=True).data)
        return Response(BrandingTimelineSerializer(entries, many=True).data)

    @action(detail=True, methods=['get', 'post'])
    def messages(self, request, pk=None):
        """List or create messages for a request."""
        req = self.get_object()
        if request.method == 'GET':
            msgs = req.messages.select_related('sender').filter(parent__isnull=True).order_by('created_at')
            page = self.paginate_queryset(msgs)
            if page is not None:
                return self.get_paginated_response(BrandingMessageSerializer(page, many=True, context={'request': request}).data)
            return Response(BrandingMessageSerializer(msgs, many=True, context={'request': request}).data)
        # POST — create message
        content = request.data.get('content', '').strip()
        parent_id = request.data.get('parent')
        if not content:
            return Response({'error': 'content is required'}, status=400)
        msg = BrandingMessage.objects.create(
            request=req,
            sender=request.user,
            content=content,
            parent_id=parent_id,
        )
        return Response(BrandingMessageSerializer(msg, context={'request': request}).data, status=201)

    @action(detail=True, methods=['get', 'post'])
    def feedback(self, request, pk=None):
        """List or submit feedback for a request."""
        req = self.get_object()
        if request.method == 'GET':
            fb = getattr(req, 'feedback', None)
            if not fb:
                return Response({'detail': 'No feedback yet.'}, status=404)
            return Response(BrandingFeedbackSerializer(fb, context={'request': request}).data)
        # POST — submit feedback
        if req.status != 'COMPLETED':
            return Response({'error': 'Feedback can only be submitted for completed requests.'}, status=400)
        if BrandingFeedback.objects.filter(request=req).exists():
            return Response({'error': 'Feedback already submitted.'}, status=400)
        try:
            rating = int(request.data.get('rating', 0))
        except (TypeError, ValueError):
            rating = 0
        if rating not in range(1, 6):
            return Response({'error': 'Rating must be 1-5.'}, status=400)
        fb = BrandingFeedback.objects.create(
            request=req,
            rating=rating,
            comment=request.data.get('comment', ''),
            would_recommend=request.data.get('would_recommend', True),
        )
        return Response(BrandingFeedbackSerializer(fb, context={'request': request}).data, status=201)


def branding_request_to_dict(req):
    """Serialize a BrandingRequest to a dict for API responses."""
    return BrandingRequestDetailSerializer(req, context={'request': None}).data


# ── Branding Asset ────────────────────────────────────────────────────────

class BrandingAssetViewSet(viewsets.ModelViewSet):
    """CRUD for assets on a branding request.

    - **Staff**: full access.
    - **Clients**: can upload and list their own request assets.
    """
    filterset_fields = ['asset_type']
    search_fields = ['original_name']
    ordering_fields = ['uploaded_at', 'original_name']

    def get_queryset(self):
        qs = BrandingAsset.objects.select_related('request')
        if self.request.user.is_staff:
            return qs.all()
        return qs.filter(request__user=self.request.user)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return BrandingAssetDetailSerializer
        return BrandingAssetListSerializer

    def get_permissions(self):
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        req = BrandingRequest.objects.get(pk=self.request.data.get('request'))
        serializer.save(request=req)


# ── Branding Notification ─────────────────────────────────────────────────

class BrandingNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """List and mark-read for notifications.

    - **list**: returns only the current user's notifications.
    - **mark_read**: POST to mark a notification as read.
    """
    serializer_class = BrandingNotificationSerializer

    def get_queryset(self):
        return BrandingNotification.objects.filter(
            recipient=self.request.user,
        ).select_related('request').order_by('-created_at')

    def get_permissions(self):
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a single notification as read."""
        notif = self.get_object()
        notif.is_read = True
        notif.save(update_fields=['is_read'])
        return Response(BrandingNotificationSerializer(notif).data)

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all unread notifications as read."""
        updated = BrandingNotification.objects.filter(
            recipient=request.user, is_read=False,
        ).update(is_read=True)
        return Response({'marked': updated})


# ── Branding Message (standalone) ─────────────────────────────────────────

class BrandingMessageViewSet(viewsets.ModelViewSet):
    """Standalone message CRUD.

    Typically used via `BrandingRequestViewSet.messages()` nested action.
    This endpoint allows direct message operations for admin/staff.
    """
    serializer_class = BrandingMessageSerializer
    filterset_fields = ['request', 'sender', 'parent']
    search_fields = ['content']
    ordering_fields = ['created_at']

    def get_queryset(self):
        qs = BrandingMessage.objects.select_related('sender', 'request')
        if self.request.user.is_staff:
            return qs.all()
        return qs.filter(
            Q(request__user=self.request.user) | Q(sender=self.request.user)
        ).distinct()

    def get_permissions(self):
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(sender=self.request.user)


# ── Branding Timeline (read-only) ─────────────────────────────────────────

class BrandingTimelineViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only timeline endpoint for audit trail."""
    serializer_class = BrandingTimelineSerializer
    filterset_fields = ['request', 'event_type']
    ordering_fields = ['created_at']

    def get_queryset(self):
        qs = BrandingTimeline.objects.select_related('actor', 'request')
        if self.request.user.is_staff:
            return qs.all()
        return qs.filter(request__user=self.request.user)

    def get_permissions(self):
        return [IsAuthenticated()]


# ── Branding Feedback (staff list + client create) ───────────────────────

class BrandingFeedbackViewSet(viewsets.ModelViewSet):
    """List feedback (staff) or retrieve own feedback (client).

    - **Staff**: list all, respond to feedback.
    - **Clients**: submit feedback on completed requests.
    """
    serializer_class = BrandingFeedbackSerializer
    filterset_fields = ['rating', 'would_recommend']
    search_fields = ['request__company_name', 'request__request_number', 'comment']
    ordering_fields = ['created_at', 'rating']

    def get_queryset(self):
        qs = BrandingFeedback.objects.select_related('request', 'request__user', 'request__collection', 'responded_by')
        if self.request.user.is_staff:
            return qs.all()
        return qs.filter(request__user=self.request.user)

    def get_permissions(self):
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'], permission_classes=[IsStaffUser])
    def respond(self, request, pk=None):
        """Staff responds to feedback."""
        fb = self.get_object()
        fb.staff_response = request.data.get('staff_response', '')
        fb.responded_by = request.user
        fb.responded_at = timezone.now()
        fb.save(update_fields=['staff_response', 'responded_by', 'responded_at', 'updated_at'])
        return Response(BrandingFeedbackSerializer(fb, context={'request': request}).data)


# ── Webhooks (staff only) ────────────────────────────────────────────────

class BrandingWebhookViewSet(viewsets.ModelViewSet):
    """CRUD for webhook endpoints (staff only).

    - **list/retrieve**: view all webhooks and delivery stats.
    - **create/update/delete**: manage webhook subscriptions.
    - **test**: POST to fire a test event.
    - **deliveries**: list delivery history for a webhook.
    """
    filterset_fields = ['is_active']
    search_fields = ['name', 'url']
    ordering_fields = ['created_at', 'last_triggered_at', 'failure_count']

    def get_queryset(self):
        return BrandingWebhook.objects.prefetch_related('deliveries').all()

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return BrandingWebhookCreateSerializer
        return BrandingWebhookSerializer

    def get_permissions(self):
        return [IsStaffUser()]

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Send a test webhook event."""
        from ..webhooks import dispatch_webhook
        webhook = self.get_object()
        # Create a minimal mock instance for the test payload
        dispatch_webhook('status_change', webhook)
        return Response({'detail': 'Test webhook dispatched.'})

    @action(detail=True, methods=['get'])
    def deliveries(self, request, pk=None):
        """List delivery history for a webhook."""
        webhook = self.get_object()
        deliveries = webhook.deliveries.order_by('-created_at')[:50]
        return Response(WebhookDeliverySerializer(deliveries, many=True).data)
