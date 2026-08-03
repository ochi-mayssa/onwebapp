"""API URL configuration for the Branding Service."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register('collections', views.BrandCollectionViewSet, basename='collection')
router.register('requests', views.BrandingRequestViewSet, basename='request')
router.register('assets', views.BrandingAssetViewSet, basename='asset')
router.register('notifications', views.BrandingNotificationViewSet, basename='notification')
router.register('messages', views.BrandingMessageViewSet, basename='message')
router.register('timeline', views.BrandingTimelineViewSet, basename='timeline')
router.register('feedback', views.BrandingFeedbackViewSet, basename='feedback')
router.register('webhooks', views.BrandingWebhookViewSet, basename='webhook')

app_name = 'branding-api'

urlpatterns = [
    path('', include(router.urls)),
]
