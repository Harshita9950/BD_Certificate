"""
fee_master/models.py
====================
Generic, configuration-driven Fee Master for the
Municipal Birth & Death Certificate Management System.

Design principles
-----------------
- NO dependency on trade_master or any other business module.
- Fees are stored in the database — never hard-coded in Python.
- Supports geographic scoping: global → state → district → ULB.
- Supports effective date ranges so historical fees are preserved.
- Extensible to any future municipal service without schema changes.

Removing Trade License-specific fields
---------------------------------------
The following fields from the old FeeMaster have been removed:
  category       (FK → trade_master.TradeCategory)
  licence_type   (REGULAR / TEMPORARY)
  size_type      (NONE / ROOMS / SEATS)
  min_size, max_size
  ac_facility    (AC / NON_AC)
  max_duration_weeks
  fee_unit       (FIXED / PER_WEEK)
  annual_increase_percent
"""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ─── Service Type Choices ─────────────────────────────────────────────────────

class ServiceType(models.TextChoices):
    """
    Identifies the Birth & Death service to which a fee record applies.
    Extensible — add new service codes here as new services are introduced.
    The fee engine selects the matching record at runtime.
    """
    BIRTH_REGISTRATION         = 'BIRTH_REGISTRATION',         _('Birth Registration')
    DEATH_REGISTRATION         = 'DEATH_REGISTRATION',         _('Death Registration')
    STILL_BIRTH_REGISTRATION   = 'STILL_BIRTH_REGISTRATION',   _('Still Birth Registration')
    ADOPTED_BIRTH_REGISTRATION = 'ADOPTED_BIRTH_REGISTRATION', _('Adopted Child Birth Registration')
    DELAYED_REGISTRATION       = 'DELAYED_REGISTRATION',       _('Delayed Registration')
    CERTIFICATE_COPY           = 'CERTIFICATE_COPY',           _('Certified Certificate Copy')
    REGISTER_SEARCH            = 'REGISTER_SEARCH',            _('Register Search')
    NON_AVAILABILITY_CERT      = 'NON_AVAILABILITY_CERT',      _('Non-Availability Certificate')
    NAME_ADDITION              = 'NAME_ADDITION',              _('Name Addition')
    CORRECTION                 = 'CORRECTION',                 _('Correction')
    CANCELLATION               = 'CANCELLATION',               _('Cancellation')
    APPEAL                     = 'APPEAL',                     _('Appeal')
    POSTAL_DELIVERY            = 'POSTAL_DELIVERY',            _('Postal Delivery')
    ORIGINAL_CERTIFICATE       = 'ORIGINAL_CERTIFICATE',       _('Original Certificate After Registration')
    OTHER                      = 'OTHER',                      _('Other')


# ─── Calculation Type Choices ─────────────────────────────────────────────────

class CalculationType(models.TextChoices):
    """
    Controls how the fee amount is applied.

    FIXED    — a flat amount; amount field holds the value directly.
    FREE     — no charge; amount must be 0.00 (stored explicitly so it is
               data-driven, not assumed).
    PER_YEAR — amount is charged per year (e.g. register search additional years).
               The calling code multiplies by the number of years.
    MANUAL   — requires officer determination; amount field is a reference/
               minimum only.
    """
    FIXED    = 'FIXED',    _('Fixed Amount')
    FREE     = 'FREE',     _('Free / No Charge')
    PER_YEAR = 'PER_YEAR', _('Per Year')
    MANUAL   = 'MANUAL',   _('Manual / Officer Determined')


# ─── Fee Master ───────────────────────────────────────────────────────────────

