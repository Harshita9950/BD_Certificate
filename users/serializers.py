"""
users/serializers.py
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Citizen self-registration. Role defaults to CITIZEN."""

    password  = serializers.CharField(write_only=True, required=True,
                                      validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True,
                                      label='Confirm Password')

    class Meta:
        model  = User
        fields = ('id', 'email', 'first_name', 'last_name', 'mobile',
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
        fields = ('id', 'email', 'first_name', 'last_name', 'mobile',
                  'role', 'ulb_code', 'department', 'zone', 'ward',
                  'is_verified', 'date_joined', 'full_name')
        read_only_fields = ('id', 'email', 'role', 'ulb_code', 'is_verified',
                            'date_joined', 'full_name')


class UserListSerializer(serializers.ModelSerializer):
    """Minimal representation for admin / officer lists."""

    full_name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model  = User
        fields = ('id', 'email', 'full_name', 'mobile', 'role',
                  'ulb_code', 'is_active', 'is_verified')
