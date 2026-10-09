# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity release action URLs (modules are releases / fix versions).

Aggregated by plane.app.urls.jira_parity and served under /api/.
"""

from django.urls import path

from plane.app.views.jira_parity.releases import ReleaseActionsViewSet

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/modules/<uuid:module_id>/release/",
        ReleaseActionsViewSet.as_view({"post": "release"}),
        name="jp-release-release",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/modules/<uuid:module_id>/unrelease/",
        ReleaseActionsViewSet.as_view({"post": "unrelease"}),
        name="jp-release-unrelease",
    ),
]
