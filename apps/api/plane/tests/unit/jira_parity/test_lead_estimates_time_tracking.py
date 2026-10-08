# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity lead-estimates feature: time tracking (original / remaining estimate, minutes)."""

import json

import pytest
from rest_framework import status

from plane.bgtasks.issue_activities_task import update_issue_activity
from plane.db.models import Issue, Project, ProjectMember, State
from plane.utils.time_tracking import normalize_estimate_minutes


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Time Tracking", identifier="TTK", workspace=workspace)
    ProjectMember.objects.create(project=project, member=create_user, role=20)
    return project


@pytest.fixture
def default_state(db, workspace, project):
    return State.objects.create(name="To Do", project=project, workspace=workspace, group="unstarted", default=True)


@pytest.fixture
def issue(db, project, default_state):
    return Issue.objects.create(name="Estimated", project=project, state=default_state, original_estimate=120)


def _activities(requested, current):
    issue_activities = []
    update_issue_activity(
        requested_data=json.dumps(requested),
        current_instance=json.dumps(current),
        issue_id="00000000-0000-0000-0000-000000000001",
        project_id="00000000-0000-0000-0000-000000000002",
        workspace_id="00000000-0000-0000-0000-000000000003",
        actor_id="00000000-0000-0000-0000-000000000004",
        issue_activities=issue_activities,
        epoch=1,
    )
    return issue_activities


@pytest.mark.unit
class TestNormalizeEstimateMinutes:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, None),
            ("", None),
            ("  ", None),
            (True, None),
            (-5, None),
            ("abc", None),
            (0, 0),
            ("0", 0),
            (90, 90),
            ("150", 150),
            (60.0, 60),
            ("2.5", 2),
        ],
    )
    def test_values(self, value, expected):
        assert normalize_estimate_minutes(value) == expected


@pytest.mark.unit
class TestEstimateActivity:
    def test_set_original_estimate(self):
        activities = _activities({"original_estimate": 150}, {"original_estimate": None})
        assert len(activities) == 1
        activity = activities[0]
        assert activity.field == "original_estimate"
        assert activity.verb == "updated"
        assert activity.old_value == ""
        assert activity.new_value == "150"

    def test_change_remaining_estimate_from_string(self):
        activities = _activities({"remaining_estimate": "30"}, {"remaining_estimate": 60})
        assert [(a.field, a.old_value, a.new_value, a.verb) for a in activities] == [
            ("remaining_estimate", "60", "30", "updated")
        ]

    def test_clear_estimate(self):
        activities = _activities({"original_estimate": None}, {"original_estimate": 480})
        assert [(a.field, a.old_value, a.new_value, a.verb) for a in activities] == [
            ("original_estimate", "480", "", "removed")
        ]

    def test_zero_is_distinct_from_unset(self):
        activities = _activities({"original_estimate": 0}, {"original_estimate": None})
        assert [(a.old_value, a.new_value) for a in activities] == [("", "0")]

    def test_unchanged_is_ignored(self):
        assert (
            _activities(
                {"original_estimate": "120", "remaining_estimate": 60},
                {
                    "original_estimate": 120,
                    "remaining_estimate": 60,
                },
            )
            == []
        )

    def test_both_fields(self):
        activities = _activities(
            {"original_estimate": 2400, "remaining_estimate": 960},
            {"original_estimate": None, "remaining_estimate": None},
        )
        assert sorted(a.field for a in activities) == ["original_estimate", "remaining_estimate"]


@pytest.mark.contract
class TestEstimateEndpoints:
    @pytest.mark.django_db
    def test_app_create_and_patch_round_trip(self, session_client, workspace, project, default_state):
        base = f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/"
        response = session_client.post(
            base, {"name": "With estimate", "original_estimate": 150, "remaining_estimate": 90}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["original_estimate"] == 150
        assert response.data["remaining_estimate"] == 90
        issue_id = response.data["id"]

        response = session_client.patch(f"{base}{issue_id}/", {"remaining_estimate": 30}, format="json")
        assert response.status_code == status.HTTP_204_NO_CONTENT, getattr(response, "data", None)
        issue = Issue.objects.get(pk=issue_id)
        assert (issue.original_estimate, issue.remaining_estimate) == (150, 30)

        response = session_client.patch(f"{base}{issue_id}/", {"original_estimate": None}, format="json")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        issue.refresh_from_db()
        assert issue.original_estimate is None

        detail = session_client.get(f"{base}{issue_id}/")
        assert detail.status_code == status.HTTP_200_OK
        assert detail.data["original_estimate"] is None
        assert detail.data["remaining_estimate"] == 30

    @pytest.mark.django_db
    def test_app_rejects_negative(self, session_client, workspace, project, default_state):
        response = session_client.post(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/",
            {"name": "Negative", "original_estimate": -1},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_app_list_includes_estimates(self, session_client, workspace, project, issue):
        response = session_client.get(f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/")
        assert response.status_code == status.HTTP_200_OK
        payload = json.dumps(response.data, default=str)
        assert '"original_estimate": 120' in payload
        assert '"remaining_estimate": null' in payload

    @pytest.mark.django_db
    def test_app_list_ordering_by_estimate(self, session_client, workspace, project, default_state):
        Issue.objects.create(name="Small", project=project, state=default_state, original_estimate=30)
        Issue.objects.create(name="Large", project=project, state=default_state, original_estimate=600)
        Issue.objects.create(name="Unset", project=project, state=default_state)
        response = session_client.get(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/",
            {"order_by": "-original_estimate", "per_page": 10},
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        names = [row["name"] for row in response.data["results"]]
        assert names[:2] == ["Large", "Small"]

    @pytest.mark.django_db
    def test_v1_create_and_read(self, api_key_client, workspace, project, default_state):
        base = f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/"
        response = api_key_client.post(base, {"name": "V1 estimate", "original_estimate": 480}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["original_estimate"] == 480
        assert response.data["remaining_estimate"] is None

        response = api_key_client.patch(f"{base}{response.data['id']}/", {"remaining_estimate": 240}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["remaining_estimate"] == 240
