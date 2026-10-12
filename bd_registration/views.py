"""
bd_registration/views.py
=========================
API ViewSets and page views for the Birth & Death Registration module.

Workflow transitions are separate @action endpoints — status cannot be
changed via generic PUT/PATCH.

Cause-of-death is NEVER exposed through public endpoints.
"""

import logging
from datetime import date as date_type

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status as http_status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from bd_master.models import (
    RegistrationOffice,
    RegistrationType,
)
from core.authentication.permissions import HasRole, IsAuthenticatedUser
from geography.models import District, ULB, Ward

from .models import (
    AdoptedBirthRegistration,
    Application,
    ApplicationDocument,
    ApplicationStatus,
    ApplicationStatusHistory,
    BirthRegistration,
    DeathRegistration,
    StillBirthRegistration,
)
from .serializers import (
    AdoptedBirthRegistrationSerializer,
    ApplicationDocumentSerializer,
    ApplicationSerializer,
    BirthApplicationSerializer,
    BirthRegistrationSerializer,
    DeathRegistrationRestrictedSerializer,
    DeathRegistrationSerializer,
    StillBirthRegistrationSerializer,
)
from .services import DelayCalculationService

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# ALLOWED TRANSITIONS — enforced by workflow actions, not generic PATCH
# ═══════════════════════════════════════════════════════════════════════════════

_ALLOWED_TRANSITIONS = {
    'submit':   {ApplicationStatus.DRAFT},
    'scrutiny': {ApplicationStatus.SUBMITTED},
    'process':  {ApplicationStatus.UNDER_SCRUTINY, ApplicationStatus.PENDING_DOCS},
    'approve':  {ApplicationStatus.UNDER_PROCESS, ApplicationStatus.UNDER_SCRUTINY},
    'reject':   {ApplicationStatus.UNDER_SCRUTINY, ApplicationStatus.UNDER_PROCESS, ApplicationStatus.SUBMITTED},
    'cancel':   {ApplicationStatus.DRAFT, ApplicationStatus.SUBMITTED,
                 ApplicationStatus.UNDER_SCRUTINY, ApplicationStatus.PENDING_DOCS, ApplicationStatus.UNDER_PROCESS},
    'register': {ApplicationStatus.APPROVED},
    'pending_docs': {ApplicationStatus.UNDER_SCRUTINY},
}


def _record_transition(application, old_status, new_status, action_code, user, remarks=''):
    """Write an immutable status-history record."""
    ApplicationStatusHistory.objects.create(
        application=application,
        old_status=old_status,
        new_status=new_status,
        action=action_code,
        changed_by=user,
        changed_at=timezone.now(),
        remarks=remarks,
    )


