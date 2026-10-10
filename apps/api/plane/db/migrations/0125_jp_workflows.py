# Jira-parity workflows: Project.is_workflow_enabled + StateTransition rules table.

import uuid

import django.contrib.postgres.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0124_jp_priorities"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="is_workflow_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="StateTransition",
            fields=[
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
                    "roles",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.PositiveSmallIntegerField(), blank=True, default=list, size=None
                    ),
                ),
                ("exclude_epics", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
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
                (
                    "from_state",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transitions_from",
                        to="db.state",
                    ),
                ),
                (
                    "to_state",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transitions_to",
                        to="db.state",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="project_%(class)s",
                        to="db.project",
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
                "verbose_name": "State Transition",
                "verbose_name_plural": "State Transitions",
                "db_table": "state_transitions",
                "ordering": ("created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="statetransition",
            index=models.Index(fields=["project", "is_active"], name="state_trans_project_active_idx"),
        ),
        migrations.AddConstraint(
            model_name="statetransition",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=("project", "from_state", "to_state", "exclude_epics"),
                name="state_transition_unique_when_deleted_at_null",
                nulls_distinct=False,
            ),
        ),
    ]
