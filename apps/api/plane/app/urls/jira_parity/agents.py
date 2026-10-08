# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity agents URLs.

Aggregated by plane.app.urls.jira_parity and served under /api/.
"""

from django.urls import path

from plane.app.views.jira_parity.agents import WorkspaceAgentEndpoint, WorkspaceAgentTokenEndpoint

urlpatterns = [
    path(
        "workspaces/<str:slug>/agents/",
        WorkspaceAgentEndpoint.as_view(http_method_names=["get", "post"]),
        name="jp-workspace-agents",
    ),
    path(
        "workspaces/<str:slug>/agents/<uuid:pk>/",
        WorkspaceAgentEndpoint.as_view(http_method_names=["get", "patch", "delete"]),
        name="jp-workspace-agent",
    ),
    path(
        "workspaces/<str:slug>/agents/<uuid:user_id>/tokens/",
        WorkspaceAgentTokenEndpoint.as_view(http_method_names=["post"]),
        name="jp-workspace-agent-tokens",
    ),
    path(
        "workspaces/<str:slug>/agents/<uuid:user_id>/tokens/<uuid:pk>/",
        WorkspaceAgentTokenEndpoint.as_view(http_method_names=["delete"]),
        name="jp-workspace-agent-token",
    ),
]
