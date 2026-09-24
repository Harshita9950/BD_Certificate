"""
users/serializers.py
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Permission, Role

User = get_user_model()


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Citizen self-registration. Role defaults to CITIZEN."""

    password  = serializers.CharField(write_only=True, required=True,
                                      validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True,
                                      label='Confirm Password')

    class Meta:
        model  = User
        fields = ('id', 'email', 'username', 'first_name', 'last_name', 'mobile',
                  'password', 'password2')
        read_only_fields = ('id',)

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        return User.objects.create_user(**validated_data)


class UserProfileSerializer(serializers.ModelSerializer):
    """Read / update own profile. Role and ULB are read-only."""

    full_name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model  = User
        fields = ('id', 'email', 'username', 'first_name', 'last_name', 'mobile',
                  'role', 'ulb_code', 'department', 'zone', 'ward',
                  'is_verified', 'date_joined', 'full_name')
        read_only_fields = ('id', 'email', 'username', 'role', 'ulb_code',
                            'is_verified', 'date_joined', 'full_name')


class UserListSerializer(serializers.ModelSerializer):
    """Minimal representation for admin / officer lists."""

    full_name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model  = User
        fields = ('id', 'email', 'full_name', 'mobile', 'role',
                  'ulb_code', 'is_active', 'is_verified')

class UserManagementSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(
        source='get_full_name',
        read_only=True
    )

    district = serializers.IntegerField(
        source='ulb_fk.district_id',
        read_only=True
    )

    district_name = serializers.CharField(
        source='ulb_fk.district.name',
        read_only=True
    )

    ulb_name = serializers.CharField(
        source='ulb_fk.name',
        read_only=True
    )

    zone_name = serializers.CharField(
        source='zone_fk.name',
        read_only=True
    )

    ward_name = serializers.CharField(
        source='ward_fk.name',
        read_only=True
    )

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'full_name',
            'mobile',
            'role',
            'district',
            'district_name',
            'ulb_fk',
            'ulb_name',
            'zone_fk',
            'zone_name',
            'ward_fk',
            'ward_name',
            'is_active',
        )
        read_only_fields = (
            'id',
            'full_name',
            'district',
            'district_name',
            'ulb_name',
            'zone_name',
            'ward_name',
        )

class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password]
    )

    password2 = serializers.CharField(
        write_only=True,
        required=True
    )

    class Meta:
        model = User
        fields = (
            'username',
            'first_name',
            'last_name',
            'email',
            'mobile',
            'role',
            'ulb_fk',
            'zone_fk',
            'ward_fk',
            'password',
            'password2',
            'is_active',
        )

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({
                'password': 'Passwords do not match.'
            })

        ulb = attrs.get('ulb_fk')
        zone = attrs.get('zone_fk')
        ward = attrs.get('ward_fk')

        if zone and zone.ulb_id != ulb.id:
            raise serializers.ValidationError({
                'zone_fk': 'Selected zone does not belong to the selected ULB.'
            })

        if ward and ward.zone_id != zone.id:
            raise serializers.ValidationError({
                'ward_fk': 'Selected ward does not belong to the selected zone.'
            })

        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')

        password = validated_data.pop('password')

        user = User(**validated_data)
        user.set_password(password)
        user.save()

        return user

class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'username',
            'first_name',
            'last_name',
            'email',
            'mobile',
            'role',
            'ulb_fk',
            'zone_fk',
            'ward_fk',
            'is_active',
        )
        read_only_fields = ('username',)

    def validate(self, attrs):
        ulb = attrs.get('ulb_fk', self.instance.ulb_fk)
        zone = attrs.get('zone_fk', self.instance.zone_fk)
        ward = attrs.get('ward_fk', self.instance.ward_fk)

        if zone and ulb and zone.ulb_id != ulb.id:
            raise serializers.ValidationError({
                'zone_fk': 'Selected zone does not belong to the selected ULB.'
            })

        if ward and zone and ward.zone_id != zone.id:
            raise serializers.ValidationError({
                'ward_fk': 'Selected ward does not belong to the selected zone.'
            })

        return attrs

class RoleManagementSerializer(serializers.ModelSerializer):
    permission_count = serializers.IntegerField(
        source='permissions.count',
        read_only=True
    )

    class Meta:
        model = Role
        fields = (
            'id',
            'name',
            'code',
            'description',
            'permissions',
            'permission_count',
            'ulb_code',
            'is_active',
        )
        read_only_fields = ('id', 'permission_count')


class RoleCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = (
            'name',
            'code',
            'description',
            'permissions',
            'ulb_code',
            'is_active',
        )


class RoleUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = (
            'name',
            'code',
            'description',
            'permissions',
            'ulb_code',
            'is_active',
        )

class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = (
            'id',
            'code',
            'description',
            'module',
        )