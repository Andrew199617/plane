# Jira-parity time tracking: Issue.original_estimate / remaining_estimate (minutes, nullable).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0127_jp_project_categories"),
    ]

    operations = [
        migrations.AddField(
            model_name="issue",
            name="original_estimate",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="issue",
            name="remaining_estimate",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
