from rest_framework import viewsets, mixins

from django_filters.rest_framework import DjangoFilterBackend

from .models import District, ULB, Zone, Ward

from .serializers import (
    DistrictSerializer,
    ULBSerializer,
    ZoneSerializer,
    WardSerializer,
)


class DistrictViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet
):
    queryset = District.objects.all()
    serializer_class = DistrictSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_active']
    search_fields = ['code', 'name']


class ULBViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet
):
    queryset = ULB.objects.all().select_related('district')
    serializer_class = ULBSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['district', 'ulb_type', 'is_active']
    search_fields = ['code', 'name']

class ZoneViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet
):
    queryset = Zone.objects.all().select_related('ulb')
    serializer_class = ZoneSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['ulb', 'is_active']
    search_fields = ['code', 'name']


class WardViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet
):
    queryset = Ward.objects.all().select_related('zone__ulb')
    serializer_class = WardSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['zone', 'is_active']
    search_fields = ['code', 'name']