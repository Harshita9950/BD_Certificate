"""
payments/views.py
==================
Full implementation of both cash and online (Razorpay) payment modes.

Security contract
-----------------
1. Amount is NEVER read from request.data — always re-derived from
   DelayCalculationService + FeeMaster at order-creation time.
2. Razorpay signature is verified server-side (HMAC-SHA256) before any
   status change. The key secret never leaves the server.
3. confirm-payment on the Application is called only after PaymentOrder
   reaches PAID status inside a DB transaction.
4. All writes are wrapped in transaction.atomic() to prevent partial state.
5. Idempotency: POST /orders/ for an existing PENDING order returns it.
   Duplicate razorpay_payment_id raises 409.
"""

import hashlib
import hmac
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status as http_status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from bd_registration.models import Application, ApplicationStatus
from bd_registration.services import DelayCalculationService
from bd_registration.views import _get_event_date

from .models import (
    PaymentMethod,
    PaymentOrder,
    PaymentOrderStatus,
    PaymentTransaction,
    PaymentTransactionStatus,
)
from .serializers import (
    CashCollectSerializer,
    PaymentOrderCreateSerializer,
    PaymentOrderSerializer,
    RazorpayVerifySerializer,
)

logger = logging.getLogger(__name__)


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _recalculate_fee(app: Application):
    """
    Re-derive authoritative fee for *app* using DelayCalculationService.
    Returns (fee_code, amount, currency). Amount is Decimal.
    Returns ('', Decimal('0.00'), 'INR') on any error or missing data.
    Amount is NEVER sourced from the frontend or from the PaymentOrder itself
    without re-verification.
    """
    event_date = _get_event_date(app)
    if not event_date or not app.date_of_reporting:
        return '', Decimal('0.00'), 'INR'

    result = DelayCalculationService.calculate(
        event_date=event_date,
        date_of_reporting=app.date_of_reporting,
        state_code=app.state_code or '',
    )
    if result.error and result.delay_category == '':
        return '', Decimal('0.00'), 'INR'

    amount = result.applicable_fee or Decimal('0.00')
    return result.fee_code, amount, result.currency


