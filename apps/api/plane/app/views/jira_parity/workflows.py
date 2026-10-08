# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity workflows views.

Endpoints (session API, served under /api/):
- GET workspaces/<slug>/projects/<project_id>/state-transitions/      rules (project members)
- PUT workspaces/<slug>/projects/<project_id>/state-transitions/      replace all rules (project admin)
      body: [{id?, from_state_id | null, to_state_id, roles: [15|10|5], exclude_epics}] (or {"rules": [...]})
- GET workspaces/<slug>/projects/<project_id>/state-transitions/me/   the requester's allowed moves:
      {"restricted": false} | {"restricted": true, "role", "epic_locked", "transitions", "epic_transitions"}
Project.is_workflow_enabled is read/written through the project endpoints (admin PATCH).
"""

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers.jira_parity.workflows import (
    StateTransitionRuleInputSerializer,
    StateTransitionSerializer,
)
from plane.app.views.base import BaseAPIView
from plane.db.models import Project, State, StateTransition
from plane.utils.workflow import get_my_transitions, replace_project_transitions

__all__ = ["ProjectStateTransitionEndpoint", "ProjectMyStateTransitionsEndpoint"]


def _rules_response(project_id):
    rules = StateTransition.objects.filter(project_id=project_id).order_by("created_at")
    return StateTransitionSerializer(rules, many=True).data


class ProjectStateTransitionEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id):
        return Response(_rules_response(project_id), status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN])
    def put(self, request, slug, project_id):
        payload = request.data
        if isinstance(payload, dict):
            payload = payload.get("rules")
        if not isinstance(payload, list):
            return Response(
                {"error": "Send the complete list of transition rules."}, status=status.HTTP_400_BAD_REQUEST
            )
        serializer = StateTransitionRuleInputSerializer(data=payload, many=True)
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid transition rules.", "rules": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rules = serializer.validated_data

        project = Project.objects.get(pk=project_id, workspace__slug=slug)
        state_ids = {rule["to_state_id"] for rule in rules} | {
            rule["from_state_id"] for rule in rules if rule.get("from_state_id")
        }
        known = set(State.objects.filter(project_id=project.id, id__in=state_ids).values_list("id", flat=True))
        unknown = sorted(str(state_id) for state_id in state_ids - known)
        if unknown:
            return Response(
                {"error": "Every state must be a state of this project.", "state_ids": unknown},
                status=status.HTTP_400_BAD_REQUEST,
            )
        replace_project_transitions(project, rules)
        return Response(_rules_response(project.id), status=status.HTTP_200_OK)


class ProjectMyStateTransitionsEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id):
        return Response(get_my_transitions(project_id, request.user), status=status.HTTP_200_OK)
