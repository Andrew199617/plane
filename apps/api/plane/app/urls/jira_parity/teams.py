# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity teams URLs.

Append path(...) entries; aggregated by plane.app.urls.jira_parity and served under /api/.
Import views from plane.app.views.jira_parity.teams.
"""

from django.urls import path

from plane.app.views.jira_parity.teams import TeamEndpoint, TeamMemberEndpoint, TeamProjectEndpoint

urlpatterns = [
    path("workspaces/<str:slug>/teams/", TeamEndpoint.as_view(), name="jp-workspace-teams"),
    path("workspaces/<str:slug>/teams/<uuid:pk>/", TeamEndpoint.as_view(), name="jp-workspace-team"),
    path(
        "workspaces/<str:slug>/teams/<uuid:team_id>/members/",
        TeamMemberEndpoint.as_view(),
        name="jp-workspace-team-members",
    ),
    path(
        "workspaces/<str:slug>/teams/<uuid:team_id>/members/<uuid:member_id>/",
        TeamMemberEndpoint.as_view(),
        name="jp-workspace-team-member",
    ),
    path(
        "workspaces/<str:slug>/teams/<uuid:team_id>/projects/",
        TeamProjectEndpoint.as_view(),
        name="jp-workspace-team-projects",
    ),
    path(
        "workspaces/<str:slug>/teams/<uuid:team_id>/projects/<uuid:project_id>/",
        TeamProjectEndpoint.as_view(),
        name="jp-workspace-team-project",
    ),
]
