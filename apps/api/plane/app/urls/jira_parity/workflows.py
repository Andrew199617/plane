# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity workflows URLs.

Aggregated by plane.app.urls.jira_parity and served under /api/.
"""

from django.urls import path

from plane.app.views.jira_parity.workflows import ProjectMyStateTransitionsEndpoint, ProjectStateTransitionEndpoint

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/state-transitions/",
        ProjectStateTransitionEndpoint.as_view(http_method_names=["get", "put"]),
        name="jp-project-state-transitions",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/state-transitions/me/",
        ProjectMyStateTransitionsEndpoint.as_view(http_method_names=["get"]),
        name="jp-project-state-transitions-me",
    ),
]
