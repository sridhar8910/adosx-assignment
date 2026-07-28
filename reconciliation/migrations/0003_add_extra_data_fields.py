# Generated manually — adds extra_data JSONField to SystemARecord and SystemBEntry
# to capture any unexpected columns in future CSV exports without schema changes.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reconciliation", "0002_alter_disagreement_entry_id_b_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemarecord",
            name="extra_data",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="systembentry",
            name="extra_data",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
