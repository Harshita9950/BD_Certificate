"""
workflow_master/management/commands/seed_bd_workflow.py
=========================================================
Idempotent management command that creates (or verifies) the default
Birth & Death Registration workflow and its steps for every active ULB.

Safe to run multiple times — uses get_or_create throughout so no
duplicate records are produced and no existing data is overwritten.

Usage
-----
    python manage.py seed_bd_workflow              # all active ULBs
    python manage.py seed_bd_workflow --ulb JMC    # single ULB by code
    python manage.py seed_bd_workflow --dry-run    # print plan, no writes

Workflow
--------
    code : BD_DEFAULT
    name : Birth & Death Registration — Default Workflow
    type : BIRTH_DEATH

Steps (step_number, code, name, role_code)
------------------------------------------
    1  SURVEY_MAIL     Survey Mail          DA
    2  SCRUTINY        Scrutiny             DA
    3  FIELD_VERIFY    Field Verification   HEALTH_OFFICER
    4  APPROVAL        Approval             OFFICER
    5  REGISTRATION    Registration         OFFICER

Design rules
------------
- unique_together on Workflow is (ulb, application_type, code) so
  get_or_create will never produce duplicates for the same ULB.
- unique_together on WorkflowStep is (workflow, step_number) and
  (workflow, code) — both checked by get_or_create.
- Existing records are left unchanged (no update_or_create).
  Pass --force-update to overwrite name/description on existing steps.
- No database PKs are hardcoded anywhere.
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from geography.models import ULB
from users.models import ApplicationCode
from workflow_master.models import Workflow, WorkflowStep

logger = logging.getLogger(__name__)

# ─── Default step definitions ─────────────────────────────────────────────────
# Order matters: step_number is the canonical sequence.
# role_code values match UserRole choices in users/models.py.

DEFAULT_STEPS = [
    {
        'step_number': 1,
        'code':        'SURVEY_MAIL',
        'name':        'Survey Mail',
        'description': 'Initial survey mail dispatched to the informant.',
        'role_code':   'DA',
    },
    {
        'step_number': 2,
        'code':        'SCRUTINY',
        'name':        'Scrutiny',
        'description': 'Document and data scrutiny by the Dealing Assistant.',
        'role_code':   'DA',
    },
    {
        'step_number': 3,
        'code':        'FIELD_VERIFY',
        'name':        'Field Verification',
        'description': 'On-ground verification by Health Officer.',
        'role_code':   'HEALTH_OFFICER',
    },
    {
        'step_number': 4,
        'code':        'APPROVAL',
        'name':        'Approval',
        'description': 'Approval by Licensing Officer.',
        'role_code':   'OFFICER',
    },
    {
        'step_number': 5,
        'code':        'REGISTRATION',
        'name':        'Registration',
        'description': 'Final registration and certificate issuance.',
        'role_code':   'OFFICER',
    },
]

WORKFLOW_CODE        = 'BD_DEFAULT'
WORKFLOW_NAME        = 'Birth & Death Registration — Default Workflow'
WORKFLOW_DESCRIPTION = (
    'Default five-step workflow for Birth & Death Certificate registrations '
    'under the Rajasthan RBD Act. Seeded by seed_bd_workflow management command.'
)


class Command(BaseCommand):
    help = (
        'Idempotently create the default Birth & Death workflow and steps '
        'for every active ULB (or a specific ULB with --ulb).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--ulb',
            type=str,
            default=None,
            help='ULB code to seed (default: all active ULBs).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Print what would be created without writing to the database.',
        )
        parser.add_argument(
            '--force-update',
            action='store_true',
            default=False,
            help=(
                'Update name/description on EXISTING steps. '
                'Does not change step_number, code, or role_code. '
                'Use with care in production.'
            ),
        )

    def handle(self, *args, **options):
        ulb_code     = options['ulb']
        dry_run      = options['dry_run']
        force_update = options['force_update']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no database writes.'))

        # ── Resolve ULBs ──────────────────────────────────────────────────────
        qs = ULB.objects.filter(is_active=True)
        if ulb_code:
            qs = qs.filter(code=ulb_code)
            if not qs.exists():
                raise CommandError(
                    f'No active ULB with code "{ulb_code}" found.'
                )

        ulbs = list(qs.order_by('code'))
        self.stdout.write(f'Processing {len(ulbs)} ULB(s)…')

        created_workflows  = 0
        existing_workflows = 0
        created_steps      = 0
        existing_steps     = 0

        for ulb in ulbs:
            wf_created, step_counts = self._seed_for_ulb(
                ulb, dry_run, force_update
            )
            if wf_created:
                created_workflows += 1
            else:
                existing_workflows += 1
            created_steps  += step_counts['created']
            existing_steps += step_counts['existing']

        # ── Summary ───────────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('── Seed complete ──'))
        self.stdout.write(
            f'  Workflows  : {created_workflows} created, {existing_workflows} already existed'
        )
        self.stdout.write(
            f'  Steps      : {created_steps} created, {existing_steps} already existed'
        )
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes written.'))

    def _seed_for_ulb(self, ulb, dry_run: bool, force_update: bool):
        """
        Seed one Workflow + steps for a single ULB.
        Returns (workflow_was_created: bool, step_counts: dict).
        """
        self.stdout.write(f'  ULB {ulb.code} — {ulb.name}')

        if dry_run:
            wf_exists = Workflow.objects.filter(
                ulb=ulb,
                application_type=ApplicationCode.BIRTH_DEATH,
                code=WORKFLOW_CODE,
            ).exists()
            status = 'EXISTS' if wf_exists else 'WOULD CREATE'
            self.stdout.write(
                f'    Workflow {WORKFLOW_CODE}: {status}'
            )
            for step in DEFAULT_STEPS:
                self.stdout.write(
                    f'    Step {step["step_number"]:>2}. '
                    f'{step["code"]:<15} ({step["role_code"]})'
                )
            return (not wf_exists), {'created': len(DEFAULT_STEPS), 'existing': 0}

        with transaction.atomic():
            workflow, wf_created = Workflow.objects.get_or_create(
                ulb=ulb,
                application_type=ApplicationCode.BIRTH_DEATH,
                code=WORKFLOW_CODE,
                defaults={
                    'name':        WORKFLOW_NAME,
                    'description': WORKFLOW_DESCRIPTION,
                    'is_active':   True,
                },
            )

            action = 'CREATED' if wf_created else 'EXISTS'
            self.stdout.write(
                f'    Workflow {WORKFLOW_CODE}: {action} (pk={workflow.pk})'
            )

            step_counts = {'created': 0, 'existing': 0}

            for step_def in DEFAULT_STEPS:
                step, step_created = WorkflowStep.objects.get_or_create(
                    workflow=workflow,
                    step_number=step_def['step_number'],
                    defaults={
                        'code':        step_def['code'],
                        'name':        step_def['name'],
                        'description': step_def['description'],
                        'role_code':   step_def['role_code'],
                        'is_active':   True,
                    },
                )

                if step_created:
                    step_counts['created'] += 1
                    step_action = 'CREATED'
                else:
                    step_counts['existing'] += 1
                    step_action = 'EXISTS'
                    if force_update:
                        # Only safe fields — never change step_number, code, role_code
                        updated = False
                        if step.name != step_def['name']:
                            step.name = step_def['name']
                            updated = True
                        if step.description != step_def['description']:
                            step.description = step_def['description']
                            updated = True
                        if updated:
                            step.save(update_fields=['name', 'description', 'updated_at'])
                            step_action = 'UPDATED'

                self.stdout.write(
                    f'    Step {step.step_number:>2}. '
                    f'{step.code:<15} ({step.role_code}): {step_action}'
                )

            return wf_created, step_counts
