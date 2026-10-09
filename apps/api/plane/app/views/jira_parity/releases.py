# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity release actions (modules are releases / fix versions).

Endpoints (session API, served under /api/):
- POST workspaces/<slug>/projects/<project_id>/modules/<module_id>/release/
      body {release_date?: YYYY-MM-DD | null, move_to?: <unreleased release id> | null}
      -> {module: module payload, moved_issues: n}
- POST workspaces/<slug>/projects/<project_id>/modules/<module_id>/unrelease/  -> {module: module payload}
Errors are 400 {error, code}; see plane.utils.jira_parity.releases.
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
from plane.app.serializers import ModuleSerializer
from plane.app.views.module.base import ModuleViewSet
from plane.bgtasks.webhook_task import model_activity
from plane.db.models import Module
from plane.utils.host import base_host
from plane.utils.jira_parity.releases import ReleaseError, release_module, unrelease_module
from plane.utils.timezone_converter import user_timezone_converter

__all__ = ["ReleaseActionsViewSet"]

# Same shape as an item of the module list endpoint.
MODULE_PAYLOAD_FIELDS = (
    "id",
    "workspace_id",
    "project_id",
    "name",
    "description",
    "description_text",
    "description_html",
    "start_date",
    "target_date",
    "status",
    "lead_id",
    "member_ids",
    "view_props",
    "sort_order",
    "external_source",
    "external_id",
    "logo_props",
    "completed_estimate_points",
    "total_estimate_points",
    "total_issues",
    "is_favorite",
    "cancelled_issues",
    "completed_issues",
    "started_issues",
    "unstarted_issues",
    "backlog_issues",
    "created_at",
    "updated_at",
)


class ReleaseActionsViewSet(ModuleViewSet):
    """Release / unrelease actions; reuses ModuleViewSet.get_queryset so responses match the module list."""

    def _payload(self, request, module_id):
        data = self.get_queryset().filter(pk=module_id).values(*MODULE_PAYLOAD_FIELDS).first()
        if data is None:
            return None
        return user_timezone_converter(data, ["created_at", "updated_at"], request.user.user_timezone)

    def _get_module(self, slug, project_id, module_id):
        return (
            Module.objects.filter(workspace__slug=slug, project_id=project_id, pk=module_id)
            .select_related("project")
            .first()
        )

    def _log_update(self, request, slug, module_id, current_instance):
        model_activity.delay(
            model_name="module",
            model_id=str(module_id),
            requested_data=request.data,
            current_instance=current_instance,
            actor_id=request.user.id,
            slug=slug,
            origin=base_host(request=request, is_app=True),
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def release(self, request, slug, project_id, module_id):
        module = self._get_module(slug, project_id, module_id)
        if module is None:
            return Response({"error": "Release not found"}, status=status.HTTP_404_NOT_FOUND)
        current_instance = json.dumps(ModuleSerializer(module).data, cls=DjangoJSONEncoder)
        try:
            moved = release_module(
                module,
                release_date=request.data.get("release_date"),
                move_to=request.data.get("move_to"),
                request=request,
                user=request.user,
            )
        except ReleaseError as error:
            return Response(error.as_response_data(), status=status.HTTP_400_BAD_REQUEST)
        self._log_update(request, slug, module.id, current_instance)
        return Response(
            {"module": self._payload(request, module.id), "moved_issues": moved},
            status=status.HTTP_200_OK,
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def unrelease(self, request, slug, project_id, module_id):
        module = self._get_module(slug, project_id, module_id)
        if module is None:
            return Response({"error": "Release not found"}, status=status.HTTP_404_NOT_FOUND)
        current_instance = json.dumps(ModuleSerializer(module).data, cls=DjangoJSONEncoder)
        try:
            unrelease_module(module)
        except ReleaseError as error:
            return Response(error.as_response_data(), status=status.HTTP_400_BAD_REQUEST)
        self._log_update(request, slug, module.id, current_instance)
        return Response({"module": self._payload(request, module.id)}, status=status.HTTP_200_OK)
