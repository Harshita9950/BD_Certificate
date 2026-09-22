from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter

from .models import TradeCategory, Trade, SubTrade, ULBTradeConfig
from .serializers import (
    TradeCategorySerializer, TradeSerializer,
    SubTradeSerializer, ULBTradeConfigSerializer,
)


class TradeCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset         = TradeCategory.objects.filter(is_active=True)
    serializer_class = TradeCategorySerializer
    filter_backends  = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['is_active']
    search_fields    = ['code', 'name']


class TradeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset         = Trade.objects.filter(is_active=True).select_related('category')
    serializer_class = TradeSerializer
    filter_backends  = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['category', 'is_active']
    search_fields    = ['code', 'name']


class SubTradeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset         = SubTrade.objects.filter(is_active=True).select_related('trade__category')
    serializer_class = SubTradeSerializer
    filter_backends  = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['trade', 'is_active']
    search_fields    = ['code', 'name']


class ULBTradeConfigViewSet(viewsets.ReadOnlyModelViewSet):
    queryset         = ULBTradeConfig.objects.select_related('ulb', 'trade__category').order_by('ulb', 'trade')
    serializer_class = ULBTradeConfigSerializer
    filter_backends  = [DjangoFilterBackend]
    filterset_fields = ['ulb', 'trade', 'is_enabled']
