# Jira-parity: add the Agent role (10) to workspace/project member and invite role choices.
# Choices-only change (no DDL). Value 10 is free: 0076 rewrote the legacy 10 ("Viewer") to 5.

from django.db import migrations, models


ROLE_CHOICES = [(20, "Admin"), (15, "Member"), (10, "Agent"), (5, "Guest")]


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0122_alter_draftissue_assignees_alter_issue_assignees_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="projectmember",
            name="role",
            field=models.PositiveSmallIntegerField(choices=ROLE_CHOICES, default=5),
        ),
        migrations.AlterField(
            model_name="projectmemberinvite",
            name="role",
            field=models.PositiveSmallIntegerField(choices=ROLE_CHOICES, default=5),
        ),
        migrations.AlterField(
            model_name="workspacemember",
            name="role",
            field=models.PositiveSmallIntegerField(choices=ROLE_CHOICES, default=5),
        ),
        migrations.AlterField(
            model_name="workspacememberinvite",
            name="role",
            field=models.PositiveSmallIntegerField(choices=ROLE_CHOICES, default=5),
        ),
    ]
