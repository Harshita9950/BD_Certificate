"""
bd_registration/admin.py
"""
from django.contrib import admin
from .models import (
    Application, BirthRegistration, DeathRegistration,
    StillBirthRegistration, AdoptedBirthRegistration,
)


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display    = ('application_number', 'service_type', 'registration_type', 'ulb', 'status', 'submitted_by', 'submitted_at', 'created_at')
    list_filter     = ('status', 'service_type', 'registration_type', 'ulb__district')
    search_fields   = ('application_number', 'remarks')
    raw_id_fields   = ('registration_type', 'district', 'ulb', 'registration_office', 'submitted_by', 'assigned_to', 'workflow', 'current_step')
    readonly_fields = ('application_number', 'created_at', 'updated_at')
    ordering        = ('-created_at',)
    fieldsets = (
        ('Application',  {'fields': ('application_number', 'service_type', 'registration_type')}),
        ('Jurisdiction', {'fields': ('state_code', 'district', 'ulb', 'registration_office')}),
        ('Workflow',     {'fields': ('status', 'workflow', 'current_step', 'assigned_to')}),
        ('Submission',   {'fields': ('submitted_by', 'date_of_reporting', 'submitted_at', 'remarks')}),
        ('Audit',        {'classes': ('collapse',), 'fields': ('created_at', 'updated_at')}),
    )


@admin.register(BirthRegistration)
class BirthRegistrationAdmin(admin.ModelAdmin):
    list_display  = ('application', 'child_first_name', 'child_last_name', 'date_of_birth', 'sex', 'registration_number', 'created_at')
    list_filter   = ('sex', 'name_recorded', 'event_location_type', 'application__ulb__district')
    search_fields = ('child_first_name', 'child_last_name', 'mother_name', 'father_name', 'registration_number', 'application__application_number')
    raw_id_fields   = ('application', 'ward')
    readonly_fields = ('created_at', 'updated_at')
    ordering        = ('-application__created_at',)
    fieldsets = (
        ('Application', {'fields': ('application',)}),
        ('Child',       {'fields': ('child_first_name', 'child_middle_name', 'child_last_name', 'name_recorded', 'date_of_birth', 'time_of_birth', 'sex')}),
        ('Place of Birth', {'fields': ('event_location_type', 'institution_name', 'place_of_birth_address', 'ward')}),
        ('Mother',      {'fields': ('mother_name', 'mother_age_at_birth', 'mother_nationality', 'mother_education', 'mother_occupation', 'mother_mobile')}),
        ('Father',      {'fields': ('father_name', 'father_age_at_birth', 'father_nationality', 'father_education', 'father_occupation', 'father_mobile')}),
        ('Address',     {'fields': ('permanent_address',)}),
        ('Informant',   {'fields': ('informant_name', 'informant_relation', 'informant_address', 'informant_mobile')}),
        ('Registration',{'fields': ('registration_number', 'date_of_registration')}),
        ('Audit',       {'classes': ('collapse',), 'fields': ('created_at', 'updated_at')}),
    )


@admin.register(DeathRegistration)
class DeathRegistrationAdmin(admin.ModelAdmin):
    list_display  = ('application', 'deceased_first_name', 'deceased_last_name', 'date_of_death', 'sex', 'registration_number', 'created_at')
    list_filter   = ('sex', 'event_location_type', 'application__ulb__district')
    search_fields = ('deceased_first_name', 'deceased_last_name', 'registration_number', 'application__application_number')
    raw_id_fields   = ('application', 'ward')
    readonly_fields = ('created_at', 'updated_at')
    ordering        = ('-application__created_at',)
    fieldsets = (
        ('Application',    {'fields': ('application',)}),
        ('Deceased',       {'fields': ('deceased_first_name', 'deceased_middle_name', 'deceased_last_name', 'sex', 'date_of_birth_of_deceased', 'nationality', 'age_at_death_years', 'age_at_death_months', 'age_at_death_days')}),
        ('Place of Death', {'fields': ('event_location_type', 'institution_name', 'place_of_death_address', 'ward', 'date_of_death', 'time_of_death')}),
        ('Residence',      {'fields': ('last_residence_address',)}),
        ('Family',         {'fields': ('father_name', 'mother_name', 'spouse_name')}),
        ('Informant',      {'fields': ('informant_name', 'informant_relation', 'informant_address', 'informant_mobile')}),
        ('Registration',   {'fields': ('registration_number', 'date_of_registration')}),
        ('Cause of Death (RESTRICTED)', {
            'description': 'WARNING: Must NOT appear on any public certificate or API response.',
            'classes': ('collapse',),
            'fields': ('cause_of_death',),
        }),
        ('Audit', {'classes': ('collapse',), 'fields': ('created_at', 'updated_at')}),
    )


@admin.register(StillBirthRegistration)
class StillBirthRegistrationAdmin(admin.ModelAdmin):
    list_display  = ('application', 'date_of_birth', 'sex', 'mother_name', 'registration_number', 'created_at')
    list_filter   = ('sex', 'event_location_type', 'application__ulb__district')
    search_fields = ('mother_name', 'father_name', 'registration_number', 'application__application_number')
    raw_id_fields   = ('application', 'ward')
    readonly_fields = ('created_at', 'updated_at')
    ordering        = ('-application__created_at',)
    fieldsets = (
        ('Application',    {'fields': ('application',)}),
        ('Event',          {'fields': ('date_of_birth', 'time_of_birth', 'sex', 'gestation_weeks')}),
        ('Place of Birth', {'fields': ('event_location_type', 'institution_name', 'place_of_birth_address', 'ward')}),
        ('Parents',        {'fields': ('mother_name', 'mother_age_at_birth', 'mother_nationality', 'father_name', 'father_nationality', 'permanent_address')}),
        ('Informant',      {'fields': ('informant_name', 'informant_relation', 'informant_address', 'informant_mobile')}),
        ('Registration',   {'fields': ('registration_number', 'date_of_registration')}),
        ('Audit',          {'classes': ('collapse',), 'fields': ('created_at', 'updated_at')}),
    )


@admin.register(AdoptedBirthRegistration)
class AdoptedBirthRegistrationAdmin(admin.ModelAdmin):
    list_display  = ('application', 'child_first_name', 'child_last_name', 'date_of_birth', 'adoption_order_number', 'registration_number', 'created_at')
    list_filter   = ('sex', 'application__ulb__district')
    search_fields = ('child_first_name', 'child_last_name', 'adoptive_father_name', 'adoptive_mother_name', 'adoption_order_number', 'registration_number', 'application__application_number')
    raw_id_fields   = ('application',)
    readonly_fields = ('created_at', 'updated_at')
    ordering        = ('-application__created_at',)
    fieldsets = (
        ('Application',      {'fields': ('application',)}),
        ('Child',            {'fields': ('child_first_name', 'child_middle_name', 'child_last_name', 'date_of_birth', 'sex')}),
        ('Adoptive Parents', {'fields': ('adoptive_father_name', 'adoptive_mother_name', 'adoptive_parents_address', 'adoptive_parents_mobile')}),
        ('Adoption Order',   {'fields': ('adoption_order_number', 'adoption_order_date', 'adopting_court_name')}),
        ('Original Record',  {'fields': ('original_registration_number', 'original_registration_district')}),
        ('Informant',        {'fields': ('informant_name', 'informant_relation', 'informant_address', 'informant_mobile')}),
        ('Registration',     {'fields': ('registration_number', 'date_of_registration')}),
        ('Audit',            {'classes': ('collapse',), 'fields': ('created_at', 'updated_at')}),
    )
