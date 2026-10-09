# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity teams service (request-free; used by the teams API views, the project-created hook
and management commands).

Models: db.Team (workspace.py; default_project_role, auto_join), db.TeamMember (team, member,
workspace), db.TeamProject (team, project, workspace) and db.TeamProvisionedMember (provenance
marker for memberships that exist only because a team provisioned them).

Semantics
- A team is linked to projects through TeamProject rows. `auto_join=True` links it to every
  non-archived project, including projects created later (apply_auto_join_teams).
- Effective project role of a team member = resolve_project_role(workspace role, team role); a user
  in several teams linked to the same project gets the highest role. The Agent role (10) only
  applies to agent accounts: other workspace members of a team with that role get Member.
- Provisioning goes through plane.utils.project_membership.ensure_project_member (idempotent,
  never downgrades an active Admin). A missing/inactive membership is created/reactivated with the
  effective role and marked as team-provisioned; an active membership is only ever upgraded
  (or, when the team role itself changes and the membership is team-provisioned, set to the new
  effective role). The project lead's row is never modified.
- An admin adding, editing or removing a member by hand (ProjectMemberViewSet) makes the
  membership a manual one: the provenance marker is dropped (clear_team_provisioning).
- Deprovisioning (member leaves a team, team unlinked from a project, team deleted) deactivates
  (soft, is_active=False) only memberships that are team-provisioned AND no longer covered by
  any team. Never deactivated: workspace admins, workspace agents (agent auto-join owns them),
  the project lead, the project's default assignee, and the last active project admin.
