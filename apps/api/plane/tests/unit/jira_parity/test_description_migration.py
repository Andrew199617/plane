# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity: an editor id-only description save (skip_activity) keeps updated_at/updated_by.

Opening an imported Jira work item in the web app makes the editor save its normalised description
once; that must not replace the imported "Updated" timestamp.
"""

from datetime import datetime, timezone

import pytest
from rest_framework import status

from plane.db.models import Issue, IssueActivity, Project, ProjectMember, State
from plane.utils.jira_parity.description_migration import is_description_migration_update

JIRA_UPDATED = datetime(2025, 8, 23, 18, 49, tzinfo=timezone.utc)


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Migration Save", identifier="MIG", workspace=workspace)
    ProjectMember.objects.create(project=project, member=create_user, role=20)
    return project


@pytest.fixture
def default_state(db, workspace, project):
    return State.objects.create(name="To Do", project=project, workspace=workspace, group="unstarted", default=True)


@pytest.fixture
def imported_issue(db, project, default_state):
    issue = Issue.objects.create(
        name="Imported", project=project, state=default_state, description_html="<p>From Jira</p>"
    )
    Issue.all_objects.filter(pk=issue.pk).update(updated_at=JIRA_UPDATED, updated_by=None)
    issue.refresh_from_db()
    return issue


def _url(workspace, project, issue):
    return f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{issue.id}/"


@pytest.mark.unit
class TestIsDescriptionMigrationUpdate:
    @pytest.mark.parametrize(
        "data,skip,expected",
        [
            ({"description_html": "<p>x</p>"}, "true", True),
            ({"description_html": "<p>x</p>"}, True, True),
            ({"description_html": "<p>x</p>", "description_json": {}}, "true", True),
            ({"description_html": "<p>x</p>"}, False, False),
            ({"description_html": "<p>x</p>"}, None, False),
            ({"description_html": "<p>x</p>"}, "false", False),
            ({"description_html": "<p>x</p>", "name": "Renamed"}, "true", False),
            ({"name": "Renamed"}, "true", False),
            ({}, "true", False),
            ("not a dict", "true", False),
        ],
    )
    def test_detection(self, data, skip, expected):
        assert is_description_migration_update(data, skip) is expected


@pytest.mark.unit
class TestMigrationSaveKeepsAuditFields:
    @pytest.mark.django_db
    def test_migration_save_keeps_updated_at(self, session_client, workspace, project, imported_issue):
        html = '<p data-id="5b0f">From Jira</p>'
        response = session_client.patch(
            _url(workspace, project, imported_issue),
            {"description_html": html, "skip_activity": "true"},
            format="json",
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT, getattr(response, "data", None)
        imported_issue.refresh_from_db()
        assert imported_issue.description_html == html
        assert imported_issue.updated_at == JIRA_UPDATED
        assert imported_issue.updated_by_id is None
        assert not IssueActivity.objects.filter(issue=imported_issue).exists()

    @pytest.mark.django_db
    def test_real_description_edit_bumps_updated_at(self, session_client, workspace, project, imported_issue):
        response = session_client.patch(
            _url(workspace, project, imported_issue), {"description_html": "<p>Edited</p>"}, format="json"
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
        imported_issue.refresh_from_db()
        assert imported_issue.description_html == "<p>Edited</p>"
        assert imported_issue.updated_at > JIRA_UPDATED

    @pytest.mark.django_db
    def test_skip_activity_with_other_fields_bumps_updated_at(self, session_client, workspace, project, imported_issue):
        response = session_client.patch(
            _url(workspace, project, imported_issue),
            {"description_html": "<p>From Jira</p>", "name": "Renamed", "skip_activity": "true"},
            format="json",
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
        imported_issue.refresh_from_db()
        assert imported_issue.name == "Renamed"
        assert imported_issue.updated_at > JIRA_UPDATED
