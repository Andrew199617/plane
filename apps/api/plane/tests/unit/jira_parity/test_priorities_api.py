# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity priorities through the HTTP APIs: defaults, validation/aliasing, ordering, grouping, intake."""

import pytest
from django.core.cache import cache
from rest_framework import status

from plane.celery import app as celery_app
from plane.db.models import (
    DeployBoard,
    Intake,
    Issue,
    IssueActivity,
    IssueAssignee,
    Project,
    ProjectMember,
    State,
)

JIRA_KEYS = ["highest", "high", "medium", "low", "lowest"]


@pytest.fixture(autouse=True)
def _reset_api_key_throttle_cache():
    cache.delete_pattern("api_key:*")
    yield
    cache.delete_pattern("api_key:*")


@pytest.fixture
def celery_eager():
    """Run the issue activity task in-process so activity rows can be asserted."""
    original_always_eager = celery_app.conf.task_always_eager
    original_eager_propagates = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    yield
    celery_app.conf.task_always_eager = original_always_eager
    celery_app.conf.task_eager_propagates = original_eager_propagates


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(
        name="Priority Project", identifier="PRI", workspace=workspace, created_by=create_user, intake_view=True
    )
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    State.objects.create(
        name="To Do", group="unstarted", default=True, project=project, workspace=workspace, color="#000000"
    )
    return project


@pytest.fixture
def one_issue_per_priority(db, workspace, project, create_user):
    state = State.objects.get(project=project, default=True)
    return {
        key: Issue.objects.create(
            name=f"{key} item", priority=key, project=project, workspace=workspace, state=state, created_by=create_user
        )
        for key in ["low", "highest", "medium", "lowest", "high"]
    }


def v1_issues_url(workspace, project):
    return f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/issues/"


def app_issues_url(workspace, project):
    return f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/"