"""

# Python imports
import uuid

# Django imports
from django.db import transaction
from django.utils import timezone

# Module imports
from plane.db.models import Project, ProjectMember, Team, WorkspaceMember
from plane.db.models.project import ROLE
from plane.db.models.team import TeamMember, TeamProject, TeamProvisionedMember
from plane.utils.project_membership import ensure_project_member

ADMIN = ROLE.ADMIN.value
MEMBER = ROLE.MEMBER.value
AGENT = ROLE.AGENT.value
GUEST = ROLE.GUEST.value

# Default teams seeded by seed_default_teams
DEFAULT_TEAMS = (
    {
        "name": "Devs",
        "description": "Developers. Added to every project.",
        "default_project_role": ADMIN,
        "auto_join": True,
        "workspace_roles": (ADMIN,),
    },
    {
        "name": "Agents",
        "description": "AI agent accounts. Added to every project with the Agent role.",
        "default_project_role": AGENT,
        "auto_join": True,
        "workspace_roles": (AGENT,),
    },
)


class TeamMembershipError(ValueError):
    """Raised when a user cannot be added to a team (not an active member of its workspace)."""

    def __init__(self, message, invalid_ids=None):
        super().__init__(message)
        self.invalid_ids = [str(i) for i in (invalid_ids or [])]


def _uuid(value):
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _uuid_set(values):
    return {_uuid(v) for v in (values or [])}


# ---------------------------------------------------------------- roles


def allowed_project_roles():
    """Project role values a team may grant (ProjectMember role choices: 20, 15, 10, 5)."""
    return {value for value, _ in ProjectMember._meta.get_field("role").choices}


def resolve_project_role(workspace_role, team_role):
    """Effective project role for a workspace member provisioned by a team.

    The workspace role caps/overrides the team role, mirroring ProjectMemberViewSet.create:
    workspace admins are always project admins, workspace agents are always project agents and
    workspace guests are always project guests. Workspace members get the team role, except the
    Agent role, which is reserved for agent accounts (agent_role_mismatch): they get Member.
    """
    if workspace_role == ADMIN:
        return ADMIN
    if workspace_role == AGENT:
        return AGENT
    if workspace_role == GUEST:
        return GUEST
    if team_role == AGENT:
        return MEMBER
    return team_role


# ---------------------------------------------------------------- queries


def _linked_projects(team):
    """Non-archived projects the team is linked to."""
    return Project.objects.filter(
        workspace_id=team.workspace_id,
        archived_at__isnull=True,
        project_teamproject__team_id=team.id,
        project_teamproject__deleted_at__isnull=True,
    ).distinct()


def desired_team_roles(project):
    """{user_id: effective role} for every active workspace member covered by a team linked to
    `project`."""
    rows = list(
        TeamMember.objects.filter(
            team__workspace_id=project.workspace_id,
            team__deleted_at__isnull=True,
            team__team_projects__project_id=project.id,
            team__team_projects__deleted_at__isnull=True,
        ).values_list("member_id", "team__default_project_role")
    )
    if not rows:
        return {}
    workspace_roles = dict(
        WorkspaceMember.objects.filter(
            workspace_id=project.workspace_id,
            member_id__in={member_id for member_id, _ in rows},
            is_active=True,
        ).values_list("member_id", "role")
    )
    result = {}
    for member_id, team_role in rows:
        workspace_role = workspace_roles.get(member_id)
        if workspace_role is None:
            continue
        role = resolve_project_role(workspace_role, team_role)
        if role > result.get(member_id, 0):
            result[member_id] = role
    return result


def team_ids_by_member(workspace_id):
    """{user_id: [team ids]} for the workspace (used by member-row badges)."""
    result = {}
    for team_id, member_id in TeamMember.objects.filter(
        workspace_id=workspace_id, team__deleted_at__isnull=True
    ).values_list("team_id", "member_id"):
        result.setdefault(member_id, []).append(team_id)
    return result


# ---------------------------------------------------------------- provisioning


def sync_project_team_members(project, *, user_ids=None, apply_roles=False):
    """Provision the team-covered users of `project` (optionally only `user_ids`).

    - missing / inactive membership -> created / reactivated with the effective role and marked
      as team-provisioned
    - active membership -> upgraded when the effective role is higher; with apply_roles=True
      (the team role changed) a team-provisioned one is set to the effective role
      (ensure_project_member never downgrades an active Admin)
    - the project lead's active row is never modified

    Returns the ids of users whose membership was created or reactivated.
    """
    if project.archived_at is not None or project.deleted_at is not None:
        return []
    desired = desired_team_roles(project)
    if user_ids is not None:
        wanted = _uuid_set(user_ids)
        desired = {member_id: role for member_id, role in desired.items() if member_id in wanted}
    if not desired:
        return []

    existing = {
        pm.member_id: pm for pm in ProjectMember.objects.filter(project_id=project.id, member_id__in=list(desired))
    }
    marked = set()
    if apply_roles:
        marked = set(
            TeamProvisionedMember.objects.filter(project_id=project.id, member_id__in=list(desired)).values_list(
                "member_id", flat=True
            )
        )
    provisioned = []
    with transaction.atomic():
        for member_id, role in desired.items():
            current = existing.get(member_id)
            if current is not None and current.is_active:
                if member_id == project.project_lead_id:
                    continue
                if role > current.role or (member_id in marked and role != current.role):
                    ensure_project_member(project, member_id, role)
                continue
            ensure_project_member(project, member_id, role)
            provisioned.append(member_id)

        if provisioned:
            TeamProvisionedMember.objects.bulk_create(
                [
                    TeamProvisionedMember(project_id=project.id, workspace_id=project.workspace_id, member_id=member_id)
                    for member_id in provisioned
                ],
                ignore_conflicts=True,
            )
    return provisioned


def deprovision_project_members(project, candidate_user_ids, *, deactivate=True):
    """Handle users that may have lost team coverage in `project`.

    For each candidate no longer covered by any team linked to the project whose membership is
    team-provisioned: deactivate the membership (unless protected, see module docstring) and drop
    the provenance marker. With deactivate=False only the markers are dropped (the memberships
    become ordinary, manually managed memberships).

    Returns the ids of users whose membership was deactivated.
    """
    candidates = _uuid_set(candidate_user_ids)
    if not candidates:
        return []
    orphans = candidates - set(desired_team_roles(project))
    if not orphans:
        return []
    marked = set(
        TeamProvisionedMember.objects.filter(project_id=project.id, member_id__in=orphans).values_list(
            "member_id", flat=True
        )
    )
    if not marked:
        return []

    deactivated = []
    with transaction.atomic():
        if deactivate:
            protected = {project.project_lead_id, project.default_assignee_id} - {None}
            protected |= set(
                WorkspaceMember.objects.filter(
                    workspace_id=project.workspace_id,
                    member_id__in=marked,
                    role__in=[ADMIN, AGENT],
                    is_active=True,
                ).values_list("member_id", flat=True)
            )
            rows = list(
                ProjectMember.objects.filter(
                    project_id=project.id, member_id__in=marked - protected, is_active=True
                ).values_list("member_id", "role")
            )
            to_deactivate = {member_id for member_id, _ in rows}
            leaving_admins = {member_id for member_id, role in rows if role == ADMIN}
            if leaving_admins:
                remaining_admins = (
                    ProjectMember.objects.filter(project_id=project.id, role=ADMIN, is_active=True)
                    .exclude(member_id__in=to_deactivate)
                    .exists()
                )
                if not remaining_admins:
                    # never leave a project without an active admin
                    to_deactivate -= leaving_admins
            if to_deactivate:
                ProjectMember.objects.filter(project_id=project.id, member_id__in=to_deactivate).update(
                    is_active=False, updated_at=timezone.now()
                )
                deactivated = list(to_deactivate)
        TeamProvisionedMember.objects.filter(project_id=project.id, member_id__in=marked).delete(soft=False)
    return deactivated


def clear_team_provisioning(project_id, user_ids):
    """Drop the provenance markers of these memberships: an admin added, edited or removed them by
    hand, so they are manual memberships from now on (team changes never deactivate them)."""
    TeamProvisionedMember.objects.filter(project_id=project_id, member_id__in=list(user_ids)).delete(soft=False)


def sync_team(team, *, user_ids=None, apply_roles=False):
    """Provision the team's members (or only `user_ids`) in every project linked to the team."""
    provisioned = {}
    for project in _linked_projects(team):
        added = sync_project_team_members(project, user_ids=user_ids, apply_roles=apply_roles)
        if added:
            provisioned[project.id] = added
    return provisioned


