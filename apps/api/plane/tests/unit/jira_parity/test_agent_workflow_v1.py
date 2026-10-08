# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity Agent role + state workflows on the public API v1 (X-Api-Key)."""

from uuid import uuid4

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    APIToken,
    Issue,
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


def _token_client(user, workspace):
    token = APIToken.objects.create(user=user, workspace=workspace, user_type=1, label="t")
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=token.token)
    return client


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Agent V1", identifier="AVO", workspace=workspace)
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
def agent_client(agent, workspace):
    return _token_client(agent, workspace)


@pytest.fixture
def issue(project, states, create_user):
    return Issue.objects.create(
        name="V1 item", project=project, workspace=project.workspace, state=states["To Do"], created_by=create_user
    )


def _items(project):
    return f"/api/v1/workspaces/{SLUG}/projects/{project.id}/work-items/"


def _item(project, issue):
    return f"{_items(project)}{issue.id}/"


@pytest.mark.contract
@pytest.mark.django_db
class TestAgentV1:
    def test_reads(self, agent_client, project, issue):
        assert agent_client.get(_items(project)).status_code == 200
        assert agent_client.get(_item(project, issue)).status_code == 200
        response = agent_client.get(f"/api/v1/workspaces/{SLUG}/work-items/AVO-{issue.sequence_id}/")
        assert response.status_code == 200
        assert agent_client.get(f"/api/v1/workspaces/{SLUG}/projects/{project.id}/states/").status_code == 200
        assert agent_client.get(f"{_item(project, issue)}comments/").status_code == 200

    def test_state_change_rules(self, agent_client, project, issue, states):
        url = _item(project, issue)
        response = agent_client.patch(url, {"state": str(states["In Progress"].id)}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.content
        response = agent_client.patch(url, {"state": str(states["Done"].id)}, format="json")
        assert response.status_code == 403 and response.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
        response = agent_client.patch(url, {"state": str(states["In Review"].id)}, format="json")
        assert response.status_code == 200
        issue.refresh_from_db()
        assert issue.state_id == states["In Review"].id

    def test_field_edits_and_create_delete_forbidden(self, agent_client, project, issue):
        response = agent_client.patch(_item(project, issue), {"name": "renamed"}, format="json")
        assert response.status_code == 403 and response.json()["code"] == "AGENT_FIELD_NOT_ALLOWED"
        response = agent_client.patch(_item(project, issue), {"priority": "highest"}, format="json")
        assert response.status_code == 403
        assert agent_client.post(_items(project), {"name": "new"}, format="json").status_code == 403
        assert agent_client.delete(_item(project, issue)).status_code == 403
        assert Issue.objects.filter(pk=issue.pk).exists()

    def test_epic_locked(self, agent_client, project, states, workspace):
        epic_type = IssueType.objects.create(workspace=workspace, name="Epic", is_epic=True)
        epic = Issue.objects.create(
            name="E", project=project, workspace=workspace, state=states["To Do"], type=epic_type
        )
        response = agent_client.patch(_item(project, epic), {"state": str(states["In Progress"].id)}, format="json")
        assert response.status_code == 403 and response.json()["code"] == "AGENT_EPIC_STATE_CHANGE_FORBIDDEN"

    def test_comments(self, agent_client, project, issue, create_user, workspace):
        url = f"{_item(project, issue)}comments/"
        response = agent_client.post(url, {"comment_html": "<p>agent note</p>"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.content
        own_id = response.json()["id"]
        assert IssueComment.objects.get(pk=own_id).actor_id is not None

        response = agent_client.patch(f"{url}{own_id}/", {"comment_html": "<p>edited</p>"}, format="json")
        assert response.status_code == 200
        assert agent_client.delete(f"{url}{own_id}/").status_code == 403

        # impersonation through created_by is not available to agents
        response = agent_client.post(
            url, {"comment_html": "<p>x</p>", "created_by": str(create_user.id)}, format="json"
        )
        assert response.status_code == 403 and response.json()["code"] == "AGENT_FIELD_NOT_ALLOWED"

        other = IssueComment.objects.create(
            issue=issue, project=project, workspace=workspace, actor=create_user, comment_html="<p>admin</p>"
        )
        response = agent_client.patch(f"{url}{other.id}/", {"comment_html": "<p>hijack</p>"}, format="json")
        assert response.status_code == 403
        assert agent_client.delete(f"{url}{other.id}/").status_code == 403

    def test_other_writes_forbidden(self, agent_client, project, issue):
        base = f"/api/v1/workspaces/{SLUG}/projects/{project.id}"
        attempts = [
            ("post", f"{base}/intake-issues/", {"issue": {"name": "x"}}),
            ("post", f"{_item(project, issue)}links/", {"url": "https://example.com"}),
            ("post", f"{base}/labels/", {"name": "l"}),
            ("post", f"{base}/states/", {"name": "S", "color": "#000000"}),
            ("post", f"{base}/cycles/", {"name": "c"}),
            ("post", f"/api/v1/workspaces/{SLUG}/projects/", {"name": "P", "identifier": "PX"}),
        ]
        for method, url, body in attempts:
            response = getattr(agent_client, method)(url, body, format="json")
            assert response.status_code == 403, (url, response.status_code)


@pytest.mark.contract
@pytest.mark.django_db
class TestMemberV1:
    def test_member_unaffected_then_restricted_by_rules(self, project, issue, states, workspace):
        member = _user(workspace, MEMBER)
        ProjectMember.objects.create(project=project, member=member, role=MEMBER)
        client = _token_client(member, workspace)
        url = _item(project, issue)
        assert client.patch(url, {"name": "member rename"}, format="json").status_code == 200
        assert client.patch(url, {"state": str(states["Done"].id)}, format="json").status_code == 200

        Project.objects.filter(pk=project.pk).update(is_workflow_enabled=True)
        StateTransition.objects.create(
            project=project,
            workspace=workspace,
            from_state=states["Done"],
            to_state=states["Won't Fix"],
            roles=[MEMBER],
        )
        response = client.patch(url, {"state": str(states["To Do"].id)}, format="json")
        assert response.status_code == 403 and response.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
        assert client.patch(url, {"state": str(states["Won't Fix"].id)}, format="json").status_code == 200

    def test_admin_token_unrestricted(self, project, issue, states, workspace, create_user):
        client = _token_client(create_user, workspace)
        Project.objects.filter(pk=project.pk).update(is_workflow_enabled=True)
        StateTransition.objects.create(
            project=project, workspace=workspace, from_state=None, to_state=states["In Progress"], roles=[MEMBER]
        )
        assert client.patch(_item(project, issue), {"state": str(states["Done"].id)}, format="json").status_code == 200
