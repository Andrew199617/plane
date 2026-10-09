# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity agents views.

Endpoints (session API, served under /api/; workspace admins only). Only agent accounts
(User.bot_type == AGENT_BOT_TYPE) are agents here; humans holding the Agent role are not.
- GET    workspaces/<slug>/agents/                          active agents of the workspace
- POST   workspaces/<slug>/agents/                          {display_name, email? (agents.<slug>.local
         only), first_name?, last_name?, generate_token=true, token_label?} -> 201 agent (+ `token`)
- PATCH  workspaces/<slug>/agents/<user_id>/                rename {display_name?, first_name?, last_name?}
- DELETE workspaces/<slug>/agents/<user_id>/                deactivate (memberships + tokens) -> 204
- POST   workspaces/<slug>/agents/<user_id>/tokens/         {label?} -> 201 token (+ `token`, shown once)
- DELETE workspaces/<slug>/agents/<user_id>/tokens/<id>/    revoke -> 204
"""

# Django imports
from django.db import IntegrityError
from django.db.models import Count, Q
from django.utils import timezone

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers.jira_parity.agents import (
    AgentCreateSerializer,
    AgentTokenCreateSerializer,
    AgentUpdateSerializer,
    serialize_agent,
    serialize_agent_token,
)
from plane.app.views.base import BaseAPIView
from plane.db.models import APIToken, ProjectMember, Workspace, WorkspaceMember
from plane.utils.agent import (
    AGENT,
    AGENT_BOT_TYPE,
    AgentProvisioningError,
    create_agent_token,
    create_agent_user,
    deactivate_agent,
)

__all__ = ["WorkspaceAgentEndpoint", "WorkspaceAgentTokenEndpoint"]


def _agent_tokens(workspace_id, user_ids):
    tokens = {}
    for token in APIToken.objects.filter(user_id__in=user_ids, is_active=True).filter(
        Q(workspace_id=workspace_id) | Q(workspace__isnull=True)
    ):
        tokens.setdefault(token.user_id, []).append(token)
    return tokens


def _project_counts(workspace_id, user_ids):
    rows = (
        ProjectMember.objects.filter(
            workspace_id=workspace_id,
            member_id__in=user_ids,
            is_active=True,
            project__archived_at__isnull=True,
        )
        .values("member_id")
        .annotate(count=Count("id"))
    )
    return {row["member_id"]: row["count"] for row in rows}


def serialize_agents(workspace_id, workspace_members):
    workspace_members = list(workspace_members)
    user_ids = [wm.member_id for wm in workspace_members]
    tokens = _agent_tokens(workspace_id, user_ids)
    counts = _project_counts(workspace_id, user_ids)
    return [
        serialize_agent(wm, project_count=counts.get(wm.member_id, 0), tokens=tokens.get(wm.member_id, []))
        for wm in workspace_members
    ]


def _agent_member(slug, user_id):
    return (
        WorkspaceMember.objects.filter(
            workspace__slug=slug, member_id=user_id, role=AGENT, is_active=True, member__bot_type=AGENT_BOT_TYPE
        )
        .select_related("member", "workspace")
        .first()
    )


def _not_found():
    return Response({"error": "Agent not found"}, status=status.HTTP_404_NOT_FOUND)


class WorkspaceAgentEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def get(self, request, slug, pk=None):
        if pk is not None:
            workspace_member = _agent_member(slug, pk)
            if workspace_member is None:
                return _not_found()
            return Response(serialize_agents(workspace_member.workspace_id, [workspace_member])[0])
        workspace = Workspace.objects.get(slug=slug)
        members = (
            WorkspaceMember.objects.filter(
                workspace=workspace, role=AGENT, is_active=True, member__bot_type=AGENT_BOT_TYPE
            )
            .select_related("member")
            .order_by("created_at")
        )
        return Response(serialize_agents(workspace.id, members), status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug):
        serializer = AgentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        workspace = Workspace.objects.get(slug=slug)
        try:
            workspace_member = create_agent_user(
                workspace,
                data["display_name"],
                email=data.get("email") or None,
                first_name=data.get("first_name") or "",
                last_name=data.get("last_name") or "",
            )
        except AgentProvisioningError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError:
            return Response({"error": "An agent with these details already exists"}, status=status.HTTP_400_BAD_REQUEST)

        token = None
        if data.get("generate_token", True):
            token = create_agent_token(workspace_member.member, workspace, label=data.get("token_label"))
        payload = serialize_agents(workspace.id, [workspace_member])[0]
        if token is not None:
            payload["token"] = token.token
        return Response(payload, status=status.HTTP_201_CREATED)

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def patch(self, request, slug, pk):
        workspace_member = _agent_member(slug, pk)
        if workspace_member is None:
            return _not_found()
        serializer = AgentUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        user = workspace_member.member
        fields = []
        for field, value in serializer.validated_data.items():
            if field == "display_name" and not value:
                return Response({"error": "display_name cannot be empty"}, status=status.HTTP_400_BAD_REQUEST)
            if getattr(user, field) != value:
                setattr(user, field, value)
                fields.append(field)
        if fields:
            user.save(update_fields=fields)
        return Response(serialize_agents(workspace_member.workspace_id, [workspace_member])[0])

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug, pk):
        workspace_member = _agent_member(slug, pk)
        if workspace_member is None:
            return _not_found()
        deactivate_agent(workspace_member)
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkspaceAgentTokenEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug, user_id):
        workspace_member = _agent_member(slug, user_id)
        if workspace_member is None:
            return _not_found()
        serializer = AgentTokenCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        token = create_agent_token(
            workspace_member.member, workspace_member.workspace, label=serializer.validated_data.get("label")
        )
        return Response(serialize_agent_token(token, include_secret=True), status=status.HTTP_201_CREATED)

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug, user_id, pk):
        workspace_member = _agent_member(slug, user_id)
        if workspace_member is None:
            return _not_found()
        revoked = APIToken.objects.filter(
            Q(workspace_id=workspace_member.workspace_id) | Q(workspace__isnull=True), pk=pk, user_id=user_id
        ).update(is_active=False, deleted_at=timezone.now(), updated_at=timezone.now())
        if not revoked:
            return Response({"error": "Token not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
