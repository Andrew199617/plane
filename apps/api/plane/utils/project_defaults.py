# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity project lead / default assignee service.

Behavior:
- On project creation the project lead defaults to the creator (actor) when unset, and the
  default assignee defaults to the project lead when unset. Both are ensured as project
  members through `ensure_project_member` (the lead as Admin).
- On project update, when the lead changes and the default assignee was the old lead (or
  unset) and the request did not pick another default assignee, the default assignee follows
  the new lead.
- Work items created without assignees get the project's default assignee
  (`assign_default_assignee`, used by the intake paths that bypass the issue serializers).

Project roles are never raised above what the workspace role allows: workspace Agents (10)
and Guests (5) are never made project Admins, and users who are not active workspace members
are never added to a project.
"""

# Python imports
import logging
import uuid

# Django imports
from django.db import IntegrityError, transaction

# Module imports
from plane.db.models import IssueAssignee, Project, ProjectMember, WorkspaceMember
from plane.db.models.project import ROLE
from plane.utils.exception_logger import log_exception
from plane.utils.project_membership import ensure_project_member

logger = logging.getLogger("plane.api")

_MISSING = object()


def _to_user_id(value):
    """Normalize a user reference (User, UUID, str, {"id": ...}) to a UUID, or None."""
    if value is None or value == "" or value == "none":
        return None
    if isinstance(value, dict):
        value = value.get("id")
        if value is None:
            return None
    if not isinstance(value, (str, uuid.UUID)) and hasattr(value, "pk"):
        value = value.pk
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _workspace_role(project, user_id):
    """Active workspace role of `user_id` in the project's workspace, or None."""
    return (
        WorkspaceMember.objects.filter(workspace_id=project.workspace_id, member_id=user_id, is_active=True)
        .values_list("role", flat=True)
        .first()
    )


def _capped_project_role(requested_role, workspace_role):
    """Workspace Members/Admins may hold any project role; Agents/Guests are capped at their role."""
    requested_role = requested_role.value if isinstance(requested_role, ROLE) else int(requested_role)
    if workspace_role >= ROLE.MEMBER.value:
        return requested_role
    return min(requested_role, workspace_role)


def ensure_lead_membership(project, user_id, *, update_role=True):
    """Ensure the project lead is an (Admin) member of the project. Returns the ProjectMember or None."""
    user_id = _to_user_id(user_id)
    if user_id is None:
        return None
    workspace_role = _workspace_role(project, user_id)
    if workspace_role is None:
        return None
    return ensure_project_member(
        project, user_id, _capped_project_role(ROLE.ADMIN, workspace_role), update_role=update_role
    )


def ensure_default_assignee_membership(project, user_id):
    """Ensure the default assignee is a project member (Member role when newly added; existing roles kept)."""
    user_id = _to_user_id(user_id)
    if user_id is None:
        return None
    workspace_role = _workspace_role(project, user_id)
    if workspace_role is None:
        return None
    return ensure_project_member(project, user_id, _capped_project_role(ROLE.MEMBER, workspace_role), update_role=False)


def _persist(project, **values):
    """Write FK id values with a queryset update (no save() side effects) and mirror them on the instance."""
    if not values:
        return
    Project.objects.filter(pk=project.pk).update(**values)
    for field, value in values.items():
        setattr(project, field, value)


def apply_project_lead_defaults(project, actor):
    """Fill project_lead / default_assignee on a newly created `project` (actor = creator).
    Called last by run_project_created_hooks.

    - project_lead: the creator when unset (only when the creator is a workspace Member/Admin).
    - default_assignee: the project lead when unset.
    - the lead is ensured as a project Admin; the default assignee as a project member.
    """
    updates = {}

    lead_id = project.project_lead_id
    if lead_id is None and actor is not None and getattr(actor, "is_authenticated", False):
        actor_role = _workspace_role(project, actor.id)
        if actor_role is not None and actor_role >= ROLE.MEMBER.value and not getattr(actor, "is_bot", False):
            lead_id = actor.id
            updates["project_lead_id"] = lead_id

    if lead_id is not None:
        ensure_lead_membership(project, lead_id)

    default_assignee_id = project.default_assignee_id
    if default_assignee_id is None and lead_id is not None:
        default_assignee_id = lead_id
        updates["default_assignee_id"] = default_assignee_id

    if default_assignee_id is not None and default_assignee_id != lead_id:
        ensure_default_assignee_membership(project, default_assignee_id)

    _persist(project, **updates)
    return updates


