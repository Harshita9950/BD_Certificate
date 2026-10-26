"""
certificate_updation/workflow_service.py
==========================================
Workflow assignment and advancement for Certificate Updation requests.
Mirrors bd_registration/workflow_service.py but operates on
CertificateUpdationRequest objects and uses BD_UPDATION workflow code.
"""

import logging

from users.models import ApplicationCode
from workflow_master.models import Workflow, WorkflowStep

logger = logging.getLogger(__name__)

UPDATION_WORKFLOW_CODE = 'BD_UPDATION'


def assign_updation_workflow(req):
    """
    Assign the BD_UPDATION workflow and its first step to an updation request.

    Parameters
    ----------
    req : CertificateUpdationRequest
        Must have req.original_application.ulb set.

    Returns (workflow, step) on success, (None, None) on miss. Never raises.
    """
    from .models import UpdationStatus

    if req.status != UpdationStatus.SUBMITTED:
        logger.warning(
            'assign_updation_workflow called for request %s with status %s — '
            'expected SUBMITTED. Skipping.',
            req.pk, req.status,
        )
        return None, None

    if req.workflow_id is not None:
        return req.workflow, req.current_step

    ulb_id = req.original_application.ulb_id if req.original_application_id else None
    if not ulb_id:
        logger.warning(
            'assign_updation_workflow: request %s has no ULB — cannot assign workflow.',
            req.pk,
        )
        return None, None

    workflow = (
        Workflow.objects
        .filter(
            ulb_id=ulb_id,
            application_type=ApplicationCode.BIRTH_DEATH,
            code=UPDATION_WORKFLOW_CODE,
            is_active=True,
        )
        .first()
    )

    if workflow is None:
        logger.warning(
            'assign_updation_workflow: no active workflow "%s" for ULB pk=%s. '
            'Run seed_updation_workflow to configure.',
            UPDATION_WORKFLOW_CODE, ulb_id,
        )
        return None, None

    first_step = (
        WorkflowStep.objects
        .filter(workflow=workflow, is_active=True)
        .order_by('step_number')
        .first()
    )

    if first_step is None:
        logger.warning(
            'assign_updation_workflow: workflow pk=%s has no active steps.', workflow.pk,
        )
        return workflow, None

    req.workflow = workflow
    req.current_step = first_step
    req.save(update_fields=['workflow', 'current_step', 'updated_at'])
    logger.info(
        'Updation request %s assigned workflow "%s" step %s "%s".',
        req.pk, workflow.code, first_step.step_number, first_step.name,
    )
    return workflow, first_step


def advance_updation_workflow(req, user):
    """
    Advance the current_step to the next active step in the updation workflow.
    Mirrors advance_workflow from bd_registration/workflow_service.py.

    Returns (old_step, new_step). Never raises.
    """
    if not req.workflow_id or not req.current_step_id:
        logger.warning(
            'advance_updation_workflow: request %s has no workflow/step assigned.', req.pk,
        )
        return None, None

    old_step = req.current_step
    next_step = (
        WorkflowStep.objects
        .filter(
            workflow_id=req.workflow_id,
            is_active=True,
            step_number__gt=old_step.step_number,
        )
        .order_by('step_number')
        .first()
    )

    if next_step is None:
        logger.info(
            'advance_updation_workflow: request %s is at last step %s.',
            req.pk, old_step.step_number,
        )
        return old_step, None

    req.current_step = next_step
    req.save(update_fields=['current_step', 'updated_at'])
    logger.info(
        'Updation request %s advanced: step %s → %s by %s.',
        req.pk, old_step.step_number, next_step.step_number, user,
    )
    return old_step, next_step


def is_last_updation_step(req):
    """Return True if the current step is the last active step in the workflow."""
    if not req.workflow_id or not req.current_step_id:
        return False
    try:
        return not WorkflowStep.objects.filter(
            workflow_id=req.workflow_id,
            is_active=True,
            step_number__gt=req.current_step.step_number,
        ).exists()
    except Exception:
        return False
