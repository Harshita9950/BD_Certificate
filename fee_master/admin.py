"""
fee_master/admin.py
====================
Django admin configuration for the generic Birth & Death Fee Master.
"""

from django.contrib import admin

from .models import FeeMaster


@admin.register(FeeMaster)
class FeeMasterAdmin(admin.ModelAdmin):

    list_display = (
        'fee_code',
        'fee_name',
        'service_type',
        'calculation_type',
        'amount',
        'currency',
        'state_code',
        'district',
        'ulb',
        'effective_from',
        'effective_to',
        'is_active',
    )

    list_filter = (
        'service_type',
        'calculation_type',
        'is_active',
        'currency',
        'state_code',
    )

    search_fields = (
        'fee_code',
        'fee_name',
        'rule_reference',
        'notes',
    )

    ordering = ('service_type', 'fee_code')

    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Identity', {
            'fields': ('fee_code', 'fee_name', 'service_type'),
        }),
        ('Fee Amount', {
            'fields': ('calculation_type', 'amount', 'currency'),
        }),
        ('Geographic Scope', {
            'description': (
                'Leave all blank for a global default fee. '
                'Fill progressively for state → district → ULB overrides.'
            ),
            'fields': ('state_code', 'district', 'ulb'),
        }),
        ('Effective Period', {
            'description': (
                'Do NOT overwrite an old record. '
                'Set effective_to on the old record and create a new one.'
            ),
            'fields': ('effective_from', 'effective_to'),
        }),
        ('Legal Reference', {
            'fields': ('rule_reference', 'notes'),
        }),
        ('Status', {
            'fields': ('is_active',),
        }),
        ('Audit', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )
