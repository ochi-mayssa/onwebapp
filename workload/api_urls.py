"""URL routing for the workload REST API."""
from rest_framework.routers import DefaultRouter

from .api import (
    WorkItemViewSet,
    WorkloadAlertViewSet,
    WorkloadDashboardViewSet,
    WorkloadPolicyViewSet,
    WorkloadResourceViewSet,
    WorkloadTeamViewSet,
)

app_name = 'workload-api'

router = DefaultRouter()
router.register('items', WorkItemViewSet, basename='work-item')
router.register('resources', WorkloadResourceViewSet, basename='resource')
router.register('teams', WorkloadTeamViewSet, basename='team')
router.register('alerts', WorkloadAlertViewSet, basename='alert')
router.register('policies', WorkloadPolicyViewSet, basename='policy')
router.register('dashboard', WorkloadDashboardViewSet, basename='dashboard')

urlpatterns = router.urls
