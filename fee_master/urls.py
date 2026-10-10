"""
fee_master/urls.py
==================
Mounted at: /api/fee-master/

Routes
------
GET/POST         /api/fee-master/                   list / create
GET/PUT/PATCH    /api/fee-master/<pk>/               retrieve / update
PATCH            /api/fee-master/<pk>/activate/      activate
PATCH            /api/fee-master/<pk>/deactivate/    deactivate
GET              /api/fee-master/service-types/      ServiceType choices
GET              /api/fee-master/calculation-types/  CalculationType choices
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CalculationTypeListView,
    FeeMasterViewSet,
    ServiceTypeListView,
)

router = DefaultRouter()
router.register('', FeeMasterViewSet, basename='feemaster')

urlpatterns = [
    # Choice endpoints — must be declared BEFORE the router include
    # so they are matched before the router catches empty string patterns.
    path('service-types/',      ServiceTypeListView.as_view(),      name='fee_service_types'),
    path('calculation-types/',  CalculationTypeListView.as_view(),  name='fee_calculation_types'),

    # ViewSet CRUD routes
    path('', include(router.urls)),
]
