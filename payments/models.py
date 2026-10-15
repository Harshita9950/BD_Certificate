"""
payments/models.py
==================
Payment data models for the Municipal Birth & Death Certificate System.

Design rules
------------
1. The fee amount is ALWAYS sourced from the backend (DelayCalculationService +
   FeeMaster). It is calculated at PaymentOrder creation time and stored here.
   No frontend-supplied amount is ever trusted or used.

2. Two-table design:
   - PaymentOrder  — one per Application, records what is owed, the payment
                     method chosen and the gateway order reference.
   - PaymentTransaction — one per payment attempt/event; records what actually
                     happened (Razorpay callback or officer cash collection).
     An Order can have multiple Transactions (retries, partial failures), but
     only one can be CAPTURED/VERIFIED.

3. Idempotency:
   - PaymentOrder.application is OneToOne: one order per application.
   - PaymentOrder.razorpay_order_id has db_index + unique (when non-blank) via
     a DB partial unique index (enforced in the model's Meta.constraints).
   - PaymentTransaction.razorpay_payment_id is unique when non-blank.

4. Cash payments do not use Razorpay fields; online payments do not use
   receipt_number. Both paths share the same models.

5. No Razorpay key/secret is stored here. Keys live in settings.py,
   loaded from .env.

6. This app imports from bd_registration.Application but does NOT import
   from trade_master or any other non-BD module.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


# ─── Payment Method ───────────────────────────────────────────────────────────

class PaymentMethod(models.TextChoices):
    CASH   = 'CASH',   _('Cash')
    ONLINE = 'ONLINE', _('Online (Razorpay)')


# ─── Payment Order Status ─────────────────────────────────────────────────────

class PaymentOrderStatus(models.TextChoices):
    PENDING   = 'PENDING',   _('Pending')          # Created, awaiting payment
    PAID      = 'PAID',      _('Paid')              # Confirmed — cash collected or Razorpay verified
    FAILED    = 'FAILED',    _('Failed')            # Razorpay payment failed / expired
    CANCELLED = 'CANCELLED', _('Cancelled')         # Voided before payment (e.g. application cancelled)
    REFUNDED  = 'REFUNDED',  _('Refunded')          # Post-payment refund (future use)


# ─── Payment Transaction Status ──────────────────────────────────────────────

class PaymentTransactionStatus(models.TextChoices):
    INITIATED  = 'INITIATED',  _('Initiated')       # Order sent to gateway / cash started
    CAPTURED   = 'CAPTURED',   _('Captured')        # Gateway confirmed payment
    FAILED     = 'FAILED',     _('Failed')          # Gateway reported failure
    REFUNDED   = 'REFUNDED',   _('Refunded')        # Refund processed


# ─── PaymentOrder ─────────────────────────────────────────────────────────────

class PaymentOrder(models.Model):
    """
    One PaymentOrder per Application.

    Created by the backend when the applicant reaches the payment step.
    The amount is always computed by DelayCalculationService + FeeMaster —
    never accepted from the frontend.

    For FREE registrations (amount == 0.00) a PAID order is created
    immediately with method=CASH and no transaction record needed.
    """

    # ── Idempotency reference ─────────────────────────────────────────────────
    reference = models.UUIDField(
        _('reference'),
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text=_('Immutable idempotency key. Use this to deduplicate callbacks.'),
    )

    # ── Application linkage ───────────────────────────────────────────────────
    application = models.OneToOneField(
        'bd_registration.Application',
        on_delete=models.PROTECT,
        related_name='payment_order',
        verbose_name=_('application'),
        help_text=_('Exactly one PaymentOrder per Application.'),
    )

    # ── Fee information (backend-sourced, immutable after creation) ───────────
    fee_code = models.CharField(
        _('fee code'),
        max_length=60,
        blank=True,
        default='',
        help_text=_(
            'FeeMaster.fee_code used to compute this charge. '
            'Blank for FREE (amount == 0.00) registrations.'
        ),
    )

    amount = models.DecimalField(
        _('amount'),
        max_digits=10,
        decimal_places=2,
        help_text=_(
            'Fee amount in the configured currency. '
            'Set by the backend from FeeMaster — NEVER from the frontend. '
            'Zero for FREE registrations.'
        ),
    )

    currency = models.CharField(
        _('currency'),
        max_length=3,
        default='INR',
        help_text=_('ISO 4217 currency code. Default: INR.'),
    )

    # ── Payment method ────────────────────────────────────────────────────────
    payment_method = models.CharField(
        _('payment method'),
        max_length=10,
        choices=PaymentMethod.choices,
        db_index=True,
        help_text=_('CASH or ONLINE (Razorpay). Chosen by applicant on the payment page.'),
    )

    # ── Order status ──────────────────────────────────────────────────────────
    status = models.CharField(
        _('status'),
        max_length=12,
        choices=PaymentOrderStatus.choices,
        default=PaymentOrderStatus.PENDING,
        db_index=True,
    )

    # ── Razorpay order reference (online payments only) ───────────────────────
    razorpay_order_id = models.CharField(
        _('Razorpay order ID'),
        max_length=100,
        blank=True,
        default='',
        db_index=True,
        help_text=_(
            'order_XXXXXXXXXXXXXXXXXX returned by Razorpay Orders API. '
            'Blank for cash payments.'
        ),
    )

    # ── Audit ─────────────────────────────────────────────────────────────────
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='created_payment_orders',
        verbose_name=_('created by'),
        help_text=_('Officer or system user who initiated this payment order.'),
    )

    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name        = _('Payment Order')
        verbose_name_plural = _('Payment Orders')
        ordering            = ['-created_at']
        constraints = [
            # Razorpay order IDs must be unique across all non-blank rows.
            models.UniqueConstraint(
                fields=['razorpay_order_id'],
                condition=~models.Q(razorpay_order_id=''),
                name='payments_unique_razorpay_order_id',
            ),
        ]
        indexes = [
            models.Index(fields=['status', 'payment_method']),
            models.Index(fields=['application', 'status']),
        ]

    def __str__(self):
        return (
            f'PaymentOrder #{self.pk} | '
            f'{self.application.application_number} | '
            f'₹{self.amount} | {self.status}'
        )

    @property
    def is_free(self):
        """True when no fee is charged (amount == 0)."""
        from decimal import Decimal
        return self.amount == Decimal('0.00')

    @property
    def is_paid(self):
        return self.status == PaymentOrderStatus.PAID


# ─── PaymentTransaction ───────────────────────────────────────────────────────

class PaymentTransaction(models.Model):
    """
    One record per payment attempt or event against a PaymentOrder.

    For cash: one CAPTURED transaction created by the receiving officer.
    For Razorpay: one INITIATED transaction when checkout opens; status updated
    to CAPTURED or FAILED when the gateway callback arrives.

    Only one transaction per order should reach CAPTURED status.
    This is enforced by application logic, not a DB constraint, because
    retry scenarios need multiple rows.
    """

    # ── Parent order ──────────────────────────────────────────────────────────
    payment_order = models.ForeignKey(
        PaymentOrder,
        on_delete=models.PROTECT,
        related_name='transactions',
        verbose_name=_('payment order'),
    )

    # ── Transaction status ────────────────────────────────────────────────────
    status = models.CharField(
        _('status'),
        max_length=12,
        choices=PaymentTransactionStatus.choices,
        default=PaymentTransactionStatus.INITIATED,
        db_index=True,
    )

    # ── Razorpay fields (online only) ─────────────────────────────────────────
    razorpay_payment_id = models.CharField(
        _('Razorpay payment ID'),
        max_length=100,
        blank=True,
        default='',
        db_index=True,
        help_text=_(
            'pay_XXXXXXXXXXXXXXXXXX from Razorpay. '
            'Populated on checkout.handler success.'
        ),
    )

    razorpay_signature = models.CharField(
        _('Razorpay signature'),
        max_length=255,
        blank=True,
        default='',
        help_text=_(
            'HMAC-SHA256 signature sent by Razorpay. '
            'Verified server-side before marking CAPTURED. '
            'Never trusted from frontend without server verification.'
        ),
    )

    razorpay_error_code = models.CharField(
        _('Razorpay error code'),
        max_length=100,
        blank=True,
        default='',
        help_text=_('Error code returned by Razorpay on failure, e.g. BAD_REQUEST_ERROR.'),
    )

    razorpay_error_description = models.TextField(
        _('Razorpay error description'),
        blank=True,
        default='',
    )

    # ── Cash fields (cash only) ───────────────────────────────────────────────
    receipt_number = models.CharField(
        _('receipt number'),
        max_length=50,
        blank=True,
        default='',
        db_index=True,
        help_text=_(
            'Manual cash receipt / challan number assigned by the officer. '
            'Blank for online payments.'
        ),
    )

    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='cash_collections',
        verbose_name=_('collected by'),
        help_text=_('Officer who physically received the cash. Null for online payments.'),
    )

    # ── Amount actually transacted ────────────────────────────────────────────
    # Mirrors PaymentOrder.amount at the time of transaction.
    # Stored here for audit integrity — order amount must not change after
    # a transaction is recorded.
    amount = models.DecimalField(
        _('amount'),
        max_digits=10,
        decimal_places=2,
        help_text=_('Amount actually transacted. Must equal PaymentOrder.amount.'),
    )

    currency = models.CharField(
        _('currency'),
        max_length=3,
        default='INR',
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    initiated_at = models.DateTimeField(
        _('initiated at'),
        auto_now_add=True,
    )

    completed_at = models.DateTimeField(
        _('completed at'),
        null=True,
        blank=True,
        help_text=_('When the transaction reached a terminal state (CAPTURED or FAILED).'),
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = models.TextField(
        _('notes'),
        blank=True,
        default='',
        help_text=_('Internal notes — e.g. officer remarks on cash collection.'),
    )

    class Meta:
        verbose_name        = _('Payment Transaction')
        verbose_name_plural = _('Payment Transactions')
        ordering            = ['-initiated_at']
        constraints = [
            # Razorpay payment IDs are globally unique when present.
            models.UniqueConstraint(
                fields=['razorpay_payment_id'],
                condition=~models.Q(razorpay_payment_id=''),
                name='payments_unique_razorpay_payment_id',
            ),
        ]
        indexes = [
            models.Index(fields=['payment_order', 'status']),
            models.Index(fields=['status', 'initiated_at']),
        ]

    def __str__(self):
        return (
            f'Txn #{self.pk} | '
            f'Order #{self.payment_order_id} | '
            f'{self.status} | ₹{self.amount}'
        )
