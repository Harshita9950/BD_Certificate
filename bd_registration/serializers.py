"""
bd_registration/serializers.py
================================
Serializers for the BD Registration module.

Key rules:
1. cause_of_death is NEVER in DeathRegistrationSerializer.
2. service_type and event_location_type are now CharField choices (not FKs).
3. institution is replaced by institution_name CharField.
4. registration_office is optional — not shown on the birth form.
5. district and ulb are nullable at the serializer level to allow draft saves
   without a full jurisdiction (validated properly on submit via the action).
"""

from rest_framework import serializers

from bd_master.models import RegistrationOffice, RegistrationType
from geography.models import District, ULB, Ward as GeographyWard

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
    ulb_name                = serializers.CharField(source='ulb.name',                  read_only=True, default=None)
    district_name           = serializers.CharField(source='district.name',             read_only=True, default=None)
    registration_office_name = serializers.CharField(
        source='registration_office.name', read_only=True, default=None
    )
    status_display          = serializers.CharField(source='get_status_display', read_only=True)
    submitted_by_name       = serializers.SerializerMethodField()
    assigned_to_name        = serializers.SerializerMethodField()

    # registration_office is always optional — not required on the birth form
    registration_office = serializers.PrimaryKeyRelatedField(
        required=False,
        allow_null=True,
        queryset=RegistrationOffice.objects.all(),
    )

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


# ─── Combined Birth Application (atomic create) ───────────────────────────────

