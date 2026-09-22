from rest_framework import serializers
from .models import District, ULB, Zone, Ward


class DistrictSerializer(serializers.ModelSerializer):
    class Meta:
        model  = District
        fields = ('id', 'code', 'name', 'is_active')


class ULBSerializer(serializers.ModelSerializer):
    district_name = serializers.CharField(source='district.name', read_only=True)

    class Meta:
        model  = ULB
        fields = ('id', 'code', 'name', 'ulb_type', 'district', 'district_name', 'is_active')


class ZoneSerializer(serializers.ModelSerializer):
    ulb_name = serializers.CharField(source='ulb.name', read_only=True)

    class Meta:
        model  = Zone
        fields = ('id', 'code', 'name', 'ulb', 'ulb_name', 'is_active')


class WardSerializer(serializers.ModelSerializer):
    zone_name = serializers.CharField(source='zone.name', read_only=True)
    ulb_code  = serializers.CharField(source='zone.ulb.code', read_only=True)

    class Meta:
        model  = Ward
        fields = ('id', 'code', 'name', 'zone', 'zone_name', 'ulb_code', 'is_active')
