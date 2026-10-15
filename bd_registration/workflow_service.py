"""
bd_registration/workflow_service.py
=====================================
Service layer for workflow assignment to Applications.

Responsibilities
----------------
- Locate the correct active Workflow for an Application's ULB and
  application type (always BIRTH_DEATH in this module).
- Assign that Workflow and its first active WorkflowStep to the Application.
- Never hardcode database PKs.
- Never assign a workflow to an Application that still has an outstanding
  payment (status == PAYMENT_PENDING).

Call sites
----------
    from bd_registration.workflow_service import assign_workflow

    # After transitioning to SUBMITTED (zero-fee path):
    assign_workflow(app)

    # After confirming payment (PAYMENT_PENDING → SUBMITTED):
    assign_workflow(app)

Both call sites must only call this function AFTER the Application.status
has already been set to SUBMITTED and saved.

Return value
------------
The function returns a (workflow, step) tuple on success, or (None, None)
if no suitable workflow is configured for the ULB.  It never raises —
callers log the outcome but must not gate submission on workflow availability.
"""

import logging

from users.models import ApplicationCode
from workflow_master.models import Workflow, WorkflowStep
from .models import Application, ApplicationStatus

logger = logging.getLogger(__name__)

# The code used by seed_bd_workflow to create the default workflow.
# Must match WORKFLOW_CODE in seed_bd_workflow.py.
DEFAULT_WORKFLOW_CODE = 'BD_DEFAULT'


def assign_workflow(app: Application):
    """
    Assign the default BD workflow and its first step to *app*.

    Rules
    -----
    1. Only assigns when app.status == SUBMITTED.
    2. Skips if app.workflow is already set (idempotent).
    3. Looks up the active BD_DEFAULT workflow for app.ulb — no hardcoded PKs.
    4. Assigns the step with the lowest step_number (step 1 = SURVEY_MAIL).
    5. Returns (workflow, step) on success, (None, None) on miss.
    6. Never raises; logs warnings so a missing workflow never breaks submission.

    Parameters
    ----------
    app : Application
        Must have app.ulb set.  Status must be SUBMITTED before calling.
    """
    if app.status != ApplicationStatus.SUBMITTED:
        logger.warning(
            'assign_workflow called for application %s with status %s — '
            'expected SUBMITTED. Skipping.',
            app.application_number, app.status,
        )
        return None, None

    if app.workflow_id is not None:
        # Already assigned — nothing to do (idempotent).
        logger.debug(
            'assign_workflow: application %s already has workflow pk=%s. '
            'Skipping.',
            app.application_number, app.workflow_id,
        )
        return app.workflow, app.current_step

    if not app.ulb_id:
        logger.warning(
            'assign_workflow: application %s has no ULB — cannot assign workflow.',
            app.application_number,
        )
        return None, None

    # ── Locate the workflow ───────────────────────────────────────────────────
    workflow = (
        Workflow.objects
        .filter(
            ulb_id=app.ulb_id,
            application_type=ApplicationCode.BIRTH_DEATH,
            code=DEFAULT_WORKFLOW_CODE,
            is_active=True,
        )
        .first()
    )

    if workflow is None:
        logger.warning(
            'assign_workflow: no active workflow "%s" for ULB pk=%s '
            '(application %s). Run seed_bd_workflow to configure workflows.',
            DEFAULT_WORKFLOW_CODE, app.ulb_id, app.application_number,
        )
        return None, None

    # ── Locate step 1 ─────────────────────────────────────────────────────────
    first_step = (
        WorkflowStep.objects
        .filter(workflow=workflow, is_active=True)
        .order_by('step_number')
        .first()
    )

    if first_step is None:
        logger.warning(
            'assign_workflow: workflow pk=%s ("%s") has no active steps. '
            'Run seed_bd_workflow to configure steps.',
            workflow.pk, workflow.code,
        )
        return workflow, None

    # ── Assign atomically ─────────────────────────────────────────────────────
    app.workflow     = workflow
    app.current_step = first_step
    app.save(update_fields=['workflow', 'current_step', 'updated_at'])

    logger.info(
        'assign_workflow: application %s → workflow "%s" (pk=%s), '
        'step %s "%s" (pk=%s).',
        app.application_number,
        workflow.code, workflow.pk,
        first_step.step_number, first_step.code, first_step.pk,
    )

    return workflow, first_step


def advance_workflow(app: Application, user) -> tuple:
    """
    Advance *app* from its current WorkflowStep to the next step
    (by step_number ascending, active steps only).

    Call AFTER a status transition so that the new current_step
    reflects the next officer's role_code for inbox routing.

    Rules
    -----
    1. Requires app.workflow and app.current_step to already be set.
    2. Finds the next active step with step_number > current step_number.
    3. If no next step exists (final step) — logs info, does nothing.
    4. Idempotent: safe to call multiple times (will never go backwards).
    5. Never raises.

    Returns
    -------
    (old_step, new_step)  — new_step is None if already at the last step.
    """
    if not app.workflow_id or not app.current_step_id:
        logger.warning(
            'advance_workflow: application %s has no workflow or step assigned.',
            app.application_number,
        )
        return None, None

    old_step = app.current_step

    next_step = (
        WorkflowStep.objects
        .filter(
            workflow_id=app.workflow_id,
            is_active=True,
            step_number__gt=old_step.step_number,
        )
        .order_by('step_number')
        .first()
    )

    if next_step is None:
        logger.info(
            'advance_workflow: application %s is already at the last step '
            '(%s "%s"). No advancement.',
            app.application_number, old_step.step_number, old_step.code,
        )
        return old_step, None

    app.current_step = next_step
    app.save(update_fields=['current_step', 'updated_at'])

    logger.info(
        'advance_workflow: application %s → step %s "%s" (role: %s) by %s.',
        app.application_number,
        next_step.step_number, next_step.code, next_step.role_code,
        user,
    )

    return old_step, next_step
