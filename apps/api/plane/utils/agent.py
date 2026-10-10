# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity agents service.

Agents are ordinary Users (is_bot=False, so they can be assigned and listed) whose
WorkspaceMember.role is ROLE.AGENT (10). They auto-join every project as ProjectMember role 10
(via plane.utils.project_membership.ensure_project_member) and authenticate to /api/v1 with
APIToken rows (X-Api-Key). What they may do is enforced by plane.app.permissions.agent.

Agent ACCOUNTS (created by create_agent_user) are marked with User.bot_type == AGENT_BOT_TYPE: only
they can be managed (and get API tokens) through the agents API, and their tokens only work in their
workspace. Humans can hold the Agent role only through an admin's invitation.

Env AGENT_AUTO_JOIN_PROJECTS=0 disables the automatic project membership sync.
"""

# Python imports
import os
import uuid

# Django imports
from django.db import transaction
from django.db.models import Q
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
from plane.utils.teams import DEFAULT_TEAMS, add_member_to_default_teams

AGENT = ROLE.AGENT.value
AGENT_BOT_TYPE = "AGENT"
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


def is_agent_account(user):
    return getattr(user, "bot_type", None) == AGENT_BOT_TYPE


def invite_role_error(requesting_role, role):
    """Why a workspace member with `requesting_role` may not invite (or re-role an invitation) at
    `role`, or None. Only admins may invite Agents: they join every project, private ones included."""
    try:
        role = int(role)
    except (TypeError, ValueError):
        return "Invalid role"
    if role not in VALID_ROLES:
        return "Invalid role"
    if role > requesting_role:
        return "You cannot invite a user with higher role"
    if role == AGENT and requesting_role != ROLE.ADMIN.value:
        return "Only workspace admins can invite agents"
    return None


def agent_role_change_error(workspace_member, new_role):
    """Why a workspace member's role may not be changed to `new_role`, or None. The Agent role is
    reserved to agent accounts and admin invitations: humans are never moved into it, agent accounts
    never out of it (deactivate the agent instead)."""
    try:
        new_role = int(new_role)
    except (TypeError, ValueError):
        return None
    if new_role == workspace_member.role:
        return None
    agent_account = is_agent_account(workspace_member.member)
    if new_role == AGENT and not agent_account:
        return "Only agent accounts and users invited as agents can have the Agent role"
    if agent_account and new_role != AGENT:
        return "Agent accounts cannot change role; deactivate the agent instead"
    return None


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
    - old role Agent, new role something else: agent project rows become min(new role, Member), the
      user's API tokens for the workspace are revoked and they leave the default Agents team
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
        _revoke_workspace_tokens(workspace_member)
        for spec in DEFAULT_TEAMS:
            if AGENT in spec["workspace_roles"]:
                TeamMember.objects.filter(
                    workspace_id=workspace_member.workspace_id,
                    member_id=workspace_member.member_id,
                    team__name__iexact=spec["name"],
                ).delete(soft=False)


def _revoke_workspace_tokens(workspace_member):
    APIToken.objects.filter(user_id=workspace_member.member_id, is_active=True).filter(
        Q(workspace_id=workspace_member.workspace_id) | Q(workspace__isnull=True, user_type=1)
    ).update(is_active=False, updated_at=timezone.now())


def agent_email_domain(workspace):
    return f"agents.{workspace.slug}.local".lower()


def is_agent_placeholder_email(email, workspace):
    """True for the generated agent email domain: nobody receives mail there, so the account cannot
    be claimed by a real person."""
    return (email or "").strip().lower().endswith(f"@{agent_email_domain(workspace)}")


def _unique_agent_email(display_name, workspace):
    local = slugify(display_name)[:48] or "agent"
    domain = agent_email_domain(workspace)
    email = f"{local}@{domain}"
    suffix = 2
    while User.objects.filter(email=email).exists():
        email = f"{local}-{suffix}@{domain}"
        suffix += 1
    return email


class AgentProvisioningError(ValueError):
    """Invalid input for agent provisioning (rendered as HTTP 400 by the views)."""


def create_agent_user(workspace, display_name, email=None, first_name="", last_name="", allow_custom_email=False):
    """Create an agent account in `workspace` and return its WorkspaceMember (role 10).

    The agent is a user marked bot_type=AGENT_BOT_TYPE (random password, onboarding done, all email
    notifications off). Its email is a placeholder on agents.<slug>.local (generated from the name
    when not given); only operators (allow_custom_email) may use another address, which is then left
    unverified. Joins every project when auto-join is on.
    """
    display_name = (display_name or "").strip()
    if not display_name:
        raise AgentProvisioningError("display_name is required")
    if len(display_name) > 255:
        raise AgentProvisioningError("display_name is too long")
    if email:
        email = email.strip().lower()
        if not allow_custom_email and not is_agent_placeholder_email(email, workspace):
            raise AgentProvisioningError(f"Agent emails must use the {agent_email_domain(workspace)} domain")
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
            is_email_verified=is_agent_placeholder_email(email, workspace),
            bot_type=AGENT_BOT_TYPE,
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
    with transaction.atomic():
        # Share the membership lock with deactivation: a stale view must not mint a token after
        # the workspace's administrator has revoked the agent's membership.
        member = (
            WorkspaceMember.objects.select_for_update()
            .filter(
                workspace=workspace,
                member=user,
                role=AGENT,
                is_active=True,
                member__bot_type=AGENT_BOT_TYPE,
                member__is_active=True,
            )
            .first()
        )
        if member is None:
            raise AgentProvisioningError("Only active agent accounts can receive agent tokens")
        return APIToken.objects.create(
            user=user,
            workspace=workspace,
            user_type=1,
            label=(label or f"{user.display_name} token")[:255],
            description="Agent token",
        )


def deactivate_agent(workspace_member):
    """Deactivate an agent in its workspace: membership, project memberships, API tokens of that
    workspace and team memberships (so deactivated agents do not linger in the workspace's teams)."""
    with transaction.atomic():
        workspace_member = WorkspaceMember.objects.select_for_update().get(pk=workspace_member.pk)
        TeamMember.objects.filter(
            workspace_id=workspace_member.workspace_id, member_id=workspace_member.member_id
        ).delete(soft=False)
        ProjectMember.objects.filter(
            workspace_id=workspace_member.workspace_id, member_id=workspace_member.member_id, is_active=True
        ).update(is_active=False, updated_at=timezone.now())
        _revoke_workspace_tokens(workspace_member)
        workspace_member.is_active = False
        workspace_member.save(update_fields=["is_active", "updated_at"])