def _get_master_context():
    """Return master-data context shared by all four registration page views."""
    return {
        'registration_types':   RegistrationType.objects.filter(is_active=True).order_by('name'),
        'districts':            District.objects.filter(is_active=True).order_by('name'),
        'ulbs':                 ULB.objects.filter(is_active=True).order_by('name'),
        'registration_offices': RegistrationOffice.objects.filter(is_active=True).order_by('name'),
        'wards':                Ward.objects.filter(is_active=True).order_by('name'),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE VIEWS — render the HTML registration form templates
# ═══════════════════════════════════════════════════════════════════════════════

class BirthRegistrationPageView(LoginRequiredMixin, View):
    """GET /birth-registration/ → renders the birth application form."""
    login_url = '/login/'

    def get(self, request):
        ctx = _get_master_context()
        ctx['application'] = None
        return render(request, 'Authority/birth_application_form.html', ctx)


class DeathRegistrationPageView(LoginRequiredMixin, View):
    """GET /death-registration/ → renders the death application form."""
    login_url = '/login/'

    def get(self, request):
        ctx = _get_master_context()
        ctx['application'] = None
        return render(request, 'Authority/death_application_form.html', ctx)


class StillBirthRegistrationPageView(LoginRequiredMixin, View):
    """GET /still-birth-registration/ → renders the still birth form."""
    login_url = '/login/'

    def get(self, request):
        ctx = _get_master_context()
        ctx['application'] = None
        return render(request, 'Authority/still_birth_application_form.html', ctx)


class AdoptedBirthRegistrationPageView(LoginRequiredMixin, View):
    """GET /adopted-birth-registration/ → renders the adopted birth form."""
    login_url = '/login/'

    def get(self, request):
        ctx = _get_master_context()
        ctx['application'] = None
        return render(request, 'Authority/adopted_birth_application_form.html', ctx)


# ═══════════════════════════════════════════════════════════════════════════════
# APPLICATION VIEWSET
# ═══════════════════════════════════════════════════════════════════════════════

class ApplicationViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    """
    CRUD for Application records.

    Status transitions are controlled exclusively through dedicated actions:
        POST .../submit/     DRAFT → SUBMITTED
        POST .../approve/    UNDER_PROCESS|UNDER_SCRUTINY → APPROVED
        POST .../reject/     UNDER_SCRUTINY|UNDER_PROCESS|SUBMITTED → REJECTED
        POST .../cancel/     DRAFT|SUBMITTED|UNDER_SCRUTINY|... → CANCELLED
        POST .../register/   APPROVED → REGISTERED (generates registration_number)

    Generic PUT/PATCH may update data fields but cannot change status.
    """

    queryset = Application.objects.select_related(
        'registration_type',
        'district', 'ulb', 'registration_office',
        'submitted_by', 'assigned_to', 'workflow', 'current_step',
    ).all()
    serializer_class = ApplicationSerializer
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'ulb', 'district',
        'status', 'registration_type', 'service_type',
        'submitted_by', 'assigned_to',
    ]
    search_fields   = ['application_number', 'remarks']
    ordering_fields = ['created_at', 'submitted_at', 'status']
    ordering        = ['-created_at']

    def perform_create(self, serializer):
        app = serializer.save(submitted_by=self.request.user)
        _record_transition(
            application=app,
            old_status='',
            new_status=ApplicationStatus.DRAFT,
            action_code='CREATED',
            user=self.request.user,
        )

    def update(self, request, *args, **kwargs):
        """
        Prevent modification of REGISTERED or CANCELLED applications.
        Also prevent users from directly setting status via PATCH/PUT.
        """
        app = self.get_object()
        if app.status in (ApplicationStatus.REGISTERED, ApplicationStatus.CANCELLED):
            return Response(
                {'detail': 'Registered or cancelled applications cannot be modified.',
                 'code': 'application_locked'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        # Strip status from data to prevent direct manipulation
        data = request.data.copy()
        for protected in ('status', 'application_number', 'registration_number',
                          'date_of_registration', 'submitted_at', 'submitted_by'):
            data.pop(protected, None)
        kwargs['partial'] = True
        serializer = self.get_serializer(app, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    # ── Submit ────────────────────────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        """POST .../submit/  DRAFT → SUBMITTED"""
        app = self.get_object()

        if app.status not in _ALLOWED_TRANSITIONS['submit']:
            return Response(
                {'detail': f'Cannot submit an application with status "{app.status}".',
                 'code': 'invalid_transition'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # Mandatory field validation
        errors = {}
        if not app.date_of_reporting:
            errors['date_of_reporting'] = 'Date of reporting is required before submission.'

        # Event-date validation per registration type
        event_date = _get_event_date(app)
        if event_date is None:
            errors['event_date'] = 'Event date (date of birth / date of death) must be set.'

        if event_date and event_date > timezone.localdate():
            errors['event_date'] = 'Event date cannot be in the future.'

        if app.date_of_reporting and event_date:
            if app.date_of_reporting < event_date:
                errors['date_of_reporting'] = (
                    'Date of reporting cannot be before the event date.'
                )

        if errors:
            return Response(
                {'detail': 'Validation failed.', 'errors': errors,
                 'code': 'validation_error'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # Delay-rule validation using the existing service
        if app.date_of_reporting and event_date:
            state_code = app.state_code or ''
            delay_result = DelayCalculationService.calculate(
                event_date=event_date,
                date_of_reporting=app.date_of_reporting,
                state_code=state_code,
            )
            # Hard date-validation errors (future event, reporting before event)
            # produce an empty delay_category — reject those.
            # Missing rule configuration (no DelayRule seeded) is a warning only
            # and must not block valid submissions.
            if delay_result.error and delay_result.delay_category == '':
                return Response(
                    {'detail': delay_result.error, 'code': 'delay_validation_error'},
                    status=http_status.HTTP_400_BAD_REQUEST,
                )
            # If >1 year AND a rule is configured that requires a permission order,
            # enforce document upload before submission.
            if delay_result.requires_permission_order and not app.documents.exists():
                return Response(
                    {
                        'detail': (
                            'This registration is delayed by more than 1 year. '
                            'An order from the prescribed authority (DM/SDM) must be '
                            'uploaded before submission.'
                        ),
                        'code': 'delayed_order_required',
                        'delay_category': delay_result.delay_category,
                        'requires_permission_order': True,
                    },
                    status=http_status.HTTP_400_BAD_REQUEST,
                )

        old_status = app.status
        app.status = ApplicationStatus.SUBMITTED
        app.submitted_at = timezone.now()
        if not app.submitted_by:
            app.submitted_by = request.user
        app.save(update_fields=['status', 'submitted_at', 'submitted_by'])

        _record_transition(app, old_status, ApplicationStatus.SUBMITTED,
                           'SUBMITTED', request.user,
                           request.data.get('remarks', ''))

        return Response(ApplicationSerializer(app).data, status=http_status.HTTP_200_OK)

    # ── Approve ───────────────────────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        """POST .../approve/"""
        app = self.get_object()
        if app.status not in _ALLOWED_TRANSITIONS['approve']:
            return Response(
                {'detail': f'Cannot approve application with status "{app.status}".',
                 'code': 'invalid_transition'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        old_status = app.status
        app.status = ApplicationStatus.APPROVED
        app.save(update_fields=['status'])
        _record_transition(app, old_status, ApplicationStatus.APPROVED,
                           'APPROVED', request.user,
                           request.data.get('remarks', ''))
        return Response(ApplicationSerializer(app).data)

    # ── Reject ────────────────────────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        """POST .../reject/  — reason is required."""
        app = self.get_object()
        if app.status not in _ALLOWED_TRANSITIONS['reject']:
            return Response(
                {'detail': f'Cannot reject application with status "{app.status}".',
                 'code': 'invalid_transition'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        reason = request.data.get('remarks', '').strip()
        if not reason:
            return Response(
                {'detail': 'A rejection reason (remarks) is required.',
                 'code': 'reason_required'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        old_status = app.status
        app.status = ApplicationStatus.REJECTED
        app.save(update_fields=['status'])
        _record_transition(app, old_status, ApplicationStatus.REJECTED,
                           'REJECTED', request.user, reason)
        return Response(ApplicationSerializer(app).data)

    # ── Cancel ────────────────────────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request, pk=None):
        """POST .../cancel/"""
        app = self.get_object()
        if app.status not in _ALLOWED_TRANSITIONS['cancel']:
            return Response(
                {'detail': f'Cannot cancel application with status "{app.status}".',
                 'code': 'invalid_transition'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        old_status = app.status
        app.status = ApplicationStatus.CANCELLED
        app.save(update_fields=['status'])
        _record_transition(app, old_status, ApplicationStatus.CANCELLED,
                           'CANCELLED', request.user,
                           request.data.get('remarks', ''))
        return Response(ApplicationSerializer(app).data)

    # ── Register ──────────────────────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='register')
    def register(self, request, pk=None):
        """
        POST .../register/  APPROVED → REGISTERED

        Generates a unique registration number and sets date_of_registration.
        Registration number is separate from application number.
        Cannot be set manually.
        """
        app = self.get_object()
        if app.status not in _ALLOWED_TRANSITIONS['register']:
            return Response(
                {'detail': f'Only APPROVED applications can be registered. '
                           f'Current status: "{app.status}".',
                 'code': 'invalid_transition'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.localdate()
        reg_number = _generate_registration_number(app, today)

        # Persist registration number and date on the transaction record
        # Use select_for_update to prevent concurrent duplicates
        with transaction.atomic():
            _set_registration_on_transaction(app, reg_number, today)
            old_status = app.status
            app.status = ApplicationStatus.REGISTERED
            app.save(update_fields=['status'])
            _record_transition(app, old_status, ApplicationStatus.REGISTERED,
                               'REGISTERED', request.user,
                               request.data.get('remarks', ''))

        return Response({
            **ApplicationSerializer(app).data,
            'registration_number': reg_number,
            'date_of_registration': str(today),
        })

    # ── Status History ────────────────────────────────────────────────────────

    @action(detail=True, methods=['get'], url_path='history')
    def history(self, request, pk=None):
        """GET .../history/  — returns status transition audit log."""
        app = self.get_object()
        entries = app.status_history.select_related('changed_by').all()
        data = [
            {
                'old_status': e.old_status,
                'new_status': e.new_status,
                'action': e.action,
                'changed_by': (
                    e.changed_by.get_full_name() or e.changed_by.username
                    if e.changed_by else None
                ),
                'changed_at': e.changed_at.isoformat(),
                'remarks': e.remarks,
            }
            for e in entries
        ]
        return Response(data)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _get_event_date(app: Application):
    """Return the event date (DOB or DOD) from the attached transaction record."""
    try:
        return app.birth_registration.date_of_birth
    except Exception:
        pass
    try:
        return app.death_registration.date_of_death
    except Exception:
        pass
    try:
        return app.still_birth_registration.date_of_birth
    except Exception:
        pass
    try:
        return app.adopted_birth_registration.date_of_birth
    except Exception:
        pass
    return None


def _generate_registration_number(app: Application, today) -> str:
    """
    Generate BD-REG-YYYY-NNNNNN where NNNNNN is the pk zero-padded.
    Distinct from application_number (BD-YYYY-NNNNNN).
    """
    return f'BD-REG-{today.year}-{app.pk:06d}'


def _set_registration_on_transaction(app: Application, reg_number: str, today):
    """Set registration_number and date_of_registration on the correct child record."""
    for rel in ('birth_registration', 'death_registration',
                'still_birth_registration', 'adopted_birth_registration'):
        try:
            child = getattr(app, rel)
            child.registration_number  = reg_number
            child.date_of_registration = today
            child.save(update_fields=['registration_number', 'date_of_registration'])
            return
        except Exception:
            continue


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION TRANSACTION VIEWSETS
# ═══════════════════════════════════════════════════════════════════════════════

class BirthRegistrationViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = BirthRegistration.objects.select_related(
        'application__ulb', 'application__district',
        'ward',
    ).all()
    serializer_class = BirthRegistrationSerializer
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'sex', 'application__ulb', 'application__district',
        'application__status',
    ]
    search_fields    = [
        'child_first_name', 'child_last_name', 'mother_name', 'father_name',
        'registration_number', 'application__application_number',
    ]
    ordering_fields  = ['date_of_birth', 'application__created_at']
    ordering         = ['-application__created_at']


class DeathRegistrationViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    """Public — cause_of_death excluded from serializer."""
    queryset = DeathRegistration.objects.select_related(
        'application__ulb', 'application__district',
        'ward',
    ).all()
    serializer_class = DeathRegistrationSerializer
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'sex', 'application__ulb', 'application__district',
        'application__status',
    ]
    search_fields    = [
        'deceased_first_name', 'deceased_last_name',
        'registration_number', 'application__application_number',
    ]
    ordering_fields  = ['date_of_death', 'application__created_at']
    ordering         = ['-application__created_at']


class DeathRegistrationRestrictedViewSet(
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    """Restricted — includes cause_of_death. HEALTH_OFFICER/CHO/ADMIN only."""
    queryset = DeathRegistration.objects.select_related(
        'application__ulb', 'application__district',
    ).all()
    serializer_class   = DeathRegistrationRestrictedSerializer
    permission_classes = [HasRole.of('HEALTH_OFFICER', 'CHO', 'ADMIN')]
    filter_backends    = [DjangoFilterBackend, SearchFilter]
    filterset_fields   = ['application__ulb', 'application__status']
    search_fields      = ['deceased_first_name', 'deceased_last_name', 'registration_number']
    ordering           = ['-application__created_at']


class StillBirthRegistrationViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = StillBirthRegistration.objects.select_related(
        'application__ulb', 'application__district',
        'ward',
    ).all()
    serializer_class = StillBirthRegistrationSerializer
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'sex', 'application__ulb', 'application__district',
        'application__status',
    ]
    search_fields    = [
        'mother_name', 'father_name',
        'registration_number', 'application__application_number',
    ]
    ordering_fields  = ['date_of_birth', 'application__created_at']
    ordering         = ['-application__created_at']


class AdoptedBirthRegistrationViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = AdoptedBirthRegistration.objects.select_related(
        'application__ulb', 'application__district',
    ).all()
    serializer_class = AdoptedBirthRegistrationSerializer
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'sex', 'application__ulb', 'application__district', 'application__status',
    ]
    search_fields    = [
        'child_first_name', 'child_last_name',
        'adoptive_father_name', 'adoptive_mother_name',
        'adoption_order_number', 'registration_number',
        'application__application_number',
    ]
    ordering_fields  = ['date_of_birth', 'application__created_at']
    ordering         = ['-application__created_at']


# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENT VIEWSET
# ═══════════════════════════════════════════════════════════════════════════════

class ApplicationDocumentViewSet(
    mixins.CreateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    """
    Upload and list documents for a specific Application.

    Mounted nested under applications:
        GET  /api/bd-registration/applications/<application_pk>/documents/
        POST /api/bd-registration/applications/<application_pk>/documents/
    """
    serializer_class = ApplicationDocumentSerializer
    parser_classes   = [MultiPartParser, FormParser]
    filter_backends  = [DjangoFilterBackend]
    filterset_fields = ['verification_status', 'document_type']

    def get_queryset(self):
        return ApplicationDocument.objects.filter(
            application_id=self.kwargs['application_pk']
        ).select_related('document_type', 'uploaded_by', 'verified_by').all()

    def perform_create(self, serializer):
        app_pk = self.kwargs['application_pk']
        try:
            app = Application.objects.get(pk=app_pk)
        except Application.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound('Application not found.')
        if app.status == ApplicationStatus.REGISTERED:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Cannot add documents to a registered application.')
        serializer.save(
            application=app,
            uploaded_by=self.request.user,
            original_filename=self.request.FILES.get('file', {}).name
            if hasattr(self.request.FILES.get('file', {}), 'name') else '',
        )


# ═══════════════════════════════════════════════════════════════════════════════
# DELAY CHECK VIEW
# ═══════════════════════════════════════════════════════════════════════════════

class DelayCheckView(APIView):
    """
    POST /api/bd-registration/delay-check/

    Request: { "event_date": "YYYY-MM-DD", "date_of_reporting": "YYYY-MM-DD", "state_code": "RJ" }
    Returns full delay result including fee, authority and document requirements.
    """

    def post(self, request):
        event_date_raw        = request.data.get('event_date', '').strip()
        date_of_reporting_raw = request.data.get('date_of_reporting', '').strip()
        state_code            = request.data.get('state_code', '').strip()

        if not event_date_raw or not date_of_reporting_raw:
            return Response(
                {'detail': 'event_date and date_of_reporting are required.',
                 'code': 'missing_fields'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        try:
            event_date = date_type.fromisoformat(event_date_raw)
        except ValueError:
            return Response(
                {'detail': f'Invalid event_date: "{event_date_raw}". Use YYYY-MM-DD.',
                 'code': 'invalid_date'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        try:
            date_of_reporting = date_type.fromisoformat(date_of_reporting_raw)
        except ValueError:
            return Response(
                {'detail': f'Invalid date_of_reporting: "{date_of_reporting_raw}". Use YYYY-MM-DD.',
                 'code': 'invalid_date'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        result = DelayCalculationService.calculate(
            event_date=event_date,
            date_of_reporting=date_of_reporting,
            state_code=state_code,
        )

        if result.error and result.delay_category == '':
            return Response(
                {'detail': result.error, 'code': 'validation_error'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        from bd_master.models import DelayCategory
        display_map = dict(DelayCategory.choices)

        return Response({
            'delay_days':               result.delay_days,
            'delay_category':           result.delay_category,
            'delay_category_display':   display_map.get(result.delay_category, result.delay_category),
            'is_normal':                result.is_normal,
            'fee_code':                 result.fee_code,
            'applicable_fee':           str(result.applicable_fee),
            'currency':                 result.currency,
            'requires_authority':       result.requires_authority,
            'authority_code':           result.authority_code,
            'authority_name':           result.authority_name,
            'authority_notes':          result.authority_notes,
            'requires_form_14':         result.requires_form_14,
            'requires_affidavit':       result.requires_affidavit,
            'requires_permission_order': result.requires_permission_order,
            'required_document_codes':  result.required_document_codes,
            'required_document_names':  result.required_document_names,
            'rule_reference':           result.rule_reference,
            'rule_code':                result.rule_code,
            'error':                    result.error,
        }, status=http_status.HTTP_200_OK)


# ═══════════════════════════════════════════════════════════════════════════════
# BIRTH APPLICATION — ATOMIC CREATE (draft or submit in one round-trip)
# ═══════════════════════════════════════════════════════════════════════════════

class BirthApplicationCreateView(APIView):
    """
    POST /api/bd-registration/birth-applications/

    Creates an Application + BirthRegistration atomically.
    Accepts an `action` field:
        "draft"  → saves as DRAFT, no strict validation beyond registration_type
        "submit" → runs full validation then transitions to SUBMITTED

    Request body: all Application + BirthRegistration fields + action.
    Returns the Application record on success.

    This endpoint eliminates the race condition of the two-step approach
    (POST /applications/ then POST /births/) where an Application could be
    left without a BirthRegistration if the second call fails.
    """

    from .serializers import BirthApplicationSerializer as _BirthAppSer  # local alias

    def post(self, request):
        from .serializers import BirthApplicationSerializer

        ser = BirthApplicationSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': ser.errors,
                 'code': 'validation_error'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        data   = ser.validated_data
        action = data.pop('action', 'draft')

        # ── Separate application vs birth fields ──────────────────────────────
        app_field_names = {
            'service_type', 'registration_type', 'state_code',
            'district', 'ulb', 'date_of_reporting', 'remarks',
        }
        birth_field_names = {
            'child_first_name', 'child_middle_name', 'child_last_name',
            'name_recorded', 'date_of_birth', 'time_of_birth', 'sex',
            'event_location_type', 'institution_name', 'place_of_birth_address',
            'ward',
            'mother_name', 'mother_age_at_birth', 'mother_nationality',
            'mother_education', 'mother_occupation', 'mother_mobile', 'mother_aadhaar',
            'father_name', 'father_age_at_birth', 'father_nationality',
            'father_education', 'father_occupation', 'father_mobile', 'father_aadhaar',
            'permanent_address',
            'informant_name', 'informant_relation', 'informant_address', 'informant_mobile',
        }

        app_data   = {k: v for k, v in data.items() if k in app_field_names and v is not None}
        birth_data = {k: v for k, v in data.items() if k in birth_field_names}

        # Remove empty string values for non-nullable FK fields
        for fk_field in ('district', 'ulb'):
            if fk_field in app_data and not app_data[fk_field]:
                del app_data[fk_field]

        try:
            with transaction.atomic():
                # Create Application
                app = Application(**app_data)
                app.submitted_by = request.user
                app.save()

                _record_transition(
                    application=app,
                    old_status='',
                    new_status=ApplicationStatus.DRAFT,
                    action_code='CREATED',
                    user=request.user,
                )

                # Create BirthRegistration
                BirthRegistration.objects.create(
                    application=app,
                    **birth_data,
                )

                # If action is submit, run the submit transition
                if action == 'submit':
                    errors = {}
                    if not app.date_of_reporting:
                        errors['date_of_reporting'] = 'Date of reporting is required.'

                    event_date = birth_data.get('date_of_birth')
                    if not event_date:
                        errors['date_of_birth'] = 'Date of birth is required.'

                    if errors:
                        raise ValueError(errors)

                    # Delay rule validation
                    state_code = app.state_code or ''
                    delay_result = DelayCalculationService.calculate(
                        event_date=event_date,
                        date_of_reporting=app.date_of_reporting,
                        state_code=state_code,
                    )
                    if delay_result.error and delay_result.delay_category == '':
                        raise ValueError({'non_field': delay_result.error})

                    if delay_result.requires_permission_order:
                        raise ValueError({
                            'non_field': (
                                'This registration is delayed by more than 1 year. '
                                'An order from the prescribed authority must be uploaded '
                                'before submission. Please save as draft first, upload '
                                'the document, then submit.'
                            )
                        })

                    app.status      = ApplicationStatus.SUBMITTED
                    app.submitted_at = timezone.now()
                    app.save(update_fields=['status', 'submitted_at'])

                    _record_transition(
                        application=app,
                        old_status=ApplicationStatus.DRAFT,
                        new_status=ApplicationStatus.SUBMITTED,
                        action_code='SUBMITTED',
                        user=request.user,
                        remarks=app_data.get('remarks', ''),
                    )

        except ValueError as exc:
            errs = exc.args[0] if exc.args else {}
            if isinstance(errs, dict):
                return Response(
                    {'detail': 'Validation failed.', 'errors': errs,
                     'code': 'validation_error'},
                    status=http_status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {'detail': str(exc), 'code': 'validation_error'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            ApplicationSerializer(app, context={'request': request}).data,
            status=http_status.HTTP_201_CREATED,
        )
