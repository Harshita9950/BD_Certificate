"""
bd_master/urls.py
==================
Mounted at: /api/bd-master/

Routes
------
/api/bd-master/registration-offices/
/api/bd-master/document-types/
/api/bd-master/registration-types/
/api/bd-master/authority-types/
/api/bd-master/delay-rules/
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    RegistrationOfficeViewSet,
    DocumentTypeViewSet,
    RegistrationTypeViewSet,
    AuthorityTypeViewSet,
    DelayRuleViewSet,
)

app_name = 'bd_master'

router = DefaultRouter()
router.register('registration-offices',  RegistrationOfficeViewSet,  basename='registrationoffice')
router.register('document-types',        DocumentTypeViewSet,         basename='documenttype')
router.register('registration-types',    RegistrationTypeViewSet,     basename='registrationtype')
router.register('authority-types',       AuthorityTypeViewSet,        basename='authoritytype')
router.register('delay-rules',           DelayRuleViewSet,            basename='delayrule')

urlpatterns = [path('', include(router.urls))]
