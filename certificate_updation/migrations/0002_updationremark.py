from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('certificate_updation', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UpdationRemark',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(max_length=50)),
                ('step_name', models.CharField(blank=True, default='', max_length=150)),
                ('step_role', models.CharField(blank=True, default='', max_length=50)),
                ('remark', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('officer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='updation_remarks', to=settings.AUTH_USER_MODEL)),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='remarks', to='certificate_updation.certificateupdationrequest')),
            ],
            options={'ordering': ['created_at']},
        ),
    ]
