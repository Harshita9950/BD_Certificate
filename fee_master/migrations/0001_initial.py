# Generated for Birth & Death Certificate Management System
# Replaces old Trade License-specific fee_master migrations.
# No dependency on trade_master.

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        # Geography FK targets — geography must be migrated first
        ('geography', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='FeeMaster',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True,
                    primary_key=True,
                    serialize=False,
                    verbose_name='ID',
                )),
                ('fee_code', models.CharField(
                    db_index=True,
                    max_length=60,
                    verbose_name='fee code',
                    help_text='Machine-readable code, e.g. BD.REG_NORMAL, BD.LATE_30.',
                )),
                ('fee_name', models.CharField(
                    max_length=200,
                    verbose_name='fee name',
                )),
                ('service_type', models.CharField(
                    choices=[
                        ('BIRTH_REGISTRATION',         'Birth Registration'),
                        ('DEATH_REGISTRATION',         'Death Registration'),
                        ('STILL_BIRTH_REGISTRATION',   'Still Birth Registration'),
                        ('ADOPTED_BIRTH_REGISTRATION', 'Adopted Child Birth Registration'),
                        ('DELAYED_REGISTRATION',       'Delayed Registration'),
                        ('CERTIFICATE_COPY',           'Certified Certificate Copy'),
                        ('REGISTER_SEARCH',            'Register Search'),
                        ('NON_AVAILABILITY_CERT',      'Non-Availability Certificate'),
                        ('NAME_ADDITION',              'Name Addition'),
                        ('CORRECTION',                 'Correction'),
                        ('CANCELLATION',               'Cancellation'),
                        ('APPEAL',                     'Appeal'),
                        ('POSTAL_DELIVERY',            'Postal Delivery'),
                        ('ORIGINAL_CERTIFICATE',       'Original Certificate After Registration'),
                        ('OTHER',                      'Other'),
                    ],
                    db_index=True,
                    max_length=40,
                    verbose_name='service type',
                )),
                ('calculation_type', models.CharField(
                    choices=[
                        ('FIXED',    'Fixed Amount'),
                        ('FREE',     'Free / No Charge'),
                        ('PER_YEAR', 'Per Year'),
                        ('MANUAL',   'Manual / Officer Determined'),
                    ],
                    default='FIXED',
                    max_length=10,
                    verbose_name='calculation type',
                )),
                ('amount', models.DecimalField(
                    decimal_places=2,
                    default=0,
                    max_digits=10,
                    verbose_name='amount',
                )),
                ('currency', models.CharField(
                    default='INR',
                    max_length=3,
                    verbose_name='currency',
                )),
                ('state_code', models.CharField(
                    blank=True,
                    db_index=True,
                    default='',
                    max_length=10,
                    verbose_name='state code',
                )),
                ('district', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='fee_rules',
                    to='geography.district',
                    verbose_name='district',
                )),
                ('ulb', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='fee_rules',
                    to='geography.ulb',
                    verbose_name='ULB',
                )),
                ('effective_from', models.DateField(
                    db_index=True,
                    default=django.utils.timezone.localdate,
                    verbose_name='effective from',
                )),
                ('effective_to', models.DateField(
                    blank=True,
                    null=True,
                    verbose_name='effective to',
                )),
                ('rule_reference', models.CharField(
                    blank=True,
                    default='',
                    max_length=300,
                    verbose_name='rule reference',
                )),
                ('notes', models.TextField(
                    blank=True,
                    default='',
                    verbose_name='notes',
                )),
                ('is_active', models.BooleanField(
                    db_index=True,
                    default=True,
                    verbose_name='active',
                )),
                ('created_at', models.DateTimeField(
                    auto_now_add=True,
                    verbose_name='created at',
                )),
                ('updated_at', models.DateTimeField(
                    auto_now=True,
                    verbose_name='updated at',
                )),
            ],
            options={
                'verbose_name':        'Fee Master',
                'verbose_name_plural': 'Fee Master Records',
                'ordering':            ['service_type', 'fee_code'],
            },
        ),

        # Unique constraint: one fee code per geographic scope
        migrations.AddConstraint(
            model_name='feemaster',
            constraint=models.UniqueConstraint(
                fields=['fee_code', 'state_code', 'district', 'ulb'],
                name='unique_fee_code_per_scope',
            ),
        ),

        # Composite indexes for fast lookups
        migrations.AddIndex(
            model_name='feemaster',
            index=models.Index(
                fields=['service_type', 'is_active', 'effective_from'],
                name='fm_service_active_date_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='feemaster',
            index=models.Index(
                fields=['state_code', 'district', 'ulb', 'is_active'],
                name='fm_geo_scope_idx',
            ),
        ),
    ]
