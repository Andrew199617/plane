# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity project categories (e.g. Mobile, Web, Platform).

Projects point to a category through Project.category (SET_NULL). An optional master-board
IssueView can point to a category through IssueView.category. Behavior lives in
plane.utils.project_categories.
"""

# Django imports
from django.db import models
from django.db.models import Q

# Module imports
from .base import BaseModel


class ProjectCategory(BaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="project_categories")
    name = models.CharField(max_length=255, verbose_name="Category Name")
    description = models.TextField(blank=True, default="")
    sort_order = models.FloatField(default=65535)
    logo_props = models.JSONField(default=dict)
    external_source = models.CharField(max_length=255, null=True, blank=True)
    external_id = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        unique_together = ["workspace", "name", "deleted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "name"],
                condition=Q(deleted_at__isnull=True),
                name="project_category_unique_workspace_name_when_deleted_at_null",
            )
        ]
        verbose_name = "Project Category"
        verbose_name_plural = "Project Categories"
        db_table = "project_categories"
        ordering = ("sort_order", "name")

    def save(self, *args, **kwargs):
        # New categories go last unless an explicit sort_order was given
        if self._state.adding and self.sort_order == 65535:
            largest = ProjectCategory.objects.filter(workspace_id=self.workspace_id).aggregate(
                largest=models.Max("sort_order")
            )["largest"]
            if largest is not None:
                self.sort_order = largest + 10000
        super(ProjectCategory, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} <{self.workspace_id}>"
