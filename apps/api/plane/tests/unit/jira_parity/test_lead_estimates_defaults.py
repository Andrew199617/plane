# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity lead-estimates feature: project lead / default assignee."""

from unittest import mock

import pytest
from rest_framework import status

from plane.db.models import (
    Intake,
    Issue,
    IssueAssignee,
    Project,
    ProjectMember,
    State,
    User,
    WorkspaceMember,
)
from plane.utils.project_defaults import (
    apply_project_lead_change,
    apply_project_lead_defaults,
    assign_default_assignee,
)


# ---------------------------------------------------------------- fixtures


def _make_user(email, workspace=None, role=15):
    user = User.objects.create(email=email, username=email.split("@")[0], first_name=email.split("@")[0])
    if workspace is not None:
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=role)
    return user


@pytest.fixture
def member_b(db, workspace):
    return _make_user("lead-b@plane.so", workspace, role=15)


@pytest.fixture
def member_c(db, workspace):
    return _make_user("member-c@plane.so", workspace, role=15)


@pytest.fixture
def agent_user(db, workspace):
    return _make_user("agent-x@plane.so", workspace, role=10)


@pytest.fixture
def bare_project(db, workspace, create_user):
    """A project created directly (no hooks), with the creator as Admin."""
    project = Project.objects.create(name="Lead Defaults", identifier="LDF", workspace=workspace)
    ProjectMember.objects.create(project=project, member=create_user, role=20)
    return project


@pytest.fixture
def default_state(db, workspace, bare_project):
    return State.objects.create(
        name="To Do", project=bare_project, workspace=workspace, group="unstarted", default=True
    )


def _role(project, user):
    return ProjectMember.objects.get(project=project, member=user).role


# ---------------------------------------------------------------- apply_project_lead_defaults


@pytest.mark.unit
class TestApplyProjectLeadDefaults:
    @pytest.mark.django_db
    def test_lead_and_default_assignee_default_to_creator(self, bare_project, create_user):
        updates = apply_project_lead_defaults(bare_project, create_user)
        bare_project.refresh_from_db()
        assert bare_project.project_lead_id == create_user.id
        assert bare_project.default_assignee_id == create_user.id
        assert set(updates) == {"project_lead_id", "default_assignee_id"}
        assert _role(bare_project, create_user) == 20

    @pytest.mark.django_db
    def test_existing_lead_becomes_default_assignee_and_admin(self, bare_project, create_user, member_b):
        Project.objects.filter(pk=bare_project.pk).update(project_lead=member_b)
        bare_project.refresh_from_db()
        apply_project_lead_defaults(bare_project, create_user)
        bare_project.refresh_from_db()
        assert bare_project.project_lead_id == member_b.id
        assert bare_project.default_assignee_id == member_b.id
        assert _role(bare_project, member_b) == 20

    @pytest.mark.django_db
    def test_existing_default_assignee_is_kept_and_made_member(self, bare_project, create_user, member_c):
        Project.objects.filter(pk=bare_project.pk).update(default_assignee=member_c)
        bare_project.refresh_from_db()
        apply_project_lead_defaults(bare_project, create_user)
        bare_project.refresh_from_db()
        assert bare_project.project_lead_id == create_user.id
        assert bare_project.default_assignee_id == member_c.id
        assert _role(bare_project, member_c) == 15

    @pytest.mark.django_db
    def test_actor_without_member_role_is_not_made_lead(self, bare_project, agent_user):
        apply_project_lead_defaults(bare_project, agent_user)
        bare_project.refresh_from_db()
        assert bare_project.project_lead_id is None
        assert bare_project.default_assignee_id is None

    @pytest.mark.django_db
    def test_no_actor_is_a_noop(self, bare_project):
        assert apply_project_lead_defaults(bare_project, None) == {}
        bare_project.refresh_from_db()
        assert bare_project.project_lead_id is None

    @pytest.mark.django_db
    def test_agent_lead_is_capped_at_agent_role(self, bare_project, create_user, agent_user):
        Project.objects.filter(pk=bare_project.pk).update(project_lead=agent_user)
        bare_project.refresh_from_db()
        apply_project_lead_defaults(bare_project, create_user)
        assert _role(bare_project, agent_user) == 10

    @pytest.mark.django_db
    def test_idempotent(self, bare_project, create_user):
        apply_project_lead_defaults(bare_project, create_user)
        assert apply_project_lead_defaults(bare_project, create_user) == {}
        assert ProjectMember.objects.filter(project=bare_project, member=create_user).count() == 1


