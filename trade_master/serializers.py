
from rest_framework import serializers

from .models import (
    TradeCategory,
    Trade,
    SubTrade,
    ULBTradeConfig,
    Application,
    CoOwner,
)


class TradeCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TradeCategory
        fields = (
            "id",
            "code",
            "name",
            "description",
            "is_active",
        )


class TradeSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
    )

    class Meta:
        model = Trade
        fields = (
            "id",
            "code",
            "name",
            "description",
            "category",
            "category_name",
            "is_active",
        )


class SubTradeSerializer(serializers.ModelSerializer):
    trade_name = serializers.CharField(
        source="trade.name",
        read_only=True,
    )
    category_name = serializers.CharField(
        source="trade.category.name",
        read_only=True,
    )

    class Meta:
        model = SubTrade
        fields = (
            "id",
            "code",
            "name",
            "description",
            "trade",
            "trade_name",
            "category_name",
            "is_active",
        )


class ULBTradeConfigSerializer(serializers.ModelSerializer):
    ulb_code = serializers.CharField(
        source="ulb.code",
        read_only=True,
    )
    trade_name = serializers.CharField(
        source="trade.name",
        read_only=True,
    )
    trade_code = serializers.CharField(
        source="trade.code",
        read_only=True,
    )

    class Meta:
        model = ULBTradeConfig
        fields = (
            "id",
            "ulb",
            "ulb_code",
            "trade",
            "trade_name",
            "trade_code",
            "is_enabled",
        )


# ── Co-Owner Serializer ──

class CoOwnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoOwner
        fields = (
            "id",
            "name",
            "relationship",
            "mobile",
            "email",
        )
        read_only_fields = ("id",)


# ── Application Serializer ──

class ApplicationSerializer(serializers.ModelSerializer):

    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
    )

    applicant_username = serializers.CharField(
        source="applicant.username",
        read_only=True,
    )

    workflow_name = serializers.CharField(
        source="workflow.name",
        read_only=True,
    )

    current_step_name = serializers.CharField(
        source="current_step.name",
        read_only=True,
    )

    co_owners = CoOwnerSerializer(
        many=True,
        required=False,
    )

    class Meta:
        model = Application
        fields = "__all__"

        read_only_fields = (
            "id",
            "application_no",
            "applicant",
            "workflow",
            "current_step",
            "assigned_to",
            "status",
            "submitted_at",
            "created_at",
            "updated_at",
        )

    def create(self, validated_data):
        co_owners_data = validated_data.pop("co_owners", [])

        application = Application.objects.create(**validated_data)

        for co_owner_data in co_owners_data:
            CoOwner.objects.create(
                application=application,
                **co_owner_data,
            )

        return application

    def update(self, instance, validated_data):
        co_owners_data = validated_data.pop("co_owners", None)

        # Update application fields.
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        # Replace co-owners only if the request includes them.
        if co_owners_data is not None:
            instance.co_owners.all().delete()

            for co_owner_data in co_owners_data:
                CoOwner.objects.create(
                    application=instance,
                    **co_owner_data,
                )

        return instance

    def validate(self, attrs):
        ulb = attrs.get("ulb", getattr(self.instance, "ulb", None))
        ward = attrs.get("ward", getattr(self.instance, "ward", None))
        category = attrs.get(
            "category",
            getattr(self.instance, "category", None),
        )

        errors = {}

        # 1. Validate ward belongs to selected ULB.
        if ulb and ward:
            if ward.zone.ulb_id != ulb.id:
                errors["ward"] = (
                    "Selected ward does not belong to the selected ULB."
                )
            elif not ward.is_active or not ward.zone.is_active:
                errors["ward"] = (
                    "Selected ward or its zone is inactive."
                )

        # 2. Validate ULB is active.
        if ulb and not ulb.is_active:
            errors["ulb"] = "Selected ULB is inactive."

        # 3. Validate category is active.
        if category and not category.is_active:
            errors["category"] = "Selected category is inactive."

        if errors:
            raise serializers.ValidationError(errors)

        return attrs