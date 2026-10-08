# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity work_item_types views.

- GET/POST          /api/workspaces/<slug>/work-item-types/
- GET/PATCH/DELETE  /api/workspaces/<slug>/work-item-types/<id>/          (writes: workspace admin)
- GET               /api/workspaces/<slug>/projects/<project_id>/work-item-types/  (active, enabled)
"""

# Django imports
from django.db import IntegrityError, transaction

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers.jira_parity.work_item_types import WorkItemTypeSerializer
from plane.app.views.base import BaseAPIView
from plane.db.models import IssueType, Project, ProjectIssueType, Workspace
from plane.utils.work_item_types import (
    annotate_issue_count,
    ensure_workspace_work_item_types,
    link_work_item_types_to_projects,
    seed_project_work_item_types,
    set_default_work_item_type,
)

__all__ = ["WorkItemTypeEndpoint", "ProjectWorkItemTypeEndpoint"]

READ_ROLES = [ROLE.ADMIN, ROLE.MEMBER, ROLE.AGENT, ROLE.GUEST]
DUPLICATE_NAME_ERROR = {"name": ["A work item type with this name already exists."]}


def _types_queryset(workspace_id):
    # Hierarchy order: Epic, standard types (by name), Sub-task
    return annotate_issue_count(IssueType.objects.filter(workspace_id=workspace_id)).order_by("-level", "name")


class WorkItemTypeEndpoint(BaseAPIView):
    @allow_permission(READ_ROLES, level="WORKSPACE")
    def get(self, request, slug, pk=None):
        workspace = Workspace.objects.get(slug=slug)
        if pk is not None:
            issue_type = _types_queryset(workspace.id).filter(pk=pk).first()
            if issue_type is None:
                return Response({"error": "Work item type not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response(WorkItemTypeSerializer(issue_type).data, status=status.HTTP_200_OK)

        # Lazily seed the standard types for workspaces created before the feature existed
        if not IssueType.objects.filter(workspace_id=workspace.id).exists():
            ensure_workspace_work_item_types(workspace)
        return Response(
            WorkItemTypeSerializer(_types_queryset(workspace.id), many=True).data,
            status=status.HTTP_200_OK,
        )

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        serializer = WorkItemTypeSerializer(data=request.data, context={"workspace_id": workspace.id})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        make_default = serializer.validated_data.get("is_default", False)
        try:
            with transaction.atomic():
                issue_type = serializer.save(workspace_id=workspace.id, is_default=False)
                if make_default:
                    set_default_work_item_type(issue_type)
                # Types are consistent across projects: enable the new type everywhere
                link_work_item_types_to_projects([issue_type], Project.objects.filter(workspace_id=workspace.id))
        except IntegrityError:
            return Response(DUPLICATE_NAME_ERROR, status=status.HTTP_400_BAD_REQUEST)
        issue_type = _types_queryset(workspace.id).get(pk=issue_type.pk)
        return Response(WorkItemTypeSerializer(issue_type).data, status=status.HTTP_201_CREATED)

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def patch(self, request, slug, pk):
        workspace = Workspace.objects.get(slug=slug)
        issue_type = _types_queryset(workspace.id).filter(pk=pk).first()
        if issue_type is None:
            return Response({"error": "Work item type not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = WorkItemTypeSerializer(
            issue_type, data=request.data, partial=True, context={"workspace_id": workspace.id}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        make_default = serializer.validated_data.get("is_default") is True and not issue_type.is_default
        try:
            with transaction.atomic():
                issue_type = serializer.save()
                if make_default:
                    set_default_work_item_type(issue_type)
        except IntegrityError:
            return Response(DUPLICATE_NAME_ERROR, status=status.HTTP_400_BAD_REQUEST)
        issue_type = _types_queryset(workspace.id).get(pk=issue_type.pk)
        return Response(WorkItemTypeSerializer(issue_type).data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug, pk):
        workspace = Workspace.objects.get(slug=slug)
        issue_type = _types_queryset(workspace.id).filter(pk=pk).first()
        if issue_type is None:
            return Response({"error": "Work item type not found."}, status=status.HTTP_404_NOT_FOUND)
        if issue_type.is_default:
            return Response(
                {"error": "The default work item type cannot be deleted.", "code": "WORK_ITEM_TYPE_IS_DEFAULT"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if issue_type.issue_count:
            return Response(
                {
                    "error": "This work item type is used by work items and cannot be deleted.",
                    "code": "WORK_ITEM_TYPE_IN_USE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            ProjectIssueType.objects.filter(issue_type_id=issue_type.id).delete()
            issue_type.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectWorkItemTypeEndpoint(BaseAPIView):
    @allow_permission(READ_ROLES)
    def get(self, request, slug, project_id):
        project = Project.objects.get(pk=project_id, workspace__slug=slug)
        active_ids = set(
            IssueType.objects.filter(workspace_id=project.workspace_id, is_active=True).values_list("id", flat=True)
        )
        linked_ids = set(
            ProjectIssueType.objects.filter(project_id=project.id, issue_type_id__in=active_ids).values_list(
                "issue_type_id", flat=True
            )
        )
        if not active_ids or active_ids - linked_ids or not project.is_issue_type_enabled:
            # Self-heal: every project has every workspace type enabled
            seed_project_work_item_types(project)
        issue_types = _types_queryset(project.workspace_id).filter(
            is_active=True,
            project_issue_types__project_id=project.id,
            project_issue_types__deleted_at__isnull=True,
        )
        return Response(WorkItemTypeSerializer(issue_types.distinct(), many=True).data, status=status.HTTP_200_OK)
