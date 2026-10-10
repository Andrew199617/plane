# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity project_categories URLs.

Append path(...) entries; aggregated by plane.app.urls.jira_parity and served under /api/.
Import views from plane.app.views.jira_parity.project_categories.
"""

from django.urls import path

from plane.app.views.jira_parity.project_categories import (
    ProjectCategoryCyclesEndpoint,
    ProjectCategoryIssuesEndpoint,
    ProjectCategoryViewSet,
)

urlpatterns = [
    path(
        "workspaces/<str:slug>/project-categories/",
        ProjectCategoryViewSet.as_view({"get": "list", "post": "create"}),
        name="jp-project-categories",
    ),
    path(
        "workspaces/<str:slug>/project-categories/<uuid:pk>/",
        ProjectCategoryViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="jp-project-category",
    ),
    path(
        "workspaces/<str:slug>/project-categories/<uuid:pk>/issues/",
        ProjectCategoryIssuesEndpoint.as_view({"get": "list"}),
        name="jp-project-category-issues",
    ),
    path(
        "workspaces/<str:slug>/project-categories/<uuid:pk>/cycles/",
        ProjectCategoryCyclesEndpoint.as_view(),
        name="jp-project-category-cycles",
    ),
]
