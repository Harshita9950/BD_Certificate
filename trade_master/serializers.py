from rest_framework import serializers
from .models import TradeCategory, Trade, SubTrade, ULBTradeConfig


class TradeCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = TradeCategory
        fields = ('id', 'code', 'name', 'description', 'is_active')


class TradeSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model  = Trade
        fields = ('id', 'code', 'name', 'description', 'category', 'category_name', 'is_active')


class SubTradeSerializer(serializers.ModelSerializer):
    trade_name    = serializers.CharField(source='trade.name', read_only=True)
    category_name = serializers.CharField(source='trade.category.name', read_only=True)

    class Meta:
        model  = SubTrade
        fields = ('id', 'code', 'name', 'description', 'trade', 'trade_name',
                  'category_name', 'is_active')


class ULBTradeConfigSerializer(serializers.ModelSerializer):
    ulb_code   = serializers.CharField(source='ulb.code',   read_only=True)
    trade_name = serializers.CharField(source='trade.name', read_only=True)
    trade_code = serializers.CharField(source='trade.code', read_only=True)

    class Meta:
        model  = ULBTradeConfig
        fields = ('id', 'ulb', 'ulb_code', 'trade', 'trade_name', 'trade_code', 'is_enabled')