# ---------------------------------------------------------------- apply_project_lead_change


def _set(project, **values):
    Project.objects.filter(pk=project.pk).update(**values)
    project.refresh_from_db()


@pytest.mark.unit
class TestApplyProjectLeadChange:
    @pytest.mark.django_db
    def test_default_assignee_follows_lead(self, bare_project, create_user, member_b):
        _set(bare_project, project_lead=member_b, default_assignee=create_user)
        updates = apply_project_lead_change(
            bare_project,
            old_lead_id=create_user.id,
            old_default_assignee_id=create_user.id,
            requested_data={"project_lead": str(member_b.id)},
        )
        bare_project.refresh_from_db()
        assert updates == {"default_assignee_id": member_b.id}
        assert bare_project.default_assignee_id == member_b.id
        # newly added lead is an Admin member
        assert _role(bare_project, member_b) == 20

    @pytest.mark.django_db
    def test_unset_default_assignee_follows_lead(self, bare_project, create_user, member_b):
        _set(bare_project, project_lead=member_b, default_assignee=None)
        apply_project_lead_change(
            bare_project, old_lead_id=create_user.id, old_default_assignee_id=None, requested_data={}
        )
        bare_project.refresh_from_db()
        assert bare_project.default_assignee_id == member_b.id

    @pytest.mark.django_db
    def test_other_default_assignee_is_kept(self, bare_project, create_user, member_b, member_c):
        _set(bare_project, project_lead=member_b, default_assignee=member_c)
        updates = apply_project_lead_change(
            bare_project, old_lead_id=create_user.id, old_default_assignee_id=member_c.id, requested_data={}
        )
        bare_project.refresh_from_db()
        assert updates == {}
        assert bare_project.default_assignee_id == member_c.id

    @pytest.mark.django_db
    def test_unchanged_default_in_request_still_follows(self, bare_project, create_user, member_b):
        """The settings UI re-sends the current default assignee together with the new lead."""
        _set(bare_project, project_lead=member_b, default_assignee=create_user)
        apply_project_lead_change(
            bare_project,
            old_lead_id=create_user.id,
            old_default_assignee_id=create_user.id,
            requested_data={"project_lead": str(member_b.id), "default_assignee": str(create_user.id)},
        )
        bare_project.refresh_from_db()
        assert bare_project.default_assignee_id == member_b.id

    @pytest.mark.django_db
    def test_explicit_default_in_request_wins(self, bare_project, create_user, member_b, member_c):
        _set(bare_project, project_lead=member_b, default_assignee=member_c)
        apply_project_lead_change(
            bare_project,
            old_lead_id=create_user.id,
            old_default_assignee_id=create_user.id,
            requested_data={"project_lead": str(member_b.id), "default_assignee": str(member_c.id)},
        )
        bare_project.refresh_from_db()
        assert bare_project.default_assignee_id == member_c.id
        # explicitly chosen default assignee is ensured as a project member
        assert _role(bare_project, member_c) == 15

    @pytest.mark.django_db
    def test_clearing_lead_clears_following_default(self, bare_project, create_user):
        _set(bare_project, project_lead=None, default_assignee=create_user)
        apply_project_lead_change(
            bare_project,
            old_lead_id=create_user.id,
            old_default_assignee_id=create_user.id,
            requested_data={"project_lead": None},
        )
        bare_project.refresh_from_db()
        assert bare_project.default_assignee_id is None

    @pytest.mark.django_db
    def test_unchanged_lead_is_noop(self, bare_project, create_user):
        _set(bare_project, project_lead=create_user, default_assignee=None)
        assert (
            apply_project_lead_change(
                bare_project, old_lead_id=create_user.id, old_default_assignee_id=None, requested_data={"name": "x"}
            )
            == {}
        )

    @pytest.mark.django_db
    def test_existing_member_role_is_not_raised(self, bare_project, create_user, member_b):
        ProjectMember.objects.create(project=bare_project, member=member_b, role=15)
        _set(bare_project, project_lead=member_b, default_assignee=create_user)
        apply_project_lead_change(
            bare_project, old_lead_id=create_user.id, old_default_assignee_id=create_user.id, requested_data={}
        )
        assert _role(bare_project, member_b) == 15

    @pytest.mark.django_db
    def test_stale_admin_row_is_reactivated_with_capped_role(self, bare_project, create_user, workspace):
        # a former project admin, removed from the workspace and re-invited as a guest
        guest = _make_user("stale-admin@plane.so", workspace, role=5)
        ProjectMember.objects.create(project=bare_project, member=guest, role=20, is_active=False)
        _set(bare_project, project_lead=guest, default_assignee=create_user)
        apply_project_lead_change(
            bare_project, old_lead_id=create_user.id, old_default_assignee_id=create_user.id, requested_data={}
        )
        member = ProjectMember.objects.get(project=bare_project, member=guest)
        assert (member.role, member.is_active) == (5, True)

    @pytest.mark.django_db
    def test_failures_are_swallowed(self, bare_project, create_user, member_b):
        _set(bare_project, project_lead=member_b, default_assignee=create_user)
        with mock.patch("plane.utils.project_defaults.ensure_project_member", side_effect=RuntimeError("boom")):
            assert (
                apply_project_lead_change(
                    bare_project, old_lead_id=create_user.id, old_default_assignee_id=create_user.id
                )
                == {}
            )


