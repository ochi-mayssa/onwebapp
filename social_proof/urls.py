from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SocialEventViewSet, DashboardView

router = DefaultRouter()
router.register(r'api/events', SocialEventViewSet, basename='social-event')

app_name = 'social_proof'

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
]
