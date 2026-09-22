from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from core.authentication.permissions import IsAuthenticatedUser
from .models import District, ULB, Zone, Ward
from .serializers import DistrictSerializer, ULBSerializer, ZoneSerializer, WardSerializer


class DistrictViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = District.objects.filter(is_active=True)
    serializer_class   = DistrictSerializer
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['is_active']
    search_fields      = ['code', 'name']


class ULBViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = ULB.objects.filter(is_active=True).select_related('district')
    serializer_class   = ULBSerializer
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['district', 'ulb_type', 'is_active']
    search_fields      = ['code', 'name']


class ZoneViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = Zone.objects.filter(is_active=True).select_related('ulb')
    serializer_class   = ZoneSerializer
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['ulb', 'is_active']
    search_fields      = ['code', 'name']


class WardViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = Ward.objects.filter(is_active=True).select_related('zone__ulb')
    serializer_class   = WardSerializer
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['zone', 'is_active']
    search_fields      = ['code', 'name']
