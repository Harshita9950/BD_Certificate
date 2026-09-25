
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

from .views import (
    TradeCategoryViewSet,
    TradeViewSet,
    SubTradeViewSet,
    ULBTradeConfigViewSet,
    ApplicationViewSet,
)

app_name = "trade_master"

router = DefaultRouter()

router.register(
    "categories",
    TradeCategoryViewSet,
    basename="tradecategory",
)

router.register(
    "trades",
    TradeViewSet,
    basename="trade",
)

router.register(
    "sub-trades",
    SubTradeViewSet,
    basename="subtrade",
)

router.register(
    "ulb-configs",
    ULBTradeConfigViewSet,
    basename="ulbtradeconfig",
)

router.register(
    "applications",
    ApplicationViewSet,
    basename="application",
)

urlpatterns = [
    # HTML application form
    path(
        "new/",
        views.new_application,
        name="new_application",
    ),

    # Existing API routes
    path("", include(router.urls)),
]