def apply_project_lead_change(project, *, old_lead_id, old_default_assignee_id, requested_data=None):
    """Keep the default assignee in step with the project lead after a project update.

    Call after the update has been saved. When the lead changed:
    - the new lead is ensured as a project member (Admin when newly added; existing roles kept);
    - if the default assignee was the old lead or unset, and the request did not explicitly pick
      a different default assignee, the default assignee follows the new lead.
    A default assignee explicitly changed by the request is ensured as a project member.

    Returns a dict of the fields this function changed ({} when nothing changed). Never raises:
    the project update has already been saved, so a failure here is logged and ignored.
    """
    try:
        with transaction.atomic():
            return _apply_project_lead_change(
                project,
                old_lead_id=old_lead_id,
                old_default_assignee_id=old_default_assignee_id,
                requested_data=requested_data,
            )
    except Exception as e:  # noqa: BLE001 - never fail an already-saved project update
        logger.warning("Jira-parity lead/default-assignee sync failed for project %s: %s", project.pk, e)
        log_exception(e)
        return {}


def _apply_project_lead_change(project, *, old_lead_id, old_default_assignee_id, requested_data):
    requested_data = requested_data or {}
    old_lead_id = _to_user_id(old_lead_id)
    old_default_assignee_id = _to_user_id(old_default_assignee_id)
    new_lead_id = _to_user_id(project.project_lead_id)
    current_default_id = _to_user_id(project.default_assignee_id)

    requested_default = requested_data.get("default_assignee", _MISSING) if hasattr(requested_data, "get") else _MISSING
    default_changed_by_request = requested_default is not _MISSING and _to_user_id(requested_default) != (
        old_default_assignee_id
    )

    updates = {}
    if new_lead_id != old_lead_id:
        if new_lead_id is not None:
            ensure_lead_membership(project, new_lead_id, update_role=False)
        follows_lead = old_default_assignee_id is None or old_default_assignee_id == old_lead_id
        if not default_changed_by_request and follows_lead and current_default_id != new_lead_id:
            updates["default_assignee_id"] = new_lead_id
            current_default_id = new_lead_id

    if default_changed_by_request and current_default_id is not None and current_default_id != new_lead_id:
        ensure_default_assignee_membership(project, current_default_id)

    _persist(project, **updates)
    return updates


def assign_default_assignee(issue, default_assignee_id=_MISSING):
    """Assign the project's default assignee to `issue` when it has no assignees.

    Mirrors the issue create serializers (app + v1): the default assignee must be an active
    project member that can be assigned (Agent role or above; Guests cannot). Returns True when
    an assignee was added.
    """
    if default_assignee_id is _MISSING:
        default_assignee_id = (
            Project.objects.filter(pk=issue.project_id).values_list("default_assignee_id", flat=True).first()
        )
    if default_assignee_id is None:
        return False
    if IssueAssignee.objects.filter(issue_id=issue.id).exists():
        return False
    if not ProjectMember.objects.filter(
        member_id=default_assignee_id,
        project_id=issue.project_id,
        role__gte=ROLE.AGENT.value,
        is_active=True,
    ).exists():
        return False
    try:
        with transaction.atomic():
            IssueAssignee.objects.create(
                assignee_id=default_assignee_id,
                issue=issue,
                project_id=issue.project_id,
                workspace_id=issue.workspace_id,
                created_by_id=issue.created_by_id,
                updated_by_id=issue.updated_by_id,
            )
    except IntegrityError:
        return False
    return True
