"""
bd_master/models.py
====================
Configuration layer for the Birth & Death Certificate Management System.

Kept as configurable masters:
  - RegistrationOffice
  - RegistrationType
  - DocumentType (used internally by DelayRule)
  - AuthorityType (used internally by DelayRule)
  - DelayRule

Removed (converted to fixed choices in bd_registration):
  - ServiceTypeMaster → ServiceType TextChoices
  - EventLocationType → EventLocation TextChoices
  - Institution → institution_name CharField on registration models
  - InstitutionType enum
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class TimestampMixin(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True


# ─── Registration Office ───────────────────────────────────────────────────────

class RegistrationOffice(TimestampMixin):
    ulb = models.ForeignKey(
        'geography.ULB', on_delete=models.PROTECT,
        related_name='registration_offices', verbose_name=_('ULB'),
    )
    code = models.CharField(_('office code'), max_length=20, unique=True, db_index=True)
    name = models.CharField(_('office name'), max_length=200)
    registrar_name = models.CharField(_('registrar name'), max_length=150, blank=True, default='')
    address = models.TextField(_('address'), blank=True, default='')
    phone = models.CharField(_('phone'), max_length=20, blank=True, default='')
    email = models.EmailField(_('email'), blank=True, default='')
    is_active = models.BooleanField(_('active'), default=True, db_index=True)

    class Meta:
        verbose_name = _('Registration Office')
        verbose_name_plural = _('Registration Offices')
        ordering = ['ulb', 'code']
        indexes = [models.Index(fields=['ulb', 'is_active'])]

    def __str__(self):
        return f'{self.name} ({self.code}) — {self.ulb.code}'


# ─── Document Type (used internally by DelayRule, not a sidebar master) ──────

class DocumentType(TimestampMixin):
    code = models.CharField(_('document code'), max_length=30, unique=True, db_index=True)
    name = models.CharField(_('document name'), max_length=150)
    description = models.TextField(_('description'), blank=True, default='')
    accepted_formats = models.CharField(_('accepted formats'), max_length=100, blank=True, default='PDF,JPG,PNG')
    max_size_mb = models.PositiveSmallIntegerField(_('max size (MB)'), default=5)
    is_mandatory = models.BooleanField(_('mandatory'), default=False)
    is_active = models.BooleanField(_('active'), default=True, db_index=True)

    class Meta:
        verbose_name = _('Document Type')
        verbose_name_plural = _('Document Types')
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.code})'


# ─── Registration Type ────────────────────────────────────────────────────────

class EventCategory(models.TextChoices):
    BIRTH       = 'BIRTH',       _('Birth')
    DEATH       = 'DEATH',       _('Death')
    STILL_BIRTH = 'STILL_BIRTH', _('Still Birth')
    OTHER       = 'OTHER',       _('Other')


class RegistrationType(TimestampMixin):
    code = models.CharField(_('type code'), max_length=40, unique=True, db_index=True)
    name = models.CharField(_('type name'), max_length=150)
    event_category = models.CharField(_('event category'), max_length=15, choices=EventCategory.choices, db_index=True)
    description = models.TextField(_('description'), blank=True, default='')
    requires_institution = models.BooleanField(_('requires institution'), default=False)
    is_delayed = models.BooleanField(_('is delayed registration'), default=False)
    is_active = models.BooleanField(_('active'), default=True, db_index=True)

    class Meta:
        verbose_name = _('Registration Type')
        verbose_name_plural = _('Registration Types')
        ordering = ['event_category', 'name']
        indexes = [models.Index(fields=['event_category', 'is_active'])]

    def __str__(self):
        return f'{self.name} ({self.code})'


# ─── Authority Type (used internally by DelayRule, not a sidebar master) ─────

class AuthorityType(TimestampMixin):
    code = models.CharField(_('authority code'), max_length=40, unique=True, db_index=True)
    name = models.CharField(_('authority name'), max_length=200)
    description = models.TextField(_('description'), blank=True, default='')
    is_active = models.BooleanField(_('active'), default=True, db_index=True)

    class Meta:
        verbose_name = _('Authority Type')
        verbose_name_plural = _('Authority Types')
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.code})'


# ─── Delay Category & Delay Rule ─────────────────────────────────────────────

class DelayCategory(models.TextChoices):
    NORMAL               = 'NORMAL',               _('Normal (0–21 days)')
    DELAYED_30_DAYS      = 'DELAYED_30_DAYS',      _('Delayed — >21 to 30 days')
    DELAYED_1_YEAR       = 'DELAYED_1_YEAR',       _('Delayed — >30 days to 1 year')
    DELAYED_ABOVE_1_YEAR = 'DELAYED_ABOVE_1_YEAR', _('Delayed — More than 1 year')


class DelayRule(TimestampMixin):
    rule_code = models.CharField(_('rule code'), max_length=60, unique=True, db_index=True)
    rule_name = models.CharField(_('rule name'), max_length=200)
    delay_category = models.CharField(_('delay category'), max_length=25, choices=DelayCategory.choices, db_index=True)
    state_code = models.CharField(_('state code'), max_length=10, blank=True, default='', db_index=True)
    district = models.ForeignKey('geography.District', on_delete=models.PROTECT, null=True, blank=True, related_name='delay_rules', verbose_name=_('district'))
    ulb = models.ForeignKey('geography.ULB', on_delete=models.PROTECT, null=True, blank=True, related_name='delay_rules', verbose_name=_('ULB'))
    min_delay_days = models.PositiveSmallIntegerField(_('minimum delay days'))
    max_delay_days = models.PositiveSmallIntegerField(_('maximum delay days'), null=True, blank=True)
    fee_code = models.CharField(_('fee master code'), max_length=60, blank=True, default='')
    requires_authority_permission = models.BooleanField(_('requires authority permission'), default=False)
    authority_type = models.ForeignKey(AuthorityType, on_delete=models.PROTECT, null=True, blank=True, related_name='delay_rules', verbose_name=_('authority type'))
    authority_notes = models.TextField(_('authority notes'), blank=True, default='')
    required_documents = models.ManyToManyField(DocumentType, blank=True, related_name='delay_rules', verbose_name=_('required documents'))
    requires_form_14 = models.BooleanField(_('requires Form 14'), default=False)
    requires_self_attested_affidavit = models.BooleanField(_('requires self-attested affidavit'), default=False)
    requires_permission_order = models.BooleanField(_('requires permission order'), default=False)
    rule_reference = models.CharField(_('rule reference'), max_length=300, blank=True, default='')
    notes = models.TextField(_('notes'), blank=True, default='')
    effective_from = models.DateField(_('effective from'))
    effective_to = models.DateField(_('effective to'), null=True, blank=True)
    is_active = models.BooleanField(_('active'), default=True, db_index=True)

    class Meta:
        verbose_name = _('Delay Rule')
        verbose_name_plural = _('Delay Rules')
        ordering = ['state_code', 'delay_category']
        indexes = [models.Index(fields=['delay_category', 'state_code', 'is_active'])]

    def __str__(self):
        scope = self.state_code or 'GLOBAL'
        return f'[{scope}] {self.rule_code} — {self.get_delay_category_display()}'
