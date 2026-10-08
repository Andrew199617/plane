# Jira-parity work item types: IssueType.is_sub_task + unique (workspace, name) for live types.
# Seeding of the Task/Story/Bug/Sub-task/Epic types is done in code
# (plane.utils.work_item_types + setup_jira_parity), not here.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0128_jp_issue_estimates"),
    ]

    operations = [
        migrations.AddField(
            model_name="issuetype",
            name="is_sub_task",
            field=models.BooleanField(default=False),
        ),
        migrations.AddConstraint(
            model_name="issuetype",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=("workspace", "name"),
                name="issue_type_unique_workspace_name_when_deleted_at_null",
            ),
        ),
    ]
