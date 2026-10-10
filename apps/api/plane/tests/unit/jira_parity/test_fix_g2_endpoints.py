# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity workflows over HTTP: null-state bypasses, creation in a state, intake and agent guards."""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from plane.db.models import (
    APIToken,
    DraftIssue,
    FileAsset,
    Intake,
    IntakeIssue,
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

ADMIN, MEMBER, AGENT = 20, 15, 10
SLUG = "test-workspace"


def _user(workspace, workspace_role):
    user = User.objects.create(email=f"{uuid4().hex[:10]}@plane.so", username=uuid4().hex[:12])
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=workspace_role)
    return user


def _session(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _token(user, workspace):
    token = APIToken.objects.create(user=user, workspace=workspace, user_type=1, label="t")
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=token.token)
    return client


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="G2 Endpoints", identifier="GTE", workspace=workspace, intake_view=True)
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
def member(workspace, project):
    user = _user(workspace, MEMBER)
    ProjectMember.objects.create(project=project, member=user, role=MEMBER)
    return user


@pytest.fixture
def agent(workspace, project):
    user = _user(workspace, AGENT)
    ProjectMember.objects.create(project=project, member=user, role=AGENT)
    return user


@pytest.fixture
def restricted(project, states):
    """Workflow on; members may only do To Do -> In Progress."""
    Project.objects.filter(pk=project.pk).update(is_workflow_enabled=True)
    StateTransition.objects.create(
        project=project,
        workspace=project.workspace,
        from_state=states["To Do"],
        to_state=states["In Progress"],
        roles=[MEMBER],
    )


def _issue(project, state, **kwargs):
    return Issue.objects.create(name="Item", project=project, workspace=project.workspace, state=state, **kwargs)


def _creator(obj, user):
    # BaseModel.save() takes created_by from the request user (none in tests)
    type(obj)._base_manager.filter(pk=obj.pk).update(created_by=user)
    return obj


def _app(project):
    return f"/api/workspaces/{SLUG}/projects/{project.id}"


def _v1(project):
    return f"/api/v1/workspaces/{SLUG}/projects/{project.id}"


def _state_id(issue):
    return Issue.all_objects.values_list("state_id", flat=True).get(pk=issue.pk)


@pytest.mark.contract
@pytest.mark.django_db
class TestMemberNullState:
    def test_app_null_state_is_checked(self, project, states, member, restricted):
        issue = _issue(project, states["Done"])
        client = _session(member)
        for payload in ({"state_id": None}, {"state": None}):
            response = client.patch(f"{_app(project)}/issues/{issue.id}/", payload, format="json")
            assert response.status_code == 403, payload
            assert response.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
            assert response.json()["to_state_id"] == str(states["To Do"].id)
        assert _state_id(issue) == states["Done"].id

    def test_v1_null_state_is_checked(self, project, states, member, workspace, restricted):
        issue = _issue(project, states["Done"])
        response = _token(member, workspace).patch(
            f"{_v1(project)}/work-items/{issue.id}/", {"state": None}, format="json"
        )
        assert response.status_code == 403 and response.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
        assert _state_id(issue) == states["Done"].id

    def test_unrestricted_null_state_still_resets(self, project, states, member, workspace):
        app_issue, v1_issue = _issue(project, states["Done"]), _issue(project, states["Done"])
        response = _session(member).patch(f"{_app(project)}/issues/{app_issue.id}/", {"state_id": None}, format="json")
        assert response.status_code == 204
        response = _token(member, workspace).patch(
            f"{_v1(project)}/work-items/{v1_issue.id}/", {"state": None}, format="json"
        )
        assert response.status_code == 200
        assert _state_id(app_issue) == _state_id(v1_issue) == states["To Do"].id


