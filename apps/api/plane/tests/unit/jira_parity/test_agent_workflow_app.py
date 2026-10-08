# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity Agent role + state workflows on the internal (session) API /api/..."""

from uuid import uuid4

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    Issue,
    IssueAssignee,
    IssueComment,
    IssueType,
    Project,
    ProjectMember,
    State,
    StateTransition,
    User,
    WorkspaceMember,
)
from plane.db.models.state import DEFAULT_STATES

ADMIN, MEMBER, AGENT, GUEST = 20, 15, 10, 5
SLUG = "test-workspace"


def _user(workspace, workspace_role):
    user = User.objects.create(email=f"{uuid4().hex[:10]}@plane.so", username=uuid4().hex[:12])
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=workspace_role)
    return user


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Agent App", identifier="AAPP", workspace=workspace)
    ProjectMember.objects.create(project=project, member=create_user, role=ADMIN)
    State.objects.bulk_create(
        [
            State(
                name=s["name"],
                color=s["color"],
                sequence=s["sequence"],
                group=s["group"],
                default=s.get("default", False),
                project=project,
                workspace=workspace,
            )
            for s in DEFAULT_STATES
        ]
    )
    return project


@pytest.fixture
def states(project):
    return {s.name: s for s in State.all_state_objects.filter(project=project)}


@pytest.fixture
def agent(workspace, project):
    user = _user(workspace, AGENT)
    ProjectMember.objects.create(project=project, member=user, role=AGENT)
    return user


@pytest.fixture
def member(workspace, project):
    user = _user(workspace, MEMBER)
    ProjectMember.objects.create(project=project, member=user, role=MEMBER)
    return user


@pytest.fixture
def guest(workspace, project):
    user = _user(workspace, GUEST)
    ProjectMember.objects.create(project=project, member=user, role=GUEST)
    return user


@pytest.fixture
def agent_client(agent):
    return _client(agent)


@pytest.fixture
def issue(project, states, create_user):
    return Issue.objects.create(
        name="Todo item", project=project, workspace=project.workspace, state=states["To Do"], created_by=create_user
    )


@pytest.fixture
def agent_created_issue(project, states, agent):
    # simulates an imported work item whose created_by is the agent
    return Issue.objects.create(
        name="Imported", project=project, workspace=project.workspace, state=states["To Do"], created_by=agent
    )


@pytest.fixture
def epic(project, states, workspace):
    epic_type = IssueType.objects.create(workspace=workspace, name="Epic", is_epic=True)
    return Issue.objects.create(
        name="Epic", project=project, workspace=workspace, state=states["To Do"], type=epic_type
    )


def _base(project):
    return f"/api/workspaces/{SLUG}/projects/{project.id}"


def _issue_url(project, issue):
    return f"{_base(project)}/issues/{issue.id}/"


def _code(response):
    return response.json().get("code")


@pytest.mark.contract
@pytest.mark.django_db
class TestAgentReads:
    def test_agent_reads_like_a_member(self, agent_client, project, issue):
        base = _base(project)
        for url in (
            f"{base}/issues/",
            f"{base}/issues/{issue.id}/",
            f"{base}/issues/{issue.id}/comments/",
            f"{base}/states/",
            f"{base}/cycles/",
            f"{base}/modules/",
            f"{base}/members/",
            f"{base}/state-transitions/",
            f"/api/workspaces/{SLUG}/members/",
        ):
            response = agent_client.get(url)
            assert response.status_code == status.HTTP_200_OK, (url, response.status_code)

    def test_agent_does_not_see_member_emails(self, agent_client, member):
        rows = agent_client.get(f"/api/workspaces/{SLUG}/members/").json()
        assert rows and all("email" not in (row.get("member") or {}) for row in rows)


