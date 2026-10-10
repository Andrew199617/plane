# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity teams: session API (/api/workspaces/<slug>/teams/...) and project-create auto-join."""

from unittest import mock
from uuid import uuid4

import pytest
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    APIToken,
    Project,
    ProjectMember,
    ProjectMemberInvite,
    Team,
    User,
    Workspace,
    WorkspaceMember,
)
from plane.db.models.team import TeamMember, TeamProject, TeamProvisionedMember

BASE = "/api/workspaces/test-workspace/teams/"


def _user(workspace, role=15):
    user = User.objects.create(email=f"{uuid4().hex[:10]}@plane.so", username=uuid4().hex[:12])
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=role)
    return user


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Teams API", identifier="TAP", workspace=workspace)
    ProjectMember.objects.create(project=project, member=create_user, role=20)
    return project


def _pm(project, user):
    return ProjectMember.objects.filter(project=project, member=user).first()


@pytest.mark.contract
@pytest.mark.django_db
class TestTeamCrud:
    def test_admin_creates_member_reads_only(self, session_client, workspace):
        response = session_client.post(BASE, {"name": "Devs"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        body = response.json()
        assert body["name"] == "Devs"
        assert body["member_ids"] == [] and body["project_ids"] == []
        assert body["member_count"] == 0 and body["default_project_role"] == 15 and body["auto_join"] is False
        assert {"id", "description", "logo_props", "created_at"} <= set(body)

        member_client = _client(_user(workspace, 15))
        assert member_client.post(BASE, {"name": "X"}, format="json").status_code == status.HTTP_403_FORBIDDEN
        listed = member_client.get(BASE)
        assert listed.status_code == status.HTTP_200_OK
        assert [team["name"] for team in listed.json()] == ["Devs"]
        detail = member_client.get(f"{BASE}{body['id']}/")
        assert detail.status_code == status.HTTP_200_OK and detail.json()["id"] == body["id"]
        assert (
            member_client.patch(f"{BASE}{body['id']}/", {"name": "Y"}, format="json").status_code
            == status.HTTP_403_FORBIDDEN
        )
        assert member_client.delete(f"{BASE}{body['id']}/").status_code == status.HTTP_403_FORBIDDEN

    def test_non_member_forbidden(self, workspace):
        outsider = User.objects.create(email="outsider@plane.so", username="outsider")
        assert _client(outsider).get(BASE).status_code == status.HTTP_403_FORBIDDEN

    def test_duplicate_name_conflict(self, session_client, workspace):
        assert session_client.post(BASE, {"name": "Devs"}, format="json").status_code == 201
        response = session_client.post(BASE, {"name": " devs "}, format="json")
        assert response.status_code == status.HTTP_409_CONFLICT
        other = session_client.post(BASE, {"name": "Agents"}, format="json").json()
        assert (
            session_client.patch(f"{BASE}{other['id']}/", {"name": "DEVS"}, format="json").status_code
            == status.HTTP_409_CONFLICT
        )

    def test_same_name_in_other_workspace_ok(self, session_client, workspace, create_user):
        other_ws = Workspace.objects.create(name="Other", slug="other-teams", owner=create_user)
        WorkspaceMember.objects.create(workspace=other_ws, member=create_user, role=20)
        assert session_client.post(BASE, {"name": "Devs"}, format="json").status_code == 201
        assert (
            session_client.post("/api/workspaces/other-teams/teams/", {"name": "Devs"}, format="json").status_code
            == 201
        )
        assert len(session_client.get(BASE).json()) == 1

    @pytest.mark.parametrize("payload", [{"name": ""}, {"name": "X", "default_project_role": 99}])
    def test_validation(self, session_client, workspace, payload):
        assert session_client.post(BASE, payload, format="json").status_code == status.HTTP_400_BAD_REQUEST

    def test_create_with_members_and_projects(self, session_client, workspace, project):
        member, guest = _user(workspace, 15), _user(workspace, 5)
        response = session_client.post(
            BASE,
            {
                "name": "Devs",
                "default_project_role": 15,
                "member_ids": [str(member.id), str(guest.id)],
                "project_ids": [str(project.id)],
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        body = response.json()
        assert set(body["member_ids"]) == {str(member.id), str(guest.id)} and body["member_count"] == 2
        assert body["project_ids"] == [str(project.id)]
        assert _pm(project, member).role == 15 and _pm(project, guest).role == 5

    def test_create_rejects_foreign_ids(self, session_client, workspace, create_user):
        other_ws = Workspace.objects.create(name="Other", slug="other-teams-2", owner=create_user)
        foreign_project = Project.objects.create(name="F", identifier="FRN", workspace=other_ws)
        outsider = User.objects.create(email="nope@plane.so", username="nope")
        response = session_client.post(BASE, {"name": "A", "member_ids": [str(outsider.id)]}, format="json")
        assert response.status_code == 400 and response.json()["invalid_ids"] == [str(outsider.id)]
        response = session_client.post(BASE, {"name": "A", "project_ids": [str(foreign_project.id)]}, format="json")
        assert response.status_code == 400
        assert not Team.objects.filter(workspace=workspace).exists()

    def test_patch_role_auto_join_and_sets(self, session_client, workspace, project):
        second = Project.objects.create(name="Second", identifier="SEC", workspace=workspace)
        member, other = _user(workspace, 15), _user(workspace, 15)
        team = session_client.post(
            BASE, {"name": "Devs", "member_ids": [str(member.id)], "project_ids": [str(project.id)]}, format="json"
        ).json()
        url = f"{BASE}{team['id']}/"

        body = session_client.patch(url, {"default_project_role": 5}, format="json").json()
        assert body["default_project_role"] == 5 and _pm(project, member).role == 5

        body = session_client.patch(url, {"member_ids": [str(other.id)]}, format="json").json()
        assert body["member_ids"] == [str(other.id)]
        assert _pm(project, member).is_active is False and _pm(project, other).is_active

        body = session_client.patch(url, {"auto_join": True}, format="json").json()
        assert body["auto_join"] is True and set(body["project_ids"]) == {str(project.id), str(second.id)}
        assert _pm(second, other).is_active

    def test_delete_team(self, session_client, workspace, project):
        member = _user(workspace, 15)
        team = session_client.post(
            BASE, {"name": "Devs", "member_ids": [str(member.id)], "project_ids": [str(project.id)]}, format="json"
        ).json()
        response = session_client.delete(f"{BASE}{team['id']}/?remove_from_projects=false")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert session_client.get(BASE).json() == []
        assert session_client.get(f"{BASE}{team['id']}/").status_code == status.HTTP_404_NOT_FOUND
        assert _pm(project, member).is_active
        assert not TeamMember.all_objects.filter(team_id=team["id"]).exists()
        assert not TeamProject.all_objects.filter(team_id=team["id"]).exists()


@pytest.mark.contract
@pytest.mark.django_db
class TestTeamMembersAndProjects:
    def test_members_endpoints(self, session_client, workspace, project):
        member = _user(workspace, 15)
        team = session_client.post(BASE, {"name": "Devs", "project_ids": [str(project.id)]}, format="json").json()
        members_url = f"{BASE}{team['id']}/members/"

        response = session_client.post(members_url, {"member_ids": [str(member.id)]}, format="json")
        assert response.status_code == 200 and response.json()["member_ids"] == [str(member.id)]
        assert _pm(project, member).is_active
        listed = session_client.get(members_url).json()
        assert [row["member"] for row in listed] == [str(member.id)]

        assert session_client.post(members_url, {"member_ids": []}, format="json").status_code == 400
        assert session_client.post(members_url, {"member_ids": ["not-a-uuid"]}, format="json").status_code == 400
        outsider = User.objects.create(email="outsider2@plane.so", username="outsider2")
        assert session_client.post(members_url, {"member_ids": [str(outsider.id)]}, format="json").status_code == 400

        response = session_client.delete(f"{members_url}{member.id}/")
        assert response.status_code == 200 and response.json()["member_ids"] == []
        assert _pm(project, member).is_active is False

    def test_remove_member_keep_projects(self, session_client, workspace, project):
        member = _user(workspace, 15)
        team = session_client.post(
            BASE, {"name": "Devs", "member_ids": [str(member.id)], "project_ids": [str(project.id)]}, format="json"
        ).json()
        session_client.delete(f"{BASE}{team['id']}/members/{member.id}/?remove_from_projects=false")
        assert _pm(project, member).is_active

    def test_projects_endpoints(self, session_client, workspace, project, create_user):
        second = Project.objects.create(name="Second", identifier="SEC", workspace=workspace)
        other_ws = Workspace.objects.create(name="Other", slug="other-teams-3", owner=create_user)
        foreign = Project.objects.create(name="F", identifier="FRN", workspace=other_ws)
        member = _user(workspace, 15)
        team = session_client.post(BASE, {"name": "Devs", "member_ids": [str(member.id)]}, format="json").json()
        projects_url = f"{BASE}{team['id']}/projects/"

        assert session_client.post(projects_url, {"project_ids": [str(foreign.id)]}, format="json").status_code == 400
        body = session_client.post(projects_url, {"project_ids": [str(project.id)]}, format="json").json()
        assert body["project_ids"] == [str(project.id)]
        body = session_client.post(projects_url, {"all_projects": True}, format="json").json()
        assert set(body["project_ids"]) == {str(project.id), str(second.id)}
        assert session_client.get(projects_url).status_code == 200

        body = session_client.delete(f"{projects_url}{second.id}/?remove_members=false").json()
        assert body["project_ids"] == [str(project.id)] and _pm(second, member).is_active
        body = session_client.delete(f"{projects_url}{project.id}/").json()
        assert body["project_ids"] == [] and _pm(project, member).is_active is False


@pytest.mark.contract
@pytest.mark.django_db
class TestProjectCreateAutoJoin:
    def _auto_join_team(self, workspace, create_user):
        member = _user(workspace, 15)
        team = Team.objects.create(workspace=workspace, name="Devs", default_project_role=15, auto_join=True)
        TeamMember.objects.create(team=team, member=create_user)
        TeamMember.objects.create(team=team, member=member)
        return team, member

    def test_app_project_create(self, session_client, workspace, create_user):
        team, member = self._auto_join_team(workspace, create_user)
        response = session_client.post(
            "/api/workspaces/test-workspace/projects/", {"name": "Auto", "identifier": "AUTO"}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        project = Project.objects.get(identifier="AUTO")
        assert TeamProject.objects.filter(team=team, project=project).exists()
        assert _pm(project, create_user).role == 20
        assert _pm(project, member).role == 15 and _pm(project, member).is_active

    def test_v1_project_create(self, api_key_client, workspace, create_user):
        team, member = self._auto_join_team(workspace, create_user)
        response = api_key_client.post(
            "/api/v1/workspaces/test-workspace/projects/", {"name": "Auto V1", "identifier": "AUTOV"}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        project = Project.objects.get(identifier="AUTOV")
        assert TeamProject.objects.filter(team=team, project=project).exists()
        assert _pm(project, create_user).role == 20
        assert _pm(project, member).role == 15


@pytest.mark.contract
@pytest.mark.django_db
class TestProjectMembersManagedByHand:
    """An admin adding, editing or removing a team-provisioned member by hand makes the membership a
    manual one: the user then keeps it when they leave the team."""

    def _provisioned(self, session_client, workspace, project):
        user = _user(workspace, 15)
        team = session_client.post(
            BASE, {"name": "Devs", "member_ids": [str(user.id)], "project_ids": [str(project.id)]}, format="json"
        ).json()
        assert TeamProvisionedMember.objects.filter(project=project, member=user).exists()
        return user, f"{BASE}{team['id']}/members/{user.id}/"

    def _members_url(self, project):
        return f"/api/workspaces/test-workspace/projects/{project.id}/members/"

    def _add(self, session_client, project, user):
        with mock.patch("plane.app.views.project.member.project_add_user_email"):
            response = session_client.post(
                self._members_url(project), {"members": [{"member_id": str(user.id), "role": 15}]}, format="json"
            )
        assert response.status_code == status.HTTP_201_CREATED, response.data

    def test_removed_then_re_added_by_hand(self, session_client, workspace, project):
        user, team_member_url = self._provisioned(session_client, workspace, project)
        response = session_client.delete(f"{self._members_url(project)}{_pm(project, user).id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not TeamProvisionedMember.objects.filter(project=project, member=user).exists()

        self._add(session_client, project, user)
        session_client.delete(team_member_url)
        assert _pm(project, user).is_active

    def test_re_added_by_hand_after_leaving(self, session_client, workspace, project):
        user, team_member_url = self._provisioned(session_client, workspace, project)
        leave = _client(user).post(f"{self._members_url(project)}leave/")
        assert leave.status_code == status.HTTP_204_NO_CONTENT
        assert not TeamProvisionedMember.objects.filter(project=project, member=user).exists()

        self._add(session_client, project, user)
        session_client.delete(team_member_url)
        assert _pm(project, user).is_active

    def test_role_changed_by_hand(self, session_client, workspace, project):
        user, team_member_url = self._provisioned(session_client, workspace, project)
        response = session_client.patch(
            f"{self._members_url(project)}{_pm(project, user).id}/", {"role": 20}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK, response.data

        session_client.delete(team_member_url)
        assert _pm(project, user).is_active and _pm(project, user).role == 20

    def test_active_membership_re_added_by_hand_is_manual(self, session_client, workspace, project):
        user, team_member_url = self._provisioned(session_client, workspace, project)
        self._add(session_client, project, user)
        assert not TeamProvisionedMember.objects.filter(project=project, member=user).exists()

        response = session_client.delete(team_member_url)
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["member_ids"] == []
        assert _pm(project, user).is_active

    def test_status_changed_by_hand_is_manual(self, session_client, workspace, project):
        user, team_member_url = self._provisioned(session_client, workspace, project)
        member_url = f"{self._members_url(project)}{_pm(project, user).id}/"
        response = session_client.patch(member_url, {"is_active": False}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert not TeamProvisionedMember.objects.filter(project=project, member=user).exists()

        self._add(session_client, project, user)
        response = session_client.delete(team_member_url)
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["member_ids"] == []
        assert _pm(project, user).is_active

    def _v1_member(self, workspace, project, user, create_user):
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=APIToken.objects.create(user=create_user, workspace=workspace).token)
        url = f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/members/{_pm(project, user).id}/"
        return client, url

    def test_role_changed_through_v1_is_manual(self, session_client, workspace, project, create_user):
        user, team_member_url = self._provisioned(session_client, workspace, project)
        client, url = self._v1_member(workspace, project, user, create_user)
        response = client.patch(url, {"role": 15}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert not TeamProvisionedMember.objects.filter(project=project, member=user).exists()
        session_client.delete(team_member_url)
        assert _pm(project, user).is_active

    def test_removed_through_v1_clears_marker(self, session_client, workspace, project, create_user):
        user, _ = self._provisioned(session_client, workspace, project)
        client, url = self._v1_member(workspace, project, user, create_user)
        response = client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT, response.data
        assert not TeamProvisionedMember.objects.filter(project=project, member=user).exists()

    @pytest.mark.parametrize("stale_role", [15, 10])
    def test_manual_join_after_leaving_is_manual(self, session_client, workspace, project, stale_role):
        user, team_member_url = self._provisioned(session_client, workspace, project)
        # Workspace removal can deactivate a project member without cleaning its provenance marker.
        ProjectMember.objects.filter(project=project, member=user).update(is_active=False, role=stale_role)
        response = _client(user).post(
            f"/api/users/me/workspaces/{workspace.slug}/projects/invitations/",
            {"project_ids": [str(project.id)]},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert not TeamProvisionedMember.objects.filter(project=project, member=user).exists()
        assert _pm(project, user).role == 15
        session_client.delete(team_member_url)
        assert _pm(project, user).is_active

    def test_invitation_rejoin_is_manual(self, session_client, workspace, project):
        user, team_member_url = self._provisioned(session_client, workspace, project)
        ProjectMember.objects.filter(project=project, member=user).update(is_active=False)
        invitation = ProjectMemberInvite.objects.create(
            project=project, workspace=workspace, email=user.email, role=15, token="invitation-token"
        )
        response = _client(user).post(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/join/{invitation.id}/",
            {"token": invitation.token, "accepted": True},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert not TeamProvisionedMember.objects.filter(project=project, member=user).exists()
        session_client.delete(team_member_url)
        assert _pm(project, user).is_active

    def test_management_command_rejoin_is_manual(self, session_client, workspace, project):
        user, team_member_url = self._provisioned(session_client, workspace, project)
        ProjectMember.objects.filter(project=project, member=user).update(is_active=False)
        call_command("create_project_member", project_id=str(project.id), user_email=user.email, role=15)
        assert not TeamProvisionedMember.objects.filter(project=project, member=user).exists()
        session_client.delete(team_member_url)
        assert _pm(project, user).is_active
