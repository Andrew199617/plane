# Jira-parity project categories: ProjectCategory + Project.category (SET_NULL)
# + IssueView.category (optional master-board view of a category).

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0126_jp_teams"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectCategory",
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
                ("name", models.CharField(max_length=255, verbose_name="Category Name")),
                ("description", models.TextField(blank=True, default="")),
                ("sort_order", models.FloatField(default=65535)),
                ("logo_props", models.JSONField(default=dict)),
                ("external_source", models.CharField(blank=True, max_length=255, null=True)),
                ("external_id", models.CharField(blank=True, max_length=255, null=True)),
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
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="project_categories",
                        to="db.workspace",
                    ),
                ),
            ],
            options={
                "verbose_name": "Project Category",
                "verbose_name_plural": "Project Categories",
                "db_table": "project_categories",
                "ordering": ("sort_order", "name"),
                "unique_together": {("workspace", "name", "deleted_at")},
            },
        ),
        migrations.AddConstraint(
            model_name="projectcategory",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=("workspace", "name"),
                name="project_category_unique_workspace_name_when_deleted_at_null",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="projects",
                to="db.projectcategory",
            ),
        ),
        migrations.AddField(
            model_name="issueview",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="board_views",
                to="db.projectcategory",
            ),
        ),
        migrations.AddConstraint(
            model_name="issueview",
            constraint=models.UniqueConstraint(
                condition=models.Q(("category__isnull", False), ("deleted_at__isnull", True)),
                fields=("category",),
                name="issue_view_unique_category_board_when_deleted_at_null",
            ),
        ),
    ]