@pytest.mark.contract
class TestV1IssuePriority:
    @pytest.mark.django_db
    def test_create_defaults_to_medium(self, api_key_client, workspace, project):
        response = api_key_client.post(v1_issues_url(workspace, project), {"name": "No priority"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["priority"] == "medium"
        assert Issue.objects.get(pk=response.data["id"]).priority == "medium"

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "sent,stored",
        [
            ("highest", "highest"),
            ("lowest", "lowest"),
            ("Highest", "highest"),
            ("urgent", "highest"),
            ("none", "medium"),
        ],
    )
    def test_create_accepts_jira_and_legacy_values(self, api_key_client, workspace, project, sent, stored):
        response = api_key_client.post(
            v1_issues_url(workspace, project), {"name": f"P {sent}", "priority": sent}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["priority"] == stored
        assert Issue.objects.get(pk=response.data["id"]).priority == stored

    @pytest.mark.django_db
    def test_create_rejects_unknown_priority(self, api_key_client, workspace, project):
        response = api_key_client.post(
            v1_issues_url(workspace, project), {"name": "Bad", "priority": "bogus"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "priority" in response.data

    @pytest.mark.django_db
    def test_patch_records_canonical_activity(self, api_key_client, workspace, project, celery_eager):
        issue = Issue.objects.create(
            name="Patch me", project=project, workspace=workspace, state=State.objects.get(project=project)
        )
        assert issue.priority == "medium"
        response = api_key_client.patch(
            f"{v1_issues_url(workspace, project)}{issue.id}/", {"priority": "urgent"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        issue.refresh_from_db()
        assert issue.priority == "highest"
        activity = IssueActivity.objects.filter(issue=issue, field="priority").order_by("-created_at").first()
        assert activity is not None
        assert (activity.old_value, activity.new_value) == ("medium", "highest")

    @pytest.mark.django_db
    def test_order_by_priority(self, api_key_client, workspace, project, one_issue_per_priority):
        url = v1_issues_url(workspace, project)
        # The public API keeps upstream semantics: "priority" lists the most important first.
        response = api_key_client.get(url, {"order_by": "priority"})
        assert response.status_code == status.HTTP_200_OK, response.data
        assert [row["priority"] for row in response.data["results"]] == JIRA_KEYS

        response = api_key_client.get(url, {"order_by": "-priority"})
        assert [row["priority"] for row in response.data["results"]] == list(reversed(JIRA_KEYS))


@pytest.mark.contract
class TestAppIssuePriority:
    @pytest.mark.django_db
    def test_create_defaults_to_medium_and_maps_legacy(self, session_client, workspace, project):
        url = app_issues_url(workspace, project)
        response = session_client.post(url, {"name": "Default"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["priority"] == "medium"

        response = session_client.post(url, {"name": "Legacy", "priority": "urgent"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["priority"] == "highest"

        response = session_client.post(url, {"name": "Bad", "priority": "bogus"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_order_by_minus_priority_lists_highest_first(
        self, session_client, workspace, project, one_issue_per_priority
    ):
        url = app_issues_url(workspace, project)
        response = session_client.get(url, {"order_by": "-priority", "per_page": 50, "cursor": "50:0:0"})
        assert response.status_code == status.HTTP_200_OK, response.data
        assert [row["priority"] for row in response.data["results"]] == JIRA_KEYS

        response = session_client.get(url, {"order_by": "priority", "per_page": 50, "cursor": "50:0:0"})
        assert [row["priority"] for row in response.data["results"]] == list(reversed(JIRA_KEYS))

    @pytest.mark.django_db
    def test_group_by_priority_has_all_jira_groups(self, session_client, workspace, project, one_issue_per_priority):
        url = app_issues_url(workspace, project)
        response = session_client.get(url, {"group_by": "priority", "per_page": 50, "cursor": "50:0:0"})
        assert response.status_code == status.HTTP_200_OK, response.data
        groups = response.data["results"]
        assert set(JIRA_KEYS) <= set(groups)
        for key in JIRA_KEYS:
            assert groups[key]["total_results"] == 1
            assert groups[key]["results"][0]["priority"] == key

    @pytest.mark.django_db
    def test_legacy_priority_query_param_is_mapped(self, session_client, workspace, project, one_issue_per_priority):
        url = app_issues_url(workspace, project)
        response = session_client.get(url, {"priority": "urgent,high", "per_page": 50, "cursor": "50:0:0"})
        assert response.status_code == status.HTTP_200_OK, response.data
        assert sorted(row["priority"] for row in response.data["results"]) == ["high", "highest"]


@pytest.mark.contract
class TestIntakePriority:
    def url(self, workspace, project):
        return f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/intake-issues/"

    @pytest.fixture
    def intake(self, db, workspace, project):
        return Intake.objects.create(name="Intake", project=project, workspace=workspace, is_default=True)

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "sent,stored", [(None, "medium"), ("lowest", "lowest"), ("none", "medium"), ("Highest", "highest")]
    )
    def test_v1_intake_create(self, api_key_client, workspace, project, intake, sent, stored):
        payload = {"issue": {"name": f"Intake {sent}"}}
        if sent is not None:
            payload["issue"]["priority"] = sent
        response = api_key_client.post(self.url(workspace, project), payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert Issue.all_objects.get(pk=response.data["issue"]).priority == stored

    @pytest.mark.django_db
    def test_v1_intake_rejects_unknown(self, api_key_client, workspace, project, intake):
        response = api_key_client.post(
            self.url(workspace, project), {"issue": {"name": "Bad", "priority": "bogus"}}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_app_intake_create_normalizes(self, session_client, workspace, project, intake):
        url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/intake-issues/"
        response = session_client.post(url, {"issue": {"name": "App intake", "priority": "Lowest"}}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert Issue.all_objects.filter(name="App intake").get().priority == "lowest"

        response = session_client.post(url, {"issue": {"name": "App intake bad", "priority": "bogus"}}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_space_intake_create_defaults_and_normalizes(self, session_client, workspace, project, intake):
        board = DeployBoard.objects.create(
            workspace=workspace, project=project, entity_name="project", entity_identifier=project.id, intake=intake
        )
        url = f"/api/public/anchor/{board.anchor}/intakes/{intake.id}/intake-issues/"

        # Upstream defaulted public intake submissions to "low"; Jira-parity default is Medium.
        response = session_client.post(url, {"issue": {"name": "Space default"}}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert Issue.all_objects.get(name="Space default").priority == "medium"

        response = session_client.post(url, {"issue": {"name": "Space legacy", "priority": "urgent"}}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert Issue.all_objects.get(name="Space legacy").priority == "highest"

        response = session_client.post(url, {"issue": {"name": "Space bad", "priority": "bogus"}}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Issue.all_objects.filter(name="Space bad").exists()


@pytest.mark.contract
class TestPriorityAnalytics:
    @pytest.mark.django_db
    def test_build_chart_orders_priority_bars_highest_first(self, workspace, project, one_issue_per_priority):
        from plane.utils.build_chart import build_analytics_chart

        chart = build_analytics_chart(Issue.issue_objects.filter(project=project), "PRIORITY")
        assert [row["key"] for row in chart["data"]] == JIRA_KEYS
        assert [row["name"] for row in chart["data"]] == ["Highest", "High", "Medium", "Low", "Lowest"]
        assert all(row["count"] == 1 for row in chart["data"])

    @pytest.mark.django_db
    def test_profile_stats_priority_distribution(self, session_client, workspace, project, create_user):
        state = State.objects.get(project=project, default=True)
        for key in ["lowest", "highest", "highest"]:
            issue = Issue.objects.create(
                name=f"mine {key}", priority=key, project=project, workspace=workspace, state=state
            )
            IssueAssignee.objects.create(issue=issue, assignee=create_user, project=project, workspace=workspace)
        response = session_client.get(f"/api/workspaces/{workspace.slug}/user-stats/{create_user.id}/")
        assert response.status_code == status.HTTP_200_OK, response.data
        distribution = [(row["priority"], row["priority_count"]) for row in response.data["priority_distribution"]]
        assert distribution == [("highest", 2), ("lowest", 1)]
