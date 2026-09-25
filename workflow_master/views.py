from rest_framework import mixins, viewsets
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter

from .models import Workflow, WorkflowStep
from .serializers import WorkflowSerializer, WorkflowStepSerializer
from .permissions import WorkflowPermission


class WorkflowViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Workflow.objects.select_related('ulb').all()
    serializer_class = WorkflowSerializer
    permission_classes = [WorkflowPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['ulb', 'application_type', 'is_active']
    search_fields = ['code', 'name', 'description']


class WorkflowStepViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = WorkflowStep.objects.select_related('workflow').all()
    serializer_class = WorkflowStepSerializer
    permission_classes = [WorkflowPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['workflow', 'role_code', 'is_active']
    search_fields = ['code', 'name', 'description', 'role_code']