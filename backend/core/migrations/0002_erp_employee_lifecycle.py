from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='erpevent', name='processed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='erpevent', name='processing_error',
            field=models.TextField(blank=True),
        ),
        migrations.CreateModel(
            name='ERPEmployeeMapping',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('external_id', models.CharField(max_length=128)),
                ('connector', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='employee_mappings', to='core.erpconnector')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='erp_employee_mapping', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='erpemployeemapping',
            constraint=models.UniqueConstraint(fields=('connector', 'external_id'), name='unique_erp_employee_identity'),
        ),
    ]
