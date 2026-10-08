# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity teams views.

Add your classes here and list their names in __all__; the package __init__ re-exports __all__.

Endpoints (session API, served under /api/):
- GET/POST   workspaces/<slug>/teams/
- GET/PATCH/DELETE workspaces/<slug>/teams/<pk>/            (DELETE ?remove_from_projects=false)
- GET/POST   workspaces/<slug>/teams/<team_id>/members/       POST {member_ids:[...]}
- DELETE     workspaces/<slug>/teams/<team_id>/members/<user_id>/   (?remove_from_projects=false)
- GET/POST   workspaces/<slug>/teams/<team_id>/projects/      POST {project_ids:[...]} | {all_projects:true}
- DELETE     workspaces/<slug>/teams/<team_id>/projects/<project_id>/  (?remove_members=false)
Reads: workspace admin/member/guest (agents read like members). Writes: workspace admin.
Every mutation returns the refreshed team JSON (except DELETE team -> 204).
"""

# Python imports
import uuid
from collections import defaultdict

# Django imports
from django.db import IntegrityError, transaction

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers.jira_parity.teams import TeamMemberSerializer, TeamSerializer
from plane.app.views.base import BaseAPIView
from plane.db.models import Project, Team, Workspace, WorkspaceMember
from plane.db.models.team import TeamMember, TeamProject
from plane.utils import teams as team_service

__all__ = ["TeamEndpoint", "TeamMemberEndpoint", "TeamProjectEndpoint"]

READ_ROLES = [ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST]
WRITE_ROLES = [ROLE.ADMIN]


def _flag(request, name, default=True):
    value = request.query_params.get(name)
    if value is None:
        return default
    return str(value).lower() not in ("false", "0", "no")


def _parse_uuid_list(value, field):
    """Return (list[uuid], error_response)."""
    if value is None:
        return [], None
    if not isinstance(value, (list, tuple)):
        return None, Response({"error": f"{field} must be a list of ids."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        return [uuid.UUID(str(item)) for item in value], None
    except (TypeError, ValueError, AttributeError):
        return None, Response({"error": f"{field} contains an invalid id."}, status=status.HTTP_400_BAD_REQUEST)


def attach_team_relations(teams, workspace_id):
    """Attach `member_ids` (active workspace members only) and `project_ids` (non-archived
    projects) to each team instance; 3 queries whatever the number of teams."""
    teams = list(teams)
    team_ids = [team.id for team in teams]
    active_members = set(
        WorkspaceMember.objects.filter(workspace_id=workspace_id, is_active=True).values_list("member_id", flat=True)
    )
    members = defaultdict(list)
    for team_id, member_id in (
        TeamMember.objects.filter(team_id__in=team_ids).order_by("created_at").values_list("team_id", "member_id")
    ):
        if member_id in active_members:
            members[team_id].append(member_id)
    projects = defaultdict(list)
    for team_id, project_id in (
        TeamProject.objects.filter(
            team_id__in=team_ids,
            project__archived_at__isnull=True,
            project__deleted_at__isnull=True,
        )
        .order_by("created_at")
        .values_list("team_id", "project_id")
    ):
        projects[team_id].append(project_id)
    for team in teams:
        team.member_ids = members[team.id]
        team.project_ids = projects[team.id]
    return teams


def _team_response(slug, team_id, response_status=status.HTTP_200_OK):
    team = Team.objects.get(workspace__slug=slug, pk=team_id)
    attach_team_relations([team], team.workspace_id)
    return Response(TeamSerializer(team).data, status=response_status)


def _duplicate_name(workspace_id, name, exclude_id=None):
    queryset = Team.objects.filter(workspace_id=workspace_id, name__iexact=(name or "").strip())
    if exclude_id is not None:
        queryset = queryset.exclude(pk=exclude_id)
    return queryset.exists()


def _invalid_member_ids(workspace_id, member_ids):
    valid = set(
        WorkspaceMember.objects.filter(workspace_id=workspace_id, member_id__in=member_ids, is_active=True).values_list(
            "member_id", flat=True
        )
    )
    return [str(member_id) for member_id in member_ids if member_id not in valid]


def _invalid_project_ids(workspace_id, project_ids):
    valid = set(
        Project.objects.filter(workspace_id=workspace_id, id__in=project_ids, archived_at__isnull=True).values_list(
            "id", flat=True
        )
    )
    return [str(project_id) for project_id in project_ids if project_id not in valid]


def _validate_relations(workspace_id, data):
    """Parse/validate optional member_ids/project_ids of a create/patch body.

    Returns (member_ids|None, project_ids|None, error_response|None); None means "not provided".
    """
    member_ids = project_ids = None
    if "member_ids" in data:
        member_ids, error = _parse_uuid_list(data.get("member_ids"), "member_ids")
        if error:
            return None, None, error
        invalid = _invalid_member_ids(workspace_id, member_ids)
        if invalid:
            return (
                None,
                None,
                Response(
                    {"error": "Only active workspace members can be added to a team.", "invalid_ids": invalid},
                    status=status.HTTP_400_BAD_REQUEST,
                ),
            )
    if "project_ids" in data:
        project_ids, error = _parse_uuid_list(data.get("project_ids"), "project_ids")
        if error:
            return None, None, error
        invalid = _invalid_project_ids(workspace_id, project_ids)
        if invalid:
            return (
                None,
                None,
                Response(
                    {"error": "Some projects do not belong to this workspace.", "invalid_ids": invalid},
                    status=status.HTTP_400_BAD_REQUEST,
                ),
            )
    return member_ids, project_ids, None


TEAM_WRITABLE_FIELDS = ("name", "description", "logo_props", "default_project_role", "auto_join")


class TeamEndpoint(BaseAPIView):
    @allow_permission(allowed_roles=READ_ROLES, level="WORKSPACE")
    def get(self, request, slug, pk=None):
        workspace = Workspace.objects.get(slug=slug)
        if pk is not None:
            return _team_response(slug, pk)
        teams = attach_team_relations(Team.objects.filter(workspace_id=workspace.id).order_by("name"), workspace.id)
        return Response(TeamSerializer(teams, many=True).data, status=status.HTTP_200_OK)

    @allow_permission(allowed_roles=WRITE_ROLES, level="WORKSPACE")
    def post(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        payload = {key: request.data[key] for key in TEAM_WRITABLE_FIELDS if key in request.data}
        serializer = TeamSerializer(data=payload)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        if _duplicate_name(workspace.id, serializer.validated_data["name"]):
            return Response({"error": "Team with this name already exists"}, status=status.HTTP_409_CONFLICT)
        member_ids, project_ids, error = _validate_relations(workspace.id, request.data)
        if error:
            return error
        try:
            with transaction.atomic():
                team = serializer.save(workspace_id=workspace.id)
                if member_ids:
                    team_service.add_team_members(team, member_ids)
                if team.auto_join:
                    team_service.link_team_projects(team, all_projects=True)
                elif project_ids:
                    team_service.link_team_projects(team, project_ids)
        except IntegrityError:
            return Response({"error": "Team with this name already exists"}, status=status.HTTP_409_CONFLICT)
        return _team_response(slug, team.id, status.HTTP_201_CREATED)

    @allow_permission(allowed_roles=WRITE_ROLES, level="WORKSPACE")
    def patch(self, request, slug, pk):
        team = Team.objects.get(workspace__slug=slug, pk=pk)
        payload = {key: request.data[key] for key in TEAM_WRITABLE_FIELDS if key in request.data}
        serializer = TeamSerializer(team, data=payload, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        new_name = serializer.validated_data.get("name")
        if new_name is not None and _duplicate_name(team.workspace_id, new_name, exclude_id=team.id):
            return Response({"error": "Team with this name already exists"}, status=status.HTTP_409_CONFLICT)
        member_ids, project_ids, error = _validate_relations(team.workspace_id, request.data)
        if error:
            return error

        old_role, old_auto_join = team.default_project_role, team.auto_join
        try:
            with transaction.atomic():
                team = serializer.save()
                if member_ids is not None:
                    team_service.set_team_members(
                        team, member_ids, remove_from_projects=_flag(request, "remove_from_projects")
                    )
                if project_ids is not None and not team.auto_join:
                    team_service.set_team_projects(team, project_ids, remove_members=_flag(request, "remove_members"))
                team_service.update_team_settings(
                    team,
                    role_changed=team.default_project_role != old_role,
                    auto_join_enabled=team.auto_join and not old_auto_join,
                )
        except IntegrityError:
            return Response({"error": "Team with this name already exists"}, status=status.HTTP_409_CONFLICT)
        return _team_response(slug, team.id)

    @allow_permission(allowed_roles=WRITE_ROLES, level="WORKSPACE")
    def delete(self, request, slug, pk):
        team = Team.objects.get(workspace__slug=slug, pk=pk)
        team_service.delete_team(team, remove_from_projects=_flag(request, "remove_from_projects"))
        return Response(status=status.HTTP_204_NO_CONTENT)


class TeamMemberEndpoint(BaseAPIView):
    @allow_permission(allowed_roles=READ_ROLES, level="WORKSPACE")
    def get(self, request, slug, team_id):
        team = Team.objects.get(workspace__slug=slug, pk=team_id)
        team_members = TeamMember.objects.filter(team_id=team.id).order_by("created_at")
        return Response(TeamMemberSerializer(team_members, many=True).data, status=status.HTTP_200_OK)

    @allow_permission(allowed_roles=WRITE_ROLES, level="WORKSPACE")
    def post(self, request, slug, team_id):
        team = Team.objects.get(workspace__slug=slug, pk=team_id)
        member_ids, error = _parse_uuid_list(request.data.get("member_ids"), "member_ids")
        if error:
            return error
        if not member_ids:
            return Response({"error": "member_ids is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            team_service.add_team_members(team, member_ids)
        except team_service.TeamMembershipError as e:
            return Response({"error": str(e), "invalid_ids": e.invalid_ids}, status=status.HTTP_400_BAD_REQUEST)
        return _team_response(slug, team.id)

    @allow_permission(allowed_roles=WRITE_ROLES, level="WORKSPACE")
    def delete(self, request, slug, team_id, member_id):
        team = Team.objects.get(workspace__slug=slug, pk=team_id)
        team_service.remove_team_member(team, member_id, remove_from_projects=_flag(request, "remove_from_projects"))
        return _team_response(slug, team.id)


class TeamProjectEndpoint(BaseAPIView):
    @allow_permission(allowed_roles=READ_ROLES, level="WORKSPACE")
    def get(self, request, slug, team_id):
        team = Team.objects.get(workspace__slug=slug, pk=team_id)
        attach_team_relations([team], team.workspace_id)
        return Response([str(project_id) for project_id in team.project_ids], status=status.HTTP_200_OK)

    @allow_permission(allowed_roles=WRITE_ROLES, level="WORKSPACE")
    def post(self, request, slug, team_id):
        team = Team.objects.get(workspace__slug=slug, pk=team_id)
        if request.data.get("all_projects") is True:
            team_service.link_team_projects(team, all_projects=True)
            return _team_response(slug, team.id)
        project_ids, error = _parse_uuid_list(request.data.get("project_ids"), "project_ids")
        if error:
            return error
        if not project_ids:
            return Response({"error": "project_ids or all_projects is required."}, status=status.HTTP_400_BAD_REQUEST)
        invalid = _invalid_project_ids(team.workspace_id, project_ids)
        if invalid:
            return Response(
                {"error": "Some projects do not belong to this workspace.", "invalid_ids": invalid},
                status=status.HTTP_400_BAD_REQUEST,
            )
        team_service.link_team_projects(team, project_ids)
        return _team_response(slug, team.id)

    @allow_permission(allowed_roles=WRITE_ROLES, level="WORKSPACE")
    def delete(self, request, slug, team_id, project_id):
        team = Team.objects.get(workspace__slug=slug, pk=team_id)
        team_service.unlink_team_project(team, project_id, remove_members=_flag(request, "remove_members"))
        return _team_response(slug, team.id)
