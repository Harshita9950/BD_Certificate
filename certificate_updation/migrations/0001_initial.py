from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('bd_registration', '0003_remove_application_state_and_more'),
        ('workflow_master', '__first__'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CertificateUpdationRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('certificate_number', models.CharField(db_index=True, max_length=50)),
                ('service_type', models.CharField(db_index=True, max_length=40)),
                ('update_reason', models.TextField()),
                ('proposed_changes', models.JSONField(default=dict)),
                ('status', models.CharField(choices=[('DRAFT', 'Draft'), ('SUBMITTED', 'Submitted'), ('UNDER_SCRUTINY', 'Under Scrutiny'), ('UNDER_PROCESS', 'Under Process'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected'), ('CANCELLED', 'Cancelled')], db_index=True, default='DRAFT', max_length=20)),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('current_step', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='updation_requests', to='workflow_master.workflowstep')),
                ('original_application', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='updation_requests', to='bd_registration.application')),
                ('submitted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='submitted_updation_requests', to=settings.AUTH_USER_MODEL)),
                ('workflow', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='updation_requests', to='workflow_master.workflow')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='UpdationStatusHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('old_status', models.CharField(blank=True, default='', max_length=20)),
                ('new_status', models.CharField(choices=[('DRAFT', 'Draft'), ('SUBMITTED', 'Submitted'), ('UNDER_SCRUTINY', 'Under Scrutiny'), ('UNDER_PROCESS', 'Under Process'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected'), ('CANCELLED', 'Cancelled')], max_length=20)),
                ('action', models.CharField(max_length=50)),
                ('changed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='updation_status_changes', to=settings.AUTH_USER_MODEL)),
                ('changed_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('remarks', models.TextField(blank=True, default='')),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='status_history', to='certificate_updation.certificateupdationrequest')),
            ],
            options={
                'ordering': ['changed_at'],
                'default_permissions': ('view',),
            },
        ),
        migrations.AddIndex(
            model_name='certificateupdationrequest',
            index=models.Index(fields=['status', 'service_type'], name='cert_upd_status_stype_idx'),
        ),
        migrations.AddIndex(
            model_name='certificateupdationrequest',
            index=models.Index(fields=['submitted_by', 'status'], name='cert_upd_sub_status_idx'),
        ),
        migrations.AddIndex(
            model_name='certificateupdationrequest',
            index=models.Index(fields=['certificate_number'], name='cert_upd_cert_no_idx'),
        ),
        migrations.AddIndex(
            model_name='updationstatushistory',
            index=models.Index(fields=['request', 'changed_at'], name='upd_hist_req_at_idx'),
        ),
    ]
