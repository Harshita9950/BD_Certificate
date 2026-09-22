from django.contrib import admin
from .models import TradeCategory, Trade, SubTrade, ULBTradeConfig


@admin.register(TradeCategory)
class TradeCategoryAdmin(admin.ModelAdmin):
    list_display  = ('code', 'name', 'is_active', 'created_at')
    list_filter   = ('is_active',)
    search_fields = ('code', 'name')
    ordering      = ('name',)


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display  = ('code', 'name', 'category', 'is_active', 'created_at')
    list_filter   = ('category', 'is_active')
    search_fields = ('code', 'name')
    raw_id_fields = ('category',)
    ordering      = ('category', 'name')


@admin.register(SubTrade)
class SubTradeAdmin(admin.ModelAdmin):
    list_display  = ('code', 'name', 'trade', 'is_active', 'created_at')
    list_filter   = ('trade__category', 'is_active')
    search_fields = ('code', 'name', 'trade__name', 'trade__code')
    raw_id_fields = ('trade',)
    ordering      = ('trade', 'name')


@admin.register(ULBTradeConfig)
class ULBTradeConfigAdmin(admin.ModelAdmin):
    list_display  = ('ulb', 'trade', 'is_enabled', 'created_at')
    list_filter   = ('is_enabled', 'ulb')
    search_fields = ('ulb__code', 'ulb__name', 'trade__code', 'trade__name')
    raw_id_fields = ('ulb', 'trade')
