"""
bd_master/serializers.py
"""
from rest_framework import serializers

from .models import (
    RegistrationOffice,
    DocumentType,
    RegistrationType,
    AuthorityType,
    DelayRule,
)


class RegistrationOfficeSerializer(serializers.ModelSerializer):
    ulb_name = serializers.CharField(source='ulb.name', read_only=True)
    ulb_code = serializers.CharField(source='ulb.code', read_only=True)

    class Meta:
        model  = RegistrationOffice
        fields = (
            'id', 'code', 'name', 'ulb', 'ulb_code', 'ulb_name',
            'registrar_name', 'address', 'phone', 'email', 'is_active',
        )
        read_only_fields = ('id', 'ulb_code', 'ulb_name')


class DocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = DocumentType
        fields = (
            'id', 'code', 'name', 'description',
            'accepted_formats', 'max_size_mb',
            'is_mandatory', 'is_active',
        )
        read_only_fields = ('id',)


class RegistrationTypeSerializer(serializers.ModelSerializer):
    event_category_display = serializers.CharField(
        source='get_event_category_display', read_only=True
    )

    class Meta:
        model  = RegistrationType
        fields = (
            'id', 'code', 'name',
            'event_category', 'event_category_display',
            'description',
            'requires_institution', 'is_delayed',
            'is_active',
        )
        read_only_fields = ('id', 'event_category_display')


class AuthorityTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = AuthorityType
        fields = ('id', 'code', 'name', 'description', 'is_active')
        read_only_fields = ('id',)


class DelayRuleSerializer(serializers.ModelSerializer):
    delay_category_display = serializers.CharField(
        source='get_delay_category_display', read_only=True
    )
    authority_type_name = serializers.CharField(
        source='authority_type.name', read_only=True, default=None
    )
    district_name = serializers.CharField(
        source='district.name', read_only=True, default=None
    )
    ulb_name = serializers.CharField(
        source='ulb.name', read_only=True, default=None
    )
    required_documents_detail = DocumentTypeSerializer(
        source='required_documents', many=True, read_only=True
    )

    class Meta:
        model  = DelayRule
        fields = (
            'id',
            'rule_code', 'rule_name',
            'delay_category', 'delay_category_display',
            'state_code',
            'district', 'district_name',
            'ulb', 'ulb_name',
            'min_delay_days', 'max_delay_days',
            'fee_code',
            'requires_authority_permission',
            'authority_type', 'authority_type_name', 'authority_notes',
            'required_documents', 'required_documents_detail',
            'requires_form_14', 'requires_self_attested_affidavit',
            'requires_permission_order',
            'rule_reference', 'notes',
            'effective_from', 'effective_to',
            'is_active',
        )
        read_only_fields = (
            'id',
            'delay_category_display',
            'authority_type_name',
            'district_name',
            'ulb_name',
            'required_documents_detail',
        )
