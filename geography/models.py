from django.db import models
from django.utils.translation import gettext_lazy as _


class ULBType(models.TextChoices):
    NAGAR_NIGAM    = 'NAGAR_NIGAM',    _('Nagar Nigam')
    NAGAR_PARISHAD = 'NAGAR_PARISHAD', _('Nagar Parishad')
    NAGAR_PALIKA   = 'NAGAR_PALIKA',   _('Nagar Palika')
    OTHER          = 'OTHER',          _('Other')


class District(models.Model):
    code       = models.CharField(max_length=20, unique=True, db_index=True)
    name       = models.CharField(max_length=100)
    is_active  = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.code})'


class ULB(models.Model):
    district   = models.ForeignKey(
        District, on_delete=models.PROTECT, related_name='ulbs'
    )
    code       = models.CharField(max_length=20, unique=True, db_index=True)
    name       = models.CharField(max_length=150)
    ulb_type   = models.CharField(max_length=20, choices=ULBType.choices)
    is_active  = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes  = [models.Index(fields=['district', 'is_active'])]

    def __str__(self):
        return f'{self.name} ({self.code})'


class Zone(models.Model):
    ulb        = models.ForeignKey(
        ULB, on_delete=models.PROTECT, related_name='zones'
    )
    code       = models.CharField(max_length=20)
    name       = models.CharField(max_length=100)
    is_active  = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering        = ['ulb', 'name']
        unique_together = [('ulb', 'code')]
        indexes         = [models.Index(fields=['ulb', 'is_active'])]

    def __str__(self):
        return f'{self.name} — {self.ulb.code}'


class Ward(models.Model):
    zone        = models.ForeignKey(
        Zone, on_delete=models.PROTECT, related_name='wards'
    )
    code        = models.CharField(max_length=20)
    name        = models.CharField(max_length=100)
    is_active   = models.BooleanField(default=True, db_index=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering        = ['zone', 'code']
        unique_together = [('zone', 'code')]
        indexes         = [models.Index(fields=['zone', 'is_active'])]

    def __str__(self):
        return f'{self.name} ({self.code}) — {self.zone.ulb.code}'