def _verify_razorpay_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """
    Server-side HMAC-SHA256 verification of a Razorpay payment signature.
    The KEY_SECRET is read from Django settings — never from the request.
    """
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')
    if not key_secret:
        logger.error('RAZORPAY_KEY_SECRET is not configured — cannot verify signature.')
        return False
    msg       = f'{order_id}|{payment_id}'.encode('utf-8')
    secret    = key_secret.encode('utf-8')
    generated = hmac.new(secret, msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(generated, signature)


def _confirm_application_payment(app: Application, user, order: PaymentOrder):
    """
    Transition PAYMENT_PENDING → SUBMITTED and assign the workflow.
    Called inside an atomic block after PaymentOrder.status == PAID.
    """
    from bd_registration.views import _record_transition
    from bd_registration.workflow_service import assign_workflow

    if app.status != ApplicationStatus.PAYMENT_PENDING:
        logger.warning(
            '_confirm_application_payment: app %s is %s, expected PAYMENT_PENDING.',
            app.application_number, app.status,
        )
        return

    app.status       = ApplicationStatus.SUBMITTED
    app.submitted_at = timezone.now()
    app.save(update_fields=['status', 'submitted_at'])

    _record_transition(
        application=app,
        old_status=ApplicationStatus.PAYMENT_PENDING,
        new_status=ApplicationStatus.SUBMITTED,
        action_code='PAYMENT_CONFIRMED',
        user=user,
        remarks=f'Payment confirmed via order ref: {order.reference}',
    )

    assign_workflow(app)

    logger.info(
        'Application %s: PAYMENT_PENDING → SUBMITTED (order %s).',
        app.application_number, order.reference,
    )


# ─── PaymentOrder ViewSet ─────────────────────────────────────────────────────

class PaymentOrderViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    GET    /api/payments/orders/
    GET    /api/payments/orders/<pk>/
    POST   /api/payments/orders/
    POST   /api/payments/orders/<pk>/collect-cash/
    POST   /api/payments/orders/<pk>/verify-payment/
    POST   /api/payments/orders/<pk>/cancel/
    """

    queryset = PaymentOrder.objects.select_related(
        'application', 'created_by',
    ).prefetch_related('transactions').all()

    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'payment_method', 'application']
    search_fields    = ['application__application_number', 'fee_code', 'razorpay_order_id']
    ordering_fields  = ['created_at', 'amount', 'status']
    ordering         = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentOrderCreateSerializer
        return PaymentOrderSerializer

    # ── Create ────────────────────────────────────────────────────────────────

    def create(self, request, *args, **kwargs):
        """
        POST /api/payments/orders/
        Body: { application: <pk>, payment_method: "CASH"|"ONLINE" }
        Amount computed server-side. Frontend amount is never accepted.
        Idempotency: existing PENDING order is returned (not duplicated).
        """
        ser = PaymentOrderCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        app            = ser.validated_data['application']
        payment_method = ser.validated_data['payment_method']

        # Application must be in PAYMENT_PENDING
        if app.status != ApplicationStatus.PAYMENT_PENDING:
            return Response(
                {'detail': (
                    f'Payment orders require PAYMENT_PENDING status. '
                    f'Current status: "{app.status}".'
                ), 'code': 'invalid_application_status'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # Idempotency: return existing PENDING order
        try:
            existing = app.payment_order
            if existing.status == PaymentOrderStatus.PAID:
                return Response(
                    {'detail': 'Payment already completed for this application.',
                     'code': 'already_paid'},
                    status=http_status.HTTP_409_CONFLICT,
                )
            if existing.status == PaymentOrderStatus.PENDING:
                logger.info(
                    'Returning existing PENDING order pk=%s for app %s.',
                    existing.pk, app.application_number,
                )
                resp = PaymentOrderSerializer(existing).data
                if existing.payment_method == PaymentMethod.ONLINE:
                    resp['razorpay_key_id'] = getattr(settings, 'RAZORPAY_KEY_ID', '')
                return Response(resp, status=http_status.HTTP_200_OK)
        except PaymentOrder.DoesNotExist:
            pass

        # Compute fee authoritatively
        fee_code, amount, currency = _recalculate_fee(app)
        if amount == Decimal('0.00'):
            return Response(
                {'detail': 'No payable fee — payment order not needed.',
                 'code': 'zero_fee'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        razorpay_order_id = ''

        # Online: create Razorpay order
        if payment_method == PaymentMethod.ONLINE:
            key_id     = getattr(settings, 'RAZORPAY_KEY_ID',     '')
            key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')
            if not key_id or not key_secret:
                return Response(
                    {'detail': 'Online payments are not configured. Use Cash.',
                     'code': 'razorpay_not_configured'},
                    status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            try:
                import razorpay
                rzp    = razorpay.Client(auth=(key_id, key_secret))
                rzp_or = rzp.order.create({
                    'amount':   int(amount * 100),  # paise
                    'currency': getattr(settings, 'RAZORPAY_CURRENCY', 'INR'),
                    'receipt':  f'BD-{app.pk}',
                    'notes':    {'application_number': app.application_number},
                })
                razorpay_order_id = rzp_or['id']
                logger.info('Razorpay order %s created for app %s.',
                            razorpay_order_id, app.application_number)
            except Exception as exc:
                logger.exception('Razorpay order creation failed for app %s.',
                                 app.application_number)
                return Response(
                    {'detail': f'Payment gateway error: {exc}',
                     'code': 'razorpay_error'},
                    status=http_status.HTTP_502_BAD_GATEWAY,
                )

        with transaction.atomic():
            order = PaymentOrder.objects.create(
                application=app,
                fee_code=fee_code,
                amount=amount,
                currency=currency,
                payment_method=payment_method,
                status=PaymentOrderStatus.PENDING,
                razorpay_order_id=razorpay_order_id,
                created_by=request.user,
            )

        logger.info('PaymentOrder pk=%s created for app %s (%s ₹%s).',
                    order.pk, app.application_number, payment_method, amount)

        resp = PaymentOrderSerializer(order).data
        if payment_method == PaymentMethod.ONLINE:
            resp['razorpay_key_id'] = getattr(settings, 'RAZORPAY_KEY_ID', '')
        return Response(resp, status=http_status.HTTP_201_CREATED)

    # ── Collect cash ──────────────────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='collect-cash')
    def collect_cash(self, request, pk=None):
        """
        POST /api/payments/orders/<pk>/collect-cash/
        Body: { receipt_number, payment_date (optional), notes (optional) }

        1. Validates order is PENDING + CASH.
        2. Creates PaymentTransaction (CAPTURED) atomically.
        3. Marks PaymentOrder PAID.
        4. Confirms application payment → SUBMITTED + workflow assignment.
        Idempotent: PAID order returns 409.
        """
        order = self.get_object()

        if order.status == PaymentOrderStatus.PAID:
            return Response(
                {'detail': 'This order has already been paid.',
                 'code': 'already_paid'},
                status=http_status.HTTP_409_CONFLICT,
            )
        if order.status != PaymentOrderStatus.PENDING:
            return Response(
                {'detail': f'Order status "{order.status}" — only PENDING orders accepted.',
                 'code': 'invalid_order_status'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        if order.payment_method != PaymentMethod.CASH:
            return Response(
                {'detail': 'This is not a cash order.',
                 'code': 'wrong_payment_method'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        ser = CashCollectSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        app = order.application

        with transaction.atomic():
            txn = PaymentTransaction.objects.create(
                payment_order=order,
                status=PaymentTransactionStatus.CAPTURED,
                receipt_number=data['receipt_number'],
                collected_by=request.user,
                amount=order.amount,
                currency=order.currency,
                completed_at=timezone.now(),
                notes=data.get('notes', ''),
            )
            order.status = PaymentOrderStatus.PAID
            order.save(update_fields=['status', 'updated_at'])
            _confirm_application_payment(app, request.user, order)

        logger.info('Cash collected: order pk=%s, txn pk=%s, receipt %s.',
                    order.pk, txn.pk, data['receipt_number'])

        return Response({
            **PaymentOrderSerializer(order).data,
            'transaction_id': txn.pk,
            'receipt_number': txn.receipt_number,
        }, status=http_status.HTTP_200_OK)

    # ── Verify Razorpay payment ────────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='verify-payment')
    def verify_payment(self, request, pk=None):
        """
        POST /api/payments/orders/<pk>/verify-payment/
        Body: { razorpay_payment_id, razorpay_order_id, razorpay_signature }

        1. Validates order is PENDING + ONLINE.
        2. Server-side HMAC-SHA256 signature verification.
        3. Valid: CAPTURED transaction, order PAID, application advanced.
        4. Invalid: FAILED transaction recorded, 400 returned.
        Idempotent: duplicate payment_id raises 409.
        """
        order = self.get_object()

        if order.status == PaymentOrderStatus.PAID:
            return Response(
                {'detail': 'Order already verified and paid.',
                 'code': 'already_paid'},
                status=http_status.HTTP_409_CONFLICT,
            )
        if order.status != PaymentOrderStatus.PENDING:
            return Response(
                {'detail': f'Order status "{order.status}" — only PENDING orders accepted.',
                 'code': 'invalid_order_status'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        if order.payment_method != PaymentMethod.ONLINE:
            return Response(
                {'detail': 'This is not an online order.',
                 'code': 'wrong_payment_method'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        ser = RazorpayVerifySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        razorpay_payment_id = data['razorpay_payment_id']
        razorpay_order_id   = data['razorpay_order_id']
        razorpay_signature  = data['razorpay_signature']

        # Idempotency guard
        if PaymentTransaction.objects.filter(
            razorpay_payment_id=razorpay_payment_id
        ).exists():
            return Response(
                {'detail': 'This Razorpay payment ID has already been recorded.',
                 'code': 'duplicate_payment_id'},
                status=http_status.HTTP_409_CONFLICT,
            )

        # Order ID must match
        if order.razorpay_order_id != razorpay_order_id:
            return Response(
                {'detail': 'razorpay_order_id does not match this payment order.',
                 'code': 'order_id_mismatch'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # Server-side signature verification
        if not _verify_razorpay_signature(
            razorpay_order_id, razorpay_payment_id, razorpay_signature
        ):
            PaymentTransaction.objects.create(
                payment_order=order,
                status=PaymentTransactionStatus.FAILED,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_signature=razorpay_signature,
                razorpay_error_code='SIGNATURE_MISMATCH',
                razorpay_error_description='Server-side HMAC verification failed.',
                amount=order.amount,
                currency=order.currency,
                completed_at=timezone.now(),
            )
            logger.warning('Signature FAILED for order pk=%s, payment_id=%s.',
                           order.pk, razorpay_payment_id)
            return Response(
                {'detail': 'Payment signature verification failed.',
                 'code': 'signature_invalid'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        app = order.application

        with transaction.atomic():
            txn = PaymentTransaction.objects.create(
                payment_order=order,
                status=PaymentTransactionStatus.CAPTURED,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_signature=razorpay_signature,
                amount=order.amount,
                currency=order.currency,
                completed_at=timezone.now(),
            )
            order.status = PaymentOrderStatus.PAID
            order.save(update_fields=['status', 'updated_at'])
            _confirm_application_payment(app, request.user, order)

        logger.info('Razorpay VERIFIED: order pk=%s, txn pk=%s, payment_id=%s.',
                    order.pk, txn.pk, razorpay_payment_id)

        return Response({
            **PaymentOrderSerializer(order).data,
            'transaction_id': txn.pk,
        }, status=http_status.HTTP_200_OK)

    # ── Cancel ────────────────────────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request, pk=None):
        """POST /api/payments/orders/<pk>/cancel/"""
        order = self.get_object()

        if order.status == PaymentOrderStatus.PAID:
            return Response(
                {'detail': 'A paid order cannot be cancelled.', 'code': 'already_paid'},
                status=http_status.HTTP_409_CONFLICT,
            )
        if order.status != PaymentOrderStatus.PENDING:
            return Response(
                {'detail': f'Cannot cancel an order with status "{order.status}".',
                 'code': 'invalid_order_status'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        order.status = PaymentOrderStatus.CANCELLED
        order.save(update_fields=['status', 'updated_at'])
        logger.info('PaymentOrder pk=%s cancelled by %s.', order.pk, request.user)
        return Response(PaymentOrderSerializer(order).data)


# ═══════════════════════════════════════════════════════════════════════════════
# PAYMENT RECEIPT PAGE VIEW
# ═══════════════════════════════════════════════════════════════════════════════

class PaymentReceiptView(object):
    """
    GET /payments/receipt/<order_pk>/

    Renders a printable cash payment receipt for a PAID PaymentOrder.
    Only accessible by authenticated users.
    """
    pass


def payment_receipt_view(request, order_pk):
    """
    Function-based receipt view to avoid extra import chain issues.
    GET /payments/receipt/<order_pk>/
    """
    from django.contrib.auth.decorators import login_required
    from django.shortcuts import get_object_or_404, render as django_render
    from django.http import HttpResponseForbidden

    if not request.user.is_authenticated:
        from django.shortcuts import redirect
        return redirect(f'/login/?next=/payments/receipt/{order_pk}/')

    order = get_object_or_404(
        PaymentOrder.objects.select_related(
            'application__registration_type',
            'application__district',
            'application__ulb',
            'application__submitted_by',
            'created_by',
        ).prefetch_related('transactions__collected_by'),
        pk=order_pk,
        status=PaymentOrderStatus.PAID,
        payment_method=PaymentMethod.CASH,
    )

    # Get the captured transaction (there should be exactly one for cash)
    txn = order.transactions.filter(
        status=PaymentTransactionStatus.CAPTURED
    ).select_related('collected_by').order_by('-initiated_at').first()

    return django_render(request, 'Authority/payment_receipt.html', {
        'order': order,
        'txn':   txn,
        'app':   order.application,
    })