def sync_team_memberships(team, projects=None, *, apply_roles=False):
    """Provision the team's members (ensure_project_member with the effective team role) in
    `projects` (Project instances or ids), or in every project linked to the team when omitted.

    Projects that are not linked to the team (or archived, or outside its workspace) are skipped:
    link them first with link_team_projects. Returns {project_id: [user ids created/reactivated]}.
    """
    if projects is None:
        return sync_team(team, apply_roles=apply_roles)
    project_ids = {getattr(project, "id", project) for project in projects}
    provisioned = {}
    for project in _linked_projects(team).filter(id__in=list(_uuid_set(project_ids))):
        added = sync_project_team_members(project, apply_roles=apply_roles)
        if added:
            provisioned[project.id] = added
    return provisioned


# ---------------------------------------------------------------- team mutations


def link_team_projects(team, project_ids=None, *, all_projects=False):
    """Link `team` to the given projects (or to every non-archived project of its workspace) and
    provision its members there. Projects outside the team's workspace are ignored.

    Returns the list of linked projects.
    """
    queryset = Project.objects.filter(workspace_id=team.workspace_id, archived_at__isnull=True)
    if not all_projects:
        queryset = queryset.filter(id__in=list(_uuid_set(project_ids)))
    projects = list(queryset)
    if not projects:
        return []
    with transaction.atomic():
        already_linked = set(
            TeamProject.objects.filter(team_id=team.id, project_id__in=[p.id for p in projects]).values_list(
                "project_id", flat=True
            )
        )
        TeamProject.objects.bulk_create(
            [
                TeamProject(team_id=team.id, project_id=project.id, workspace_id=team.workspace_id)
                for project in projects
                if project.id not in already_linked
            ],
            ignore_conflicts=True,
        )
        for project in projects:
            sync_project_team_members(project)
    return projects


