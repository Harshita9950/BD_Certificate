"""
bd_registration/serializers.py
================================
Serializers for the BD Registration module.

Key rules:
1. cause_of_death is NEVER in DeathRegistrationSerializer.
2. service_type and event_location_type are now CharField choices (not FKs).
3. institution is replaced by institution_name CharField.
"""

from rest_framework import serializers

from .models import (
    Application,
    ApplicationDocument,
    BirthRegistration,
    DeathRegistration,
    StillBirthRegistration,
    AdoptedBirthRegistration,
)


# ─── Application ──────────────────────────────────────────────────────────────

class ApplicationSerializer(serializers.ModelSerializer):
    service_type_display    = serializers.CharField(source='get_service_type_display', read_only=True)
    registration_type_name  = serializers.CharField(source='registration_type.name',    read_only=True)
    ulb_name                = serializers.CharField(source='ulb.name',                  read_only=True)
    district_name           = serializers.CharField(source='district.name',             read_only=True)
    registration_office_name = serializers.CharField(
        source='registration_office.name', read_only=True, default=None
    )
    status_display          = serializers.CharField(source='get_status_display', read_only=True)
    submitted_by_name       = serializers.SerializerMethodField()
    assigned_to_name        = serializers.SerializerMethodField()

    class Meta:
        model  = Application
        fields = (
            'id',
            'application_number',
            'service_type',         'service_type_display',
            'registration_type',    'registration_type_name',
            'state_code',
            'district',             'district_name',
            'ulb',                  'ulb_name',
            'registration_office',  'registration_office_name',
            'submitted_by',         'submitted_by_name',
            'status',               'status_display',
            'workflow',
            'current_step',
            'assigned_to',          'assigned_to_name',
            'date_of_reporting',
            'submitted_at',
            'remarks',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'application_number',
            'service_type_display',
            'registration_type_name',
            'district_name',
            'ulb_name',
            'registration_office_name',
            'status_display',
            'submitted_by_name',
            'assigned_to_name',
            'created_at',
            'updated_at',
        )

    def get_submitted_by_name(self, obj):
        if obj.submitted_by:
            return obj.submitted_by.get_full_name() or obj.submitted_by.username
        return None

    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            return obj.assigned_to.get_full_name() or obj.assigned_to.username
        return None


# ─── Birth Registration ───────────────────────────────────────────────────────

class BirthRegistrationSerializer(serializers.ModelSerializer):
    application_number = serializers.CharField(
        source='application.application_number', read_only=True
    )
    event_location_type_display = serializers.CharField(
        source='get_event_location_type_display', read_only=True, default=''
    )
    ward_name = serializers.CharField(source='ward.name', read_only=True, default=None)
    sex_display = serializers.CharField(source='get_sex_display', read_only=True)
    informant_relation_display = serializers.CharField(
        source='get_informant_relation_display', read_only=True
    )

    class Meta:
        model  = BirthRegistration
        fields = (
            'id',
            'application',          'application_number',
            'child_first_name',     'child_middle_name',    'child_last_name',
            'name_recorded',
            'date_of_birth',        'time_of_birth',
            'sex',                  'sex_display',
            'event_location_type',  'event_location_type_display',
            'institution_name',
            'place_of_birth_address',
            'ward',                 'ward_name',
            'mother_name',          'mother_age_at_birth',
            'mother_nationality',   'mother_education',
            'mother_occupation',    'mother_mobile',
            'father_name',          'father_age_at_birth',
            'father_nationality',   'father_education',
            'father_occupation',    'father_mobile',
            'permanent_address',
            'informant_name',       'informant_relation',
            'informant_relation_display',
            'informant_address',    'informant_mobile',
            'registration_number',  'date_of_registration',
            'created_at',           'updated_at',
        )
        read_only_fields = (
            'id', 'application_number', 'event_location_type_display',
            'ward_name', 'sex_display', 'informant_relation_display',
            'created_at', 'updated_at',
        )


# ─── Death Registration — PUBLIC (cause_of_death excluded) ───────────────────