@pytest.mark.contract
@pytest.mark.django_db
class TestCreateInState:
    def test_app_create(self, project, states, member, restricted):
        client = _session(member)
        url = f"{_app(project)}/issues/"
        response = client.post(url, {"name": "Done item", "state_id": str(states["Done"].id)}, format="json")
        assert response.status_code == 403 and response.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
        assert not Issue.objects.filter(project=project, name="Done item").exists()
        for name, state in (("plain", None), ("todo", "To Do"), ("progress", "In Progress")):
            payload = {"name": name, **({"state_id": str(states[state].id)} if state else {})}
            assert client.post(url, payload, format="json").status_code == 201, name

    def test_v1_create(self, project, states, member, workspace, restricted):
        client = _token(member, workspace)
        url = f"{_v1(project)}/work-items/"
        response = client.post(url, {"name": "Done item", "state": str(states["Done"].id)}, format="json")
        assert response.status_code == 403 and response.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
        assert not Issue.objects.filter(project=project, name="Done item").exists()
        response = client.post(url, {"name": "Progress item", "state": str(states["In Progress"].id)}, format="json")
        assert response.status_code == 201

    def test_unrestricted_and_admin_create(self, project, states, member, session_client, restricted):
        payload = {"name": "Admin done", "state_id": str(states["Done"].id)}
        assert session_client.post(f"{_app(project)}/issues/", payload, format="json").status_code == 201
        Project.objects.filter(pk=project.pk).update(is_workflow_enabled=False)
        payload = {"name": "Member done", "state_id": str(states["Done"].id)}
        assert _session(member).post(f"{_app(project)}/issues/", payload, format="json").status_code == 201

    def test_draft_conversion(self, project, states, member, restricted):
        draft = _creator(
            DraftIssue.objects.create(name="Draft", project=project, workspace=project.workspace, state=states["Done"]),
            member,
        )
        url = f"/api/workspaces/{SLUG}/draft-to-issue/{draft.id}/"
        client = _session(member)
        response = client.post(url, {"name": "Draft", "state_id": str(states["Done"].id)}, format="json")
        assert response.status_code == 403 and response.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
        assert DraftIssue.objects.filter(pk=draft.pk).exists()
        response = client.post(url, {"name": "Draft", "state_id": str(states["To Do"].id)}, format="json")
        assert response.status_code == 201


@pytest.mark.contract
@pytest.mark.django_db
class TestIntake:
    @pytest.fixture
    def intake_issue(self, project, states, member):
        intake = Intake.objects.create(name="Intake", project=project, workspace=project.workspace, is_default=True)
        issue = _creator(_issue(project, states["Triage"]), member)
        IntakeIssue.objects.create(intake=intake, issue=issue, project=project, workspace=project.workspace)
        return issue

    @pytest.mark.parametrize("alias,state_name", [("state", "Done"), ("state", None), ("state_id", "Done")])
    def test_app_create_always_starts_in_triage(
        self, project, states, member, intake_issue, restricted, alias, state_name
    ):
        state_id = str(states[state_name].id) if state_name else None
        payload = {"issue": {"name": "New intake", alias: state_id}}
        response = _session(member).post(f"{_app(project)}/intake-issues/", payload, format="json")
        assert response.status_code == 200
        created = Issue.objects.get(project=project, name="New intake")
        assert created.state_id == states["Triage"].id
        assert IntakeIssue.objects.get(issue=created).status == -2

    def test_v1_create_always_starts_in_triage(self, project, states, member, workspace, intake_issue, restricted):
        payload = {"issue": {"name": "New intake", "state": str(states["Done"].id)}}
        response = _token(member, workspace).post(f"{_v1(project)}/intake-issues/", payload, format="json")
        assert response.status_code == 201
        created = Issue.objects.get(project=project, name="New intake")
        assert created.state_id == states["Triage"].id
        assert IntakeIssue.objects.get(issue=created).status == -2

    def test_v1_leaving_triage_uses_the_persisted_state(
        self, project, states, member, workspace, intake_issue, restricted
    ):
        client = _token(member, workspace)
        url = f"{_v1(project)}/intake-issues/{intake_issue.id}/"
        for target in ("Done", "In Progress", "To Do"):
            response = client.patch(url, {"issue": {"state": str(states[target].id)}}, format="json")
            assert response.status_code == 403 and response.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
            assert _state_id(intake_issue) == states["Triage"].id
        # The regular v1 issue endpoint also exposes intake items, so it must enforce the same rules.
        response = client.patch(
            f"{_v1(project)}/work-items/{intake_issue.id}/", {"state": str(states["In Progress"].id)}, format="json"
        )
        assert response.status_code == 403 and response.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
        assert IntakeIssue.objects.get(issue=intake_issue).status == -2
        # An explicit any-source rule permits the direct edit.
        StateTransition.objects.create(
            project=project,
            workspace=workspace,
            from_state=None,
            to_state=states["In Progress"],
            roles=[MEMBER],
        )
        response = client.patch(url, {"issue": {"state": str(states["In Progress"].id)}}, format="json")
        assert response.status_code == 200 and _state_id(intake_issue) == states["In Progress"].id
        # back in a regular state: a null state is a move to the default state
        response = client.patch(url, {"issue": {"state": None}}, format="json")
        assert response.status_code == 403
        assert _state_id(intake_issue) == states["In Progress"].id

    def test_app_null_state(self, project, states, member, intake_issue, restricted):
        client = _session(member)
        url = f"{_app(project)}/intake-issues/{intake_issue.id}/"
        response = client.patch(url, {"issue": {"state_id": None}}, format="json")
        assert response.status_code == 403 and response.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
        assert _state_id(intake_issue) == states["Triage"].id
        Issue.objects.filter(pk=intake_issue.pk).update(state=states["Done"])
        response = client.patch(url, {"issue": {"state_id": None}}, format="json")
        assert response.status_code == 403 and response.json()["code"] == "STATE_TRANSITION_NOT_ALLOWED"
        assert _state_id(intake_issue) == states["Done"].id

    def test_accept_moves_to_default_state(self, project, states, intake_issue, session_client, restricted):
        url = f"{_app(project)}/intake-issues/{intake_issue.id}/"
        assert session_client.patch(url, {"status": 1}, format="json").status_code == 200
        assert _state_id(intake_issue) == states["To Do"].id
        assert IntakeIssue.objects.get(issue=intake_issue).status == 1

    def test_v1_accept_moves_to_default_state(self, project, states, intake_issue, workspace, create_user, restricted):
        url = f"{_v1(project)}/intake-issues/{intake_issue.id}/"
        assert _token(create_user, workspace).patch(url, {"status": 1}, format="json").status_code == 200
        assert _state_id(intake_issue) == states["To Do"].id
        assert IntakeIssue.objects.get(issue=intake_issue).status == 1


