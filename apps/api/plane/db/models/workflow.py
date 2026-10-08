# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity workflows: role-based state transition rules.

A row allows the project roles in `roles` (ProjectMember.role values, e.g. 15 Member, 10 Agent,
5 Guest) to move a work item from `from_state` (NULL = any state) to `to_state`.
`exclude_epics=True` means the rule does not apply to epics. Rules are only enforced when
`Project.is_workflow_enabled` is True. All enforcement lives in plane.utils.workflow.
"""

# Django imports
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

# Module imports
from .project import ProjectBaseModel


class StateTransition(ProjectBaseModel):
    from_state = models.ForeignKey(
        "db.State",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="transitions_from",
    )
    to_state = models.ForeignKey("db.State", on_delete=models.CASCADE, related_name="transitions_to")
    roles = ArrayField(models.PositiveSmallIntegerField(), default=list, blank=True)
    exclude_epics = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "State Transition"
        verbose_name_plural = "State Transitions"
        db_table = "state_transitions"
        ordering = ("created_at",)
        constraints = [
            # At most one rule per (from, to) pair and epic scope; NULL from_state counts as a value.
            models.UniqueConstraint(
                fields=["project", "from_state", "to_state", "exclude_epics"],
                condition=Q(deleted_at__isnull=True),
                nulls_distinct=False,
                name="state_transition_unique_when_deleted_at_null",
            )
        ]
        indexes = [models.Index(fields=["project", "is_active"], name="state_trans_project_active_idx")]

    def __str__(self):
        return f"{self.project_id}: {self.from_state_id or '*'} -> {self.to_state_id} {self.roles}"
