from django.contrib import admin
from .models import District, ULB, Zone, Ward


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display  = ('code', 'name', 'is_active', 'created_at')
    list_filter   = ('is_active',)
    search_fields = ('code', 'name')
    ordering      = ('name',)


@admin.register(ULB)
class ULBAdmin(admin.ModelAdmin):
    list_display   = ('code', 'name', 'ulb_type', 'district', 'is_active', 'created_at')
    list_filter    = ('ulb_type', 'is_active', 'district')
    search_fields  = ('code', 'name')
    raw_id_fields  = ('district',)
    ordering       = ('name',)


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display  = ('code', 'name', 'ulb', 'is_active', 'created_at')
    list_filter   = ('is_active', 'ulb__district')
    search_fields = ('code', 'name', 'ulb__name', 'ulb__code')
    raw_id_fields = ('ulb',)
    ordering      = ('ulb', 'name')


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display  = ('code', 'name', 'zone', 'is_active', 'created_at')
    list_filter   = ('is_active', 'zone__ulb')
    search_fields = ('code', 'name', 'zone__name', 'zone__ulb__code')
    raw_id_fields = ('zone',)
    ordering      = ('zone', 'code')