class DeathRegistrationSerializer(serializers.ModelSerializer):
    application_number = serializers.CharField(
        source='application.application_number', read_only=True
    )
    event_location_type_display = serializers.CharField(
        source='get_event_location_type_display', read_only=True, default=''
    )
    ward_name = serializers.CharField(source='ward.name', read_only=True, default=None)
    sex_display = serializers.CharField(source='get_sex_display', read_only=True)
    informant_relation_display = serializers.CharField(
        source='get_informant_relation_display', read_only=True
    )

    class Meta:
        model  = DeathRegistration
        fields = (
            'id',
            'application',              'application_number',
            'deceased_first_name',      'deceased_middle_name',     'deceased_last_name',
            'sex',                      'sex_display',
            'date_of_birth_of_deceased',
            'age_at_death_years',       'age_at_death_months',      'age_at_death_days',
            'nationality',
            'date_of_death',            'time_of_death',
            'event_location_type',      'event_location_type_display',
            'institution_name',
            'place_of_death_address',
            'ward',                     'ward_name',
            'last_residence_address',
            'father_name',              'mother_name',              'spouse_name',
            'informant_name',           'informant_relation',
            'informant_relation_display',
            'informant_address',        'informant_mobile',
            'registration_number',      'date_of_registration',
            'created_at',               'updated_at',
        )
        read_only_fields = (
            'id', 'application_number', 'event_location_type_display',
            'ward_name', 'sex_display', 'informant_relation_display',
            'created_at', 'updated_at',
        )


class DeathRegistrationRestrictedSerializer(DeathRegistrationSerializer):
    class Meta(DeathRegistrationSerializer.Meta):
        fields = DeathRegistrationSerializer.Meta.fields + ('cause_of_death',)


# ─── Still Birth Registration ─────────────────────────────────────────────────

class StillBirthRegistrationSerializer(serializers.ModelSerializer):
    application_number = serializers.CharField(
        source='application.application_number', read_only=True
    )
    event_location_type_display = serializers.CharField(
        source='get_event_location_type_display', read_only=True, default=''
    )
    ward_name   = serializers.CharField(source='ward.name', read_only=True, default=None)
    sex_display = serializers.CharField(source='get_sex_display', read_only=True)
    informant_relation_display = serializers.CharField(
        source='get_informant_relation_display', read_only=True
    )

    class Meta:
        model  = StillBirthRegistration
        fields = (
            'id',
            'application',              'application_number',
            'date_of_birth',            'time_of_birth',
            'sex',                      'sex_display',
            'event_location_type',      'event_location_type_display',
            'institution_name',
            'place_of_birth_address',
            'ward',                     'ward_name',
            'mother_name',              'mother_age_at_birth',      'mother_nationality',
            'father_name',              'father_nationality',
            'permanent_address',
            'gestation_weeks',
            'informant_name',           'informant_relation',
            'informant_relation_display',
            'informant_address',        'informant_mobile',
            'registration_number',      'date_of_registration',
            'created_at',               'updated_at',
        )
        read_only_fields = (
            'id', 'application_number', 'event_location_type_display',
            'ward_name', 'sex_display', 'informant_relation_display',
            'created_at', 'updated_at',
        )


# ─── Adopted Birth Registration ───────────────────────────────────────────────

class AdoptedBirthRegistrationSerializer(serializers.ModelSerializer):
    application_number = serializers.CharField(
        source='application.application_number', read_only=True
    )
    sex_display = serializers.CharField(source='get_sex_display', read_only=True)
    informant_relation_display = serializers.CharField(
        source='get_informant_relation_display', read_only=True
    )

    class Meta:
        model  = AdoptedBirthRegistration
        fields = (
            'id',
            'application',              'application_number',
            'child_first_name',         'child_middle_name',        'child_last_name',
            'date_of_birth',
            'sex',                      'sex_display',
            'adoptive_father_name',     'adoptive_mother_name',
            'adoptive_parents_address', 'adoptive_parents_mobile',
            'adoption_order_number',    'adoption_order_date',      'adopting_court_name',
            'original_registration_number', 'original_registration_district',
            'informant_name',           'informant_relation',
            'informant_relation_display',
            'informant_address',        'informant_mobile',
            'registration_number',      'date_of_registration',
            'created_at',               'updated_at',
        )
        read_only_fields = (
            'id', 'application_number', 'sex_display',
            'informant_relation_display', 'created_at', 'updated_at',
        )


# ─── Application Document ─────────────────────────────────────────────────────

class ApplicationDocumentSerializer(serializers.ModelSerializer):
    document_type_name      = serializers.CharField(
        source='document_type.name', read_only=True, default=None
    )
    verification_status_display = serializers.CharField(
        source='get_verification_status_display', read_only=True
    )
    uploaded_by_name = serializers.SerializerMethodField()
    file_url         = serializers.SerializerMethodField()

    class Meta:
        model  = ApplicationDocument
        fields = (
            'id',
            'application',
            'document_type',        'document_type_name',
            'file',                 'file_url',
            'original_filename',
            'uploaded_by',          'uploaded_by_name',
            'verification_status',  'verification_status_display',
            'verified_by',
            'verified_at',
            'remarks',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id', 'application', 'uploaded_by', 'document_type_name',
            'verification_status_display', 'uploaded_by_name', 'file_url',
            'verified_by', 'verified_at', 'created_at', 'updated_at',
        )

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return obj.uploaded_by.get_full_name() or obj.uploaded_by.username
        return None

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None
