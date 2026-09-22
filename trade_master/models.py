from django.db import models


class TradeCategory(models.Model):
    code        = models.CharField(max_length=20, unique=True, db_index=True)
    name        = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active   = models.BooleanField(default=True, db_index=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering    = ['name']
        verbose_name_plural = 'Trade Categories'

    def __str__(self):
        return f'{self.name} ({self.code})'


class Trade(models.Model):
    category    = models.ForeignKey(
        TradeCategory, on_delete=models.PROTECT, related_name='trades'
    )
    code        = models.CharField(max_length=20, unique=True, db_index=True)
    name        = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active   = models.BooleanField(default=True, db_index=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'name']
        indexes  = [models.Index(fields=['category', 'is_active'])]

    def __str__(self):
        return f'{self.name} ({self.code})'


class SubTrade(models.Model):
    trade       = models.ForeignKey(
        Trade, on_delete=models.PROTECT, related_name='sub_trades'
    )
    code        = models.CharField(max_length=20)
    name        = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active   = models.BooleanField(default=True, db_index=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering        = ['trade', 'name']
        unique_together = [('trade', 'code')]
        indexes         = [models.Index(fields=['trade', 'is_active'])]

    def __str__(self):
        return f'{self.name} ({self.code}) — {self.trade.code}'


class ULBTradeConfig(models.Model):
    """
    Controls which trades are enabled for a specific ULB.
    Allows different ULBs to offer different trade lists without
    altering the core Trade/SubTrade master records.
    Sub-trade–level overrides can be added here as needed in future phases.
    """
    ulb         = models.ForeignKey(
        'geography.ULB', on_delete=models.PROTECT, related_name='trade_configs'
    )
    trade       = models.ForeignKey(
        Trade, on_delete=models.PROTECT, related_name='ulb_configs'
    )
    is_enabled  = models.BooleanField(default=True, db_index=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('ulb', 'trade')]
        ordering        = ['ulb', 'trade']
        indexes         = [models.Index(fields=['ulb', 'is_enabled'])]

    def __str__(self):
        status = 'enabled' if self.is_enabled else 'disabled'
        return f'{self.ulb.code} — {self.trade.code} [{status}]'
