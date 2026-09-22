from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TradeCategoryViewSet, TradeViewSet, SubTradeViewSet, ULBTradeConfigViewSet

app_name = 'trade_master'

router = DefaultRouter()
router.register('categories',  TradeCategoryViewSet,  basename='tradecategory')
router.register('trades',      TradeViewSet,          basename='trade')
router.register('sub-trades',  SubTradeViewSet,       basename='subtrade')
router.register('ulb-configs', ULBTradeConfigViewSet, basename='ulbtradeconfig')

urlpatterns = [path('', include(router.urls))]