# ---------------------------------------------------------------- assign_default_assignee


@pytest.mark.unit
class TestAssignDefaultAssignee:
    @pytest.mark.django_db
    def test_assigns_when_no_assignees(self, bare_project, default_state, create_user):
        _set(bare_project, default_assignee=create_user)
        issue = Issue.objects.create(name="A", project=bare_project, state=default_state)
        assert assign_default_assignee(issue) is True
        assert list(IssueAssignee.objects.filter(issue=issue).values_list("assignee_id", flat=True)) == [create_user.id]
        # idempotent / keeps existing assignees
        assert assign_default_assignee(issue) is False

    @pytest.mark.django_db
    def test_skips_non_member_default(self, bare_project, default_state, member_b):
        _set(bare_project, default_assignee=member_b)
        issue = Issue.objects.create(name="B", project=bare_project, state=default_state)
        assert assign_default_assignee(issue) is False
        assert not IssueAssignee.objects.filter(issue=issue).exists()

    @pytest.mark.django_db
    def test_no_default(self, bare_project, default_state):
        issue = Issue.objects.create(name="C", project=bare_project, state=default_state)
        assert assign_default_assignee(issue) is False

    @pytest.mark.django_db
    def test_agent_default_is_assignable(self, bare_project, default_state, agent_user):
        """Agents (10) can be assignees, same as the issue create serializers."""
        ProjectMember.objects.create(project=bare_project, member=agent_user, role=10)
        _set(bare_project, default_assignee=agent_user)
        issue = Issue.objects.create(name="D", project=bare_project, state=default_state)
        assert assign_default_assignee(issue) is True

    @pytest.mark.django_db
    def test_guest_default_is_skipped(self, bare_project, default_state, workspace):
        guest = _make_user("guest-g@plane.so", workspace, role=5)
        ProjectMember.objects.create(project=bare_project, member=guest, role=5)
        _set(bare_project, default_assignee=guest)
        issue = Issue.objects.create(name="E", project=bare_project, state=default_state)
        assert assign_default_assignee(issue) is False


# ---------------------------------------------------------------- endpoints