class BirthApplicationSerializer(serializers.Serializer):
    """
    Write-only serializer for atomically creating an Application +
    BirthRegistration in a single API call.

    POST /api/bd-registration/birth-applications/
    Body: { ...application fields..., ...birth fields..., action: 'draft'|'submit' }

    Returns the created Application data on success.
    """

    # ── Action ────────────────────────────────────────────────────────────────
    action = serializers.ChoiceField(
        choices=['draft', 'submit'],
        default='draft',
        write_only=True,
    )

    # ── Application fields ────────────────────────────────────────────────────
    service_type       = serializers.CharField(default='BIRTH_REGISTRATION')
    registration_type  = serializers.PrimaryKeyRelatedField(
        queryset=RegistrationType.objects.filter(is_active=True)
    )
    state_code         = serializers.CharField(default='RJ', max_length=10)
    district           = serializers.PrimaryKeyRelatedField(
        required=False, allow_null=True,
        queryset=District.objects.filter(is_active=True),
    )
    ulb                = serializers.PrimaryKeyRelatedField(
        required=False, allow_null=True,
        queryset=ULB.objects.filter(is_active=True),
    )
    date_of_reporting  = serializers.DateField(required=False, allow_null=True)
    remarks            = serializers.CharField(required=False, allow_blank=True, default='')

    # ── Birth-specific fields ─────────────────────────────────────────────────
    child_first_name    = serializers.CharField(required=False, allow_blank=True, default='', max_length=100)
    child_middle_name   = serializers.CharField(required=False, allow_blank=True, default='', max_length=100)
    child_last_name     = serializers.CharField(required=False, allow_blank=True, default='', max_length=100)
    name_recorded       = serializers.BooleanField(default=False)
    date_of_birth       = serializers.DateField(required=False, allow_null=True)
    time_of_birth       = serializers.TimeField(required=False, allow_null=True)
    sex                 = serializers.CharField(required=False, allow_blank=True, default='UNKNOWN', max_length=10)
    event_location_type = serializers.CharField(required=False, allow_blank=True, default='', max_length=25)
    institution_name    = serializers.CharField(required=False, allow_blank=True, default='', max_length=250)
    place_of_birth_address = serializers.CharField(required=False, allow_blank=True, default='')
    ward                = serializers.PrimaryKeyRelatedField(
        required=False, allow_null=True,
        queryset=GeographyWard.objects.filter(is_active=True),
    )
    mother_name         = serializers.CharField(required=False, allow_blank=True, default='', max_length=150)
    mother_age_at_birth = serializers.IntegerField(required=False, allow_null=True, min_value=10, max_value=70)
    mother_nationality  = serializers.CharField(required=False, allow_blank=True, default='Indian', max_length=100)
    mother_education    = serializers.CharField(required=False, allow_blank=True, default='', max_length=100)
    mother_occupation   = serializers.CharField(required=False, allow_blank=True, default='', max_length=100)
    mother_mobile       = serializers.CharField(required=False, allow_blank=True, default='', max_length=15)
    mother_aadhaar      = serializers.CharField(required=False, allow_blank=True, default='', max_length=12)
    father_name         = serializers.CharField(required=False, allow_blank=True, default='', max_length=150)
    father_age_at_birth = serializers.IntegerField(required=False, allow_null=True, min_value=10, max_value=100)
    father_nationality  = serializers.CharField(required=False, allow_blank=True, default='Indian', max_length=100)
    father_education    = serializers.CharField(required=False, allow_blank=True, default='', max_length=100)
    father_occupation   = serializers.CharField(required=False, allow_blank=True, default='', max_length=100)
    father_mobile       = serializers.CharField(required=False, allow_blank=True, default='', max_length=15)
    father_aadhaar      = serializers.CharField(required=False, allow_blank=True, default='', max_length=12)
    permanent_address   = serializers.CharField(required=False, allow_blank=True, default='')
    informant_name      = serializers.CharField(required=False, allow_blank=True, default='', max_length=150)
    informant_relation  = serializers.CharField(required=False, allow_blank=True, default='', max_length=20)
    informant_address   = serializers.CharField(required=False, allow_blank=True, default='')
    informant_mobile    = serializers.CharField(required=False, allow_blank=True, default='', max_length=15)

    # ── Cross-field validation for SUBMIT action ──────────────────────────────

    def validate(self, data):
        action = data.get('action', 'draft')

        if action == 'submit':
            errors = {}

            if not data.get('district'):
                errors['district'] = 'District is required for submission.'
            if not data.get('ulb'):
                errors['ulb'] = 'ULB is required for submission.'
            if not data.get('date_of_reporting'):
                errors['date_of_reporting'] = 'Date of reporting is required for submission.'
            if not data.get('date_of_birth'):
                errors['date_of_birth'] = 'Date of birth is required for submission.'
            if not data.get('sex') or data.get('sex') == 'UNKNOWN':
                errors['sex'] = 'Sex is required for submission.'

            from django.utils import timezone
            today = timezone.localdate()

            dob = data.get('date_of_birth')
            dor = data.get('date_of_reporting')

            if dob and dob > today:
                errors['date_of_birth'] = 'Date of birth cannot be in the future.'
            if dor and dor > today:
                errors['date_of_reporting'] = 'Date of reporting cannot be in the future.'
            if dob and dor and dor < dob:
                errors['date_of_reporting'] = 'Date of reporting cannot be before date of birth.'

            # Aadhaar format check
            import re
            for field in ('mother_aadhaar', 'father_aadhaar'):
                val = data.get(field, '')
                if val and not re.match(r'^[0-9]{12}$', val):
                    errors[field] = 'Aadhaar must be exactly 12 digits.'

            if errors:
                raise serializers.ValidationError(errors)

        return data


# ─── Combined Death Application (atomic create) ───────────────────────────────

