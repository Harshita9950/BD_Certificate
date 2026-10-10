"""
bd_master/views.py
"""
from rest_framework import viewsets, mixins
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import (
    RegistrationOffice,
    DocumentType,
    RegistrationType,
    AuthorityType,
    DelayRule,
)
from .serializers import (
    RegistrationOfficeSerializer,
    DocumentTypeSerializer,
    RegistrationTypeSerializer,
    AuthorityTypeSerializer,
    DelayRuleSerializer,
)


class RegistrationOfficeViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = RegistrationOffice.objects.select_related('ulb').all()
    serializer_class = RegistrationOfficeSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['ulb', 'is_active']
    search_fields = ['code', 'name', 'registrar_name']
    ordering_fields = ['code', 'name']
    ordering = ['ulb', 'code']


class DocumentTypeViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = DocumentType.objects.all()
    serializer_class = DocumentTypeSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['is_mandatory', 'is_active']
    search_fields = ['code', 'name', 'description']
    ordering = ['name']


class RegistrationTypeViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = RegistrationType.objects.all()
    serializer_class = RegistrationTypeSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['event_category', 'is_delayed', 'is_active']
    search_fields = ['code', 'name', 'description']
    ordering_fields = ['code', 'name', 'event_category']
    ordering = ['event_category', 'name']


class AuthorityTypeViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = AuthorityType.objects.all()
    serializer_class = AuthorityTypeSerializer
    filter_backends  = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['is_active']
    search_fields    = ['code', 'name', 'description']
    ordering         = ['name']


class DelayRuleViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = DelayRule.objects.select_related(
        'district', 'ulb', 'authority_type'
    ).prefetch_related('required_documents').all()
    serializer_class = DelayRuleSerializer
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'delay_category', 'state_code', 'district', 'ulb',
        'is_active', 'requires_authority_permission',
        'requires_form_14', 'requires_permission_order',
    ]
    search_fields    = ['rule_code', 'rule_name', 'fee_code', 'rule_reference']
    ordering_fields  = ['delay_category', 'state_code', 'min_delay_days']
    ordering         = ['state_code', 'delay_category']
