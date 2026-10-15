"""
fee_master/views.py
====================
Generic CRUD API views for the Birth & Death Fee Master.

Endpoints
---------
GET    /api/fee-master/                     list all fee records (filterable)
POST   /api/fee-master/                     create a fee record
GET    /api/fee-master/<pk>/                retrieve a single record
PUT    /api/fee-master/<pk>/                full update
PATCH  /api/fee-master/<pk>/                partial update
PATCH  /api/fee-master/<pk>/activate/       activate a fee record
PATCH  /api/fee-master/<pk>/deactivate/     deactivate a fee record
GET    /api/fee-master/service-types/       list all ServiceType choices
GET    /api/fee-master/calculation-types/   list all CalculationType choices

Authentication: global IsAuthenticatedUser (from settings)
Permissions:    read = any authenticated user
                write = ADMIN role only (enforced per-view)
"""

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from core.authentication.permissions import IsAdminUser, IsAuthenticatedUser

from .models import CalculationType, FeeMaster, ServiceType
from .serializers import (
    CalculationTypeChoiceSerializer,
    FeeMasterListSerializer,
    FeeMasterSerializer,
    ServiceTypeChoiceSerializer,
)

logger = logging.getLogger(__name__)


# ─── Fee Master ViewSet ───────────────────────────────────────────────────────

class FeeMasterViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    CRUD ViewSet for Fee Master records.

    List/Retrieve: any authenticated user.
    Create/Update/Activate/Deactivate: ADMIN only.

    Filtering
    ---------
    ?service_type=BIRTH_REGISTRATION
    ?is_active=true
    ?state_code=RJ
    ?district=<id>
    ?ulb=<id>
    ?effective_on=YYYY-MM-DD   (returns records effective on that date)
    ?search=<term>             (searches fee_code, fee_name, rule_reference)
    """

    queryset = FeeMaster.objects.select_related('district', 'ulb').all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['service_type', 'calculation_type', 'is_active',
                        'state_code', 'district', 'ulb', 'currency']
    search_fields    = ['fee_code', 'fee_name', 'rule_reference', 'notes']
    ordering_fields  = ['service_type', 'fee_code', 'amount', 'effective_from']
    ordering         = ['service_type', 'fee_code']

    def get_serializer_class(self):
        if self.action == 'list':
            return FeeMasterListSerializer
        return FeeMasterSerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update',
                           'activate', 'deactivate'):
            return [IsAdminUser()]
        return [IsAuthenticatedUser()]

    def get_queryset(self):
        qs = super().get_queryset()

        # Optional: filter by effective_on date
        effective_on = self.request.query_params.get('effective_on')
        if effective_on:
            try:
                from datetime import date
                d = date.fromisoformat(effective_on)
                qs = qs.filter(
                    effective_from__lte=d,
                ).filter(
                    Q(effective_to__isnull=True) | Q(effective_to__gte=d)
                )
            except ValueError:
                pass  # ignore invalid date — return unfiltered

        return qs

    @action(detail=True, methods=['patch'], url_path='activate')
    def activate(self, request, pk=None):
        """PATCH /api/fee-master/<pk>/activate/"""
        record = self.get_object()
        record.is_active = True
        record.save(update_fields=['is_active', 'updated_at'])
        logger.info('FeeMaster %s activated by %s', record.fee_code, request.user.email)
        return Response(
            {'detail': f'Fee record "{record.fee_code}" activated.',
             'id': record.id, 'is_active': True},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['patch'], url_path='deactivate')
    def deactivate(self, request, pk=None):
        """PATCH /api/fee-master/<pk>/deactivate/"""
        record = self.get_object()
        record.is_active = False
        record.save(update_fields=['is_active', 'updated_at'])
        logger.info('FeeMaster %s deactivated by %s', record.fee_code, request.user.email)
        return Response(
            {'detail': f'Fee record "{record.fee_code}" deactivated.',
             'id': record.id, 'is_active': False},
            status=status.HTTP_200_OK,
        )


# ─── Choice Endpoints ─────────────────────────────────────────────────────────

class ServiceTypeListView(APIView):
    """
    GET /api/fee-master/service-types/
    Returns all available ServiceType choices.
    Used by frontend dropdowns when creating/filtering fee records.
    """
    permission_classes = [IsAuthenticatedUser]

    def get(self, request):
        choices = [
            {'value': v, 'display': str(l)}
            for v, l in ServiceType.choices
        ]
        return Response(choices)


class CalculationTypeListView(APIView):
    """
    GET /api/fee-master/calculation-types/
    Returns all available CalculationType choices.
    """
    permission_classes = [IsAuthenticatedUser]

    def get(self, request):
        choices = [
            {'value': v, 'display': str(l)}
            for v, l in CalculationType.choices
        ]
        return Response(choices)


# ─── Fee Master HTML Page View ────────────────────────────────────────────────

class FeeMasterPageView(LoginRequiredMixin, View):
    """GET /masters/fees/"""
    login_url = '/login/'

    def get(self, request):
        service_type_choices = [
            {'value': v, 'display': str(l)}
            for v, l in ServiceType.choices
        ]
        calculation_type_choices = [
            {'value': v, 'display': str(l)}
            for v, l in CalculationType.choices
        ]
        return render(request, 'Authority/fee_master_list.html', {
            'service_type_choices':     service_type_choices,
            'calculation_type_choices': calculation_type_choices,
        })


class FeeMasterAddView(LoginRequiredMixin, View):
    """GET /masters/fees/add/"""
    login_url = '/login/'

    def get(self, request):
        return render(request, 'Authority/fee_master_add.html', {
            'fee_id': '',
            'service_type_choices': [
                {'value': v, 'display': str(l)} for v, l in ServiceType.choices
            ],
            'calculation_type_choices': [
                {'value': v, 'display': str(l)} for v, l in CalculationType.choices
            ],
        })


class FeeMasterEditView(LoginRequiredMixin, View):
    """GET /masters/fees/<pk>/edit/"""
    login_url = '/login/'

    def get(self, request, pk):
        return render(request, 'Authority/fee_master_add.html', {
            'fee_id': pk,
            'service_type_choices': [
                {'value': v, 'display': str(l)} for v, l in ServiceType.choices
            ],
            'calculation_type_choices': [
                {'value': v, 'display': str(l)} for v, l in CalculationType.choices
            ],
        })
