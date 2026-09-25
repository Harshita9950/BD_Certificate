from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import WorkflowViewSet, WorkflowStepViewSet


router = DefaultRouter()

router.register('workflows', WorkflowViewSet, basename='workflow')
router.register('steps', WorkflowStepViewSet, basename='workflow-step')


urlpatterns = [
    path('', include(router.urls)),
]