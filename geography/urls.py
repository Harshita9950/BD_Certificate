from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DistrictViewSet, ULBViewSet, ZoneViewSet, WardViewSet

app_name = 'geography'

router = DefaultRouter()
router.register('districts', DistrictViewSet, basename='district')
router.register('ulbs',      ULBViewSet,      basename='ulb')
router.register('zones',     ZoneViewSet,     basename='zone')
router.register('wards',     WardViewSet,     basename='ward')

urlpatterns = [path('', include(router.urls))]
