# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity sprint lifecycle views (cycles are sprints).

Endpoints (session API, served under /api/):
- GET  workspaces/<slug>/projects/<project_id>/sprints/next-name/          {"name": "LGD Sprint 5"}
- POST workspaces/<slug>/projects/<project_id>/cycles/<cycle_id>/start/     start a future sprint
      body {name?, description?, start_date: YYYY-MM-DD, end_date: YYYY-MM-DD} -> cycle payload
- POST workspaces/<slug>/projects/<project_id>/cycles/<cycle_id>/complete/  complete the active sprint
      body {move_to: "backlog" | "new" | <future sprint id>}
      -> {cycle, moved_issues, moved_to: {id, name} | null, new_sprint: cycle payload | null}
Errors are 400 {error, code[, active_sprint]}; see plane.utils.jira_parity.sprints.
"""

# Python imports
import json

# Django imports
from django.core.serializers.json import DjangoJSONEncoder

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers import CycleSerializer
from plane.app.views.base import BaseAPIView
from plane.app.views.cycle.base import CycleViewSet
from plane.bgtasks.webhook_task import model_activity
from plane.db.models import Cycle, Project
from plane.utils.host import base_host
from plane.utils.jira_parity.sprints import (
    SPRINT_FIELDS,
    SprintError,
    complete_sprint,
    next_sprint_name,
    start_sprint,
)
from plane.utils.timezone_converter import user_timezone_converter

__all__ = ["SprintNextNameEndpoint", "SprintLifecycleViewSet"]

# Same shape as an item of the cycle list endpoint.
CYCLE_PAYLOAD_FIELDS = (
    "id",
    "workspace_id",
    "project_id",
    "name",
    "description",
    "start_date",
    "end_date",
    "owned_by_id",
    "view_props",
    "sort_order",
    "external_source",
    "external_id",
    "progress_snapshot",
    "logo_props",
    "is_favorite",
    "total_issues",
    "cancelled_issues",
    "completed_issues",
    "assignee_ids",
    "status",
    "version",
    "created_by",
    *SPRINT_FIELDS,
)


class SprintNextNameEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id):
        project = Project.objects.get(pk=project_id, workspace__slug=slug)
        return Response({"name": next_sprint_name(project)}, status=status.HTTP_200_OK)


class SprintLifecycleViewSet(CycleViewSet):
    """Start / complete actions; reuses CycleViewSet.get_queryset so responses match the cycle list."""

    def _payload(self, cycle_id):
        data = self.get_queryset().filter(pk=cycle_id).values(*CYCLE_PAYLOAD_FIELDS).first()
        if data is None:
            return None
        project_timezone = Project.objects.get(pk=self.kwargs.get("project_id")).timezone
        return user_timezone_converter(data, ["start_date", "end_date"], project_timezone)

    def _get_cycle(self, slug, project_id, cycle_id):
        return Cycle.objects.filter(workspace__slug=slug, project_id=project_id, pk=cycle_id).first()

    def _log_update(self, request, slug, cycle_id, current_instance):
        model_activity.delay(
            model_name="cycle",
            model_id=str(cycle_id),
            requested_data=request.data,
            current_instance=current_instance,
            actor_id=request.user.id,
            slug=slug,
            origin=base_host(request=request, is_app=True),
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def start(self, request, slug, project_id, cycle_id):
        cycle = self._get_cycle(slug, project_id, cycle_id)
        if cycle is None:
            return Response({"error": "Sprint not found"}, status=status.HTTP_404_NOT_FOUND)
        current_instance = json.dumps(CycleSerializer(cycle).data, cls=DjangoJSONEncoder)
        try:
            cycle = start_sprint(cycle, request.data)
        except SprintError as error:
            return Response(error.as_response_data(), status=status.HTTP_400_BAD_REQUEST)
        self._log_update(request, slug, cycle.id, current_instance)
        return Response(self._payload(cycle.id), status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def complete(self, request, slug, project_id, cycle_id):
        cycle = self._get_cycle(slug, project_id, cycle_id)
        if cycle is None:
            return Response({"error": "Sprint not found"}, status=status.HTTP_404_NOT_FOUND)
        current_instance = json.dumps(CycleSerializer(cycle).data, cls=DjangoJSONEncoder)
        try:
            result = complete_sprint(cycle, request.data.get("move_to"), request=request, user=request.user)
        except SprintError as error:
            return Response(error.as_response_data(), status=status.HTTP_400_BAD_REQUEST)
        self._log_update(request, slug, cycle.id, current_instance)

        moved_to = result["moved_to"]
        new_sprint = result["new_sprint"]
        return Response(
            {
                "cycle": self._payload(cycle.id),
                "moved_issues": result["moved_issues"],
                "moved_to": {"id": str(moved_to.id), "name": moved_to.name} if moved_to is not None else None,
                "new_sprint": self._payload(new_sprint.id) if new_sprint is not None else None,
            },
            status=status.HTTP_200_OK,
        )