@pytest.mark.contract
@pytest.mark.django_db
class TestAgentIssueWrites:
    def test_create_and_delete_forbidden(self, agent_client, project, states, agent_created_issue):
        response = agent_client.post(f"{_base(project)}/issues/", {"name": "x"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN and _code(response) == "AGENT_ACTION_FORBIDDEN"
        # creator bypass of allow_permission must not let an agent delete an (imported) item it "created"
        assert agent_client.delete(_issue_url(project, agent_created_issue)).status_code == 403
        assert Issue.objects.filter(pk=agent_created_issue.pk).exists()
        response = agent_client.post(
            f"{_base(project)}/bulk-delete-issues/", {"issue_ids": [str(agent_created_issue.id)]}, format="json"
        )
        assert response.status_code == 403
        assert agent_client.post(f"{_base(project)}/bulk-archive-issues/", {}, format="json").status_code == 403
        assert (
            agent_client.put(_issue_url(project, agent_created_issue), {"name": "renamed"}, format="json").status_code
            == 403
        )

    @pytest.mark.parametrize(
        "payload",
        [
            {"name": "renamed"},
            {"priority": "highest"},
            {"assignee_ids": []},
            {"label_ids": []},
            {"parent_id": None},
            {"description_html": "<p>x</p>"},
            {"original_estimate": 60},
        ],
    )
    def test_field_edits_forbidden(self, agent_client, project, issue, payload):
        response = agent_client.patch(_issue_url(project, issue), payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert _code(response) == "AGENT_FIELD_NOT_ALLOWED"

    def test_state_plus_other_field_forbidden(self, agent_client, project, issue, states):
        response = agent_client.patch(
            _issue_url(project, issue), {"state_id": str(states["In Progress"].id), "name": "x"}, format="json"
        )
        assert response.status_code == 403 and _code(response) == "AGENT_FIELD_NOT_ALLOWED"
        issue.refresh_from_db()
        assert issue.state_id == states["To Do"].id and issue.name == "Todo item"

    def test_allowed_transitions(self, agent_client, project, issue, states):
        url = _issue_url(project, issue)
        assert agent_client.patch(url, {"state_id": str(states["In Progress"].id)}, format="json").status_code == 204
        assert agent_client.patch(url, {"state_id": str(states["In Review"].id)}, format="json").status_code == 204
        issue.refresh_from_db()
        assert issue.state_id == states["In Review"].id

        for target in ("Done", "To Do", "Won't Fix"):
            response = agent_client.patch(url, {"state_id": str(states[target].id)}, format="json")
            assert response.status_code == 403, target
            body = response.json()
            assert body["code"] == "STATE_TRANSITION_NOT_ALLOWED" and body["error"]
        issue.refresh_from_db()
        assert issue.state_id == states["In Review"].id

    def test_kanban_drop_payload(self, agent_client, project, issue, states):
        url = _issue_url(project, issue)
        payload = {
            "id": str(issue.id),
            "project_id": str(project.id),
            "sort_order": 1234.0,
            "state_id": str(states["In Progress"].id),
        }
        assert agent_client.patch(url, payload, format="json").status_code == 204
        issue.refresh_from_db()
        assert issue.state_id == states["In Progress"].id and issue.sort_order == 1234.0
        # a reorder alone (no state) is not an agent action
        assert agent_client.patch(url, {"sort_order": 1.0}, format="json").status_code == 403
        # the same state with a reorder is a no-op transition
        assert agent_client.patch(url, {"state_id": str(states["In Progress"].id)}, format="json").status_code == 204

    def test_state_and_state_id_must_agree(self, agent_client, project, issue, states):
        response = agent_client.patch(
            _issue_url(project, issue),
            {"state_id": str(states["In Progress"].id), "state": str(states["Done"].id)},
            format="json",
        )
        assert response.status_code == 403 and _code(response) == "AGENT_FIELD_NOT_ALLOWED"

    def test_epic_locked(self, agent_client, project, epic, states):
        response = agent_client.patch(
            _issue_url(project, epic), {"state_id": str(states["In Progress"].id)}, format="json"
        )
        assert response.status_code == 403 and _code(response) == "AGENT_EPIC_STATE_CHANGE_FORBIDDEN"

    def test_other_writes_forbidden(self, agent_client, project, issue, states):
        base = _base(project)
        attempts = [
            ("post", f"{base}/issues/{issue.id}/reactions/", {"reaction": "+1"}),
            ("post", f"{base}/issues/{issue.id}/issue-links/", {"url": "https://example.com"}),
            ("post", f"{base}/issues/{issue.id}/sub-issues/", {"sub_issue_ids": []}),
            ("post", f"{base}/issues/{issue.id}/issue-relation/", {"relation_type": "relates_to", "issues": []}),
            ("post", f"{base}/issue-labels/", {"name": "x"}),
            ("post", f"{base}/intake-issues/", {"issue": {"name": "x"}}),
            ("patch", f"{base}/states/{states['To Do'].id}/", {"name": "Renamed"}),
            ("post", f"{base}/cycles/", {"name": "c"}),
            ("post", f"{base}/modules/", {"name": "m"}),
            ("post", f"{base}/members/leave/", {}),
            ("put", f"{base}/state-transitions/", []),
            ("post", f"/api/workspaces/{SLUG}/projects/", {"name": "P", "identifier": "PP"}),
            ("post", f"/api/workspaces/{SLUG}/agents/", {"display_name": "x"}),
        ]
        for method, url, body in attempts:
            response = getattr(agent_client, method)(url, body, format="json")
            assert response.status_code == status.HTTP_403_FORBIDDEN, (method, url, response.status_code)
        assert State.objects.get(pk=states["To Do"].pk).name == "To Do"

    def test_personal_writes_allowed(self, agent_client, project, issue):
        base = _base(project)
        assert agent_client.post(f"{base}/issues/{issue.id}/subscribe/", {}, format="json").status_code == 201
        assert agent_client.delete(f"{base}/issues/{issue.id}/subscribe/").status_code == 204
        response = agent_client.patch(
            f"{base}/user-properties/", {"display_filters": {"layout": "kanban"}}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.contract
@pytest.mark.django_db
class TestAgentComments:
    def test_comment_rules(self, agent_client, session_client, project, issue):
        url = f"{_base(project)}/issues/{issue.id}/comments/"
        response = agent_client.post(url, {"comment_html": "<p>on it</p>"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.content
        own_id = response.json()["id"]

        response = agent_client.patch(f"{url}{own_id}/", {"comment_html": "<p>edited</p>"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert "edited" in IssueComment.objects.get(pk=own_id).comment_html

        assert agent_client.delete(f"{url}{own_id}/").status_code == status.HTTP_403_FORBIDDEN
        assert IssueComment.objects.filter(pk=own_id).exists()

        other_id = session_client.post(url, {"comment_html": "<p>admin</p>"}, format="json").json()["id"]
        response = agent_client.patch(f"{url}{other_id}/", {"comment_html": "<p>hijack</p>"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "admin" in IssueComment.objects.get(pk=other_id).comment_html

        response = agent_client.post(url, {"comment_html": "<p>x</p>", "created_by": str(uuid4())}, format="json")
        assert response.status_code == 403 and _code(response) == "AGENT_FIELD_NOT_ALLOWED"


@pytest.mark.contract
@pytest.mark.django_db
class TestAssignmentAndMembers:
    def test_agents_can_be_assigned_guests_cannot(self, session_client, project, issue, agent, guest):
        response = session_client.patch(
            _issue_url(project, issue), {"assignee_ids": [str(agent.id), str(guest.id)]}, format="json"
        )
        assert response.status_code == 204
        assignees = set(IssueAssignee.objects.filter(issue=issue).values_list("assignee_id", flat=True))
        assert assignees == {agent.id}

    def test_project_member_role_coherence(self, session_client, project, workspace, agent):
        new_agent = _user(workspace, AGENT)
        human = _user(workspace, MEMBER)
        url = f"{_base(project)}/members/"
        bad = session_client.post(url, {"members": [{"member_id": str(new_agent.id), "role": MEMBER}]}, format="json")
        assert bad.status_code == 400
        bad = session_client.post(url, {"members": [{"member_id": str(human.id), "role": AGENT}]}, format="json")
        assert bad.status_code == 400
        ok = session_client.post(url, {"members": [{"member_id": str(new_agent.id), "role": AGENT}]}, format="json")
        assert ok.status_code == 201
        row = ProjectMember.objects.get(project=project, member=agent)
        response = session_client.patch(f"{url}{row.id}/", {"role": MEMBER}, format="json")
        assert response.status_code == 400
        assert ProjectMember.objects.get(pk=row.pk).role == AGENT

    def test_workspace_role_change_cascades(self, session_client, project, workspace, member):
        other = Project.objects.create(name="Other", identifier="OTHR", workspace=workspace)
        workspace_member = WorkspaceMember.objects.get(workspace=workspace, member=member)
        response = session_client.patch(
            f"/api/workspaces/{SLUG}/members/{workspace_member.id}/", {"role": AGENT}, format="json"
        )
        assert response.status_code == 200, response.content
        assert set(ProjectMember.objects.filter(member=member, is_active=True).values_list("project_id", "role")) == {
            (project.id, AGENT),
            (other.id, AGENT),
        }
        response = session_client.patch(
            f"/api/workspaces/{SLUG}/members/{workspace_member.id}/", {"role": MEMBER}, format="json"
        )
        assert response.status_code == 200
        assert set(ProjectMember.objects.filter(member=member).values_list("role", flat=True)) == {MEMBER}

    def test_project_create_joins_agents_and_seeds_workflow(self, session_client, agent):
        response = session_client.post(
            f"/api/workspaces/{SLUG}/projects/", {"name": "Fresh", "identifier": "FRSH"}, format="json"
        )
        assert response.status_code == 201, response.content
        project = Project.objects.get(identifier="FRSH")
        assert project.is_workflow_enabled is True
        assert ProjectMember.objects.get(project=project, member=agent).role == AGENT
        names = list(State.objects.filter(project=project).order_by("sequence").values_list("name", flat=True))
        assert names == ["To Do", "In Progress", "In Review", "Done", "Won't Fix"]
        assert State.objects.get(project=project, default=True).name == "To Do"
        assert {
            (rule.from_state.name, rule.to_state.name, tuple(rule.roles))
            for rule in StateTransition.objects.filter(project=project)
        } == {("To Do", "In Progress", (AGENT,)), ("In Progress", "In Review", (AGENT,))}


@pytest.mark.contract
@pytest.mark.django_db
class TestMemberWorkflow:
    def test_member_unrestricted_by_default(self, project, issue, states, member):
        client = _client(member)
        url = _issue_url(project, issue)
        assert client.patch(url, {"state_id": str(states["Done"].id)}, format="json").status_code == 204
        assert client.patch(url, {"name": "Member rename"}, format="json").status_code == 204
        assert client.get(f"{_base(project)}/state-transitions/me/").json() == {"restricted": False}

    def test_member_rules_enforced_when_enabled(self, session_client, project, issue, states, member):
        Project.objects.filter(pk=project.pk).update(is_workflow_enabled=True)
        response = session_client.put(
            f"{_base(project)}/state-transitions/",
            [
                {
                    "from_state_id": str(states["To Do"].id),
                    "to_state_id": str(states["In Progress"].id),
                    "roles": [MEMBER],
                }
            ],
            format="json",
        )
        assert response.status_code == 200
        client = _client(member)
        url = _issue_url(project, issue)
        response = client.patch(url, {"state_id": str(states["Done"].id)}, format="json")
        assert response.status_code == 403 and _code(response) == "STATE_TRANSITION_NOT_ALLOWED"
        issue.refresh_from_db()
        assert issue.state_id == states["To Do"].id
        # PUT is routed through partial_update (and its checks) too
        assert client.put(url, {"state_id": str(states["Done"].id)}, format="json").status_code == 403
        assert client.patch(url, {"state_id": str(states["In Progress"].id)}, format="json").status_code == 204
        # admins are never restricted
        assert session_client.patch(url, {"state_id": str(states["Done"].id)}, format="json").status_code == 204
        mine = client.get(f"{_base(project)}/state-transitions/me/").json()
        assert mine["restricted"] is True and mine["role"] == MEMBER
        assert mine["transitions"][str(states["To Do"].id)] == [str(states["In Progress"].id)]

    def test_agent_my_transitions(self, agent_client, session_client, project, states):
        mine = agent_client.get(f"{_base(project)}/state-transitions/me/").json()
        assert mine["restricted"] is True and mine["role"] == AGENT and mine["epic_locked"] is True
        assert mine["transitions"][str(states["To Do"].id)] == [str(states["In Progress"].id)]
        assert session_client.get(f"{_base(project)}/state-transitions/me/").json() == {"restricted": False}
