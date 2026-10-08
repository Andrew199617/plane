# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity work_item_types URLs.

Append path(...) entries; aggregated by plane.app.urls.jira_parity and served under /api/.
Import views from plane.app.views.jira_parity.work_item_types.
"""

from django.urls import path

from plane.app.views.jira_parity.work_item_types import ProjectWorkItemTypeEndpoint, WorkItemTypeEndpoint

urlpatterns = [
    path(
        "workspaces/<str:slug>/work-item-types/",
        WorkItemTypeEndpoint.as_view(),
        name="jp-workspace-work-item-types",
    ),
    path(
        "workspaces/<str:slug>/work-item-types/<uuid:pk>/",
        WorkItemTypeEndpoint.as_view(),
        name="jp-workspace-work-item-type",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-item-types/",
        ProjectWorkItemTypeEndpoint.as_view(),
        name="jp-project-work-item-types",
    ),
]