def unlink_team_project(team, project_id, *, remove_members=True):
    """Unlink `team` from a project. Team-provisioned members that are no longer covered by
    another team are deactivated there (unless remove_members=False)."""
    project = Project.objects.filter(id=project_id, workspace_id=team.workspace_id).first()
    if project is None:
        return []
    candidates = set(TeamMember.objects.filter(team_id=team.id).values_list("member_id", flat=True))
    with transaction.atomic():
        TeamProject.objects.filter(team_id=team.id, project_id=project.id).delete(soft=False)
        return deprovision_project_members(project, candidates, deactivate=remove_members)


def set_team_projects(team, project_ids, *, remove_members=True):
    """Make the team's linked projects exactly `project_ids` (non-archived projects only)."""
    wanted = _uuid_set(project_ids)
    current = set(_linked_projects(team).values_list("id", flat=True))
    with transaction.atomic():
        for project_id in current - wanted:
            unlink_team_project(team, project_id, remove_members=remove_members)
        if wanted - current:
            link_team_projects(team, wanted - current)


def add_team_members(team, user_ids):
    """Add users to `team` and provision them in the team's projects.

    Raises TeamMembershipError when a user is not an active member of the team's workspace.
    Returns the ids of the users that were newly added to the team.
    """
    ids = _uuid_set(user_ids)
    if not ids:
        return []
    valid = set(
        WorkspaceMember.objects.filter(workspace_id=team.workspace_id, member_id__in=ids, is_active=True).values_list(
            "member_id", flat=True
        )
    )
    invalid = ids - valid
    if invalid:
        raise TeamMembershipError("Only active workspace members can be added to a team.", invalid)
    with transaction.atomic():
        existing = set(
            TeamMember.objects.filter(team_id=team.id, member_id__in=ids).values_list("member_id", flat=True)
        )
        new_ids = ids - existing
        TeamMember.objects.bulk_create(
            [TeamMember(team_id=team.id, workspace_id=team.workspace_id, member_id=member_id) for member_id in new_ids],
            ignore_conflicts=True,
        )
        # existing members are re-synced too: repairs memberships removed by hand
        sync_team(team, user_ids=ids)
    return list(new_ids)


def remove_team_member(team, user_id, *, remove_from_projects=True):
    """Remove a user from `team`; their team-provisioned memberships in the team's projects are
    deactivated unless another team still covers them (or remove_from_projects=False)."""
    user_id = _uuid(user_id)
    projects = list(_linked_projects(team))
    deactivated = {}
    with transaction.atomic():
        TeamMember.objects.filter(team_id=team.id, member_id=user_id).delete(soft=False)
        for project in projects:
            removed = deprovision_project_members(project, {user_id}, deactivate=remove_from_projects)
            if removed:
                deactivated[project.id] = removed
    return deactivated


def set_team_members(team, user_ids, *, remove_from_projects=True):
    """Make the team's members exactly `user_ids`."""
    wanted = _uuid_set(user_ids)
    current = set(TeamMember.objects.filter(team_id=team.id).values_list("member_id", flat=True))
    with transaction.atomic():
        if wanted - current:
            add_team_members(team, wanted - current)
        for user_id in current - wanted:
            remove_team_member(team, user_id, remove_from_projects=remove_from_projects)


def update_team_settings(team, *, role_changed=False, auto_join_enabled=False):
    """Re-apply provisioning after a team's settings changed (call after saving the team)."""
    if auto_join_enabled:
        link_team_projects(team, all_projects=True)
    if role_changed:
        sync_team(team, apply_roles=True)


def delete_team(team, *, remove_from_projects=True):
    """Delete a team (hard delete; nothing else references teams, and the name becomes free
    again): its links and memberships go with it, and team-provisioned project memberships no
    longer covered by another team are deactivated (unless remove_from_projects=False)."""
    projects = list(_linked_projects(team))
    member_ids = set(TeamMember.objects.filter(team_id=team.id).values_list("member_id", flat=True))
    with transaction.atomic():
        TeamProject.all_objects.filter(team_id=team.id).delete()
        TeamMember.all_objects.filter(team_id=team.id).delete()
        team.delete(soft=False)
        for project in projects:
            deprovision_project_members(project, member_ids, deactivate=remove_from_projects)


