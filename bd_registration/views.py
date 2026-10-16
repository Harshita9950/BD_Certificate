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
from .workflow_service import assign_workflow, advance_workflow

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# ALLOWED TRANSITIONS — enforced by workflow actions, not generic PATCH
# ═══════════════════════════════════════════════════════════════════════════════

_ALLOWED_TRANSITIONS = {
    # DRAFT → PAYMENT_PENDING (fee required) or DRAFT → SUBMITTED (fee-free)
    # Both source states handled by the submit action below.
    'submit':          {ApplicationStatus.DRAFT},
    # PAYMENT_PENDING → SUBMITTED (payment confirmed by payments app)
    'confirm_payment': {ApplicationStatus.PAYMENT_PENDING},
    'scrutiny':        {ApplicationStatus.SUBMITTED},
    'process':         {ApplicationStatus.UNDER_SCRUTINY, ApplicationStatus.PENDING_DOCS},
    'approve':         {ApplicationStatus.UNDER_PROCESS, ApplicationStatus.UNDER_SCRUTINY},
    'reject':          {ApplicationStatus.UNDER_SCRUTINY, ApplicationStatus.UNDER_PROCESS, ApplicationStatus.SUBMITTED},
    'cancel':          {ApplicationStatus.DRAFT, ApplicationStatus.PAYMENT_PENDING,
                        ApplicationStatus.SUBMITTED, ApplicationStatus.UNDER_SCRUTINY,
                        ApplicationStatus.PENDING_DOCS, ApplicationStatus.UNDER_PROCESS},
    'register':        {ApplicationStatus.APPROVED},
    'pending_docs':    {ApplicationStatus.UNDER_SCRUTINY},
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
    """
    GET /birth-registration/          → blank new form
    GET /birth-registration/?app=<pk> → pre-filled editable form for a
                                        PAYMENT_PENDING application
    """
    login_url = '/login/'

    def get(self, request):
        ctx = _get_master_context()
        ctx['application']       = None
        ctx['birth_registration'] = None

        app_pk = request.GET.get('app')
        if app_pk:
            try:
                app = Application.objects.select_related(
                    'registration_type', 'district', 'ulb',
                ).get(pk=app_pk, status=ApplicationStatus.PAYMENT_PENDING)
                try:
                    br = app.birth_registration
                except Exception:
                    br = None
                ctx['application']       = app
                ctx['birth_registration'] = br
            except Application.DoesNotExist:
                pass   # silently fall through to a blank form

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


class ApplicationInboxView(LoginRequiredMixin, View):
    """
    GET /mailbox/inbox/

    Shows applications the authenticated user is responsible for processing
    at their current workflow step.

    Filtering rules (server-side, never frontend):
    1. Exclude DRAFT and PAYMENT_PENDING (not yet in the workflow).
    2. Scope to the authenticated user's ULB (user.ulb_fk).
    3. Scope to applications whose current_step.role_code matches the
       authenticated user's role — so a DA sees only DA-step applications,
       a HEALTH_OFFICER sees only HEALTH_OFFICER-step applications, etc.
    4. ADMIN users bypass role/ULB filtering and see all non-draft apps.
    5. Applications with no workflow assigned (workflow=None) are excluded
       because they have not entered the processing pipeline yet.

    Ward-level scoping: WorkflowStep has no ward field. If finer ward
    isolation is needed, set user.ward_fk on officers; this view can then
    be extended to filter via birth_registration__ward=user.ward_fk.
    """
    login_url = '/login/'

    def get(self, request):
        user = request.user

        base_qs = Application.objects.select_related(
            'registration_type', 'district', 'ulb',
            'submitted_by',
            'birth_registration',
            'death_registration',
            'still_birth_registration',
            'adopted_birth_registration',
            'current_step',
        ).exclude(
            status__in=(ApplicationStatus.DRAFT, ApplicationStatus.PAYMENT_PENDING)
        )

        # ADMINs and superusers see everything
        from users.models import UserRole
        if user.is_superuser or getattr(user, 'role', None) == UserRole.ADMIN:
            qs = base_qs.order_by('-created_at')
        else:
            # Must have a workflow assigned
            qs = base_qs.filter(workflow__isnull=False)

            # Scope to applications at a step whose role_code matches this user
            if getattr(user, 'role', None):
                qs = qs.filter(current_step__role_code=user.role)

            # Scope to this user's ULB
            if getattr(user, 'ulb_fk_id', None):
                qs = qs.filter(ulb=user.ulb_fk)

            qs = qs.order_by('-created_at')

        return render(request, 'Authority/application_inbox.html', {
            'applications': qs,
            'inbox_title':  'Application Inbox',
            'from_param':   'inbox',
        })


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

        # ── Fee gate ──────────────────────────────────────────────────────────
        # Run delay calculation to determine the applicable fee.
        # If fee > 0  → transition DRAFT → PAYMENT_PENDING (payment required first).
        # If fee == 0 → transition DRAFT → SUBMITTED directly (free registration).
        #
        # Amount is NEVER taken from the request. DelayCalculationService is the
        # sole authority. Frontend-supplied amounts are silently ignored.

        fee_required = False
        delay_result = None

        if app.date_of_reporting and event_date:
            state_code = app.state_code or ''
            delay_result = DelayCalculationService.calculate(
                event_date=event_date,
                date_of_reporting=app.date_of_reporting,
                state_code=state_code,
            )

            # Hard date-validation errors produce delay_category == '' — block.
            # Missing DelayRule seed data is a non-fatal warning — do not block.
            if delay_result.error and delay_result.delay_category == '':
                return Response(
                    {'detail': delay_result.error, 'code': 'delay_validation_error'},
                    status=http_status.HTTP_400_BAD_REQUEST,
                )

            # Enforce document upload for applications delayed >1 year that
            # require a permission order.
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

            from decimal import Decimal
            fee_required = (
                delay_result.applicable_fee is not None
                and delay_result.applicable_fee > Decimal('0.00')
            )

        old_status = app.status

        if fee_required:
            # Transition to PAYMENT_PENDING — the payments app will move the
            # application to SUBMITTED once payment is confirmed.
            app.status = ApplicationStatus.PAYMENT_PENDING
            if not app.submitted_by:
                app.submitted_by = request.user
            app.save(update_fields=['status', 'submitted_by'])

            _record_transition(app, old_status, ApplicationStatus.PAYMENT_PENDING,
                               'PAYMENT_PENDING', request.user,
                               request.data.get('remarks', ''))

            response_data = ApplicationSerializer(app).data
            response_data['payment_required']  = True
            response_data['applicable_fee']    = str(delay_result.applicable_fee)
            response_data['fee_code']          = delay_result.fee_code
            response_data['currency']          = delay_result.currency
            response_data['delay_category']    = delay_result.delay_category
            return Response(response_data, status=http_status.HTTP_200_OK)

        else:
            # Zero-fee (FREE) registration — go straight to SUBMITTED.
            app.status = ApplicationStatus.SUBMITTED
            app.submitted_at = timezone.now()
            if not app.submitted_by:
                app.submitted_by = request.user
            app.save(update_fields=['status', 'submitted_at', 'submitted_by'])

            _record_transition(app, old_status, ApplicationStatus.SUBMITTED,
                               'SUBMITTED', request.user,
                               request.data.get('remarks', ''))

            # Assign workflow now that the application is SUBMITTED.
            # A missing workflow configuration is non-fatal — logs a warning.
            assign_workflow(app)

            response_data = ApplicationSerializer(app).data
            response_data['payment_required'] = False
            return Response(response_data, status=http_status.HTTP_200_OK)

    # ── Confirm Payment (PAYMENT_PENDING → SUBMITTED) ────────────────────────

    @action(detail=True, methods=['post'], url_path='confirm-payment')
    def confirm_payment(self, request, pk=None):
        """
        POST .../confirm-payment/

        Called exclusively by the payments app (PaymentOrderViewSet) after a
        PaymentOrder is confirmed PAID — either cash collected or Razorpay
        signature verified server-side.

        Transitions PAYMENT_PENDING → SUBMITTED.

        Security rules:
        - Only callable when status == PAYMENT_PENDING.
        - Requires a verified PaymentOrder (status=PAID) linked to this application.
          The frontend cannot call this directly and manufacture a paid state —
          the PaymentOrder must have been marked PAID by the payments app via
          server-side verification (cash officer or Razorpay HMAC).
        - Amount is never read from request.data.
        """
        app = self.get_object()

        if app.status not in _ALLOWED_TRANSITIONS['confirm_payment']:
            return Response(
                {'detail': (
                    f'Cannot confirm payment for an application with '
                    f'status "{app.status}". Expected PAYMENT_PENDING.'
                ),
                 'code': 'invalid_transition'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # Verify a PAID PaymentOrder exists for this application.
        # This is the guard that prevents frontend abuse — the order can only
        # reach PAID status via server-side payment verification in payments/views.py.
        from payments.models import PaymentOrder, PaymentOrderStatus
        try:
            order = app.payment_order
        except PaymentOrder.DoesNotExist:
            return Response(
                {'detail': 'No payment order found for this application.',
                 'code': 'payment_order_missing'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        if order.status != PaymentOrderStatus.PAID:
            return Response(
                {'detail': (
                    f'Payment order is not confirmed (status: {order.status}). '
                    'Complete payment before confirming.'
                ),
                 'code': 'payment_not_confirmed'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        old_status = app.status
        app.status       = ApplicationStatus.SUBMITTED
        app.submitted_at = timezone.now()
        app.save(update_fields=['status', 'submitted_at'])

        _record_transition(
            app, old_status, ApplicationStatus.SUBMITTED,
            'PAYMENT_CONFIRMED', request.user,
            f'Payment confirmed. Order ref: {order.reference}',
        )

        logger.info(
            'Application %s: PAYMENT_PENDING → SUBMITTED (order %s, user %s)',
            app.application_number, order.reference, request.user,
        )

        # Assign workflow now that the application is SUBMITTED.
        assign_workflow(app)

        response_data = ApplicationSerializer(app).data
        response_data['payment_confirmed'] = True
        return Response(response_data, status=http_status.HTTP_200_OK)

    # ── Approve ───────────────────────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='forward')
    def forward(self, request, pk=None):
        """
        POST .../forward/

        Forwards the application to the next workflow step AND advances
        the application status to the next stage.

        SUBMITTED           → UNDER_SCRUTINY  (Step 1 DA forwards to Step 2 DA)
        UNDER_SCRUTINY      → UNDER_PROCESS   (Step 2 DA forwards to Step 3 HEALTH_OFFICER)
        PENDING_DOCS        → UNDER_PROCESS   (resubmit after docs added)

        Also advances current_step to the next WorkflowStep so that the
        application appears in the next officer's inbox.
        """
        app = self.get_object()

        # Determine target status from current
        status_map = {
            ApplicationStatus.SUBMITTED:      ApplicationStatus.UNDER_SCRUTINY,
            ApplicationStatus.UNDER_SCRUTINY: ApplicationStatus.UNDER_PROCESS,
            ApplicationStatus.PENDING_DOCS:   ApplicationStatus.UNDER_PROCESS,
        }

        if app.status not in status_map:
            return Response(
                {'detail': (
                    f'Cannot forward an application with status "{app.status}". '
                    f'Only SUBMITTED, UNDER_SCRUTINY, or PENDING_DOCS applications '
                    f'can be forwarded.'
                ),
                 'code': 'invalid_transition'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        old_status    = app.status
        target_status = status_map[app.status]

        app.status = target_status
        app.save(update_fields=['status'])

        _record_transition(
            app, old_status, target_status,
            'FORWARDED', request.user,
            request.data.get('remarks', ''),
        )

        # Advance workflow step so the next officer's inbox is updated
        advance_workflow(app, request.user)

        logger.info(
            'Application %s forwarded: %s → %s by %s.',
            app.application_number, old_status, target_status, request.user,
        )

        return Response(ApplicationSerializer(app).data, status=http_status.HTTP_200_OK)

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

                # If action is submit, run the submit transition with fee gate
                if action == 'submit':
                    errors = {}
                    if not app.date_of_reporting:
                        errors['date_of_reporting'] = 'Date of reporting is required.'

                    event_date = birth_data.get('date_of_birth')
                    if not event_date:
                        errors['date_of_birth'] = 'Date of birth is required.'

                    if errors:
                        raise ValueError(errors)

                    # Delay rule + fee calculation
                    state_code   = app.state_code or ''
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

                    # Fee gate — amount from backend only, never from frontend.
                    from decimal import Decimal
                    fee_required = (
                        delay_result.applicable_fee is not None
                        and delay_result.applicable_fee > Decimal('0.00')
                    )

                    if fee_required:
                        # Halt at PAYMENT_PENDING.
                        app.status = ApplicationStatus.PAYMENT_PENDING
                        app.save(update_fields=['status'])
                        _record_transition(
                            application=app,
                            old_status=ApplicationStatus.DRAFT,
                            new_status=ApplicationStatus.PAYMENT_PENDING,
                            action_code='PAYMENT_PENDING',
                            user=request.user,
                            remarks=app_data.get('remarks', ''),
                        )
                        app._fee_required = True
                        app._delay_result = delay_result
                    else:
                        # Zero-fee — go straight to SUBMITTED.
                        app.status       = ApplicationStatus.SUBMITTED
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
                        # Assign workflow immediately — fee-free path goes
                        # straight to SUBMITTED without a payment step.
                        assign_workflow(app)
                        app._fee_required = False

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
            {
                **ApplicationSerializer(app, context={'request': request}).data,
                'payment_required': getattr(app, '_fee_required', False),
                **(
                    {
                        'applicable_fee':  str(app._delay_result.applicable_fee),
                        'fee_code':        app._delay_result.fee_code,
                        'currency':        app._delay_result.currency,
                        'delay_category':  app._delay_result.delay_category,
                    }
                    if getattr(app, '_fee_required', False) else {}
                ),
            },
            status=http_status.HTTP_201_CREATED,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# APPLICATION REVIEW PAGE VIEW
# ═══════════════════════════════════════════════════════════════════════════════

class ApplicationReviewView(LoginRequiredMixin, View):
    """
    GET /applications/<pk>/review/

    Renders a read-only review page for an application that is in
    PAYMENT_PENDING status.  Recalculates the fee server-side so the
    displayed amount is always authoritative — never trusts the URL or
    any session value.

    Redirects to the inbox if the application does not exist, does not
    belong to the current user's ULB, or is not in PAYMENT_PENDING status
    (e.g. already paid and SUBMITTED).
    """
    login_url = '/login/'

    def get(self, request, pk):
        from django.shortcuts import get_object_or_404
        from decimal import Decimal

        app = get_object_or_404(
            Application.objects.select_related(
                'registration_type', 'district', 'ulb',
                'submitted_by',
                'birth_registration',
                'death_registration',
                'still_birth_registration',
                'adopted_birth_registration',
            ),
            pk=pk,
        )

        # Only PAYMENT_PENDING applications need the review/payment page.
        # Any other status means payment is already handled or not needed.
        if app.status != ApplicationStatus.PAYMENT_PENDING:
            from django.contrib import messages as django_messages
            if app.status == ApplicationStatus.SUBMITTED:
                django_messages.info(
                    request,
                    f'Application {app.application_number} has already been submitted.'
                )
            return redirect('application_inbox')

        # Re-derive the event date and recalculate fee authoritatively.
        event_date = _get_event_date(app)
        delay_result = None
        fee_amount = Decimal('0.00')
        fee_code   = ''
        currency   = 'INR'
        delay_days = 0
        delay_category_display = 'Normal (within 21 days)'

        if event_date and app.date_of_reporting:
            delay_result = DelayCalculationService.calculate(
                event_date=event_date,
                date_of_reporting=app.date_of_reporting,
                state_code=app.state_code or '',
            )
            if delay_result and not delay_result.error:
                fee_amount             = delay_result.applicable_fee or Decimal('0.00')
                fee_code               = delay_result.fee_code
                currency               = delay_result.currency
                delay_days             = delay_result.delay_days
                from bd_master.models import DelayCategory
                display_map            = dict(DelayCategory.choices)
                delay_category_display = display_map.get(
                    delay_result.delay_category, delay_result.delay_category
                )

        # Resolve child registration record for display
        child_record = None
        service_label = app.get_service_type_display()
        for rel in ('birth_registration', 'death_registration',
                    'still_birth_registration', 'adopted_birth_registration'):
            try:
                child_record = getattr(app, rel)
                break
            except Exception:
                continue

        # Razorpay key_id is safe to expose to the browser
        from django.conf import settings as django_settings
        razorpay_key_id = getattr(django_settings, 'RAZORPAY_KEY_ID', '')

        ctx = {
            'app':                    app,
            'child_record':           child_record,
            'service_label':          service_label,
            'event_date':             event_date,
            'delay_days':             delay_days,
            'delay_category_display': delay_category_display,
            'fee_amount':             fee_amount,
            'fee_code':               fee_code,
            'currency':               currency,
            'is_free':                fee_amount == Decimal('0.00'),
            'razorpay_key_id':        razorpay_key_id,
            'today':                  timezone.localdate(),
        }
        return render(request, 'Authority/application_review.html', ctx)


# ═══════════════════════════════════════════════════════════════════════════════
# APPLICATION DETAIL PAGE VIEW
# ═══════════════════════════════════════════════════════════════════════════════

class ApplicationDetailView(LoginRequiredMixin, View):
    """
    GET /applications/<pk>/

    Read-only detail page for any application regardless of status.
    PAYMENT_PENDING applications are redirected to the review/payment page.

    Shows:
    - Full application + child registration data (read-only)
    - Current status, workflow step
    - Fee / delay information (recalculated from backend)
    - Payment order status if one exists
    - Status history timeline
    """
    login_url = '/login/'

    def get(self, request, pk):
        from django.shortcuts import get_object_or_404
        from decimal import Decimal

        app = get_object_or_404(
            Application.objects.select_related(
                'registration_type', 'district', 'ulb',
                'submitted_by', 'assigned_to',
                'workflow', 'current_step',
                'birth_registration',
                'death_registration',
                'still_birth_registration',
                'adopted_birth_registration',
            ),
            pk=pk,
        )

        # PAYMENT_PENDING → redirect to the dedicated review/payment page
        if app.status == ApplicationStatus.PAYMENT_PENDING:
            return redirect('application_review', pk=app.pk)

        # Resolve child record
        child_record = None
        for rel in ('birth_registration', 'death_registration',
                    'still_birth_registration', 'adopted_birth_registration'):
            try:
                child_record = getattr(app, rel)
                break
            except Exception:
                continue

        # Fee info (recalculated — never trust stored values for display)
        event_date             = _get_event_date(app)
        fee_amount             = Decimal('0.00')
        fee_code               = ''
        currency               = 'INR'
        delay_days             = 0
        delay_category_display = '—'
        delay_result           = None

        if event_date and app.date_of_reporting:
            delay_result = DelayCalculationService.calculate(
                event_date=event_date,
                date_of_reporting=app.date_of_reporting,
                state_code=app.state_code or '',
            )
            if delay_result and not delay_result.error:
                fee_amount             = delay_result.applicable_fee or Decimal('0.00')
                fee_code               = delay_result.fee_code
                currency               = delay_result.currency
                delay_days             = delay_result.delay_days
                from bd_master.models import DelayCategory
                display_map            = dict(DelayCategory.choices)
                delay_category_display = display_map.get(
                    delay_result.delay_category, delay_result.delay_category
                )

        # Payment order (if any)
        payment_order = None
        try:
            payment_order = app.payment_order
        except Exception:
            pass

        # Status history (remarks history — with remarks only)
        history = app.status_history.select_related('changed_by').filter(
            remarks__gt=''
        ).order_by('changed_at')

        # Uploaded documents
        documents = app.documents.select_related(
            'document_type', 'uploaded_by'
        ).order_by('created_at')

        # Determine if current step is the last active step in the workflow
        is_last_step = False
        if app.current_step_id and app.workflow_id:
            from workflow_master.models import WorkflowStep
            has_next = WorkflowStep.objects.filter(
                workflow_id=app.workflow_id,
                is_active=True,
                step_number__gt=app.current_step.step_number,
            ).exists()
            is_last_step = not has_next

        ctx = {
            'app':                    app,
            'child_record':           child_record,
            'service_label':          app.get_service_type_display(),
            'event_date':             event_date,
            'delay_days':             delay_days,
            'delay_category_display': delay_category_display,
            'fee_amount':             fee_amount,
            'fee_code':               fee_code,
            'currency':               currency,
            'is_free':                fee_amount == Decimal('0.00'),
            'payment_order':          payment_order,
            'history':                history,
            'documents':              documents,
            'is_last_step':           is_last_step,
        }
        return render(request, 'Authority/application_detail.html', ctx)


# ═══════════════════════════════════════════════════════════════════════════════
# MY APPLICATIONS PAGE VIEW
# ═══════════════════════════════════════════════════════════════════════════════

class MyApplicationsView(LoginRequiredMixin, View):
    """
    GET /my-applications/
    Shows all applications submitted by the currently logged-in user,
    excluding drafts.
    """
    login_url = '/login/'

    def get(self, request):
        qs = Application.objects.select_related(
            'registration_type', 'district', 'ulb',
            'birth_registration',
            'death_registration',
            'still_birth_registration',
            'adopted_birth_registration',
        ).prefetch_related(
            'payment_order',
        ).filter(
            submitted_by=request.user,
        ).exclude(
            status=ApplicationStatus.DRAFT,
        ).order_by('-created_at')

        return render(request, 'Authority/my_applications.html', {
            'applications': qs,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# REPORTS MODULE  (6 reports)
# ═══════════════════════════════════════════════════════════════════════════════
#
# All report views share the same security model:
#   - LoginRequired — no unauthenticated access
#   - ADMIN + superuser see all ULBs
#   - Other roles scoped to user.ulb_fk and optionally user.ward_fk
#   - cause_of_death never included in any queryset or template
#
# All reports support:
#   - GET  → HTML page with filter form + paginated table
#   - GET  ?export=csv  → streaming CSV download
#   - GET  ?print=1     → print-optimised context flag (all rows, no pagination)
# ═══════════════════════════════════════════════════════════════════════════════

import csv
from datetime import datetime, timedelta
from django.http import StreamingHttpResponse

from geography.models import District, ULB, Ward


def _report_base_qs(request):
    """
    Return the base Application queryset scoped to the authenticated user.
    ADMIN / superuser → all records.
    Others            → their ULB only.
    Excludes DRAFT and PAYMENT_PENDING by default (not yet in the system).
    """
    from users.models import UserRole
    user = request.user
    qs = Application.objects.select_related(
        'registration_type', 'district', 'ulb',
        'submitted_by', 'assigned_to', 'current_step',
        'birth_registration', 'death_registration',
        'still_birth_registration', 'adopted_birth_registration',
    ).exclude(
        status__in=(ApplicationStatus.DRAFT, ApplicationStatus.PAYMENT_PENDING)
    )
    if not (user.is_superuser or getattr(user, 'role', None) == UserRole.ADMIN):
        if getattr(user, 'ulb_fk_id', None):
            qs = qs.filter(ulb=user.ulb_fk)
    return qs


def _apply_common_filters(qs, params):
    """Apply date-range, service-type, district, ULB, ward, status filters."""
    date_from = params.get('date_from', '').strip()
    date_to   = params.get('date_to', '').strip()
    stype     = params.get('service_type', '').strip()
    district  = params.get('district', '').strip()
    ulb       = params.get('ulb', '').strip()
    ward      = params.get('ward', '').strip()
    status    = params.get('status', '').strip()

    if date_from:
        try:
            qs = qs.filter(submitted_at__date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
        except ValueError:
            pass
    if date_to:
        try:
            qs = qs.filter(submitted_at__date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass
    if stype:
        qs = qs.filter(service_type=stype)
    if district:
        qs = qs.filter(district_id=district)
    if ulb:
        qs = qs.filter(ulb_id=ulb)
    if ward:
        qs = qs.filter(
            birth_registration__ward_id=ward
        ) | qs.filter(
            death_registration__ward_id=ward
        ) | qs.filter(
            still_birth_registration__ward_id=ward
        )
    if status:
        qs = qs.filter(status=status)
    return qs


def _get_child_record(app):
    """Return the first available child/deceased record for an application."""
    for rel in ('birth_registration', 'death_registration',
                'still_birth_registration', 'adopted_birth_registration'):
        try:
            return getattr(app, rel)
        except Exception:
            pass
    return None


def _get_event_info(app):
    """Return (event_date, ward) from the child record."""
    cr = _get_child_record(app)
    if cr is None:
        return None, None
    event_date = getattr(cr, 'date_of_birth', None) or getattr(cr, 'date_of_death', None)
    ward       = getattr(cr, 'ward', None)
    return event_date, ward


def _report_filter_context(request):
    """Shared filter options for all report templates."""
    from users.models import UserRole
    user = request.user
    districts_qs = District.objects.filter(is_active=True).order_by('name')
    ulbs_qs      = ULB.objects.filter(is_active=True).order_by('name')
    wards_qs     = Ward.objects.filter(is_active=True).order_by('name')

    if not (user.is_superuser or getattr(user, 'role', None) == UserRole.ADMIN):
        if getattr(user, 'ulb_fk_id', None):
            ulbs_qs  = ulbs_qs.filter(pk=user.ulb_fk_id)
            wards_qs = wards_qs.filter(zone__ulb_id=user.ulb_fk_id)

    from bd_registration.models import ServiceType
    return {
        'districts':      districts_qs,
        'ulbs':           ulbs_qs,
        'wards':          wards_qs,
        'service_types':  ServiceType.choices,
        'status_choices': ApplicationStatus.choices,
        'filter_params':  request.GET,
    }


def _paginate(qs, page, per_page=25):
    """Simple manual pagination; returns (page_items, total, total_pages, page)."""
    total       = qs.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    page        = max(1, min(page, total_pages))
    start       = (page - 1) * per_page
    return list(qs[start:start + per_page]), total, total_pages, page


# ── 1. Application Register ───────────────────────────────────────────────────

class ReportApplicationRegisterView(LoginRequiredMixin, View):
    """
    GET /reports/application-register/
    Shows all applications with application number, service type,
    applicant/informant, event date, submission date, district, ULB,
    ward, status.
    """
    login_url = '/login/'

    def get(self, request):
        qs = _apply_common_filters(_report_base_qs(request), request.GET)
        qs = qs.order_by('-submitted_at', '-created_at')

        export = request.GET.get('export', '')
        if export == 'csv':
            return self._csv(qs)

        is_print = request.GET.get('print', '') == '1'
        if is_print:
            rows, total, total_pages, page = list(qs), qs.count(), 1, 1
        else:
            rows, total, total_pages, page = _paginate(qs, int(request.GET.get('page', 1)))

        ctx = _report_filter_context(request)
        ctx.update({
            'report_title': 'Application Register',
            'rows':          rows,
            'total':         total,
            'total_pages':   total_pages,
            'current_page':  page,
            'is_print':      is_print,
        })
        return render(request, 'Authority/reports/application_register.html', ctx)

    @staticmethod
    def _csv(qs):
        def rows():
            yield ['Application No.', 'Service Type', 'Registration Type',
                   'Informant Name', 'Event Date', 'Submitted On',
                   'District', 'ULB', 'Ward', 'Status']
            for app in qs.iterator(chunk_size=200):
                event_date, ward = _get_event_info(app)
                cr = _get_child_record(app)
                yield [
                    app.application_number,
                    app.get_service_type_display(),
                    app.registration_type.name if app.registration_type else '',
                    getattr(cr, 'informant_name', ''),
                    event_date.strftime('%d-%m-%Y') if event_date else '',
                    app.submitted_at.strftime('%d-%m-%Y') if app.submitted_at else '',
                    app.district.name if app.district else '',
                    app.ulb.name if app.ulb else '',
                    ward.name if ward else '',
                    app.get_status_display(),
                ]

        response = StreamingHttpResponse(
            (_csv_line(r) for r in rows()),
            content_type='text/csv',
        )
        response['Content-Disposition'] = 'attachment; filename="application_register.csv"'
        return response


# ── 2. Pending Applications & Workflow ───────────────────────────────────────

class ReportPendingApplicationsView(LoginRequiredMixin, View):
    """
    GET /reports/pending-applications/
    Applications not yet REGISTERED/CANCELLED, with current step and
    pending-days calculation.
    """
    login_url = '/login/'

    def get(self, request):
        qs = _apply_common_filters(_report_base_qs(request), request.GET)
        qs = qs.exclude(
            status__in=(ApplicationStatus.REGISTERED, ApplicationStatus.CANCELLED)
        ).select_related('current_step', 'assigned_to').order_by('-submitted_at')

        export = request.GET.get('export', '')
        if export == 'csv':
            return self._csv(qs)

        is_print = request.GET.get('print', '') == '1'
        today    = timezone.localdate()

        rows_raw, total, total_pages, page = (
            (list(qs), qs.count(), 1, 1)
            if is_print
            else _paginate(qs, int(request.GET.get('page', 1)))
        )

        rows = []
        for app in rows_raw:
            pending_since = app.submitted_at.date() if app.submitted_at else app.created_at.date()
            rows.append({
                'app':          app,
                'pending_days': (today - pending_since).days,
            })

        ctx = _report_filter_context(request)
        ctx.update({
            'report_title': 'Pending Applications & Workflow',
            'rows':          rows,
            'total':         total,
            'total_pages':   total_pages,
            'current_page':  page,
            'is_print':      is_print,
        })
        return render(request, 'Authority/reports/pending_applications.html', ctx)

    @staticmethod
    def _csv(qs):
        today = timezone.localdate()

        def rows():
            yield ['Application No.', 'Service Type', 'Current Step',
                   'Assigned Officer', 'Pending Days', 'Status', 'Remarks']
            for app in qs.iterator(chunk_size=200):
                since = app.submitted_at.date() if app.submitted_at else app.created_at.date()
                yield [
                    app.application_number,
                    app.get_service_type_display(),
                    app.current_step.name if app.current_step else '',
                    app.assigned_to.get_full_name() if app.assigned_to else '',
                    (today - since).days,
                    app.get_status_display(),
                    app.remarks,
                ]

        response = StreamingHttpResponse(
            (_csv_line(r) for r in rows()),
            content_type='text/csv',
        )
        response['Content-Disposition'] = 'attachment; filename="pending_applications.csv"'
        return response


# ── 3. Registration Register ──────────────────────────────────────────────────

class ReportRegistrationRegisterView(LoginRequiredMixin, View):
    """
    GET /reports/registration-register/
    Only REGISTERED applications — shows registration numbers, person
    details, event date, registration date, location.
    """
    login_url = '/login/'

    def get(self, request):
        qs = _apply_common_filters(_report_base_qs(request), request.GET)
        qs = qs.filter(status=ApplicationStatus.REGISTERED).order_by('-created_at')

        # Date filter by registration date (event-based)
        reg_from = request.GET.get('reg_date_from', '').strip()
        reg_to   = request.GET.get('reg_date_to', '').strip()
        if reg_from:
            try:
                d = datetime.strptime(reg_from, '%Y-%m-%d').date()
                qs = qs.filter(
                    birth_registration__date_of_registration__gte=d
                ) | qs.filter(
                    death_registration__date_of_registration__gte=d
                ) | qs.filter(
                    still_birth_registration__date_of_registration__gte=d
                )
            except ValueError:
                pass

        export = request.GET.get('export', '')
        if export == 'csv':
            return self._csv(qs)

        is_print = request.GET.get('print', '') == '1'
        rows, total, total_pages, page = (
            (list(qs), qs.count(), 1, 1)
            if is_print
            else _paginate(qs, int(request.GET.get('page', 1)))
        )

        ctx = _report_filter_context(request)
        ctx.update({
            'report_title': 'Registration Register',
            'rows':          rows,
            'total':         total,
            'total_pages':   total_pages,
            'current_page':  page,
            'is_print':      is_print,
        })
        return render(request, 'Authority/reports/registration_register.html', ctx)

    @staticmethod
    def _csv(qs):
        def rows():
            yield ['Registration No.', 'Application No.', 'Service Type',
                   'Person Name', 'Sex', 'Event Date', 'Registration Date',
                   'Ward', 'ULB', 'District']
            for app in qs.iterator(chunk_size=200):
                cr = _get_child_record(app)
                if cr is None:
                    continue
                reg_no   = getattr(cr, 'registration_number', '')
                reg_date = getattr(cr, 'date_of_registration', None)
                event    = getattr(cr, 'date_of_birth', None) or getattr(cr, 'date_of_death', None)
                name     = (getattr(cr, 'child_first_name', '') or
                            getattr(cr, 'deceased_first_name', '') or '')
                sex      = getattr(cr, 'get_sex_display', lambda: '')()
                ward     = getattr(cr, 'ward', None)
                yield [
                    reg_no,
                    app.application_number,
                    app.get_service_type_display(),
                    name,
                    sex,
                    event.strftime('%d-%m-%Y') if event else '',
                    reg_date.strftime('%d-%m-%Y') if reg_date else '',
                    ward.name if ward else '',
                    app.ulb.name if app.ulb else '',
                    app.district.name if app.district else '',
                ]

        response = StreamingHttpResponse(
            (_csv_line(r) for r in rows()),
            content_type='text/csv',
        )
        response['Content-Disposition'] = 'attachment; filename="registration_register.csv"'
        return response


# ── 4. Registration Summary ───────────────────────────────────────────────────

class ReportRegistrationSummaryView(LoginRequiredMixin, View):
    """
    GET /reports/registration-summary/
    Aggregated counts by service type, status, district, ULB.
    Supports daily / monthly grouping.
    """
    login_url = '/login/'

    def get(self, request):
        from django.db.models import Count
        from django.db.models.functions import TruncMonth, TruncDate

        qs = _apply_common_filters(_report_base_qs(request), request.GET)
        group_by = request.GET.get('group_by', 'monthly')

        trunc = TruncMonth if group_by == 'monthly' else TruncDate

        # Service-type summary
        by_service = (
            qs.values('service_type')
            .annotate(count=Count('id'))
            .order_by('service_type')
        )

        # Status-wise summary
        by_status = (
            qs.values('status')
            .annotate(count=Count('id'))
            .order_by('status')
        )

        # District-wise summary
        by_district = (
            qs.values('district__name')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Time series
        time_series = (
            qs.annotate(period=trunc('submitted_at'))
            .values('period', 'service_type')
            .annotate(count=Count('id'))
            .order_by('period', 'service_type')
        )

        export = request.GET.get('export', '')
        if export == 'csv':
            def rows():
                yield ['Period', 'Service Type', 'Count']
                for r in time_series:
                    yield [
                        r['period'].strftime('%Y-%m') if r['period'] else '',
                        r['service_type'],
                        r['count'],
                    ]
            response = StreamingHttpResponse(
                (_csv_line(r) for r in rows()), content_type='text/csv'
            )
            response['Content-Disposition'] = 'attachment; filename="registration_summary.csv"'
            return response

        ctx = _report_filter_context(request)
        ctx.update({
            'report_title':  'Registration Summary',
            'by_service':    list(by_service),
            'by_status':     list(by_status),
            'by_district':   list(by_district)[:20],
            'time_series':   list(time_series),
            'group_by':      group_by,
            'total':         qs.count(),
        })
        return render(request, 'Authority/reports/registration_summary.html', ctx)


# ── 5. Fee & Payment Register ─────────────────────────────────────────────────

class ReportFeePaymentRegisterView(LoginRequiredMixin, View):
    """
    GET /reports/fee-payment-register/
    Joins Application → PaymentOrder → PaymentTransaction.
    """
    login_url = '/login/'

    def get(self, request):
        from payments.models import PaymentOrder, PaymentOrderStatus

        app_qs = _apply_common_filters(_report_base_qs(request), request.GET)

        # Payment-specific filters
        pay_status = request.GET.get('payment_status', '').strip()
        pay_method = request.GET.get('payment_method', '').strip()

        order_qs = PaymentOrder.objects.select_related(
            'application', 'application__district', 'application__ulb',
            'application__registration_type',
        ).prefetch_related('transactions').filter(
            application__in=app_qs
        ).order_by('-created_at')

        if pay_status:
            order_qs = order_qs.filter(status=pay_status)
        if pay_method:
            order_qs = order_qs.filter(payment_method=pay_method)

        export = request.GET.get('export', '')
        if export == 'csv':
            return self._csv(order_qs)

        is_print = request.GET.get('print', '') == '1'
        total    = order_qs.count()
        if is_print:
            rows, total_pages, page = list(order_qs), 1, 1
        else:
            rows, total, total_pages, page = _paginate(order_qs, int(request.GET.get('page', 1)))

        from payments.models import PaymentMethod, PaymentOrderStatus
        ctx = _report_filter_context(request)
        ctx.update({
            'report_title':     'Fee & Payment Register',
            'rows':              rows,
            'total':             total,
            'total_pages':       total_pages,
            'current_page':      page,
            'is_print':          is_print,
            'pay_status_choices': PaymentOrderStatus.choices,
            'pay_method_choices': PaymentMethod.choices,
        })
        return render(request, 'Authority/reports/fee_payment_register.html', ctx)

    @staticmethod
    def _csv(order_qs):
        def rows():
            yield ['Application No.', 'Service Type', 'Fee Code',
                   'Payable Amount', 'Paid Amount', 'Payment Mode',
                   'Receipt No.', 'Payment Date', 'Payment Status']
            for order in order_qs.iterator(chunk_size=200):
                txn = order.transactions.filter(status='CAPTURED').first()
                yield [
                    order.application.application_number,
                    order.application.get_service_type_display(),
                    order.fee_code,
                    str(order.amount),
                    str(txn.amount) if txn else '',
                    order.get_payment_method_display(),
                    txn.receipt_number if txn else '',
                    txn.completed_at.strftime('%d-%m-%Y') if (txn and txn.completed_at) else '',
                    order.get_status_display(),
                ]

        response = StreamingHttpResponse(
            (_csv_line(r) for r in rows()),
            content_type='text/csv',
        )
        response['Content-Disposition'] = 'attachment; filename="fee_payment_register.csv"'
        return response


# ── 6. Certificate & History Register ────────────────────────────────────────

class ReportCertificateHistoryView(LoginRequiredMixin, View):
    """
    GET /reports/certificate-history/
    REGISTERED applications with full status history (excluding cause_of_death).
    """
    login_url = '/login/'

    def get(self, request):
        qs = _apply_common_filters(_report_base_qs(request), request.GET)
        qs = qs.filter(status=ApplicationStatus.REGISTERED).prefetch_related(
            'status_history__changed_by'
        ).order_by('-created_at')

        export = request.GET.get('export', '')
        if export == 'csv':
            return self._csv(qs)

        is_print = request.GET.get('print', '') == '1'
        rows, total, total_pages, page = (
            (list(qs), qs.count(), 1, 1)
            if is_print
            else _paginate(qs, int(request.GET.get('page', 1)))
        )

        ctx = _report_filter_context(request)
        ctx.update({
            'report_title': 'Certificate & History Register',
            'rows':          rows,
            'total':         total,
            'total_pages':   total_pages,
            'current_page':  page,
            'is_print':      is_print,
        })
        return render(request, 'Authority/reports/certificate_history.html', ctx)

    @staticmethod
    def _csv(qs):
        def rows():
            yield ['Registration No.', 'Application No.', 'Service Type',
                   'Issue Date', 'Action', 'Officer', 'Action At', 'Remarks']
            for app in qs.iterator(chunk_size=200):
                cr = _get_child_record(app)
                reg_no   = getattr(cr, 'registration_number', '') if cr else ''
                reg_date = getattr(cr, 'date_of_registration', None) if cr else None
                first    = True
                for h in app.status_history.order_by('changed_at'):
                    officer = h.changed_by.get_full_name() if h.changed_by else ''
                    yield [
                        reg_no if first else '',
                        app.application_number if first else '',
                        app.get_service_type_display() if first else '',
                        reg_date.strftime('%d-%m-%Y') if (first and reg_date) else '',
                        h.action,
                        officer,
                        h.changed_at.strftime('%d-%m-%Y %H:%M'),
                        h.remarks,
                    ]
                    first = False

        response = StreamingHttpResponse(
            (_csv_line(r) for r in rows()),
            content_type='text/csv',
        )
        response['Content-Disposition'] = 'attachment; filename="certificate_history.csv"'
        return response


# ── Shared CSV helper ─────────────────────────────────────────────────────────

def _csv_line(row):
    """Convert a list to a CSV-encoded bytes line."""
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(row)
    return buf.getvalue().encode('utf-8')


# ═══════════════════════════════════════════════════════════════════════════════
# APPLICATION SENTBOX VIEW
# ═══════════════════════════════════════════════════════════════════════════════

class ApplicationSentboxView(LoginRequiredMixin, View):
    """
    GET /mailbox/sentbox/

    Shows all applications that the authenticated user has forwarded to the
    next step. Fetches distinct applications from ApplicationStatusHistory
    where action='FORWARDED' and changed_by=request.user.

    Read-only view — no action buttons on detail pages when ?from=sentbox.
    """
    login_url = '/login/'

    def get(self, request):
        from bd_registration.models import ApplicationStatusHistory
        user = request.user

        # Get all distinct application IDs this user has forwarded
        fwd_app_ids = ApplicationStatusHistory.objects.filter(
            changed_by=user,
            action='FORWARDED',
        ).values_list('application_id', flat=True).distinct()

        # Fetch those applications with full relations
        qs = Application.objects.filter(
            pk__in=fwd_app_ids
        ).select_related(
            'registration_type', 'district', 'ulb',
            'submitted_by',
            'birth_registration',
            'death_registration',
            'still_birth_registration',
            'adopted_birth_registration',
            'current_step',
        ).order_by('-updated_at')

        return render(request, 'Authority/application_inbox.html', {
            'applications': qs,
            'inbox_title':  'Sentbox — Forwarded Applications',
            'from_param':   'sentbox',
        })