class DeathApplicationSerializer(serializers.Serializer):
    """
    Write-only serializer for atomically creating an Application +
    DeathRegistration in a single API call.

    POST /api/bd-registration/death-applications/
    Body: { ...application fields..., ...death fields..., action: 'draft'|'submit' }
    """

    # ── Action ────────────────────────────────────────────────────────────────
    action = serializers.ChoiceField(
        choices=['draft', 'submit'],
        default='draft',
        write_only=True,
    )

    # ── Application fields ────────────────────────────────────────────────────
    service_type       = serializers.CharField(default='DEATH_REGISTRATION')
    registration_type  = serializers.PrimaryKeyRelatedField(
        required=False, allow_null=True,
        queryset=RegistrationType.objects.filter(is_active=True),
    )
    state_code         = serializers.CharField(required=False, allow_blank=True, default='RJ')
    district           = serializers.PrimaryKeyRelatedField(
        required=False, allow_null=True,
        queryset=District.objects.filter(is_active=True),
    )
    ulb                = serializers.PrimaryKeyRelatedField(
        required=False, allow_null=True,
        queryset=ULB.objects.filter(is_active=True),
    )
    date_of_reporting  = serializers.DateField(required=False, allow_null=True)
    remarks            = serializers.CharField(required=False, allow_blank=True, default='')

    # ── Death-specific fields ─────────────────────────────────────────────────
    deceased_first_name      = serializers.CharField(required=False, allow_blank=True, default='', max_length=100)
    deceased_middle_name     = serializers.CharField(required=False, allow_blank=True, default='', max_length=100)
    deceased_last_name       = serializers.CharField(required=False, allow_blank=True, default='', max_length=100)
    sex                      = serializers.CharField(required=False, allow_blank=True, default='UNKNOWN', max_length=10)
    date_of_birth_of_deceased = serializers.DateField(required=False, allow_null=True)
    age_at_death_years       = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    age_at_death_months      = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=11)
    age_at_death_days        = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=30)
    nationality              = serializers.CharField(required=False, allow_blank=True, default='Indian', max_length=100)
    date_of_death            = serializers.DateField(required=False, allow_null=True)
    time_of_death            = serializers.TimeField(required=False, allow_null=True)
    event_location_type      = serializers.CharField(required=False, allow_blank=True, default='', max_length=25)
    institution_name         = serializers.CharField(required=False, allow_blank=True, default='', max_length=250)
    place_of_death_address   = serializers.CharField(required=False, allow_blank=True, default='')
    ward                     = serializers.PrimaryKeyRelatedField(
        required=False, allow_null=True,
        queryset=GeographyWard.objects.filter(is_active=True),
    )
    last_residence_address   = serializers.CharField(required=False, allow_blank=True, default='')
    father_name              = serializers.CharField(required=False, allow_blank=True, default='', max_length=150)
    mother_name              = serializers.CharField(required=False, allow_blank=True, default='', max_length=150)
    spouse_name              = serializers.CharField(required=False, allow_blank=True, default='', max_length=150)
    informant_name           = serializers.CharField(required=False, allow_blank=True, default='', max_length=150)
    informant_relation       = serializers.CharField(required=False, allow_blank=True, default='', max_length=20)
    informant_address        = serializers.CharField(required=False, allow_blank=True, default='')
    informant_mobile         = serializers.CharField(required=False, allow_blank=True, default='', max_length=15)

    def validate(self, data):
        action = data.get('action', 'draft')

        if action == 'submit':
            errors = {}

            if not data.get('district'):
                errors['district'] = 'District is required for submission.'
            if not data.get('ulb'):
                errors['ulb'] = 'ULB is required for submission.'
            if not data.get('date_of_reporting'):
                errors['date_of_reporting'] = 'Date of reporting is required for submission.'
            if not data.get('date_of_death'):
                errors['date_of_death'] = 'Date of death is required for submission.'
            if not data.get('deceased_first_name', '').strip():
                errors['deceased_first_name'] = 'Deceased first name is required for submission.'
            if not data.get('sex') or data.get('sex') == 'UNKNOWN':
                errors['sex'] = 'Sex is required for submission.'

            from django.utils import timezone
            today = timezone.localdate()

            dod = data.get('date_of_death')
            dor = data.get('date_of_reporting')

            if dod and dod > today:
                errors['date_of_death'] = 'Date of death cannot be in the future.'
            if dor and dor > today:
                errors['date_of_reporting'] = 'Date of reporting cannot be in the future.'
            if dod and dor and dor < dod:
                errors['date_of_reporting'] = 'Date of reporting cannot be before date of death.'

            if errors:
                raise serializers.ValidationError(errors)

        return data
