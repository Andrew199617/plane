# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity sprint lifecycle URLs (cycles are sprints).

Aggregated by plane.app.urls.jira_parity and served under /api/.
"""

from django.urls import path

from plane.app.views.jira_parity.sprints import SprintLifecycleViewSet, SprintNextNameEndpoint

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/sprints/next-name/",
        SprintNextNameEndpoint.as_view(http_method_names=["get"]),
        name="jp-sprint-next-name",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/cycles/<uuid:cycle_id>/start/",
        SprintLifecycleViewSet.as_view({"post": "start"}),
        name="jp-sprint-start",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/cycles/<uuid:cycle_id>/complete/",
        SprintLifecycleViewSet.as_view({"post": "complete"}),
        name="jp-sprint-complete",
    ),
]