@pytest.mark.contract
@pytest.mark.django_db
class TestAgentNullState:
    @pytest.fixture
    def epic(self, project, states, workspace):
        epic_type = IssueType.objects.create(workspace=workspace, name="Epic", is_epic=True)
        return _issue(project, states["In Progress"], type=epic_type)

    @pytest.mark.parametrize(
        "payload",
        [{"state": None}, {"state_id": None}, {"state_id": ""}, {"state_id": "CURRENT", "state": None}],
    )
    def test_app(self, project, states, agent, epic, payload):
        client = _session(agent)
        for issue in (_issue(project, states["In Progress"]), epic):
            body = {key: str(issue.state_id) if value == "CURRENT" else value for key, value in payload.items()}
            response = client.patch(f"{_app(project)}/issues/{issue.id}/", body, format="json")
            assert response.status_code == 403 and response.json()["code"] == "AGENT_FIELD_NOT_ALLOWED", body
            assert _state_id(issue) == states["In Progress"].id

    @pytest.mark.parametrize("payload", [{"state": None}, {"state_id": "CURRENT", "state": None}])
    def test_v1(self, project, states, agent, epic, workspace, payload):
        client = _token(agent, workspace)
        for issue in (_issue(project, states["In Progress"]), epic):
            body = {key: str(issue.state_id) if value == "CURRENT" else value for key, value in payload.items()}
            response = client.patch(f"{_v1(project)}/work-items/{issue.id}/", body, format="json")
            assert response.status_code == 403 and response.json()["code"] == "AGENT_FIELD_NOT_ALLOWED", body
            assert _state_id(issue) == states["In Progress"].id

    def test_allowed_move_still_works(self, project, states, agent):
        issue = _issue(project, states["In Progress"])
        url = f"{_app(project)}/issues/{issue.id}/"
        body = {"state_id": str(states["In Review"].id), "state": str(states["In Review"].id)}
        assert _session(agent).patch(url, body, format="json").status_code == 204
        assert _state_id(issue) == states["In Review"].id


@pytest.mark.contract
@pytest.mark.django_db
class TestAgentCommentAssetLink:
    def test_asset_ids_must_be_a_list_of_ids(self, project, states, agent):
        issue = _issue(project, states["To Do"])
        comment = IssueComment.objects.create(
            issue=issue, project=project, workspace=project.workspace, actor=agent, comment_html="<p>x</p>"
        )
        asset = FileAsset.objects.create(
            asset="comment.png",
            attributes={"name": "comment.png", "type": "image/png", "size": 1},
            entity_type=FileAsset.EntityTypeContext.COMMENT_DESCRIPTION,
            workspace=project.workspace,
        )
        _creator(asset, agent)
        url = f"/api/assets/v2/workspaces/{SLUG}/projects/{project.id}/{comment.id}/bulk/"
        client = _session(agent)
        for asset_ids in ({str(asset.id): True}, str(asset.id), [], ["not-a-uuid"], [{"id": str(asset.id)}]):
            response = client.post(url, {"asset_ids": asset_ids}, format="json")
            assert response.status_code == 403 and response.json()["code"] == "AGENT_FIELD_NOT_ALLOWED", asset_ids
        assert client.post(url, {}, format="json").status_code == 400
        assert client.post(url, {"asset_ids": [str(asset.id)]}, format="json").status_code == 204
        assert FileAsset.objects.get(pk=asset.pk).comment_id == comment.id