class FeeMaster(models.Model):
    """
    Generic fee record for any Birth & Death certificate service.

    Geographic scoping (nullable FKs support a precedence hierarchy):
        Global      state_code=None, district=None, ulb=None
        State       state_code='RJ', district=None, ulb=None
        District    state_code='RJ', district=<obj>, ulb=None
        ULB         state_code='RJ', district=<obj>, ulb=<obj>

    The fee engine (built separately) resolves the most specific
    applicable record at runtime. The model simply stores the data.

    Effective date ranges preserve fee history:
        Old fee: effective_from=<old>, effective_to=<new start date>
        New fee: effective_from=<new start date>, effective_to=None
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    fee_code = models.CharField(
        _('fee code'),
        max_length=60,
        db_index=True,
        help_text=_(
            'Machine-readable code, e.g. BD.REG_NORMAL, BD.LATE_30. '
            'Unique per geographic scope.'
        ),
    )

    fee_name = models.CharField(
        _('fee name'),
        max_length=200,
        help_text=_('Human-readable name, e.g. "Normal Registration Fee".'),
    )

    # ── Service Classification ─────────────────────────────────────────────────
    service_type = models.CharField(
        _('service type'),
        max_length=40,
        choices=ServiceType.choices,
        db_index=True,
        help_text=_('The Birth & Death service this fee applies to.'),
    )

    # ── Calculation ───────────────────────────────────────────────────────────
    calculation_type = models.CharField(
        _('calculation type'),
        max_length=10,
        choices=CalculationType.choices,
        default=CalculationType.FIXED,
        help_text=_(
            'FIXED: flat amount. FREE: always zero. '
            'PER_YEAR: multiply by years. MANUAL: officer determined.'
        ),
    )

    amount = models.DecimalField(
        _('amount'),
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text=_('Fee amount in the configured currency. Set to 0.00 for FREE services.'),
    )

    currency = models.CharField(
        _('currency'),
        max_length=3,
        default='INR',
        help_text=_('ISO 4217 currency code. Default: INR.'),
    )

    # ── Geographic Scope ──────────────────────────────────────────────────────
    state_code = models.CharField(
        _('state code'),
        max_length=10,
        blank=True,
        default='',
        db_index=True,
        help_text=_(
            'State identifier, e.g. RJ for Rajasthan. '
            'Leave blank for a global/default fee.'
        ),
    )

    district = models.ForeignKey(
        'geography.District',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='fee_rules',
        verbose_name=_('district'),
        help_text=_('District-level override. Leave blank for state/global scope.'),
    )

    ulb = models.ForeignKey(
        'geography.ULB',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='fee_rules',
        verbose_name=_('ULB'),
        help_text=_('ULB-level override. Leave blank for district/state/global scope.'),
    )

    # ── Effective Dates ───────────────────────────────────────────────────────
    effective_from = models.DateField(
        _('effective from'),
        default=timezone.localdate,
        db_index=True,
        help_text=_('Date from which this fee record is in force.'),
    )

    effective_to = models.DateField(
        _('effective to'),
        null=True,
        blank=True,
        help_text=_(
            'Date until which this fee is in force. '
            'Leave blank for an open-ended / current fee. '
            'Do NOT overwrite an old fee — set effective_to and create a new record.'
        ),
    )

    # ── Legal Reference ───────────────────────────────────────────────────────
    rule_reference = models.CharField(
        _('rule reference'),
        max_length=300,
        blank=True,
        default='',
        help_text=_(
            'Source rule/notification, e.g. '
            '"Rajasthan Registration of Births and Deaths (Amendment) Rules, 2025".'
        ),
    )

    notes = models.TextField(
        _('notes'),
        blank=True,
        default='',
        help_text=_('Internal notes about this fee record.'),
    )

    # ── Status & Timestamps ───────────────────────────────────────────────────
    is_active = models.BooleanField(
        _('active'),
        default=True,
        db_index=True,
    )

    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    # ── Meta ──────────────────────────────────────────────────────────────────
    class Meta:
        verbose_name        = _('Fee Master')
        verbose_name_plural = _('Fee Master Records')
        ordering            = ['service_type', 'fee_code']

        # Prevent duplicate fee rules for the same service + geographic scope
        unique_together = [
            ('fee_code', 'state_code', 'district', 'ulb'),
        ]

        indexes = [
            models.Index(
                fields=['service_type', 'is_active', 'effective_from'],
                name='fm_service_active_date_idx',
            ),
            models.Index(
                fields=['state_code', 'district', 'ulb', 'is_active'],
                name='fm_geo_scope_idx',
            ),
        ]

    def __str__(self):
        scope_parts = []
        if self.ulb:
            scope_parts.append(f'ULB:{self.ulb.code}')
        elif self.district:
            scope_parts.append(f'District:{self.district.code}')
        elif self.state_code:
            scope_parts.append(f'State:{self.state_code}')
        else:
            scope_parts.append('Global')
        scope = ', '.join(scope_parts)
        return f'[{self.fee_code}] {self.fee_name} — ₹{self.amount} ({scope})'
