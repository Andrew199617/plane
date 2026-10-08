# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity teams.

`Team` itself lives in workspace.py (upstream CE stub) and gained `default_project_role` and
`auto_join`. This module adds the membership (TeamMember) and project-link (TeamProject) tables.
Behavior (provisioning ProjectMember rows, auto-join) lives in plane.utils.teams.
"""

# Django imports
from django.conf import settings
from django.db import models
from django.db.models import Q

# Module imports
from .base import BaseModel
from .project import ProjectBaseModel
from .workspace import Team  # noqa: F401  (re-export for convenience)


class TeamMember(BaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="workspace_team_members")
    team = models.ForeignKey("db.Team", on_delete=models.CASCADE, related_name="team_members")
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="team_memberships")

    class Meta:
        unique_together = ["team", "member", "deleted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "member"],
                condition=Q(deleted_at__isnull=True),
                name="team_member_unique_team_member_active",
            )
        ]
        verbose_name = "Team Member"
        verbose_name_plural = "Team Members"
        db_table = "team_members"
        ordering = ("-created_at",)

    def save(self, *args, **kwargs):
        if not self.workspace_id and self.team_id:
            self.workspace_id = self.team.workspace_id
        super(TeamMember, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.team_id} {self.member_id}"


class TeamProject(ProjectBaseModel):
    """Links a team to a project; team members are provisioned as ProjectMembers of the project."""

    team = models.ForeignKey("db.Team", on_delete=models.CASCADE, related_name="team_projects")

    class Meta:
        unique_together = ["team", "project", "deleted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "project"],
                condition=Q(deleted_at__isnull=True),
                name="team_project_unique_team_project_active",
            )
        ]
        verbose_name = "Team Project"
        verbose_name_plural = "Team Projects"
        db_table = "team_projects"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.team_id} {self.project_id}"