# ---------------------------------------------------------------- hooks / seeding


def apply_auto_join_teams(project):
    """Link every auto_join team of the project's workspace to `project` (TeamProject) and
    provision its members as ProjectMembers with the team's default_project_role.
    Called by run_project_created_hooks (after the creator and lead memberships exist).

    Returns the ids of users whose membership was created or reactivated.
    """
    if project.archived_at is not None:
        return []
    team_ids = list(Team.objects.filter(workspace_id=project.workspace_id, auto_join=True).values_list("id", flat=True))
    if not team_ids:
        return []
    with transaction.atomic():
        already_linked = set(
            TeamProject.objects.filter(project_id=project.id, team_id__in=team_ids).values_list("team_id", flat=True)
        )
        TeamProject.objects.bulk_create(
            [
                TeamProject(team_id=team_id, project_id=project.id, workspace_id=project.workspace_id)
                for team_id in team_ids
                if team_id not in already_linked
            ],
            ignore_conflicts=True,
        )
        return sync_project_team_members(project)


def add_member_to_default_teams(workspace, user_ids):
    """Add users to the existing default teams their workspace role qualifies them for (workspace
    admins -> Devs, workspace agents -> Agents) and provision them in those teams' projects.

    For flows that create workspace members after the teams were seeded (e.g. creating an agent).
    Teams that do not exist (not seeded / deleted) are skipped; never creates teams.
    Returns {team name: [user ids newly added]}.
    """
    ids = _uuid_set(user_ids)
    if not ids:
        return {}
    roles = dict(
        WorkspaceMember.objects.filter(workspace_id=workspace.id, member_id__in=ids, is_active=True).values_list(
            "member_id", "role"
        )
    )
    result = {}
    for spec in DEFAULT_TEAMS:
        member_ids = [member_id for member_id, role in roles.items() if role in spec["workspace_roles"]]
        if not member_ids:
            continue
        team = Team.objects.filter(workspace_id=workspace.id, name__iexact=spec["name"]).first()
        if team is None:
            continue
        added = add_team_members(team, member_ids)
        if added:
            result[team.name] = added
    return result


def seed_default_teams(workspace):
    """Idempotently create the default teams (Devs, Agents) of a workspace.

    Devs: default project role Admin, auto-join, members = active workspace admins.
    Agents: default project role Agent, auto-join, members = active workspace agents (role 10).
    Existing teams (matched by name, case-insensitive) keep their description; role and auto_join
    are enforced and missing members are added (extra members are kept). Every team is linked
    to all non-archived projects and provisioned. Safe to re-run (e.g. after creating agents).

    Returns {team name: Team}.
    """
    result = {}
    for spec in DEFAULT_TEAMS:
        with transaction.atomic():
            team = Team.objects.filter(workspace_id=workspace.id, name__iexact=spec["name"]).first()
            role_changed = False
            if team is None:
                team = Team.objects.create(
                    workspace_id=workspace.id,
                    name=spec["name"],
                    description=spec["description"],
                    default_project_role=spec["default_project_role"],
                    auto_join=spec["auto_join"],
                )
            elif team.default_project_role != spec["default_project_role"] or team.auto_join != spec["auto_join"]:
                role_changed = team.default_project_role != spec["default_project_role"]
                team.default_project_role = spec["default_project_role"]
                team.auto_join = spec["auto_join"]
                team.save(update_fields=["default_project_role", "auto_join", "updated_at"])

            member_ids = list(
                WorkspaceMember.objects.filter(
                    workspace_id=workspace.id,
                    role__in=spec["workspace_roles"],
                    is_active=True,
                    member__is_bot=False,
                    member__is_active=True,
                ).values_list("member_id", flat=True)
            )
            add_team_members(team, member_ids)
            link_team_projects(team, all_projects=True)
            if role_changed:
                sync_team(team, apply_roles=True)
        result[spec["name"]] = team
    return result
