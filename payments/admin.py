"""
payments/admin.py
==================
Django admin registration for PaymentOrder and PaymentTransaction.
Provides a read-only audit view of payment records in the admin interface.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import PaymentOrder, PaymentTransaction


class PaymentTransactionInline(admin.TabularInline):
    model        = PaymentTransaction
    extra        = 0
    can_delete   = False
    show_change_link = True
    readonly_fields = (
        'status', 'amount', 'currency',
        'razorpay_payment_id', 'razorpay_error_code',
        'receipt_number', 'collected_by',
        'initiated_at', 'completed_at', 'notes',
    )
    exclude = ('razorpay_signature', 'razorpay_error_description')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PaymentOrder)
class PaymentOrderAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'application_number', 'amount_display',
        'payment_method', 'status_badge', 'created_at',
    )
    list_filter  = ('status', 'payment_method', 'currency')
    search_fields = (
        'application__application_number',
        'fee_code',
        'razorpay_order_id',
        'reference',
    )
    readonly_fields = (
        'reference', 'application', 'fee_code',
        'amount', 'currency', 'payment_method',
        'razorpay_order_id', 'created_by',
        'created_at', 'updated_at',
    )
    inlines = [PaymentTransactionInline]
    ordering = ('-created_at',)

    def application_number(self, obj):
        return obj.application.application_number
    application_number.short_description = 'Application'

    def amount_display(self, obj):
        return f'₹ {obj.amount}'
    amount_display.short_description = 'Amount'

    def status_badge(self, obj):
        colours = {
            'PENDING':   '#f59e0b',
            'PAID':      '#10b981',
            'FAILED':    '#ef4444',
            'CANCELLED': '#6b7280',
            'REFUNDED':  '#3b82f6',
        }
        colour = colours.get(obj.status, '#6b7280')
        return format_html(
            '<span style="color:{}; font-weight:600;">{}</span>',
            colour, obj.get_status_display(),
        )
    status_badge.short_description = 'Status'

    def has_add_permission(self, request):
        return False   # Orders created via API only

    def has_delete_permission(self, request, obj=None):
        return False   # Financial records must not be deleted


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'payment_order', 'status',
        'amount', 'razorpay_payment_id',
        'receipt_number', 'initiated_at',
    )
    list_filter  = ('status',)
    search_fields = (
        'payment_order__application__application_number',
        'razorpay_payment_id',
        'receipt_number',
    )
    readonly_fields = (
        'payment_order', 'status', 'amount', 'currency',
        'razorpay_payment_id', 'razorpay_error_code',
        'razorpay_error_description',
        'receipt_number', 'collected_by',
        'initiated_at', 'completed_at', 'notes',
    )
    exclude = ('razorpay_signature',)
    ordering = ('-initiated_at',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