@pytest.mark.contract
class TestProjectEndpoints:
    @pytest.mark.django_db
    def test_app_create_sets_lead_and_default_assignee(self, session_client, workspace, create_user):
        response = session_client.post(
            f"/api/workspaces/{workspace.slug}/projects/", {"name": "Lead App", "identifier": "LAPP"}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        project = Project.objects.get(pk=response.data["id"])
        assert project.project_lead_id == create_user.id
        assert project.default_assignee_id == create_user.id
        assert str(response.data["project_lead"]) == str(create_user.id)
        assert str(response.data["default_assignee"]) == str(create_user.id)

    @pytest.mark.django_db
    def test_app_list_includes_default_assignee(self, session_client, workspace, create_user):
        """The create-work-item modal pre-fills the assignee from the project list payload."""
        created = session_client.post(
            f"/api/workspaces/{workspace.slug}/projects/", {"name": "Lead List", "identifier": "LLST"}, format="json"
        )
        assert created.status_code == status.HTTP_201_CREATED, created.data
        response = session_client.get(f"/api/workspaces/{workspace.slug}/projects/")
        assert response.status_code == status.HTTP_200_OK
        row = next(p for p in response.data if str(p["id"]) == str(created.data["id"]))
        assert str(row["default_assignee"]) == str(create_user.id)
        assert str(row["project_lead"]) == str(create_user.id)

    @pytest.mark.django_db
    def test_app_create_with_other_lead(self, session_client, workspace, member_b):
        response = session_client.post(
            f"/api/workspaces/{workspace.slug}/projects/",
            {"name": "Lead Other", "identifier": "LOTH", "project_lead": str(member_b.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        project = Project.objects.get(pk=response.data["id"])
        assert project.project_lead_id == member_b.id
        assert project.default_assignee_id == member_b.id
        assert _role(project, member_b) == 20

    @pytest.mark.django_db
    def test_app_patch_lead_moves_default_assignee(self, session_client, workspace, create_user, member_b):
        created = session_client.post(
            f"/api/workspaces/{workspace.slug}/projects/", {"name": "Lead Patch", "identifier": "LPAT"}, format="json"
        )
        project_id = created.data["id"]
        response = session_client.patch(
            f"/api/workspaces/{workspace.slug}/projects/{project_id}/",
            {"project_lead": str(member_b.id), "default_assignee": str(create_user.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert str(response.data["default_assignee"]) == str(member_b.id)
        project = Project.objects.get(pk=project_id)
        assert project.project_lead_id == member_b.id
        assert project.default_assignee_id == member_b.id
        assert ProjectMember.objects.filter(project=project, member=member_b, is_active=True).exists()

    @pytest.mark.django_db
    def test_v1_create_and_patch(self, api_key_client, workspace, create_user, member_b):
        response = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/projects/", {"name": "Lead V1", "identifier": "LVONE"}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        project = Project.objects.get(pk=response.data["id"])
        assert project.project_lead_id == create_user.id
        assert project.default_assignee_id == create_user.id

        response = api_key_client.patch(
            f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/",
            {"project_lead": str(member_b.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        project.refresh_from_db()
        assert project.project_lead_id == member_b.id
        assert project.default_assignee_id == member_b.id


@pytest.mark.contract
class TestIssueDefaultAssignee:
    @pytest.mark.django_db
    def test_app_issue_create_uses_default_assignee(
        self, session_client, workspace, bare_project, default_state, create_user
    ):
        _set(bare_project, default_assignee=create_user)
        response = session_client.post(
            f"/api/workspaces/{workspace.slug}/projects/{bare_project.id}/issues/",
            {"name": "No assignee"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert [str(a) for a in response.data["assignee_ids"]] == [str(create_user.id)]

    @pytest.mark.django_db
    def test_app_issue_create_keeps_explicit_assignees(
        self, session_client, workspace, bare_project, default_state, create_user, member_c
    ):
        ProjectMember.objects.create(project=bare_project, member=member_c, role=15)
        _set(bare_project, default_assignee=create_user)
        response = session_client.post(
            f"/api/workspaces/{workspace.slug}/projects/{bare_project.id}/issues/",
            {"name": "Explicit", "assignee_ids": [str(member_c.id)]},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert [str(a) for a in response.data["assignee_ids"]] == [str(member_c.id)]

    @pytest.mark.django_db
    def test_v1_issue_create_uses_default_assignee(
        self, api_key_client, workspace, bare_project, default_state, create_user
    ):
        _set(bare_project, default_assignee=create_user)
        response = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/projects/{bare_project.id}/work-items/",
            {"name": "V1 no assignee"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        issue = Issue.objects.get(pk=response.data["id"])
        assert list(IssueAssignee.objects.filter(issue=issue).values_list("assignee_id", flat=True)) == [create_user.id]

    @pytest.mark.django_db
    def test_v1_intake_create_uses_default_assignee(
        self, api_key_client, workspace, bare_project, default_state, create_user
    ):
        _set(bare_project, default_assignee=create_user, intake_view=True)
        Intake.objects.create(name="Intake", project=bare_project, is_default=True)
        response = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/projects/{bare_project.id}/intake-issues/",
            {"issue": {"name": "From intake"}},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        issue = Issue.all_objects.get(name="From intake", project=bare_project)
        assert list(IssueAssignee.objects.filter(issue=issue).values_list("assignee_id", flat=True)) == [create_user.id]
