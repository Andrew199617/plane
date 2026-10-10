# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Shared, idempotent project-membership helper (Jira-parity scaffold).

Every Jira-parity feature that adds people to projects (teams auto-join, agent sync, project
lead/default assignee, Jira import) goes through `ensure_project_member` so the rules stay in
one place:

- missing row      -> create it (ProjectMember.save also creates the ProjectUserProperty row)
- inactive row     -> reactivate it (is_active=True) with the requested role (the stale role of a
                      deactivated row never survives: callers cap the requested role)
- active row       -> set the requested role when `update_role` is True (the default)
- an active Admin (20) is NEVER downgraded, whatever the requested role
"""

# Python imports
import uuid

# Django imports
from django.db import IntegrityError, transaction

# Third party imports
from crum import get_current_user

# Module imports
from plane.db.models import ProjectMember, ProjectUserProperty
from plane.db.models.project import ROLE


def _role_value(role):
    return role.value if isinstance(role, ROLE) else int(role)


def _user_id(user):
    if user is None:
        raise ValueError("ensure_project_member requires a user")
    if isinstance(user, (uuid.UUID, str)):
        return uuid.UUID(str(user))
    return user.id


def _resolve_role(current_role, requested_role):
    """Never downgrade an active Admin; otherwise the requested role wins."""
    if current_role == ROLE.ADMIN.value and requested_role < ROLE.ADMIN.value:
        return current_role
    return requested_role


def _create_member(project, user_id, role):
    """Create the ProjectMember row.

    ProjectMember.save() unconditionally creates a ProjectUserProperty, which would violate the
    (user, project) unique constraint when a property row survived an earlier membership. In that
    case the member row is inserted with bulk_create (skips save()) and the property is reused.
    """
    if ProjectUserProperty.objects.filter(project_id=project.id, user_id=user_id).exists():
        current_user = get_current_user()
        member = ProjectMember(
            project_id=project.id,
            workspace_id=project.workspace_id,
            member_id=user_id,
            role=role,
            is_active=True,
            created_by_id=(current_user.id if current_user is not None and not current_user.is_anonymous else None),
        )
        ProjectMember.objects.bulk_create([member])
        return member
    return ProjectMember.objects.create(project=project, member_id=user_id, role=role, is_active=True)


def ensure_project_member(project, user, role, *, update_role=True):
    """Make sure `user` is an active member of `project` and return the ProjectMember.

    Args:
        project: db.Project instance.
        user: db.User instance or user id (UUID / str).
        role: int (20 Admin, 15 Member, 10 Agent, 5 Guest) or a ROLE enum member.
        update_role: when False, an already-active member keeps their current role
            (inactive rows are still reactivated with the requested role).

    Idempotent; safe to call repeatedly and inside an outer transaction.
    """
    role = _role_value(role)
    user_id = _user_id(user)

    member = ProjectMember.objects.filter(project_id=project.id, member_id=user_id).first()
    if member is None:
        try:
            with transaction.atomic():
                return _create_member(project, user_id, role)
        except IntegrityError:
            # Created concurrently; fall through to the update path.
            member = ProjectMember.objects.filter(project_id=project.id, member_id=user_id).first()
            if member is None:
                raise

    update_fields = []
    if not member.is_active:
        member.is_active = True
        update_fields.append("is_active")
        new_role = role
    elif update_role:
        new_role = _resolve_role(member.role, role)
    else:
        new_role = member.role

    if new_role != member.role:
        member.role = new_role
        update_fields.append("role")

    if update_fields:
        member.save(update_fields=[*update_fields, "updated_at", "updated_by"])
    return member
