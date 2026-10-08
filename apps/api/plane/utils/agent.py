# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity agents service.

Agents are ordinary Users (is_bot=False, so they can be assigned and listed) whose
WorkspaceMember.role is ROLE.AGENT (10). They auto-join every project as ProjectMember role 10
(via plane.utils.project_membership.ensure_project_member) and authenticate to /api/v1 with
APIToken rows (X-Api-Key). What they may do is enforced by plane.app.permissions.agent.

Env AGENT_AUTO_JOIN_PROJECTS=0 disables the automatic project membership sync.
"""

# Python imports
import os
import uuid

# Django imports
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

# Module imports
from plane.db.models import (
    APIToken,
    Profile,
    Project,
    ProjectMember,
    User,
    UserNotificationPreference,
    WorkspaceMember,
)
from plane.db.models.project import ROLE
from plane.db.models.team import TeamMember
from plane.utils.project_membership import ensure_project_member
from plane.utils.teams import add_member_to_default_teams

AGENT = ROLE.AGENT.value
VALID_ROLES = {role.value for role in ROLE}


def auto_join_enabled():
    return os.environ.get("AGENT_AUTO_JOIN_PROJECTS", "1") == "1"


def agent_role_mismatch(workspace_role, project_role):
    """True when a project role is incoherent with the workspace role: workspace agents can only be
    project agents, and only workspace agents can hold the project Agent role."""
    try:
        project_role = int(project_role)
    except (TypeError, ValueError):
        project_role = None
    return (workspace_role == AGENT) != (project_role == AGENT)


def _user_ids(users):
    return [getattr(user, "id", user) for user in users]


def _sync_memberships(workspace, user_ids, projects=None):
    if projects is None:
        projects = Project.objects.filter(workspace_id=workspace.id, archived_at__isnull=True)
    count = 0
    for project in projects:
        for user_id in user_ids:
            ensure_project_member(project, user_id, AGENT)
            count += 1
    return count


def sync_agent_memberships(workspace, users=None, projects=None):
    """Make every active workspace agent (or only those of `users`) an active role-10 member of every
    non-archived project of `workspace` (or only `projects`). Idempotent; returns the number of
    (agent, project) pairs ensured. Called by run_project_created_hooks with projects=[project],
    on agent creation, on a workspace role change to Agent, and by `manage.py sync_agent_memberships`.
    """
    if not auto_join_enabled():
        return 0
    agents = WorkspaceMember.objects.filter(workspace_id=workspace.id, role=AGENT, is_active=True)
    if users is not None:
        agents = agents.filter(member_id__in=_user_ids(users))
    agent_ids = list(agents.values_list("member_id", flat=True))
    if not agent_ids:
        return 0
    return _sync_memberships(workspace, agent_ids, projects)


def onboard_invited_agent(user, workspace_ids):
    """After `user` joined workspaces through an invitation: for each workspace where they are now
    an active Agent (role 10), join every project as Agent and add them to the default Agents team.
    No-op for any other role. Returns the ids of the workspaces where the agent was onboarded."""
    user_id = getattr(user, "id", user)
    onboarded = []
    for workspace_member in WorkspaceMember.objects.filter(
        workspace_id__in=list(workspace_ids), member_id=user_id, role=AGENT, is_active=True
    ).select_related("workspace"):
        sync_agent_memberships(workspace_member.workspace, users=[user_id])
        add_member_to_default_teams(workspace_member.workspace, [user_id])
        onboarded.append(workspace_member.workspace_id)
    return onboarded


def apply_agent_workspace_role_change(workspace_member, new_role):
    """Keep project roles coherent when an admin changes a workspace member's role.

    Called BEFORE the new role is saved (workspace_member.role is still the old one).
    - new role Agent: every project membership becomes Agent, and the user joins every project
    - old role Agent, new role something else: agent project rows become min(new role, Member)
    """
    try:
        new_role = int(new_role)
    except (TypeError, ValueError):
        return
    old_role = workspace_member.role
    if new_role not in VALID_ROLES or new_role == old_role:
        return
    memberships = ProjectMember.objects.filter(
        workspace_id=workspace_member.workspace_id, member_id=workspace_member.member_id
    )
    if new_role == AGENT:
        memberships.update(role=AGENT)
        if auto_join_enabled():
            _sync_memberships(workspace_member.workspace, [workspace_member.member_id])
    elif old_role == AGENT:
        memberships.filter(role=AGENT).update(role=min(new_role, ROLE.MEMBER.value))


def _unique_agent_email(display_name, workspace):
    local = slugify(display_name)[:48] or "agent"
    domain = f"agents.{workspace.slug}.local"
    email = f"{local}@{domain}"
    suffix = 2
    while User.objects.filter(email=email).exists():
        email = f"{local}-{suffix}@{domain}"
        suffix += 1
    return email


class AgentProvisioningError(ValueError):
    """Invalid input for agent provisioning (rendered as HTTP 400 by the views)."""


def create_agent_user(workspace, display_name, email=None, first_name="", last_name=""):
    """Create an agent account in `workspace` and return its WorkspaceMember (role 10).

    The agent is an ordinary user (random password, email verified, onboarding done, all email
    notifications off) - agent emails are placeholders by default (<name>@agents.<slug>.local).
    Joins every project when auto-join is on.
    """
    display_name = (display_name or "").strip()
    if not display_name:
        raise AgentProvisioningError("display_name is required")
    if len(display_name) > 255:
        raise AgentProvisioningError("display_name is too long")
    if email:
        email = email.strip().lower()
        if User.objects.filter(email=email).exists():
            raise AgentProvisioningError("A user with this email already exists")
    else:
        email = _unique_agent_email(display_name, workspace)

    with transaction.atomic():
        user = User(
            email=email,
            username=f"agent_{uuid.uuid4().hex[:16]}",
            display_name=display_name,
            first_name=(first_name or display_name)[:255],
            last_name=(last_name or "")[:255],
            is_password_autoset=True,
            is_email_verified=True,
            user_timezone=getattr(workspace, "timezone", None) or "UTC",
        )
        user.set_password(uuid.uuid4().hex + uuid.uuid4().hex)
        user.save()
        Profile.objects.update_or_create(
            user=user,
            defaults={
                "is_onboarded": True,
                "is_tour_completed": True,
                "is_navigation_tour_completed": True,
                "onboarding_step": {
                    "profile_complete": True,
                    "workspace_create": True,
                    "workspace_invite": True,
                    "workspace_join": True,
                },
                "last_workspace_id": workspace.id,
            },
        )
        UserNotificationPreference.objects.filter(user=user).update(
            property_change=False, state_change=False, comment=False, mention=False, issue_completed=False
        )
        workspace_member = WorkspaceMember.objects.create(workspace=workspace, member=user, role=AGENT)
        sync_agent_memberships(workspace, users=[user])
        # join the default "Agents" team when it exists (no-op otherwise)
        add_member_to_default_teams(workspace, [user.id])
    return workspace_member


def create_agent_token(user, workspace, label=None):
    """Mint an API token (X-Api-Key for /api/v1) for an agent; the token string is only shown once."""
    return APIToken.objects.create(
        user=user,
        workspace=workspace,
        user_type=1,
        label=(label or f"{user.display_name} token")[:255],
        description="Agent token",
    )


def deactivate_agent(workspace_member):
    """Deactivate an agent in its workspace: membership, project memberships, API tokens and team
    memberships (so deactivated agents do not linger in the workspace's teams)."""
    with transaction.atomic():
        TeamMember.objects.filter(
            workspace_id=workspace_member.workspace_id, member_id=workspace_member.member_id
        ).delete(soft=False)
        ProjectMember.objects.filter(
            workspace_id=workspace_member.workspace_id, member_id=workspace_member.member_id, is_active=True
        ).update(is_active=False, updated_at=timezone.now())
        APIToken.objects.filter(user_id=workspace_member.member_id, is_active=True).update(
            is_active=False, updated_at=timezone.now()
        )
        workspace_member.is_active = False
        workspace_member.save(update_fields=["is_active", "updated_at"])
