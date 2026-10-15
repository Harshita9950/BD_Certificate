"""
bd_registration/models.py
==========================
Core registration data architecture for the
Municipal Birth & Death Certificate Management System.

Architecture
------------
Application          ← common parent for all BD services
  └── BirthRegistration        (1:1)
  └── DeathRegistration        (1:1)
  └── StillBirthRegistration   (1:1)
  └── AdoptedBirthRegistration (1:1)

Design rules
------------
- Application holds jurisdiction, status, workflow, timestamps and applicant.
- Each transaction model holds only the event-specific fields.
- Cause of death is stored on DeathRegistration with explicit privacy controls —
  it is excluded from all public serializer fields.
- Delay is NOT determined programmatically here; only event/submission dates
  are stored so delay can be computed by the fee engine later.
- No DeleteModelMixin — records can only be deactivated (is_active=False) or
  processed through workflow status transitions.
- All geography FKs are preserved at snapshot time (application_state_code etc.)
  to protect historical records even if masters change later.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from bd_master.models import TimestampMixin


# ─── Application Status ───────────────────────────────────────────────────────

class ApplicationStatus(models.TextChoices):
    DRAFT           = 'DRAFT',           _('Draft')
    PAYMENT_PENDING = 'PAYMENT_PENDING', _('Payment Pending')
    SUBMITTED       = 'SUBMITTED',       _('Submitted')
    UNDER_SCRUTINY  = 'UNDER_SCRUTINY',  _('Under Scrutiny')
    PENDING_DOCS    = 'PENDING_DOCS',    _('Pending Documents')
    UNDER_PROCESS   = 'UNDER_PROCESS',   _('Under Process')
    APPROVED        = 'APPROVED',        _('Approved')
    REJECTED        = 'REJECTED',        _('Rejected')
    REGISTERED      = 'REGISTERED',      _('Registered')
    CANCELLED       = 'CANCELLED',       _('Cancelled')


# ─── Sex choices (used across multiple registration models) ───────────────────

class Sex(models.TextChoices):
    MALE    = 'MALE',    _('Male')
    FEMALE  = 'FEMALE',  _('Female')
    OTHER   = 'OTHER',   _('Other / Intersex')
    UNKNOWN = 'UNKNOWN', _('Unknown / Not Determined')


# ─── Informant Relation choices ───────────────────────────────────────────────

class InformantRelation(models.TextChoices):
    """
    Relation of the person reporting the event to the Registration Office.
    Based on RBD Act — 'persons required to give information'.
    """
    FATHER             = 'FATHER',             _('Father')
    MOTHER             = 'MOTHER',             _('Mother')
    SPOUSE             = 'SPOUSE',             _('Spouse')
    SON_DAUGHTER       = 'SON_DAUGHTER',       _('Son / Daughter')
    HEAD_OF_FAMILY     = 'HEAD_OF_FAMILY',     _('Head of Family')
    MEDICAL_OFFICER    = 'MEDICAL_OFFICER',    _('Medical Officer / In-charge')
    INSTITUTION_HEAD   = 'INSTITUTION_HEAD',   _('Institution Head')
    RELATIVE           = 'RELATIVE',           _('Other Relative')
    NEIGHBOUR          = 'NEIGHBOUR',          _('Neighbour')
    OTHER              = 'OTHER',              _('Other')


# ─── Service Type (fixed choices — replaces ServiceTypeMaster) ───────────────

class ServiceType(models.TextChoices):
    BIRTH        = 'BIRTH_REGISTRATION',         _('Birth Registration')
    DEATH        = 'DEATH_REGISTRATION',         _('Death Registration')
    STILL_BIRTH  = 'STILL_BIRTH_REGISTRATION',   _('Still Birth Registration')
    ADOPTED_BIRTH = 'ADOPTED_BIRTH_REGISTRATION', _('Adopted Birth Registration')


# ─── Event Location (fixed choices — replaces EventLocationType) ──────────────

class EventLocation(models.TextChoices):
    HOME               = 'HOME',               _('Home')
    HOSPITAL           = 'HOSPITAL',           _('Hospital')
    OTHER_INSTITUTION  = 'OTHER_INSTITUTION',  _('Other Institution')
    OTHER              = 'OTHER',              _('Other')


# ─── Application (Common Parent) ─────────────────────────────────────────────

class Application(TimestampMixin):
    """
    Common parent record for every Birth & Death service transaction.

    One Application record is created regardless of service type.
    The type-specific transaction record (BirthRegistration, etc.) is
    linked via a 1:1 FK back to this Application.

    Jurisdiction snapshot
    ---------------------
    state, district, ulb, registration_office are stored directly so that
    the jurisdictional record is preserved even if geography masters change.
    The service is administered by the ULB / registration_office at the
    time of submission.

    Workflow reference
    ------------------
    The existing workflow_master provides a configurable step-based engine.
    Application stores a FK to Workflow (for the assigned workflow template)
    and current_step (the active WorkflowStep).
    These are nullable because workflow may be assigned after submission.

    Application number
    ------------------
    Generated on first save using a year + zero-padded PK pattern,
    e.g. BD-2025-000001. A temporary UUID is used until PK is available.
    """

    # ── Application Number ────────────────────────────────────────────────────
    application_number = models.CharField(
        _('application number'),
        max_length=30,
        unique=True,
        db_index=True,
    )

    # ── Service / Registration Type ───────────────────────────────────────────
    service_type = models.CharField(
        _('service type'),
        max_length=40,
        choices=ServiceType.choices,
        db_index=True,
        help_text=_('The BD service being applied for.'),
    )

    registration_type = models.ForeignKey(
        'bd_master.RegistrationType',
        on_delete=models.PROTECT,
        related_name='applications',
        verbose_name=_('registration type'),
        help_text=_('Specific type of registration (e.g. BIRTH_NORMAL, DEATH_DELAYED).'),
    )

    # ── Jurisdiction ──────────────────────────────────────────────────────────
    state_code = models.CharField(
        _('state code'),
        max_length=10,
        blank=True,
        default='',
        db_index=True,
        help_text=_('State identifier, e.g. RJ for Rajasthan. Used by delay rules.'),
    )

    district = models.ForeignKey(
        'geography.District',
        on_delete=models.PROTECT,
        related_name='applications',
        verbose_name=_('district'),
    )

    ulb = models.ForeignKey(
        'geography.ULB',
        on_delete=models.PROTECT,
        related_name='applications',
        verbose_name=_('ULB'),
    )

    registration_office = models.ForeignKey(
        'bd_master.RegistrationOffice',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='applications',
        verbose_name=_('registration office'),
        help_text=_('Assigned registrar office for this application.'),
    )

    # ── Applicant / Submitted by ──────────────────────────────────────────────
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='submitted_applications',
        verbose_name=_('submitted by'),
        help_text=_('User who submitted this application (citizen or officer).'),
    )

    # ── Status ────────────────────────────────────────────────────────────────
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.DRAFT,
        db_index=True,
    )

    # ── Workflow ──────────────────────────────────────────────────────────────
    workflow = models.ForeignKey(
        'workflow_master.Workflow',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='applications',
        verbose_name=_('workflow'),
        help_text=_('Assigned workflow template.'),
    )

    current_step = models.ForeignKey(
        'workflow_master.WorkflowStep',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='current_applications',
        verbose_name=_('current step'),
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='assigned_applications',
        verbose_name=_('assigned to'),
        help_text=_('Officer currently responsible for processing.'),
    )

    # ── Key Dates ─────────────────────────────────────────────────────────────
    # Three dates must be kept separate for delay calculation under the Rules.
    #
    #   date_of_reporting  ← Date the informant visited / reported the event
    #                         to the Registration Office. This is the critical
    #                         date for the 21-day window under Rajasthan Rule 5.
    #                         Populated by the receiving officer at intake.
    #
    #   submitted_at       ← Datetime the digital application record was
    #                         formally submitted in the system (may be the same
    #                         day as date_of_reporting or later for back-entry).
    #
    #   date_of_registration ← Stored on the transaction model (BirthRegistration
    #                           etc.) — the date the event is officially entered
    #                           in the register after approval.
    #
    # Delay days = date_of_reporting − date_of_event (from transaction model).
    # Computed by the fee/rules engine, NOT stored here.

    date_of_reporting = models.DateField(
        _('date of reporting'),
        null=True,
        blank=True,
        help_text=_(
            'Date the informant reported the event to the Registration Office. '
            'This is the date used to calculate delay under the Rules. '
            'Distinct from submitted_at (digital submission) and '
            'date_of_registration (official register entry).'
        ),
    )

    submitted_at = models.DateTimeField(
        _('submitted at'),
        null=True,
        blank=True,
        help_text=_('Datetime the application was formally submitted in the system.'),
    )

    # ── Remarks ───────────────────────────────────────────────────────────────
    remarks = models.TextField(
        _('remarks'),
        blank=True,
        default='',
        help_text=_('Officer remarks or internal notes.'),
    )

    class Meta:
        verbose_name        = _('Application')
        verbose_name_plural = _('Applications')
        ordering            = ['-created_at']
        indexes = [
            models.Index(fields=['ulb', 'status']),
            models.Index(fields=['status', 'registration_type']),
            models.Index(fields=['submitted_by', 'status']),
            models.Index(fields=['assigned_to', 'status']),
        ]

    def __str__(self):
        return self.application_number

    def save(self, *args, **kwargs):
        if not self.application_number:
            # Assign a temporary unique value; final number set after PK is known.
            self.application_number = f'TEMP-{uuid.uuid4().hex[:12].upper()}'
            super().save(*args, **kwargs)
            self.application_number = (
                f'BD-{timezone.localdate().year}-{self.pk:06d}'
            )
            super().save(update_fields=['application_number'])
            return
        super().save(*args, **kwargs)


# ─── BirthRegistration ────────────────────────────────────────────────────────

class BirthRegistration(TimestampMixin):
    """
    Birth-specific registration data.
    One-to-one with Application where registration_type.event_category = BIRTH.

    Fields follow the information required under the Registration of Births
    and Deaths Act and Rajasthan Rules:
      - Part I  : Child details
      - Part II : Place of birth
      - Part III: Father / Mother details
      - Part IV : Informant details
    """

    application = models.OneToOneField(
        Application,
        on_delete=models.PROTECT,
        related_name='birth_registration',
        verbose_name=_('application'),
    )

    # ── Child Name ────────────────────────────────────────────────────────────
    child_first_name  = models.CharField(_('child first name'),  max_length=100, blank=True, default='')
    child_middle_name = models.CharField(_('child middle name'), max_length=100, blank=True, default='')
    child_last_name   = models.CharField(_('child last name'),   max_length=100, blank=True, default='')

    name_recorded = models.BooleanField(
        _('name recorded at registration'),
        default=False,
        help_text=_(
            'True when the child name was provided at time of registration. '
            'False means name addition will be required later.'
        ),
    )

    # ── Date & Time of Birth ──────────────────────────────────────────────────
    date_of_birth = models.DateField(_('date of birth'))

    time_of_birth = models.TimeField(
        _('time of birth'),
        null=True,
        blank=True,
        help_text=_('24-hour time. Null if not known.'),
    )

    # ── Sex ───────────────────────────────────────────────────────────────────
    sex = models.CharField(
        _('sex'),
        max_length=10,
        choices=Sex.choices,
        default=Sex.UNKNOWN,
        db_index=True,
    )

    # ── Place of Birth ────────────────────────────────────────────────────────
    event_location_type = models.CharField(
        _('event location type'),
        max_length=25,
        choices=EventLocation.choices,
        blank=True,
        default='',
        db_index=True,
        help_text=_('Type of place where birth occurred (Home, Hospital, etc.).'),
    )

    institution_name = models.CharField(
        _('institution name'),
        max_length=250,
        blank=True,
        default='',
        help_text=_('Name of hospital/nursing home where birth occurred, if applicable.'),
    )

    place_of_birth_address = models.TextField(
        _('place of birth address'),
        blank=True,
        default='',
        help_text=_('Full address where birth occurred (if not at an institution).'),
    )

    ward = models.ForeignKey(
        'geography.Ward',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='births',
        verbose_name=_('ward of birth'),
    )

    # ── Mother Details ────────────────────────────────────────────────────────
    mother_name         = models.CharField(_('mother name'),         max_length=150, blank=True, default='')
    mother_age_at_birth = models.PositiveSmallIntegerField(
        _('mother age at birth'), null=True, blank=True,
        help_text=_('Mother\'s age in completed years at time of birth.'),
    )
    mother_nationality  = models.CharField(_('mother nationality'), max_length=100, blank=True, default='Indian')
    mother_education    = models.CharField(
        _('mother education'),
        max_length=100,
        blank=True,
        default='',
        help_text=_('Highest level of education (informational/statistical).'),
    )
    mother_occupation   = models.CharField(_('mother occupation'), max_length=100, blank=True, default='')
    mother_aadhaar      = models.CharField(
        _('mother Aadhaar number'),
        max_length=12,
        blank=True,
        default='',
        help_text=_('12-digit Aadhaar UID. Stored for verification only.'),
    )
    mother_mobile       = models.CharField(_('mother mobile'), max_length=15, blank=True, default='')

    # ── Father Details ────────────────────────────────────────────────────────
    father_name         = models.CharField(_('father name'),         max_length=150, blank=True, default='')
    father_age_at_birth = models.PositiveSmallIntegerField(
        _('father age at birth'), null=True, blank=True,
    )
    father_nationality  = models.CharField(_('father nationality'), max_length=100, blank=True, default='Indian')
    father_education    = models.CharField(_('father education'),    max_length=100, blank=True, default='')
    father_occupation   = models.CharField(_('father occupation'),   max_length=100, blank=True, default='')
    father_aadhaar      = models.CharField(_('father Aadhaar number'), max_length=12, blank=True, default='')
    father_mobile       = models.CharField(_('father mobile'), max_length=15, blank=True, default='')

    # ── Permanent Address ─────────────────────────────────────────────────────
    permanent_address = models.TextField(
        _('permanent address'),
        blank=True,
        default='',
        help_text=_('Permanent address of parents / child for registration record.'),
    )

    # ── Informant Details ─────────────────────────────────────────────────────
    informant_name     = models.CharField(_('informant name'),  max_length=150, blank=True, default='')
    informant_relation = models.CharField(
        _('informant relation'),
        max_length=20,
        choices=InformantRelation.choices,
        blank=True,
        default='',
    )
    informant_address  = models.TextField(_('informant address'), blank=True, default='')
    informant_mobile   = models.CharField(_('informant mobile'), max_length=15, blank=True, default='')

    # ── Registration Record ───────────────────────────────────────────────────
    registration_number = models.CharField(
        _('registration number'),
        max_length=50,
        blank=True,
        default='',
        db_index=True,
        help_text=_(
            'Official registration number assigned after approval. '
            'Format determined by Registrar/state rules.'
        ),
    )

    date_of_registration = models.DateField(
        _('date of registration'),
        null=True,
        blank=True,
        help_text=_('Date the birth was officially registered in the register.'),
    )

    # Date of event (date_of_birth) vs date_of_registration are both stored
    # so delay in days can be calculated later by the fee/rules engine.

    class Meta:
        verbose_name        = _('Birth Registration')
        verbose_name_plural = _('Birth Registrations')
        ordering            = ['-application__created_at']
        indexes = [
            models.Index(fields=['date_of_birth']),
            models.Index(fields=['registration_number']),
        ]

    def __str__(self):
        child = (
            f'{self.child_first_name} {self.child_last_name}'.strip()
            or 'Unnamed'
        )
        return f'Birth: {child} — {self.application.application_number}'


# ─── DeathRegistration ────────────────────────────────────────────────────────

class DeathRegistration(TimestampMixin):
    """
    Death-specific registration data.
    One-to-one with Application where registration_type.event_category = DEATH.

    IMPORTANT: cause_of_death is a restricted field.
    It must NEVER appear in any public-facing certificate or API response.
    The serializer explicitly excludes it from the default field set and
    it is only accessible through a dedicated secured internal API endpoint.
    """

    application = models.OneToOneField(
        Application,
        on_delete=models.PROTECT,
        related_name='death_registration',
        verbose_name=_('application'),
    )

    # ── Deceased Identity ─────────────────────────────────────────────────────
    deceased_first_name  = models.CharField(_('first name'),  max_length=100)
    deceased_middle_name = models.CharField(_('middle name'), max_length=100, blank=True, default='')
    deceased_last_name   = models.CharField(_('last name'),   max_length=100, blank=True, default='')

    sex = models.CharField(
        _('sex'),
        max_length=10,
        choices=Sex.choices,
        default=Sex.UNKNOWN,
        db_index=True,
    )

    date_of_birth_of_deceased = models.DateField(
        _('date of birth of deceased'),
        null=True,
        blank=True,
        help_text=_('Date of birth if known; else age_at_death is used.'),
    )

    age_at_death_years  = models.PositiveSmallIntegerField(
        _('age at death (years)'), null=True, blank=True,
    )
    age_at_death_months = models.PositiveSmallIntegerField(
        _('age at death (months)'), null=True, blank=True,
        help_text=_('Months component (for infants under 1 year).'),
    )
    age_at_death_days   = models.PositiveSmallIntegerField(
        _('age at death (days)'), null=True, blank=True,
        help_text=_('Days component (for neonates).'),
    )

    nationality         = models.CharField(_('nationality'), max_length=100, blank=True, default='Indian')

    # ── Date & Time of Death ──────────────────────────────────────────────────
    date_of_death = models.DateField(_('date of death'))

    time_of_death = models.TimeField(
        _('time of death'),
        null=True,
        blank=True,
    )

    # ── Place of Death ────────────────────────────────────────────────────────
    event_location_type = models.CharField(
        _('event location type'),
        max_length=25,
        choices=EventLocation.choices,
        blank=True,
        default='',
        db_index=True,
    )

    institution_name = models.CharField(
        _('institution name'),
        max_length=250,
        blank=True,
        default='',
        help_text=_('Name of hospital/nursing home where death occurred, if applicable.'),
    )

    place_of_death_address = models.TextField(
        _('place of death address'),
        blank=True,
        default='',
    )

    ward = models.ForeignKey(
        'geography.Ward',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='deaths',
        verbose_name=_('ward of death'),
    )

    # ── Last Usual Residence ──────────────────────────────────────────────────
    last_residence_address = models.TextField(
        _('last usual residence address'),
        blank=True,
        default='',
        help_text=_('Address where the deceased normally lived.'),
    )

    # ── Parents / Spouse ──────────────────────────────────────────────────────
    father_name  = models.CharField(_('father name'),  max_length=150, blank=True, default='')
    mother_name  = models.CharField(_('mother name'),  max_length=150, blank=True, default='')
    spouse_name  = models.CharField(_('spouse name'),  max_length=150, blank=True, default='')

    # ── Medical / Cause of Death ──────────────────────────────────────────────
    # RESTRICTED FIELD — must never be included in public certificate response.
    # Only accessible via a secured internal medical officer endpoint.
    cause_of_death = models.TextField(
        _('cause of death'),
        blank=True,
        default='',
        help_text=_(
            'RESTRICTED. Medical cause of death. '
            'Must NOT be included in any public certificate or open API response. '
            'Access restricted to authorised medical/health officers only.'
        ),
    )

    # ── Informant Details ─────────────────────────────────────────────────────
    informant_name     = models.CharField(_('informant name'),  max_length=150, blank=True, default='')
    informant_relation = models.CharField(
        _('informant relation'),
        max_length=20,
        choices=InformantRelation.choices,
        blank=True,
        default='',
    )
    informant_address  = models.TextField(_('informant address'), blank=True, default='')
    informant_mobile   = models.CharField(_('informant mobile'), max_length=15, blank=True, default='')

    # ── Registration Record ───────────────────────────────────────────────────
    registration_number = models.CharField(
        _('registration number'),
        max_length=50,
        blank=True,
        default='',
        db_index=True,
    )

    date_of_registration = models.DateField(
        _('date of registration'),
        null=True,
        blank=True,
    )

    # date_of_death vs date_of_registration are both stored
    # so delay can be calculated later by the fee/rules engine.

    class Meta:
        verbose_name        = _('Death Registration')
        verbose_name_plural = _('Death Registrations')
        ordering            = ['-application__created_at']
        indexes = [
            models.Index(fields=['date_of_death']),
            models.Index(fields=['registration_number']),
        ]

    def __str__(self):
        name = (
            f'{self.deceased_first_name} {self.deceased_last_name}'.strip()
            or 'Unknown'
        )
        return f'Death: {name} — {self.application.application_number}'


# ─── StillBirthRegistration ───────────────────────────────────────────────────

class StillBirthRegistration(TimestampMixin):
    """
    Still-birth registration.
    A still birth is a birth where the child shows no sign of life after delivery.
    It requires a separate register entry under the RBD Act.
    Not forced into BirthRegistration — it has distinct fields.
    """

    application = models.OneToOneField(
        Application,
        on_delete=models.PROTECT,
        related_name='still_birth_registration',
        verbose_name=_('application'),
    )

    # ── Event Details ─────────────────────────────────────────────────────────
    date_of_birth = models.DateField(_('date of still birth'))

    time_of_birth = models.TimeField(_('time of still birth'), null=True, blank=True)

    sex = models.CharField(
        _('sex'),
        max_length=10,
        choices=Sex.choices,
        default=Sex.UNKNOWN,
        db_index=True,
    )

    # ── Place of Still Birth ──────────────────────────────────────────────────
    event_location_type = models.CharField(
        _('event location type'),
        max_length=25,
        choices=EventLocation.choices,
        blank=True,
        default='',
        db_index=True,
    )

    institution_name = models.CharField(
        _('institution name'),
        max_length=250,
        blank=True,
        default='',
        help_text=_('Name of hospital/nursing home, if applicable.'),
    )

    place_of_birth_address = models.TextField(_('place of birth address'), blank=True, default='')

    ward = models.ForeignKey(
        'geography.Ward',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='still_births',
    )

    # ── Mother Details ────────────────────────────────────────────────────────
    mother_name         = models.CharField(_('mother name'),         max_length=150, blank=True, default='')
    mother_age_at_birth = models.PositiveSmallIntegerField(_('mother age'), null=True, blank=True)
    mother_nationality  = models.CharField(_('mother nationality'),  max_length=100, blank=True, default='Indian')

    # ── Father Details ────────────────────────────────────────────────────────
    father_name         = models.CharField(_('father name'),        max_length=150, blank=True, default='')
    father_nationality  = models.CharField(_('father nationality'), max_length=100, blank=True, default='Indian')

    # ── Permanent Address ─────────────────────────────────────────────────────
    permanent_address = models.TextField(_('permanent address'), blank=True, default='')

    # ── Medical Note ─────────────────────────────────────────────────────────
    # Duration of pregnancy in completed weeks (informational/statistical).
    gestation_weeks = models.PositiveSmallIntegerField(
        _('gestation weeks'), null=True, blank=True,
        help_text=_('Duration of pregnancy in completed weeks at time of still birth.'),
    )

    # ── Informant ─────────────────────────────────────────────────────────────
    informant_name     = models.CharField(_('informant name'),  max_length=150, blank=True, default='')
    informant_relation = models.CharField(
        _('informant relation'), max_length=20,
        choices=InformantRelation.choices, blank=True, default='',
    )
    informant_address  = models.TextField(_('informant address'), blank=True, default='')
    informant_mobile   = models.CharField(_('informant mobile'), max_length=15, blank=True, default='')

    # ── Registration Record ───────────────────────────────────────────────────
    registration_number  = models.CharField(_('registration number'), max_length=50, blank=True, default='', db_index=True)
    date_of_registration = models.DateField(_('date of registration'), null=True, blank=True)

    class Meta:
        verbose_name        = _('Still Birth Registration')
        verbose_name_plural = _('Still Birth Registrations')
        ordering            = ['-application__created_at']
        indexes = [
            models.Index(fields=['date_of_birth']),
        ]

    def __str__(self):
        return f'Still Birth — {self.application.application_number}'


# ─── AdoptedBirthRegistration ─────────────────────────────────────────────────

class AdoptedBirthRegistration(TimestampMixin):
    """
    Birth registration for an adopted child.

    Under the RBD Act / adoption-related provisions, a new birth certificate
    can be issued after a court adoption order. This captures the specific
    data required for such cases: new name, adoptive parents, and the
    original registration reference.
    """

    application = models.OneToOneField(
        Application,
        on_delete=models.PROTECT,
        related_name='adopted_birth_registration',
        verbose_name=_('application'),
    )

    # ── Child Name (Post-Adoption) ────────────────────────────────────────────
    child_first_name  = models.CharField(_('child first name'),  max_length=100, blank=True, default='')
    child_middle_name = models.CharField(_('child middle name'), max_length=100, blank=True, default='')
    child_last_name   = models.CharField(_('child last name'),   max_length=100, blank=True, default='')

    date_of_birth = models.DateField(_('date of birth'))

    sex = models.CharField(
        _('sex'), max_length=10, choices=Sex.choices, default=Sex.UNKNOWN, db_index=True,
    )

    # ── Adoptive Parents ──────────────────────────────────────────────────────
    adoptive_father_name  = models.CharField(_('adoptive father name'),  max_length=150, blank=True, default='')
    adoptive_mother_name  = models.CharField(_('adoptive mother name'),  max_length=150, blank=True, default='')
    adoptive_parents_address = models.TextField(_('adoptive parents address'), blank=True, default='')
    adoptive_parents_mobile  = models.CharField(_('adoptive parents mobile'), max_length=15, blank=True, default='')

    # ── Court / Adoption Order ────────────────────────────────────────────────
    adoption_order_number = models.CharField(
        _('adoption order number'),
        max_length=100,
        blank=True,
        default='',
        help_text=_('Court order number under which adoption was granted.'),
    )
    adoption_order_date = models.DateField(
        _('adoption order date'),
        null=True,
        blank=True,
    )
    adopting_court_name = models.CharField(
        _('adopting court name'),
        max_length=200,
        blank=True,
        default='',
    )

    # ── Original Registration Reference ───────────────────────────────────────
    original_registration_number = models.CharField(
        _('original registration number'),
        max_length=50,
        blank=True,
        default='',
        help_text=_(
            'Reference to the original birth registration (if the child was '
            'previously registered under biological parents).'
        ),
    )
    original_registration_district = models.CharField(
        _('original registration district'),
        max_length=100,
        blank=True,
        default='',
    )

    # ── Informant ─────────────────────────────────────────────────────────────
    informant_name     = models.CharField(_('informant name'),  max_length=150, blank=True, default='')
    informant_relation = models.CharField(
        _('informant relation'), max_length=20,
        choices=InformantRelation.choices, blank=True, default='',
    )
    informant_address  = models.TextField(_('informant address'), blank=True, default='')
    informant_mobile   = models.CharField(_('informant mobile'), max_length=15, blank=True, default='')

    # ── New Registration ──────────────────────────────────────────────────────
    registration_number  = models.CharField(_('new registration number'), max_length=50, blank=True, default='', db_index=True)
    date_of_registration = models.DateField(_('date of registration'), null=True, blank=True)

    class Meta:
        verbose_name        = _('Adopted Birth Registration')
        verbose_name_plural = _('Adopted Birth Registrations')
        ordering            = ['-application__created_at']

    def __str__(self):
        child = (
            f'{self.child_first_name} {self.child_last_name}'.strip()
            or 'Unnamed'
        )
        return f'Adopted Birth: {child} — {self.application.application_number}'


# ─── Document Verification Status ────────────────────────────────────────────

class DocumentVerificationStatus(models.TextChoices):
    PENDING  = 'PENDING',  _('Pending Verification')
    VERIFIED = 'VERIFIED', _('Verified')
    REJECTED = 'REJECTED', _('Rejected')


# ─── Application Document ─────────────────────────────────────────────────────

class ApplicationDocument(TimestampMixin):
    """
    A file uploaded in support of an Application.

    Multiple documents may be attached to one application.
    Files are stored under media/bd_documents/<year>/<month>/.
    cause_of_death is never stored here — it lives on DeathRegistration only.
    """

    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name=_('application'),
    )

    document_type = models.ForeignKey(
        'bd_master.DocumentType',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='application_documents',
        verbose_name=_('document type'),
        help_text=_('Type of document (e.g. Aadhaar, Hospital Certificate).'),
    )

    file = models.FileField(
        _('file'),
        upload_to='bd_documents/%Y/%m/',
        help_text=_('Uploaded file. Max 10 MB. Accepted: PDF, JPG, PNG.'),
    )

    original_filename = models.CharField(
        _('original filename'),
        max_length=255,
        blank=True,
        default='',
        help_text=_('Original name of the uploaded file as provided by the browser.'),
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='uploaded_documents',
        verbose_name=_('uploaded by'),
    )

    verification_status = models.CharField(
        _('verification status'),
        max_length=10,
        choices=DocumentVerificationStatus.choices,
        default=DocumentVerificationStatus.PENDING,
        db_index=True,
    )

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='verified_documents',
        verbose_name=_('verified by'),
    )

    verified_at = models.DateTimeField(_('verified at'), null=True, blank=True)

    remarks = models.TextField(_('remarks'), blank=True, default='')

    class Meta:
        verbose_name        = _('Application Document')
        verbose_name_plural = _('Application Documents')
        ordering            = ['-created_at']
        indexes = [
            models.Index(fields=['application', 'verification_status']),
        ]

    def __str__(self):
        return (
            f'{self.original_filename or self.file.name} '
            f'— {self.application.application_number}'
        )


# ─── Application Status History ───────────────────────────────────────────────

class ApplicationStatusHistory(TimestampMixin):
    """
    Immutable audit trail of every status transition on an Application.
    Records must never be deleted.
    """

    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name='status_history',
        verbose_name=_('application'),
    )

    old_status = models.CharField(
        _('old status'),
        max_length=20,
        choices=ApplicationStatus.choices,
        blank=True,
        default='',
        help_text=_('Status before this transition. Empty for the initial creation event.'),
    )

    new_status = models.CharField(
        _('new status'),
        max_length=20,
        choices=ApplicationStatus.choices,
    )

    action = models.CharField(
        _('action'),
        max_length=50,
        help_text=_(
            'Machine-readable action code, e.g. CREATED, SUBMITTED, '
            'APPROVED, REJECTED, REGISTERED, CANCELLED.'
        ),
    )

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='application_status_changes',
        verbose_name=_('changed by'),
    )

    changed_at = models.DateTimeField(
        _('changed at'),
        default=timezone.now,
        db_index=True,
    )

    remarks = models.TextField(_('remarks'), blank=True, default='')

    class Meta:
        verbose_name        = _('Application Status History')
        verbose_name_plural = _('Application Status Histories')
        ordering            = ['changed_at']
        # Audit records must not be deleted from admin
        default_permissions = ('view',)
        indexes = [
            models.Index(fields=['application', 'changed_at']),
        ]

    def __str__(self):
        return (
            f'{self.application.application_number}: '
            f'{self.old_status or "NEW"} → {self.new_status} '
            f'({self.action})'
        )
