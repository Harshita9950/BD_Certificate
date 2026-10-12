"""
bd_registration/urls.py
========================
Mounted at: /api/bd-registration/

Routes
------
GET/POST         /api/bd-registration/applications/
GET/PUT/PATCH    /api/bd-registration/applications/<pk>/
POST             /api/bd-registration/applications/<pk>/submit/
POST             /api/bd-registration/applications/<pk>/approve/
POST             /api/bd-registration/applications/<pk>/reject/
POST             /api/bd-registration/applications/<pk>/cancel/
POST             /api/bd-registration/applications/<pk>/register/
GET              /api/bd-registration/applications/<pk>/history/
GET/POST         /api/bd-registration/applications/<pk>/documents/
GET              /api/bd-registration/applications/<pk>/documents/<doc_pk>/

GET/POST         /api/bd-registration/births/
GET/POST         /api/bd-registration/deaths/
GET/POST         /api/bd-registration/still-births/
GET/POST         /api/bd-registration/adopted-births/
POST             /api/bd-registration/delay-check/
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdoptedBirthRegistrationViewSet,
    ApplicationDocumentViewSet,
    ApplicationViewSet,
    BirthApplicationCreateView,
    BirthRegistrationViewSet,
    DeathRegistrationRestrictedViewSet,
    DeathRegistrationViewSet,
    DelayCheckView,
    StillBirthRegistrationViewSet,
)

app_name = 'bd_registration'

# ── Top-level router ──────────────────────────────────────────────────────────
router = DefaultRouter()
router.register('applications',       ApplicationViewSet,             basename='application')
router.register('births',             BirthRegistrationViewSet,       basename='birth')
router.register('deaths',             DeathRegistrationViewSet,       basename='death')
router.register('deaths/restricted',  DeathRegistrationRestrictedViewSet, basename='death-restricted')
router.register('still-births',       StillBirthRegistrationViewSet,  basename='still-birth')
router.register('adopted-births',     AdoptedBirthRegistrationViewSet, basename='adopted-birth')

urlpatterns = [
    # ── Delay calculation endpoint ─────────────────────────────────────────────
    path('delay-check/', DelayCheckView.as_view(), name='delay_check'),

    # ── Atomic birth application create (draft or submit in one call) ──────────
    path('birth-applications/', BirthApplicationCreateView.as_view(), name='birth_application_create'),

    # ── Nested document routes (manual, no extra package needed) ──────────────
    path(
        'applications/<int:application_pk>/documents/',
        ApplicationDocumentViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='application-document-list',
    ),
    path(
        'applications/<int:application_pk>/documents/<int:pk>/',
        ApplicationDocumentViewSet.as_view({'get': 'retrieve'}),
        name='application-document-detail',
    ),

    # ── Top-level ViewSet routes ───────────────────────────────────────────────
    path('', include(router.urls)),
]
