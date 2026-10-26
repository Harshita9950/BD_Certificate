"""
Management command: seed_updation_workflow

Creates the BD_UPDATION workflow for all active ULBs, mirroring the
step structure of BD_DEFAULT but with independent step instances.

Usage:
    python manage.py seed_updation_workflow
    python manage.py seed_updation_workflow --ulb=1   # specific ULB
"""

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Seed BD_UPDATION workflow for all active ULBs (mirrors BD_DEFAULT steps).'

    def add_arguments(self, parser):
        parser.add_argument('--ulb', type=int, default=None, help='Seed for a specific ULB pk only.')

    def handle(self, *args, **options):
        from geography.models import ULB
        from users.models import ApplicationCode
        from workflow_master.models import Workflow, WorkflowStep

        ulb_qs = ULB.objects.filter(is_active=True)
        if options['ulb']:
            ulb_qs = ulb_qs.filter(pk=options['ulb'])

        created_count = 0
        skipped_count = 0

        for ulb in ulb_qs:
            # Find the reference BD_DEFAULT workflow for this ULB
            default_wf = Workflow.objects.filter(
                ulb=ulb,
                application_type=ApplicationCode.BIRTH_DEATH,
                code='BD_DEFAULT',
                is_active=True,
            ).first()

            if default_wf is None:
                self.stdout.write(self.style.WARNING(
                    f'  ULB {ulb.code}: no BD_DEFAULT workflow found — skipping.'
                ))
                continue

            with transaction.atomic():
                # Create or skip BD_UPDATION workflow
                upd_wf, created = Workflow.objects.get_or_create(
                    ulb=ulb,
                    application_type=ApplicationCode.BIRTH_DEATH,
                    code='BD_UPDATION',
                    defaults={
                        'name': f'Certificate Updation — {ulb.name}',
                        'description': (
                            'Workflow for certificate correction/updation requests. '
                            'Independent of the new-registration workflow.'
                        ),
                        'is_active': True,
                    },
                )

                if not created:
                    self.stdout.write(f'  ULB {ulb.code}: BD_UPDATION already exists — skipping.')
                    skipped_count += 1
                    continue

                # Copy steps from BD_DEFAULT
                default_steps = WorkflowStep.objects.filter(
                    workflow=default_wf,
                    is_active=True,
                ).order_by('step_number')

                for step in default_steps:
                    WorkflowStep.objects.create(
                        workflow=upd_wf,
                        step_number=step.step_number,
                        code=step.code,
                        name=step.name,
                        description=step.description,
                        role_code=step.role_code,
                        is_active=True,
                    )

                self.stdout.write(self.style.SUCCESS(
                    f'  ULB {ulb.code}: BD_UPDATION created with {default_steps.count()} steps.'
                ))
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Created: {created_count}, Skipped (already existed): {skipped_count}.'
        ))
