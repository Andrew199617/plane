# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity agents settings API (/api/workspaces/<slug>/agents/...) and workflow rules API
(/api/workspaces/<slug>/projects/<pid>/state-transitions/...)."""

from uuid import uuid4

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    APIToken,
    Issue,
    Project,
    ProjectMember,
    State,
    StateTransition,
    User,
    Workspace,
    WorkspaceMember,
)
from plane.db.models.state import DEFAULT_STATES

ADMIN, MEMBER, AGENT, GUEST = 20, 15, 10, 5
SLUG = "test-workspace"
AGENTS = f"/api/workspaces/{SLUG}/agents/"


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
    project = Project.objects.create(name="Endpoints", identifier="ENDP", workspace=workspace)
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


@pytest.mark.contract
@pytest.mark.django_db
class TestAgentsApi:
    def test_create_list_token_and_use_it(self, session_client, project, states):
        response = session_client.post(AGENTS, {"display_name": "Claude Dev", "token_label": "ci"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.content
        body = response.json()
        assert body["token"].startswith("plane_api_")
        assert body["role"] == AGENT and body["project_count"] == 1
        assert body["member"]["display_name"] == "Claude Dev"
        assert body["member"]["email"] == "claude-dev@agents.test-workspace.local"
        assert [t["label"] for t in body["tokens"]] == ["ci"]
        assert "token" not in body["tokens"][0]
        user_id = body["member"]["id"]
        assert ProjectMember.objects.get(project=project, member_id=user_id).role == AGENT

        listed = session_client.get(AGENTS).json()
        assert [row["member"]["id"] for row in listed] == [user_id]
        assert "token" not in listed[0] and "token" not in listed[0]["tokens"][0]
        assert session_client.get(f"{AGENTS}{user_id}/").json()["member"]["id"] == user_id

        # the token works on /api/v1 with the agent restrictions
        issue = Issue.objects.create(name="i", project=project, workspace=project.workspace, state=states["To Do"])
        v1 = APIClient()
        v1.credentials(HTTP_X_API_KEY=body["token"])
        url = f"/api/v1/workspaces/{SLUG}/projects/{project.id}/work-items/{issue.id}/"
        assert v1.patch(url, {"state": str(states["In Progress"].id)}, format="json").status_code == 200
        assert v1.patch(url, {"name": "nope"}, format="json").status_code == 403

    def test_create_without_token_and_validation(self, session_client, workspace, create_user):
        response = session_client.post(AGENTS, {"display_name": "Quiet", "generate_token": False}, format="json")
        assert response.status_code == 201 and "token" not in response.json()
        assert response.json()["tokens"] == []
        assert session_client.post(AGENTS, {"display_name": ""}, format="json").status_code == 400
        assert session_client.post(AGENTS, {}, format="json").status_code == 400
        dup = session_client.post(
            AGENTS, {"display_name": "Dup", "email": response.json()["member"]["email"]}, format="json"
        )
        assert dup.status_code == 400 and "already exists" in dup.json()["error"]
        # agents only get placeholder addresses: an existing (or any real) email is refused
        real = session_client.post(AGENTS, {"display_name": "Real", "email": create_user.email}, format="json")
        assert real.status_code == 400 and "domain" in real.json()["error"]
        bad_email = session_client.post(AGENTS, {"display_name": "Bad", "email": "not-an-email"}, format="json")
        assert bad_email.status_code == 400

    def test_rename_tokens_and_deactivate(self, session_client, project):
        body = session_client.post(AGENTS, {"display_name": "Old name"}, format="json").json()
        user_id = body["member"]["id"]
        response = session_client.patch(f"{AGENTS}{user_id}/", {"display_name": "New name"}, format="json")
        assert response.status_code == 200 and response.json()["member"]["display_name"] == "New name"
        assert session_client.patch(f"{AGENTS}{user_id}/", {"display_name": ""}, format="json").status_code == 400

        response = session_client.post(f"{AGENTS}{user_id}/tokens/", {"label": "second"}, format="json")
        assert response.status_code == 201 and response.json()["token"].startswith("plane_api_")
        second_id = response.json()["id"]
        assert len(session_client.get(f"{AGENTS}{user_id}/").json()["tokens"]) == 2

        assert session_client.delete(f"{AGENTS}{user_id}/tokens/{second_id}/").status_code == 204
        assert not APIToken.objects.filter(pk=second_id).exists()
        assert len(session_client.get(f"{AGENTS}{user_id}/").json()["tokens"]) == 1
        assert session_client.delete(f"{AGENTS}{user_id}/tokens/{second_id}/").status_code == 404

        assert session_client.delete(f"{AGENTS}{user_id}/").status_code == 204
        assert session_client.get(AGENTS).json() == []
        assert not WorkspaceMember.objects.get(workspace__slug=SLUG, member_id=user_id).is_active
        assert not ProjectMember.objects.filter(member_id=user_id, is_active=True).exists()
        assert not APIToken.objects.filter(user_id=user_id, is_active=True).exists()
        assert session_client.patch(f"{AGENTS}{user_id}/", {"display_name": "x"}, format="json").status_code == 404

    def test_unknown_or_human_user_is_not_an_agent(self, session_client, workspace):
        human = _user(workspace, MEMBER)
        assert session_client.get(f"{AGENTS}{human.id}/").status_code == 404
        assert session_client.delete(f"{AGENTS}{human.id}/").status_code == 404
        assert session_client.post(f"{AGENTS}{human.id}/tokens/", {}, format="json").status_code == 404
        assert WorkspaceMember.objects.get(member=human).is_active
        # holding the Agent role does not make a human an agent account
        human_agent = _user(workspace, AGENT)
        assert session_client.get(f"{AGENTS}{human_agent.id}/").status_code == 404
        assert session_client.post(f"{AGENTS}{human_agent.id}/tokens/", {}, format="json").status_code == 404
        assert session_client.get(AGENTS).json() == []

    def test_admin_only(self, workspace):
        member_client = _client(_user(workspace, MEMBER))
        assert member_client.get(AGENTS).status_code == 403
        assert member_client.post(AGENTS, {"display_name": "x"}, format="json").status_code == 403
        other_ws = Workspace.objects.create(name="Other", slug="other-agents", owner=_user(workspace, MEMBER))
        assert member_client.get("/api/workspaces/other-agents/agents/").status_code == 403
        assert other_ws.id


@pytest.mark.contract
@pytest.mark.django_db
class TestStateTransitionsApi:
    def _url(self, project):
        return f"/api/workspaces/{SLUG}/projects/{project.id}/state-transitions/"

    def test_list_and_replace(self, session_client, project, states):
        assert session_client.get(self._url(project)).json() == []
        rules = [
            {
                "from_state_id": str(states["To Do"].id),
                "to_state_id": str(states["In Progress"].id),
                "roles": [AGENT],
                "exclude_epics": True,
            },
            {"from_state_id": None, "to_state_id": str(states["Done"].id), "roles": [MEMBER, GUEST]},
        ]
        response = session_client.put(self._url(project), rules, format="json")
        assert response.status_code == 200, response.content
        body = response.json()
        assert len(body) == 2
        by_to = {rule["to_state_id"]: rule for rule in body}
        assert by_to[str(states["In Progress"].id)]["roles"] == [AGENT]
        assert by_to[str(states["In Progress"].id)]["exclude_epics"] is True
        assert by_to[str(states["Done"].id)]["from_state_id"] is None
        assert by_to[str(states["Done"].id)]["roles"] == [MEMBER, GUEST]
        assert {"id", "from_state_id", "to_state_id", "roles", "exclude_epics"} <= set(body[0])
        assert session_client.get(self._url(project)).json() == body

        # wrapped body, replace again: the any->Done rule is dropped, the other keeps its id
        kept_id = by_to[str(states["In Progress"].id)]["id"]
        response = session_client.put(self._url(project), {"rules": rules[:1]}, format="json")
        assert response.status_code == 200
        assert [rule["id"] for rule in response.json()] == [kept_id]
        assert session_client.put(self._url(project), [], format="json").json() == []
        assert StateTransition.all_objects.filter(project=project).count() == 0

    def test_replace_validation(self, session_client, project, states, workspace):
        other = Project.objects.create(name="Other", identifier="OTRP", workspace=workspace)
        foreign = State.objects.create(
            name="Foreign", group="started", color="#000", project=other, workspace=workspace
        )
        todo, done = str(states["To Do"].id), str(states["Done"].id)
        bad_bodies = [
            [{"from_state_id": todo, "to_state_id": str(foreign.id), "roles": [MEMBER]}],
            [{"from_state_id": todo, "to_state_id": str(states["Triage"].id), "roles": [MEMBER]}],
            [{"from_state_id": todo, "to_state_id": todo, "roles": [MEMBER]}],
            [{"from_state_id": todo, "to_state_id": done, "roles": [ADMIN]}],
            [{"from_state_id": todo, "to_state_id": done, "roles": [7]}],
            [{"from_state_id": todo, "roles": [MEMBER]}],
            {"not": "a list"},
        ]
        for body in bad_bodies:
            response = session_client.put(self._url(project), body, format="json")
            assert response.status_code == 400, body
        assert StateTransition.objects.filter(project=project).count() == 0

    def test_permissions(self, project, states, workspace):
        member = _user(workspace, MEMBER)
        ProjectMember.objects.create(project=project, member=member, role=MEMBER)
        client = _client(member)
        assert client.get(self._url(project)).status_code == 200
        assert client.get(f"{self._url(project)}me/").status_code == 200
        body = [{"from_state_id": None, "to_state_id": str(states["Done"].id), "roles": [MEMBER]}]
        assert client.put(self._url(project), body, format="json").status_code == 403
        outsider = _client(_user(workspace, MEMBER))
        assert outsider.get(self._url(project)).status_code == 403
        assert outsider.get(f"{self._url(project)}me/").status_code == 403

    def test_workflow_flag_via_project_patch(self, session_client, project, workspace):
        url = f"/api/workspaces/{SLUG}/projects/{project.id}/"
        response = session_client.patch(url, {"is_workflow_enabled": True}, format="json")
        assert response.status_code == 200, response.content
        project.refresh_from_db()
        assert project.is_workflow_enabled is True
        assert session_client.get(url).json()["is_workflow_enabled"] is True
        member = _user(workspace, MEMBER)
        ProjectMember.objects.create(project=project, member=member, role=MEMBER)
        assert _client(member).patch(url, {"is_workflow_enabled": False}, format="json").status_code == 403
