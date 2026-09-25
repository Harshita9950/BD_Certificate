from rest_framework import serializers

from users.models import Role

from .models import Workflow, WorkflowStep


class WorkflowSerializer(serializers.ModelSerializer):
    ulb_name = serializers.CharField(source='ulb.name', read_only=True)

    class Meta:
        model = Workflow
        fields = (
            'id',
            'application_type',
            'ulb',
            'ulb_name',
            'code',
            'name',
            'description',
            'is_active',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


class WorkflowStepSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(
        source='workflow.name',
        read_only=True
    )
    role_name = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowStep
        fields = (
            'id',
            'workflow',
            'workflow_name',
            'step_number',
            'code',
            'name',
            'description',
            'role_code',
            'role_name',
            'is_active',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'workflow_name',
            'role_name',
            'created_at',
            'updated_at',
        )

    def get_role_name(self, obj):
        role = Role.objects.filter(
            code=obj.role_code,
            is_active=True,
        ).first()

        return role.name if role else obj.role_code

    def validate_role_code(self, value):
        if not Role.objects.filter(
            code=value,
            is_active=True,
        ).exists():
            raise serializers.ValidationError(
                'Selected role does not exist or is inactive.'
            )

        return value