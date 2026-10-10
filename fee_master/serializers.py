"""
fee_master/serializers.py
==========================
Serializers for the generic Birth & Death Fee Master.
"""

from rest_framework import serializers

from .models import FeeMaster, ServiceType, CalculationType


class FeeMasterSerializer(serializers.ModelSerializer):
    """
    Full serializer for Fee Master records.
    Used for list, retrieve, create and update.
    """

    # Read-only display helpers
    service_type_display     = serializers.CharField(
        source='get_service_type_display',
        read_only=True,
    )
    calculation_type_display = serializers.CharField(
        source='get_calculation_type_display',
        read_only=True,
    )
    district_name = serializers.CharField(
        source='district.name',
        read_only=True,
        default=None,
    )
    ulb_name = serializers.CharField(
        source='ulb.name',
        read_only=True,
        default=None,
    )

    class Meta:
        model  = FeeMaster
        fields = (
            'id',
            'fee_code',
            'fee_name',
            'service_type',
            'service_type_display',
            'calculation_type',
            'calculation_type_display',
            'amount',
            'currency',
            'state_code',
            'district',
            'district_name',
            'ulb',
            'ulb_name',
            'effective_from',
            'effective_to',
            'rule_reference',
            'notes',
            'is_active',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'service_type_display',
            'calculation_type_display',
            'district_name',
            'ulb_name',
            'created_at',
            'updated_at',
        )

    def validate(self, attrs):
        # FREE services must have amount = 0
        calc  = attrs.get('calculation_type',
                          getattr(self.instance, 'calculation_type', None))
        amount = attrs.get('amount',
                           getattr(self.instance, 'amount', 0))

        if calc == CalculationType.FREE and amount != 0:
            raise serializers.ValidationError({
                'amount': 'Amount must be 0.00 for FREE services.',
            })

        # effective_to must be after effective_from if provided
        eff_from = attrs.get('effective_from',
                             getattr(self.instance, 'effective_from', None))
        eff_to   = attrs.get('effective_to',
                             getattr(self.instance, 'effective_to', None))

        if eff_from and eff_to and eff_to <= eff_from:
            raise serializers.ValidationError({
                'effective_to': 'effective_to must be after effective_from.',
            })

        # ULB must belong to the given district when both are provided
        district = attrs.get('district',
                             getattr(self.instance, 'district', None))
        ulb      = attrs.get('ulb',
                             getattr(self.instance, 'ulb', None))

        if ulb and district and ulb.district_id != district.id:
            raise serializers.ValidationError({
                'ulb': 'Selected ULB does not belong to the selected District.',
            })

        return attrs


class FeeMasterListSerializer(serializers.ModelSerializer):
    """
    Compact serializer for list views — omits verbose fields.
    """
    service_type_display     = serializers.CharField(
        source='get_service_type_display',
        read_only=True,
    )
    calculation_type_display = serializers.CharField(
        source='get_calculation_type_display',
        read_only=True,
    )

    class Meta:
        model  = FeeMaster
        fields = (
            'id',
            'fee_code',
            'fee_name',
            'service_type',
            'service_type_display',
            'calculation_type',
            'calculation_type_display',
            'amount',
            'currency',
            'state_code',
            'district',
            'ulb',
            'effective_from',
            'effective_to',
            'is_active',
        )


class ServiceTypeChoiceSerializer(serializers.Serializer):
    """Returns all available ServiceType choices."""
    value   = serializers.CharField()
    display = serializers.CharField()


class CalculationTypeChoiceSerializer(serializers.Serializer):
    """Returns all available CalculationType choices."""
    value   = serializers.CharField()
    display = serializers.CharField()
