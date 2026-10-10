"""
bd_registration/services.py
============================
Delay registration rules engine for the
Municipal Birth & Death Certificate Management System.

Source: Rajasthan Registration of Births and Deaths (Amendment) Rules, 2025
        (published in Rajasthan Gazette, February 07, 2025)
        amending Rajasthan Registration of Births and Deaths Rules, 2000.

Date arithmetic follows Rule 5(2) and Rule 9 (as amended):
    Rule 5(2): information shall be given within 21 days from the event date.
    Rule 9(i):  >21 days to within 30 days → late fee of Rs. 20 (no authority permission).
    Rule 9(ii): >30 days to within 1 year  → written permission of District Registrar
                or Block Statistical Officer or any officer authorized by Chief Registrar
                (Births & Deaths) + Form No. 14 + late fee of Rs. 50.
    Rule 9(iii):>1 year                    → order of District Magistrate or
                Sub-Divisional Magistrate or Executive Magistrate authorized by DM
                + late fee of Rs. 100.

Boundary behaviour:
    delay_days = 0   → NORMAL      (same-day reporting)
    delay_days = 21  → NORMAL      (exactly 21 days — within normal window per Rule 5(2))
    delay_days = 22  → DELAYED_30_DAYS
    delay_days = 30  → DELAYED_30_DAYS (Rule 9(i): "within thirty days")
    delay_days = 31  → DELAYED_1_YEAR
    1-year boundary  → anniversary-based (handles leap years correctly)
    delay > 1 year   → DELAYED_ABOVE_1_YEAR

Design principles
-----------------
- The delay category is ALWAYS computed from dates — never stored by users.
- No rule amounts are hard-coded in this file; they come from FeeMaster.
- No authority designations are hard-coded; they come from DelayRule.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from django.db import models as dj_models
from django.utils import timezone

from bd_master.models import DelayCategory, DelayRule

logger = logging.getLogger(__name__)


# ─── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class DelayResult:
    """
    Immutable result object returned by DelayCalculationService.calculate().

    Fields
    ------
    delay_days              Number of calendar days between event and reporting.
    delay_category          One of the DelayCategory values.
    is_normal               True when delay_category is NORMAL.
    fee_code                FeeMaster fee_code for the applicable fee.
    applicable_fee          Decimal fee amount (0 for FREE / NORMAL).
    currency                ISO currency code (INR by default).
    requires_authority      True when authority permission is required.
    authority_code          AuthorityType.code or None.
    authority_name          AuthorityType.name or None.
    authority_notes         Additional notes on the authority requirement.
    requires_form_14        True when Form 14 must be submitted.
    requires_affidavit      True when self-attested affidavit is required.
    requires_permission_order True when a formal permission order is required.
    required_document_codes List of DocumentType.code values.
    required_document_names List of DocumentType.name values.
    rule_reference          Source legal reference for the rule.
    rule_code               DelayRule.rule_code or empty string.
    error                   Non-empty if calculation failed (invalid input etc.).
    """
    delay_days:               int
    delay_category:           str
    is_normal:                bool
    fee_code:                 str
    applicable_fee:           Decimal
    currency:                 str
    requires_authority:       bool
    authority_code:           Optional[str]
    authority_name:           Optional[str]
    authority_notes:          str
    requires_form_14:         bool
    requires_affidavit:       bool
    requires_permission_order: bool
    required_document_codes:  list = field(default_factory=list)
    required_document_names:  list = field(default_factory=list)
    rule_reference:           str  = ''
    rule_code:                str  = ''
    error:                    str  = ''


# ─── Delay constants ─────────────────────────────────────────────────────────
# Boundary values from Rajasthan RBD Rules 2000 as amended by 2025 Amendment.
# Rule 5(2): normal window = within 21 days.
# Rule 9(i): >21 to within 30 days (late fee Rs. 20, no authority).
# Rule 9(ii): >30 days to within 1 year (District Registrar/BSO/authorized, Form 14, Rs. 50).
# Rule 9(iii): >1 year (DM/SDM/Executive Magistrate order, Rs. 100).

_NORMAL_MAX_DAYS      = 21   # ≤21 days → NORMAL (Rule 5(2))
_DELAYED_30_MAX_DAYS  = 30   # >21 to ≤30 days → DELAYED_30_DAYS (Rule 9(i))
# >30 days to ≤1 year → DELAYED_1_YEAR (Rule 9(ii)) — 1-year boundary is anniversary-based
# >1 year → DELAYED_ABOVE_1_YEAR (Rule 9(iii))


def _compute_delay_days(event_date: date, date_of_reporting: date) -> int:
    """Return calendar days between event and reporting (reporting − event)."""
    return (date_of_reporting - event_date).days


def _is_within_one_year(event_date: date, date_of_reporting: date) -> bool:
    """
    True when date_of_reporting is within one calendar year of event_date.

    Rule 9(ii) 2025: "within one year of its occurrence"
    Rule 9(iii) 2025: "after one year of its occurrence"

    Uses anniversary-based comparison (event_date + 1 year) to handle
    leap years correctly (e.g. event on 2024-02-29 → anniversary is 2025-02-28).
    If date_of_reporting <= anniversary → DELAYED_1_YEAR (within 1 year).
    If date_of_reporting > anniversary → DELAYED_ABOVE_1_YEAR (after 1 year).
    """
    try:
        anniversary = event_date.replace(year=event_date.year + 1)
    except ValueError:
        # event_date is Feb 29 and next year is not a leap year
        anniversary = event_date.replace(year=event_date.year + 1, day=28)
    return date_of_reporting <= anniversary


def _classify_delay(event_date: date, date_of_reporting: date) -> tuple[int, str]:
    """
    Compute delay_days and return (delay_days, DelayCategory).
    Caller must validate that event_date <= date_of_reporting before calling.
    """
    delay_days = _compute_delay_days(event_date, date_of_reporting)

    if delay_days <= _NORMAL_MAX_DAYS:
        return delay_days, DelayCategory.NORMAL

    if delay_days <= _DELAYED_30_MAX_DAYS:
        return delay_days, DelayCategory.DELAYED_30_DAYS

    if _is_within_one_year(event_date, date_of_reporting):
        return delay_days, DelayCategory.DELAYED_1_YEAR

    return delay_days, DelayCategory.DELAYED_ABOVE_1_YEAR


def _fetch_fee(fee_code: str, state_code: str, as_of: date) -> tuple[Decimal, str, str]:
    """
    Look up the fee for a fee_code from FeeMaster.
    Returns (amount, currency, actual_fee_code).
    Falls back to amount=0 / currency=INR if no record found.
    """
    if not fee_code:
        return Decimal('0.00'), 'INR', ''

    try:
        from fee_master.models import FeeMaster
        from django.db.models import Q

        qs = FeeMaster.objects.filter(
            fee_code=fee_code,
            is_active=True,
            effective_from__lte=as_of,
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=as_of)
        )

        # Prefer most specific geographic scope: ULB → District → State → Global
        record = (
            qs.filter(state_code=state_code).exclude(district=None).exclude(ulb=None).first()
            or qs.filter(state_code=state_code, district=None, ulb=None).first()
            or qs.filter(state_code='', district=None, ulb=None).first()
            or qs.first()
        )

        if record:
            return record.amount, record.currency, record.fee_code

    except Exception:
        logger.exception('DelayCalculationService: error fetching fee for %s', fee_code)

    return Decimal('0.00'), 'INR', fee_code


def _fetch_delay_rule(
    delay_category: str,
    state_code: str,
    as_of: date,
) -> Optional[DelayRule]:
    """
    Fetch the most specific active DelayRule for a given category and state.
    Geographic precedence: ULB (not implemented in this lookup — add if needed)
    → District → State → Global.
    """
    try:
        from django.db.models import Q

        qs = DelayRule.objects.filter(
            delay_category=delay_category,
            is_active=True,
            effective_from__lte=as_of,
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=as_of)
        ).prefetch_related('required_documents').select_related('authority_type')

        return (
            qs.filter(state_code=state_code, district=None, ulb=None).first()
            or qs.filter(state_code='', district=None, ulb=None).first()
            or qs.first()
        )

    except Exception:
        logger.exception(
            'DelayCalculationService: error fetching delay rule for %s/%s',
            delay_category, state_code,
        )
        return None


# ─── Service ──────────────────────────────────────────────────────────────────

class DelayCalculationService:
    """
    Stateless service. All methods are classmethods.
    Instantiation is not required.

    Usage:
        result = DelayCalculationService.calculate(
            event_date=...,
            date_of_reporting=...,
            state_code='RJ',
        )
    """

    @classmethod
    def calculate(
        cls,
        event_date: date,
        date_of_reporting: date,
        state_code: str = '',
        as_of: Optional[date] = None,
    ) -> DelayResult:
        """
        Main entry point.

        Parameters
        ----------
        event_date        Date of birth or death.
        date_of_reporting Date the informant reported to the Registrar.
                          (Application.date_of_reporting)
        state_code        State identifier e.g. 'RJ' for Rajasthan.
        as_of             Date for fee/rule effective-date lookup.
                          Defaults to today.

        Returns
        -------
        DelayResult — always returns a result object; check result.error
        for validation failures.
        """
        as_of = as_of or timezone.localdate()

        # ── Input validation ──────────────────────────────────────────────────
        if not event_date or not date_of_reporting:
            return cls._error_result('event_date and date_of_reporting are required.')

        today = timezone.localdate()

        if event_date > today:
            return cls._error_result(
                'Event date is in the future. Future event dates are not valid.'
            )

        if date_of_reporting > today:
            return cls._error_result(
                'Date of reporting is in the future.'
            )

        if date_of_reporting < event_date:
            return cls._error_result(
                f'Date of reporting ({date_of_reporting}) cannot be before '
                f'event date ({event_date}).'
            )

        # ── Classify ──────────────────────────────────────────────────────────
        delay_days, delay_category = _classify_delay(event_date, date_of_reporting)

        # ── Fetch matching DelayRule ───────────────────────────────────────────
        rule = _fetch_delay_rule(delay_category, state_code, as_of)

        # ── Fetch fee from FeeMaster ──────────────────────────────────────────
        fee_code = rule.fee_code if rule else ''
        amount, currency, resolved_fee_code = _fetch_fee(fee_code, state_code, as_of)

        # ── Build result ──────────────────────────────────────────────────────
        if rule is None:
            # No rule configured — return category + fee but flag missing config
            logger.warning(
                'DelayCalculationService: no DelayRule found for '
                'category=%s state=%s as_of=%s', delay_category, state_code, as_of
            )
            return DelayResult(
                delay_days=delay_days,
                delay_category=delay_category,
                is_normal=(delay_category == DelayCategory.NORMAL),
                fee_code=resolved_fee_code,
                applicable_fee=amount,
                currency=currency,
                requires_authority=False,
                authority_code=None,
                authority_name=None,
                authority_notes='',
                requires_form_14=False,
                requires_affidavit=False,
                requires_permission_order=False,
                required_document_codes=[],
                required_document_names=[],
                rule_reference='',
                rule_code='',
                error='No delay rule configured for this category/state.',
            )

        doc_codes = list(rule.required_documents.values_list('code', flat=True))
        doc_names = list(rule.required_documents.values_list('name', flat=True))

        return DelayResult(
            delay_days=delay_days,
            delay_category=delay_category,
            is_normal=(delay_category == DelayCategory.NORMAL),
            fee_code=resolved_fee_code,
            applicable_fee=amount,
            currency=currency,
            requires_authority=rule.requires_authority_permission,
            authority_code=(
                rule.authority_type.code if rule.authority_type else None
            ),
            authority_name=(
                rule.authority_type.name if rule.authority_type else None
            ),
            authority_notes=rule.authority_notes,
            requires_form_14=rule.requires_form_14,
            requires_affidavit=rule.requires_self_attested_affidavit,
            requires_permission_order=rule.requires_permission_order,
            required_document_codes=doc_codes,
            required_document_names=doc_names,
            rule_reference=rule.rule_reference,
            rule_code=rule.rule_code,
            error='',
        )

    @classmethod
    def is_delayed(cls, event_date: date, date_of_reporting: date) -> bool:
        """
        Quick check: returns True if delay > 21 days.
        Does NOT query the database. Safe to call anywhere.
        """
        if not event_date or not date_of_reporting:
            return False
        if date_of_reporting < event_date:
            return False
        return _compute_delay_days(event_date, date_of_reporting) > _NORMAL_MAX_DAYS

    @staticmethod
    def _error_result(message: str) -> DelayResult:
        return DelayResult(
            delay_days=0,
            delay_category='',
            is_normal=False,
            fee_code='',
            applicable_fee=Decimal('0.00'),
            currency='INR',
            requires_authority=False,
            authority_code=None,
            authority_name=None,
            authority_notes='',
            requires_form_14=False,
            requires_affidavit=False,
            requires_permission_order=False,
            required_document_codes=[],
            required_document_names=[],
            rule_reference='',
            rule_code='',
            error=message,
        )
