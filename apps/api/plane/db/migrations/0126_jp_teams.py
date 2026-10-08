# Jira-parity teams: Team.default_project_role / auto_join + TeamMember + TeamProject.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _audit_fields():
    return [
        ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
        ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Last Modified At")),
        ("deleted_at", models.DateTimeField(blank=True, null=True, verbose_name="Deleted At")),
        (
            "id",
            models.UUIDField(
                db_index=True,
                default=uuid.uuid4,
                editable=False,
                primary_key=True,
                serialize=False,
                unique=True,
            ),
        ),
        (
            "created_by",
            models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(class)s_created_by",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Created By",
            ),
        ),
        (
            "updated_by",
            models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(class)s_updated_by",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Last Modified By",
            ),
        ),
    ]


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0125_jp_workflows"),
    ]

    operations = [
        migrations.AddField(
            model_name="team",
            name="auto_join",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="team",
            name="default_project_role",
            field=models.PositiveSmallIntegerField(default=15),
        ),
        migrations.CreateModel(
            name="TeamMember",
            fields=[
                *_audit_fields(),
                (
                    "member",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="team_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="team_members",
                        to="db.team",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workspace_team_members",
                        to="db.workspace",
                    ),
                ),
            ],
            options={
                "verbose_name": "Team Member",
                "verbose_name_plural": "Team Members",
                "db_table": "team_members",
                "ordering": ("-created_at",),
                "unique_together": {("team", "member", "deleted_at")},
            },
        ),
        migrations.AddConstraint(
            model_name="teammember",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=("team", "member"),
                name="team_member_unique_team_member_active",
            ),
        ),
        migrations.CreateModel(
            name="TeamProject",
            fields=[
                *_audit_fields(),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="project_%(class)s",
                        to="db.project",
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="team_projects",
                        to="db.team",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workspace_%(class)s",
                        to="db.workspace",
                    ),
                ),
            ],
            options={
                "verbose_name": "Team Project",
                "verbose_name_plural": "Team Projects",
                "db_table": "team_projects",
                "ordering": ("-created_at",),
                "unique_together": {("team", "project", "deleted_at")},
            },
        ),
        migrations.AddConstraint(
            model_name="teamproject",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=("team", "project"),
                name="team_project_unique_team_project_active",
            ),
        ),
    ]
