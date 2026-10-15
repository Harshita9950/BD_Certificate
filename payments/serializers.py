"""
payments/serializers.py
========================
Serializers for the payments app.

Rules
-----
- Amount is NEVER accepted from the frontend. It is read-only on all
  write serializers — always computed server-side from FeeMaster.
- razorpay_signature is write-only (never returned to clients).
- PaymentOrderCreateSerializer validates payment_method choice and
  delegates amount calculation to the view/service layer.
"""

from rest_framework import serializers

from .models import (
    PaymentMethod,
    PaymentOrder,
    PaymentOrderStatus,
    PaymentTransaction,
    PaymentTransactionStatus,
)


# ─── PaymentTransaction ───────────────────────────────────────────────────────

class PaymentTransactionSerializer(serializers.ModelSerializer):
    """Read-only representation of a single transaction attempt."""

    status_display = serializers.CharField(
        source='get_status_display', read_only=True
    )
    collected_by_name = serializers.SerializerMethodField()

    class Meta:
        model  = PaymentTransaction
        fields = (
            'id',
            'payment_order',
            'status',               'status_display',
            'razorpay_payment_id',
            # razorpay_signature intentionally excluded — never expose
            'razorpay_error_code',  'razorpay_error_description',
            'receipt_number',
            'collected_by',         'collected_by_name',
            'amount',               'currency',
            'initiated_at',         'completed_at',
            'notes',
        )
        read_only_fields = fields  # all read-only; writes go through dedicated endpoints

    def get_collected_by_name(self, obj):
        if obj.collected_by:
            return obj.collected_by.get_full_name() or obj.collected_by.username
        return None


# ─── PaymentOrder — read ──────────────────────────────────────────────────────

class PaymentOrderSerializer(serializers.ModelSerializer):
    """Full read representation including nested transactions."""

    status_display         = serializers.CharField(source='get_status_display',         read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    application_number     = serializers.CharField(
        source='application.application_number', read_only=True
    )
    created_by_name = serializers.SerializerMethodField()
    transactions    = PaymentTransactionSerializer(many=True, read_only=True)
    is_free         = serializers.BooleanField(read_only=True)
    is_paid         = serializers.BooleanField(read_only=True)

    class Meta:
        model  = PaymentOrder
        fields = (
            'id',
            'reference',
            'application',          'application_number',
            'fee_code',
            'amount',               'currency',
            'payment_method',       'payment_method_display',
            'status',               'status_display',
            'razorpay_order_id',
            'created_by',           'created_by_name',
            'created_at',           'updated_at',
            'is_free',              'is_paid',
            'transactions',
        )
        read_only_fields = fields

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None


# ─── PaymentOrder — create ────────────────────────────────────────────────────

class PaymentOrderCreateSerializer(serializers.Serializer):
    """
    Used by POST /api/payments/orders/.

    The frontend supplies:
      - application  (PK of the Application to pay for)
      - payment_method  (CASH or ONLINE)

    The backend computes amount from FeeMaster via DelayCalculationService.
    Amount from the frontend is explicitly rejected.
    """

    application    = serializers.PrimaryKeyRelatedField(
        queryset=__import__(
            'bd_registration.models', fromlist=['Application']
        ).Application.objects.all()
    )
    payment_method = serializers.ChoiceField(choices=PaymentMethod.choices)

    def validate_application(self, app):
        # Block if a PAID order already exists for this application
        if hasattr(app, 'payment_order'):
            existing = app.payment_order
            if existing.status == PaymentOrderStatus.PAID:
                raise serializers.ValidationError(
                    'A completed payment already exists for this application.'
                )
        return app


# ─── Cash collection ──────────────────────────────────────────────────────────

class CashCollectSerializer(serializers.Serializer):
    """
    Used by POST /api/payments/orders/<pk>/collect-cash/.
    Officer records a cash receipt against an existing PENDING cash order.
    """

    receipt_number = serializers.CharField(max_length=50)
    payment_date   = serializers.DateField(required=False, allow_null=True)
    notes          = serializers.CharField(required=False, allow_blank=True, default='')


# ─── Razorpay verify ──────────────────────────────────────────────────────────

class RazorpayVerifySerializer(serializers.Serializer):
    """
    Used by POST /api/payments/orders/<pk>/verify-payment/.

    The frontend sends the three fields Razorpay provides in checkout.handler.
    Signature verification is done server-side — the signature value is
    write-only and never returned.
    """

    razorpay_payment_id = serializers.CharField(max_length=100)
    razorpay_order_id   = serializers.CharField(max_length=100)
    razorpay_signature  = serializers.CharField(max_length=255, write_only=True)
