# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity project_categories views.

Add your classes here and list their names in __all__; the package __init__ re-exports __all__.

- ProjectCategoryViewSet: CRUD of workspace project categories (workspace members incl. agents
  and guests read, workspace admins write).
- ProjectCategoryIssuesEndpoint: master-board issues of a category. Same params and response as
  the workspace issues endpoints (rich `filters`, legacy filters, order_by, cursor/per_page,
  group_by/sub_group_by with grouped pagination) via WorkspaceViewIssuesViewSet's queryset,
  permission filters and annotations, scoped to the category's projects; adds group_by /
  sub_group_by "state__name" and the cycle_name / state_name filters.
- ProjectCategoryCyclesEndpoint: the category's cycles distinct by name (sprint filter).
"""

# Python imports
import copy

# Django imports
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.gzip import gzip_page
from django_filters import filters as df_filters

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers.jira_parity.project_categories import ProjectCategorySerializer
from plane.app.views.base import BaseAPIView, BaseViewSet
from plane.app.views.view.base import WorkspaceViewIssuesViewSet
from plane.db.models import Issue, ProjectCategory, Workspace
from plane.utils.filters.filterset import CharInFilter, IssueFilterSet, UUIDInFilter
from plane.utils.grouper import issue_on_results, issue_queryset_grouper
from plane.utils.issue_filters import issue_filters
from plane.utils.order_queryset import order_issue_queryset
from plane.utils.paginator import GroupedOffsetPaginator, SubGroupedOffsetPaginator
from plane.utils.project_categories import (
    annotate_project_ids,
    category_cycles,
    category_group_by_allowlist,
    category_group_values,
    category_project_ids,
    delete_category,
    member_project_ids,
)

__all__ = [
    "ProjectCategoryViewSet",
    "ProjectCategoryIssuesEndpoint",
    "ProjectCategoryCyclesEndpoint",
    "ProjectCategoryIssueFilterSet",
]

# Workspace roles that may read categories, boards and sprints (agents read like members).
READ_ROLES = [ROLE.ADMIN, ROLE.MEMBER, ROLE.AGENT, ROLE.GUEST]
WRITE_ROLES = [ROLE.ADMIN]

# Same per-group count filter as the project / profile grouped issue lists.
GROUP_COUNT_FILTER = Q(
    Q(issue_intake__status=1) | Q(issue_intake__status=-1) | Q(issue_intake__status=2) | Q(issue_intake__isnull=True),
    archived_at__isnull=True,
    is_draft=False,
)


class ProjectCategoryIssueFilterSet(IssueFilterSet):
    """IssueFilterSet plus sprint-by-name and state-by-name rich filters for master boards."""

    cycle_name = df_filters.CharFilter(method="filter_cycle_name")
    cycle_name__in = CharInFilter(method="filter_cycle_name_in", lookup_expr="in")
    state_name = df_filters.CharFilter(field_name="state__name")
    state_name__in = CharInFilter(field_name="state__name", lookup_expr="in")
    # Work item type quick filter of the board (rich filter `type_id__in`)
    type_id = df_filters.UUIDFilter(field_name="type_id")
    type_id__in = UUIDInFilter(field_name="type_id", lookup_expr="in")

    class Meta(IssueFilterSet.Meta):
        pass

    def filter_cycle_name(self, queryset, name, value):
        return Q(
            issue_cycle__cycle__name=value,
            issue_cycle__deleted_at__isnull=True,
            issue_cycle__cycle__deleted_at__isnull=True,
        )

    def filter_cycle_name_in(self, queryset, name, value):
        return Q(
            issue_cycle__cycle__name__in=value,
            issue_cycle__deleted_at__isnull=True,
            issue_cycle__cycle__deleted_at__isnull=True,
        )


def _get_category(slug, pk):
    return ProjectCategory.objects.filter(workspace__slug=slug, pk=pk).first()


def _category_not_found():
    return Response({"error": "Project category not found."}, status=status.HTTP_404_NOT_FOUND)


class ProjectCategoryViewSet(BaseViewSet):
    serializer_class = ProjectCategorySerializer
    model = ProjectCategory

    def get_queryset(self):
        return annotate_project_ids(ProjectCategory.objects.filter(workspace__slug=self.kwargs.get("slug"))).order_by(
            "sort_order", "name"
        )

    def _response_row(self, pk, response_status=status.HTTP_200_OK):
        category = self.get_queryset().filter(pk=pk).first()
        return Response(ProjectCategorySerializer(category).data, status=response_status)

    @allow_permission(allowed_roles=READ_ROLES, level="WORKSPACE")
    def list(self, request, slug):
        return Response(ProjectCategorySerializer(self.get_queryset(), many=True).data, status=status.HTTP_200_OK)

    @allow_permission(allowed_roles=READ_ROLES, level="WORKSPACE")
    def retrieve(self, request, slug, pk):
        category = self.get_queryset().filter(pk=pk).first()
        if category is None:
            return _category_not_found()
        return Response(ProjectCategorySerializer(category).data, status=status.HTTP_200_OK)

    @allow_permission(allowed_roles=WRITE_ROLES, level="WORKSPACE")
    def create(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        serializer = ProjectCategorySerializer(data=request.data, context={"workspace_id": workspace.id})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        category = serializer.save()
        return self._response_row(category.id, status.HTTP_201_CREATED)

    @allow_permission(allowed_roles=WRITE_ROLES, level="WORKSPACE")
    def partial_update(self, request, slug, pk):
        category = _get_category(slug, pk)
        if category is None:
            return _category_not_found()
        serializer = ProjectCategorySerializer(
            category, data=request.data, partial=True, context={"workspace_id": category.workspace_id}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return self._response_row(category.id)

    @allow_permission(allowed_roles=WRITE_ROLES, level="WORKSPACE")
    def destroy(self, request, slug, pk):
        category = _get_category(slug, pk)
        if category is None:
            return _category_not_found()
        delete_category(category)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectCategoryIssuesEndpoint(WorkspaceViewIssuesViewSet):
    """GET /api/workspaces/<slug>/project-categories/<pk>/issues/ (master board)."""

    filterset_class = ProjectCategoryIssueFilterSet

    def get_queryset(self):
        return Issue.issue_objects.filter(
            workspace__slug=self.kwargs.get("slug"),
            project__category_id=self.kwargs.get("pk"),
            project__deleted_at__isnull=True,
        )

    @method_decorator(gzip_page)
    @allow_permission(allowed_roles=READ_ROLES, level="WORKSPACE")
    def list(self, request, slug, pk):
        category = _get_category(slug, pk)
        if category is None:
            return _category_not_found()

        group_by = request.GET.get("group_by") or None
        sub_group_by = request.GET.get("sub_group_by") or None
        allowed_group_by = category_group_by_allowlist()
        for param, value in (("group_by", group_by), ("sub_group_by", sub_group_by)):
            if value is not None and value not in allowed_group_by:
                return Response({"error": f"Invalid {param} field: {value}"}, status=status.HTTP_400_BAD_REQUEST)
        if group_by and sub_group_by and group_by == sub_group_by:
            return Response(
                {"error": "Group by and sub group by cannot have same parameters"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Rich (JSON) filters, then legacy query-param filters, then project membership / guest scope
        issue_queryset = self.filter_queryset(self.get_queryset())
        filters = issue_filters(request.query_params, "GET")
        issue_queryset = issue_queryset.filter(**filters)
        issue_queryset = issue_queryset.filter(self._get_project_permission_filters())

        total_issue_queryset = copy.deepcopy(issue_queryset).only("id")

        issue_queryset = self.apply_annotations(issue_queryset)
        issue_queryset, order_by_param = order_issue_queryset(
            issue_queryset=issue_queryset, order_by_param=request.GET.get("order_by", "-created_at")
        )
        issue_queryset = issue_queryset_grouper(queryset=issue_queryset, group_by=group_by, sub_group_by=sub_group_by)

        def on_results(issues):
            return issue_on_results(group_by=group_by, issues=issues, sub_group_by=sub_group_by)

        if not group_by:
            return self.paginate(
                order_by=order_by_param,
                request=request,
                queryset=issue_queryset,
                total_count_queryset=total_issue_queryset,
                on_results=on_results,
            )

        # Columns only from the projects whose issues the requester can see (same scope as the rows)
        project_ids = member_project_ids(category_project_ids(category.id), request.user)

        def group_values(field):
            return category_group_values(
                field=field, slug=slug, project_ids=project_ids, filters=filters, queryset=total_issue_queryset
            )

        # The grouped paginators are built here (not via paginate(paginator_cls=...)) because the
        # shared ISSUE_GROUP_BY_ALLOWLIST check in BasePaginator.paginate does not know
        # "state__name"; group_by/sub_group_by were validated against the category allowlist above.
        if sub_group_by:
            paginator = SubGroupedOffsetPaginator(
                queryset=issue_queryset,
                order_by=order_by_param,
                group_by_field_name=group_by,
                sub_group_by_field_name=sub_group_by,
                group_by_fields=group_values(group_by),
                sub_group_by_fields=group_values(sub_group_by),
                count_filter=GROUP_COUNT_FILTER,
                total_count_queryset=total_issue_queryset,
            )
        else:
            paginator = GroupedOffsetPaginator(
                queryset=issue_queryset,
                order_by=order_by_param,
                group_by_field_name=group_by,
                group_by_fields=group_values(group_by),
                count_filter=GROUP_COUNT_FILTER,
                total_count_queryset=total_issue_queryset,
            )
        return self.paginate(
            request=request,
            paginator=paginator,
            on_results=on_results,
            group_by_field_name=group_by,
            sub_group_by_field_name=sub_group_by,
        )


class ProjectCategoryCyclesEndpoint(BaseAPIView):
    """GET /api/workspaces/<slug>/project-categories/<pk>/cycles/ -> [{name, start_date, end_date,
    project_ids}] distinct by name over the category's projects the user is a member of."""

    @allow_permission(allowed_roles=READ_ROLES, level="WORKSPACE")
    def get(self, request, slug, pk):
        category = _get_category(slug, pk)
        if category is None:
            return _category_not_found()
        project_ids = member_project_ids(category_project_ids(category.id), request.user)
        return Response(category_cycles(project_ids), status=status.HTTP_200_OK)
