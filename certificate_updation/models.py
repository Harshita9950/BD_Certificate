"""
certificate_updation/models.py
================================
Models for the Certificate Updation module.

Design principles
-----------------
- CertificateUpdationRequest is the core request record.
- It references the original Application (the registered certificate).
- Proposed changes are stored as JSON (field-level old/new values).
- Workflow status mirrors the existing ApplicationStatus choices subset.
- A separate UpdationStatusHistory table is the immutable audit trail.
- The original BirthRegistration / DeathRegistration records are NEVER
  touched until final approval — rejected requests leave them untouched.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from bd_registration.models import Application


# ─── Status choices for updation requests ────────────────────────────────────

class UpdationStatus(models.TextChoices):
    DRAFT          = 'DRAFT',          _('Draft')
    SUBMITTED      = 'SUBMITTED',      _('Submitted')
    UNDER_SCRUTINY = 'UNDER_SCRUTINY', _('Under Scrutiny')
    UNDER_PROCESS  = 'UNDER_PROCESS',  _('Under Process')
    APPROVED       = 'APPROVED',       _('Approved')
    REJECTED       = 'REJECTED',       _('Rejected')
    CANCELLED      = 'CANCELLED',      _('Cancelled')


# ─── Main updation request ───────────────────────────────────────────────────

class CertificateUpdationRequest(models.Model):
    """
    A request to update the details on an already-registered certificate.

    The proposed_changes JSON field stores field-level diffs:
        {
            "child_first_name": {"old": "Komal", "new": "Kamla"},
            "mother_name":      {"old": "Sheela", "new": "Sheila"},
        }

    Changes are applied to BirthRegistration / DeathRegistration only
    after status reaches APPROVED.
    """

    # ── Unique reference ──────────────────────────────────────────────────────
    reference = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False,
        help_text='Unique idempotency key for this request.',
    )

    # ── Original certificate reference ────────────────────────────────────────
    original_application = models.ForeignKey(
        Application,
        on_delete=models.PROTECT,
        related_name='updation_requests',
        help_text='The original REGISTERED application whose certificate is being updated.',
    )

    # ── Request details ───────────────────────────────────────────────────────
    certificate_number = models.CharField(
        max_length=50, db_index=True,
        help_text='Registration/certificate number from the original record (copied on creation).',
    )
    service_type = models.CharField(
        max_length=40,
        help_text='BIRTH_REGISTRATION or DEATH_REGISTRATION (copied from original application).',
        db_index=True,
    )
    update_reason = models.TextField(
        help_text='Reason provided by the applicant for requesting the update.',
    )

    # ── Proposed changes (field-level old/new) ────────────────────────────────
    proposed_changes = models.JSONField(
        default=dict,
        help_text=(
            'Dict of {field_name: {old: ..., new: ...}} for every changed field. '
            'Read-only after submission. Used to apply changes on approval.'
        ),
    )

    # ── Workflow ──────────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=UpdationStatus.choices,
        default=UpdationStatus.DRAFT,
        db_index=True,
    )
    workflow = models.ForeignKey(
        'workflow_master.Workflow',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='updation_requests',
    )
    current_step = models.ForeignKey(
        'workflow_master.WorkflowStep',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='updation_requests',
    )

    # ── People ────────────────────────────────────────────────────────────────
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='submitted_updation_requests',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'service_type']),
            models.Index(fields=['submitted_by', 'status']),
            models.Index(fields=['certificate_number']),
        ]

    def __str__(self):
        return f'UPD-{self.pk} | {self.certificate_number} | {self.status}'

    @property
    def smart_status(self):
        """Show 'Pending at {step}' for in-workflow statuses."""
        IN_WORKFLOW = {
            UpdationStatus.SUBMITTED,
            UpdationStatus.UNDER_SCRUTINY,
            UpdationStatus.UNDER_PROCESS,
        }
        if self.status in IN_WORKFLOW:
            try:
                if self.current_step_id:
                    return f'Pending at {self.current_step.name}'
            except Exception:
                pass
            return 'Pending'
        return self.get_status_display()


# ─── Immutable audit trail ───────────────────────────────────────────────────

class UpdationStatusHistory(models.Model):
    """
    Immutable audit trail for every status transition on a
    CertificateUpdationRequest. Records must never be deleted.
    """

    request = models.ForeignKey(
        CertificateUpdationRequest,
        on_delete=models.CASCADE,
        related_name='status_history',
    )
    old_status = models.CharField(max_length=20, blank=True, default='')
    new_status = models.CharField(max_length=20, choices=UpdationStatus.choices)
    action = models.CharField(
        max_length=50,
        help_text='Machine-readable action code: UPD_CREATED, UPD_SUBMITTED, UPD_FORWARDED, UPD_APPROVED, UPD_REJECTED.',
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='updation_status_changes',
    )
    changed_at = models.DateTimeField(default=timezone.now, db_index=True)
    remarks = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['changed_at']
        default_permissions = ('view',)
        indexes = [
            models.Index(fields=['request', 'changed_at']),
        ]

    def __str__(self):
        return f'{self.request} | {self.action} @ {self.changed_at:%d-%m-%Y %H:%M}'


# ─── Per-action Remark Log ────────────────────────────────────────────────────

class UpdationRemark(models.Model):
    """
    Stores the remark entered by an officer at each action (Forward/Reject/Approve).
    Separate from UpdationStatusHistory so the remark can be queried independently.
    """

    request = models.ForeignKey(
        CertificateUpdationRequest,
        on_delete=models.CASCADE,
        related_name='remarks',
    )
    action = models.CharField(
        max_length=50,
        help_text='Action code: UPD_FORWARDED, UPD_REJECTED, UPD_APPROVED.',
    )
    step_name = models.CharField(
        max_length=150, blank=True, default='',
        help_text='Workflow step name at the time of this remark.',
    )
    step_role = models.CharField(
        max_length=50, blank=True, default='',
        help_text='Role code of the step at the time of this remark.',
    )
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='updation_remarks',
    )
    remark = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Remark by {self.officer} on request {self.request_id} — {self.action}'
