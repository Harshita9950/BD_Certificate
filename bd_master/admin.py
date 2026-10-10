"""
bd_master/admin.py
"""
from django.contrib import admin

from .models import (
    RegistrationOffice,
    DocumentType,
    RegistrationType,
    AuthorityType,
    DelayRule,
)


@admin.register(RegistrationOffice)
class RegistrationOfficeAdmin(admin.ModelAdmin):
    list_display  = ('code', 'name', 'ulb', 'registrar_name', 'is_active', 'created_at')
    list_filter   = ('is_active', 'ulb__district')
    search_fields = ('code', 'name', 'registrar_name')
    raw_id_fields = ('ulb',)
    ordering      = ('ulb', 'code')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Identity',  {'fields': ('code', 'name', 'ulb')}),
        ('Registrar', {'fields': ('registrar_name',)}),
        ('Contact',   {'fields': ('address', 'phone', 'email')}),
        ('Status',    {'fields': ('is_active',)}),
        ('Audit',     {'classes': ('collapse',), 'fields': ('created_at', 'updated_at')}),
    )


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display  = ('code', 'name', 'accepted_formats', 'max_size_mb', 'is_mandatory', 'is_active', 'created_at')
    list_filter   = ('is_mandatory', 'is_active')
    search_fields = ('code', 'name', 'description')
    ordering      = ('name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(RegistrationType)
class RegistrationTypeAdmin(admin.ModelAdmin):
    list_display  = ('code', 'name', 'event_category', 'is_delayed', 'requires_institution', 'is_active', 'created_at')
    list_filter   = ('event_category', 'is_delayed', 'requires_institution', 'is_active')
    search_fields = ('code', 'name', 'description')
    ordering      = ('event_category', 'name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AuthorityType)
class AuthorityTypeAdmin(admin.ModelAdmin):
    list_display    = ('code', 'name', 'is_active', 'created_at')
    list_filter     = ('is_active',)
    search_fields   = ('code', 'name', 'description')
    ordering        = ('name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DelayRule)
class DelayRuleAdmin(admin.ModelAdmin):
    list_display = (
        'rule_code', 'delay_category', 'state_code',
        'min_delay_days', 'max_delay_days',
        'fee_code', 'requires_authority_permission',
        'requires_form_14', 'requires_permission_order',
        'effective_from', 'effective_to', 'is_active',
    )
    list_filter  = ('delay_category', 'is_active', 'state_code',
                    'requires_authority_permission', 'requires_form_14',
                    'requires_permission_order')
    search_fields   = ('rule_code', 'rule_name', 'fee_code', 'rule_reference')
    raw_id_fields   = ('district', 'ulb', 'authority_type')
    filter_horizontal = ('required_documents',)
    ordering        = ('state_code', 'delay_category')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Identity',      {'fields': ('rule_code', 'rule_name', 'delay_category')}),
        ('Delay Window',  {'fields': ('min_delay_days', 'max_delay_days')}),
        ('Geographic Scope', {'fields': ('state_code', 'district', 'ulb')}),
        ('Fee Reference', {'fields': ('fee_code',)}),
        ('Authority',     {'fields': (
            'requires_authority_permission', 'authority_type', 'authority_notes',
        )}),
        ('Documents / Forms', {'fields': (
            'required_documents',
            'requires_form_14',
            'requires_self_attested_affidavit',
            'requires_permission_order',
        )}),
        ('Legal Reference', {'fields': ('rule_reference', 'notes')}),
        ('Validity',       {'fields': ('effective_from', 'effective_to', 'is_active')}),
        ('Audit',          {'classes': ('collapse',), 'fields': ('created_at', 'updated_at')}),
    )
