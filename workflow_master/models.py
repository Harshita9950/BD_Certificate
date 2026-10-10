from django.db import models
from users.models import ApplicationCode


class Workflow(models.Model):
    application_type = models.CharField(
        max_length=50,
        choices=ApplicationCode.choices,
        default=ApplicationCode.BIRTH_DEATH,
        db_index=True,
    )
    ulb = models.ForeignKey(
        'geography.ULB',
        on_delete=models.PROTECT,
        related_name='workflows',
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['ulb', 'name']
        unique_together = [('ulb', 'application_type', 'code')]
        indexes = [
            models.Index(fields=['ulb', 'application_type', 'is_active']),
        ]

    def __str__(self):
        return f'{self.name} — {self.ulb.code}'

class WorkflowStep(models.Model):
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name='steps',
    )
    step_number = models.PositiveIntegerField()
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    role_code = models.CharField(max_length=30)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['workflow', 'step_number']
        unique_together = [
            ('workflow', 'step_number'),
            ('workflow', 'code'),
        ]
        indexes = [
            models.Index(fields=['workflow', 'step_number']),
        ]

    def __str__(self):
        return f'{self.workflow.code} — {self.step_number}. {self.name}'