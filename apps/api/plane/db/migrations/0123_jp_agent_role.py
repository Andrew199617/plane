# Jira-parity: add the Agent role (10) to workspace/project member and invite role choices.
# Choices-only change (no DDL). 0076 rewrote the legacy 10 ("Viewer") to 5 on member rows only, so
# pending invites still carrying the legacy 10 are rewritten to 5 here (they would otherwise become
# Agent invites). Reverse: every remaining role-10 row (members and invites) becomes Guest (5).

from django.db import migrations, models


ROLE_CHOICES = [(20, "Admin"), (15, "Member"), (10, "Agent"), (5, "Guest")]


def remap_legacy_viewer_invites(apps, schema_editor):
    for model_name in ("WorkspaceMemberInvite", "ProjectMemberInvite"):
        apps.get_model("db", model_name).objects.filter(role=10).update(role=5)


def remove_agent_role(apps, schema_editor):
    for model_name in ("WorkspaceMember", "ProjectMember", "WorkspaceMemberInvite", "ProjectMemberInvite"):
        apps.get_model("db", model_name).objects.filter(role=10).update(role=5)


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0122_alter_draftissue_assignees_alter_issue_assignees_and_more"),
    ]

    operations = [
        migrations.RunPython(remap_legacy_viewer_invites, remove_agent_role),
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
