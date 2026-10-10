# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity agents: Agent invitations, the agent account marker (bot_type), agent token scoping,
workspace role changes, agent read permissions and the agent role migrations."""

import importlib
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

import pytest
from django.apps import apps as django_apps
from django.core.management import call_command
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from plane.db.models import (
    APIToken,
    Project,
    ProjectMember,
    ProjectMemberInvite,
    User,
    Workspace,
    WorkspaceMember,
    WorkspaceMemberInvite,
)
from plane.db.models.team import TeamMember
from plane.utils.agent import AGENT_BOT_TYPE, AgentProvisioningError, create_agent_token, create_agent_user
from plane.utils.teams import seed_default_teams

ADMIN, MEMBER, AGENT, GUEST = 20, 15, 10, 5
SLUG = "test-workspace"
OTHER_SLUG = "other-workspace"
INVITES = f"/api/workspaces/{SLUG}/invitations/"
AGENTS = f"/api/workspaces/{SLUG}/agents/"
MEMBERS = f"/api/workspaces/{SLUG}/members/"


def _user(workspace, workspace_role, username=None):
    user = User.objects.create(email=f"{uuid4().hex[:10]}@example.com", username=username or uuid4().hex[:12])
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=workspace_role)
    return user


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _token_client(token):
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=token.token)
    return client


@pytest.fixture
def private_project(workspace, create_user):
    project = Project.objects.create(name="Private", identifier="PRIV", workspace=workspace, network=0)
    ProjectMember.objects.create(project=project, member=create_user, role=ADMIN)
    return project


@pytest.fixture
def other_workspace(create_user):
    other = Workspace.objects.create(name="Other", slug=OTHER_SLUG, owner=create_user)
    WorkspaceMember.objects.create(workspace=other, member=create_user, role=ADMIN)
    return other


@pytest.fixture
def no_invite_emails():
    with mock.patch("plane.app.views.workspace.invite.workspace_invitation.delay") as delay:
        yield delay


@pytest.mark.contract
@pytest.mark.django_db
class TestAgentInvitations:
    def test_member_cannot_invite_agents(self, workspace, private_project, no_invite_emails):
        client = _client(_user(workspace, MEMBER))
        response = client.post(INVITES, {"emails": [{"email": "bot@example.com", "role": AGENT}]}, format="json")
        assert response.status_code == 400, response.content
        assert not WorkspaceMemberInvite.objects.filter(email="bot@example.com").exists()

    def test_member_still_invites_at_or_below_their_role(self, workspace, no_invite_emails):
        client = _client(_user(workspace, MEMBER))
        emails = [{"email": "member@example.com", "role": MEMBER}, {"email": "guest@example.com", "role": GUEST}]
        assert client.post(INVITES, {"emails": emails}, format="json").status_code == 200
        assert WorkspaceMemberInvite.objects.filter(workspace=workspace).count() == 2
        response = client.post(INVITES, {"emails": [{"email": "a@example.com", "role": ADMIN}]}, format="json")
        assert response.status_code == 400

    def test_admin_invites_agents_and_invalid_roles_are_rejected(self, session_client, workspace, no_invite_emails):
        for role in (7, "abc", None):
            response = session_client.post(
                INVITES, {"emails": [{"email": "x@example.com", "role": role}]}, format="json"
            )
            assert response.status_code == 400, role
        response = session_client.post(
            INVITES, {"emails": [{"email": "bot@example.com", "role": AGENT}]}, format="json"
        )
        assert response.status_code == 200, response.content
        assert WorkspaceMemberInvite.objects.get(email="bot@example.com").role == AGENT

    def test_invitation_role_update_rules(self, workspace, session_client):
        invite = WorkspaceMemberInvite.objects.create(workspace=workspace, email="i@example.com", role=GUEST, token="t")
        url = f"{INVITES}{invite.id}/"
        member_client = _client(_user(workspace, MEMBER))
        assert member_client.patch(url, {"role": AGENT}, format="json").status_code == 400
        assert member_client.patch(url, {"role": ADMIN}, format="json").status_code == 400
        assert session_client.patch(url, {"role": 7}, format="json").status_code == 400
        invite.refresh_from_db()
        assert invite.role == GUEST
        assert member_client.patch(url, {"role": MEMBER}, format="json").status_code == 200
        assert session_client.patch(url, {"role": AGENT}, format="json").status_code == 200
        invite.refresh_from_db()
        assert invite.role == AGENT


@pytest.mark.contract
@pytest.mark.django_db
class TestAgentAccounts:
    def test_agents_api_only_manages_agent_accounts(self, session_client, workspace, private_project):
        human_agent = _user(workspace, AGENT)
        body = session_client.post(AGENTS, {"display_name": "Marked", "generate_token": False}, format="json").json()
        assert User.objects.get(pk=body["member"]["id"]).bot_type == AGENT_BOT_TYPE
        assert [row["member"]["id"] for row in session_client.get(AGENTS).json()] == [body["member"]["id"]]
        assert session_client.get(f"{AGENTS}{human_agent.id}/").status_code == 404
        assert session_client.post(f"{AGENTS}{human_agent.id}/tokens/", {}, format="json").status_code == 404
        assert session_client.delete(f"{AGENTS}{human_agent.id}/").status_code == 404
        assert not APIToken.objects.filter(user=human_agent).exists()

    def test_token_service_requires_an_active_marked_account(self, workspace):
        human = _user(workspace, AGENT)
        with pytest.raises(AgentProvisioningError):
            create_agent_token(human, workspace)
        agent = create_agent_user(workspace, "Inactive").member
        WorkspaceMember.objects.filter(workspace=workspace, member=agent).update(is_active=False)
        with pytest.raises(AgentProvisioningError):
            create_agent_token(agent, workspace)
        assert not APIToken.objects.filter(user__in=[human, agent]).exists()

    def test_profile_cannot_change_the_agent_account_marker(self, workspace):
        for user, marker in (
            (_user(workspace, MEMBER), None),
            (create_agent_user(workspace, "Bot").member, AGENT_BOT_TYPE),
        ):
            response = _client(user).patch(
                "/api/users/me/", {"bot_type": "" if marker else AGENT_BOT_TYPE}, format="json"
            )
            assert response.status_code == 200, response.content
            user.refresh_from_db()
            assert user.bot_type == marker

    def test_agent_emails_are_placeholders(self, session_client, workspace):
        for email in ("someone@example.com", "bot@agents.other-workspace.local"):
            response = session_client.post(AGENTS, {"display_name": "Bot", "email": email}, format="json")
            assert response.status_code == 400, email
            assert not User.objects.filter(email=email).exists()
        response = session_client.post(
            AGENTS, {"display_name": "Bot", "email": "Bot@Agents.Test-Workspace.local"}, format="json"
        )
        assert response.status_code == 201, response.content
        user = User.objects.get(pk=response.json()["member"]["id"])
        assert user.email == "bot@agents.test-workspace.local" and user.is_email_verified is True

    def test_operator_custom_email_is_not_verified(self, workspace):
        user = create_agent_user(workspace, "Ops", email="ops@example.com", allow_custom_email=True).member
        assert user.bot_type == AGENT_BOT_TYPE and user.is_email_verified is False and user.is_bot is False

    def test_create_agent_command_marks_the_account(self, workspace):
        call_command("create_agent", workspace=SLUG, name="Cmd Bot", no_token=True)
        user = User.objects.get(display_name="Cmd Bot")
        assert user.bot_type == AGENT_BOT_TYPE
        # a human holding the Agent role with the same name is never reused (nor given a token)
        human = _user(workspace, AGENT)
        User.objects.filter(pk=human.pk).update(display_name="Twin")
        call_command("create_agent", workspace=SLUG, name="Twin")
        assert User.objects.filter(display_name="Twin", bot_type=AGENT_BOT_TYPE).count() == 1
        assert not APIToken.objects.filter(user=human).exists()

    def test_deactivate_only_revokes_the_workspace_tokens(self, workspace, other_workspace):
        workspace_member = create_agent_user(workspace, "Bot")
        token = create_agent_token(workspace_member.member, workspace)
        foreign = APIToken.objects.create(user=workspace_member.member, workspace=other_workspace, user_type=1)
        from plane.utils.agent import deactivate_agent

        deactivate_agent(workspace_member)
        assert not APIToken.objects.get(pk=token.pk).is_active
        assert APIToken.objects.get(pk=foreign.pk).is_active


@pytest.mark.contract
@pytest.mark.django_db
class TestWorkspaceRoleChanges:
    def _member_url(self, workspace, user):
        return f"{MEMBERS}{WorkspaceMember.objects.get(workspace=workspace, member=user).id}/"

    def test_humans_cannot_be_moved_into_the_agent_role(self, session_client, workspace, private_project):
        human = _user(workspace, MEMBER)
        ProjectMember.objects.create(project=private_project, member=human, role=MEMBER)
        response = session_client.patch(self._member_url(workspace, human), {"role": AGENT}, format="json")
        assert response.status_code == 400 and "error" in response.json()
        assert WorkspaceMember.objects.get(workspace=workspace, member=human).role == MEMBER
        assert ProjectMember.objects.get(project=private_project, member=human).role == MEMBER

    def test_agent_accounts_keep_the_agent_role(self, session_client, workspace, private_project):
        agent = create_agent_user(workspace, "Bot").member
        response = session_client.patch(self._member_url(workspace, agent), {"role": MEMBER}, format="json")
        assert response.status_code == 400
        assert WorkspaceMember.objects.get(workspace=workspace, member=agent).role == AGENT
        assert ProjectMember.objects.get(project=private_project, member=agent).role == AGENT

    def test_invalid_payload_changes_nothing(self, session_client, workspace, private_project):
        human = _user(workspace, AGENT)
        ProjectMember.objects.create(project=private_project, member=human, role=AGENT)
        token = APIToken.objects.create(user=human, workspace=workspace, user_type=1)
        url = self._member_url(workspace, human)
        for role in (MEMBER, GUEST):
            response = session_client.patch(url, {"role": role, "workspace": "bad"}, format="json")
            assert response.status_code == 400
        assert ProjectMember.objects.get(project=private_project, member=human).role == AGENT
        assert APIToken.objects.get(pk=token.pk).is_active

    def test_role_patch_cannot_move_a_membership_to_another_workspace(
        self, session_client, workspace, other_workspace, private_project
    ):
        human = _user(workspace, AGENT)
        ProjectMember.objects.create(project=private_project, member=human, role=AGENT)
        response = session_client.patch(
            self._member_url(workspace, human), {"role": MEMBER, "workspace": str(other_workspace.id)}, format="json"
        )
        assert response.status_code == 400, response.content
        assert WorkspaceMember.objects.get(workspace=workspace, member=human).role == AGENT
        assert ProjectMember.objects.get(project=private_project, member=human).role == AGENT

    def test_role_change_is_atomic(self, session_client, workspace, private_project):
        human = _user(workspace, AGENT)
        ProjectMember.objects.create(project=private_project, member=human, role=AGENT)
        with mock.patch(
            "plane.app.views.workspace.member.WorkSpaceMemberSerializer.save", side_effect=RuntimeError("boom")
        ):
            response = session_client.patch(self._member_url(workspace, human), {"role": MEMBER}, format="json")
        assert response.status_code >= 400
        assert ProjectMember.objects.get(project=private_project, member=human).role == AGENT
        assert WorkspaceMember.objects.get(workspace=workspace, member=human).role == AGENT

    def test_leaving_the_agent_role_revokes_tokens_and_agents_team(
        self, session_client, workspace, other_workspace, private_project
    ):
        agents_team = seed_default_teams(workspace)["Agents"]
        human = _user(workspace, AGENT)
        ProjectMember.objects.update_or_create(
            project=private_project, member=human, defaults={"role": AGENT, "is_active": True}
        )
        TeamMember.objects.get_or_create(team=agents_team, member=human, workspace=workspace)
        token = APIToken.objects.create(user=human, workspace=workspace, user_type=1)
        foreign = APIToken.objects.create(user=human, workspace=other_workspace, user_type=1)
        legacy = APIToken.objects.create(user=human, user_type=1)
        personal = APIToken.objects.create(user=human, user_type=0)

        response = session_client.patch(self._member_url(workspace, human), {"role": MEMBER}, format="json")
        assert response.status_code == 200, response.content
        assert ProjectMember.objects.get(project=private_project, member=human).role == MEMBER
        assert not APIToken.objects.get(pk=token.pk).is_active
        assert APIToken.objects.get(pk=foreign.pk).is_active
        assert not APIToken.objects.get(pk=legacy.pk).is_active
        assert APIToken.objects.get(pk=personal.pk).is_active
        assert not TeamMember.objects.filter(team=agents_team, member=human).exists()


@pytest.mark.contract
@pytest.mark.django_db
class TestAgentTokenScope:
    def test_agent_token_only_works_in_its_workspace(self, workspace, other_workspace, private_project):
        agent = create_agent_user(workspace, "Scoped Bot").member
        foreign_project = Project.objects.create(name="Foreign", identifier="FRGN", workspace=other_workspace)
        WorkspaceMember.objects.create(workspace=other_workspace, member=agent, role=MEMBER)
        ProjectMember.objects.create(project=foreign_project, member=agent, role=MEMBER)
        client = _token_client(create_agent_token(agent, workspace))

        assert client.get(f"/api/v1/workspaces/{SLUG}/projects/{private_project.id}/states/").status_code == 200
        assert client.get("/api/v1/users/me/").status_code == 200
        response = client.get(f"/api/v1/workspaces/{OTHER_SLUG}/projects/{foreign_project.id}/states/")
        assert response.status_code in (401, 403)
        assert "workspace" in str(response.json())

    def test_legacy_human_agent_tokens_cannot_impersonate_the_human(self, workspace, private_project):
        human = _user(workspace, MEMBER)
        ProjectMember.objects.create(project=private_project, member=human, role=MEMBER)
        token = APIToken.objects.create(user=human, workspace=workspace, user_type=1, description="Agent token")
        response = _token_client(token).get(f"/api/v1/workspaces/{SLUG}/projects/{private_project.id}/states/")
        assert response.status_code in (401, 403), response.content

    def test_legacy_bot_tokens_are_workspace_scoped(self, workspace, other_workspace, private_project):
        human = _user(workspace, AGENT)
        ProjectMember.objects.create(project=private_project, member=human, role=AGENT)
        WorkspaceMember.objects.create(workspace=other_workspace, member=human, role=ADMIN)
        foreign_project = Project.objects.create(name="Foreign", identifier="FRGN", workspace=other_workspace)
        ProjectMember.objects.create(project=foreign_project, member=human, role=ADMIN)
        token = APIToken.objects.create(user=human, workspace=workspace, user_type=1)
        response = _token_client(token).get(f"/api/v1/workspaces/{OTHER_SLUG}/projects/{foreign_project.id}/states/")
        assert response.status_code in (401, 403), response.content

    def test_unscoped_agent_tokens_are_rejected(self, workspace):
        agent = create_agent_user(workspace, "Old Bot").member
        token = APIToken.objects.create(user=agent, user_type=1)
        assert _token_client(token).get("/api/v1/users/me/").status_code in (401, 403)

    def test_existing_unscoped_integration_bot_tokens_remain_valid(self, create_bot_user):
        token = APIToken.objects.create(user=create_bot_user, user_type=1)
        response = _token_client(token).get("/api/v1/users/me/")
        assert response.status_code == 200, response.content

    def test_workspace_uuid_scope_is_enforced(self, workspace, other_workspace):
        from plane.api.middleware.api_authentication import APIKeyAuthentication

        token = create_agent_token(create_agent_user(workspace, "Bot").member, workspace)
        for target, allowed in ((workspace, True), (other_workspace, False)):
            request = SimpleNamespace(parser_context={"kwargs": {"workspace_id": str(target.id)}})
            assert APIKeyAuthentication.agent_token_allowed(token, request) is allowed

    def test_ordinary_tokens_are_unchanged(self, workspace, other_workspace, create_user):
        foreign_project = Project.objects.create(name="Foreign", identifier="FRGN", workspace=other_workspace)
        ProjectMember.objects.create(project=foreign_project, member=create_user, role=ADMIN)
        token = APIToken.objects.create(user=create_user, workspace=workspace, user_type=0)
        response = _token_client(token).get(f"/api/v1/workspaces/{OTHER_SLUG}/projects/{foreign_project.id}/states/")
        assert response.status_code == 200


@pytest.mark.contract
@pytest.mark.django_db
class TestAgentReadPermissions:
    def test_agents_cannot_read_invitations_or_member_emails(self, workspace):
        agent = create_agent_user(workspace, "Reader").member
        WorkspaceMemberInvite.objects.create(workspace=workspace, email="pending@example.com", role=MEMBER, token="t")
        assert _client(agent).get(INVITES).status_code == 403
        client = _token_client(create_agent_token(agent, workspace))
        for url in (f"/api/v1/workspaces/{SLUG}/members/", f"/api/v1/workspaces/{SLUG}/members-lite/"):
            response = client.get(url)
            assert response.status_code == 403, (url, response.status_code)


@pytest.mark.unit
@pytest.mark.django_db
class TestAgentRoleMigrations:
    def test_0123_remaps_legacy_viewer_invites(self, workspace, create_user):
        migration = importlib.import_module("plane.db.migrations.0123_jp_agent_role")
        project = Project.objects.create(name="Legacy", identifier="LEG", workspace=workspace)
        workspace_invite = WorkspaceMemberInvite.objects.create(workspace=workspace, email="v@example.com", role=10)
        project_invite = ProjectMemberInvite.objects.create(
            project=project, workspace=workspace, email="v@example.com", role=10, token="t"
        )
        migration.remap_legacy_viewer_invites(django_apps, None)
        workspace_invite.refresh_from_db()
        project_invite.refresh_from_db()
        assert workspace_invite.role == GUEST and project_invite.role == GUEST

        agent = _user(workspace, AGENT)
        ProjectMember.objects.create(project=project, member=agent, role=AGENT)
        migration.remove_agent_role(django_apps, None)
        assert WorkspaceMember.objects.get(workspace=workspace, member=agent).role == GUEST
        assert ProjectMember.objects.get(project=project, member=agent).role == GUEST

    def test_0131_marks_only_agent_accounts(self, workspace):
        migration = importlib.import_module("plane.db.migrations.0131_jp_agent_account_marker")
        agent = _user(workspace, AGENT, username=f"agent_{uuid4().hex[:16]}")
        User.objects.filter(pk=agent.pk).update(is_password_autoset=True)
        human_agent = _user(workspace, AGENT)
        prefix_human = _user(workspace, AGENT, username="agent_human_name")
        former_agent = _user(workspace, MEMBER, username=f"agent_{uuid4().hex[:16]}")
        migration.mark_agent_accounts(django_apps, None)
        assert User.objects.get(pk=agent.pk).bot_type == AGENT_BOT_TYPE
        assert User.objects.get(pk=human_agent.pk).bot_type is None
        assert User.objects.get(pk=prefix_human.pk).bot_type is None
        assert User.objects.get(pk=former_agent.pk).bot_type is None

    def test_0132_cleans_already_applied_legacy_invites_and_tokens(self, workspace):
        migration = importlib.import_module("plane.db.migrations.0132_jp_agent_security_cleanup")
        cutoff = timezone.now()
        project = Project.objects.create(name="Legacy", identifier="LEG", workspace=workspace)
        legacy_workspace = WorkspaceMemberInvite.objects.create(
            workspace=workspace, email="legacy@example.com", role=AGENT
        )
        legacy_project = ProjectMemberInvite.objects.create(
            project=project, workspace=workspace, email="legacy@example.com", role=AGENT
        )
        current_invite = WorkspaceMemberInvite.objects.create(
            workspace=workspace, email="current@example.com", role=AGENT
        )
        WorkspaceMemberInvite.objects.filter(pk=legacy_workspace.pk).update(created_at=cutoff - timedelta(days=1))
        ProjectMemberInvite.objects.filter(pk=legacy_project.pk).update(created_at=cutoff - timedelta(days=1))
        WorkspaceMemberInvite.objects.filter(pk=current_invite.pk).update(created_at=cutoff + timedelta(seconds=1))

        human = _user(workspace, MEMBER)
        compromised = APIToken.objects.create(user=human, workspace=workspace, user_type=1, description="renamed")
        personal = APIToken.objects.create(user=human, user_type=0)
        agent = create_agent_user(workspace, "Active").member
        valid = create_agent_token(agent, workspace)
        unscoped = APIToken.objects.create(user=agent, user_type=1)
        inactive = _user(workspace, AGENT, username=f"agent_{uuid4().hex[:16]}")
        real_owner_email = inactive.email
        User.objects.filter(pk=inactive.pk).update(is_password_autoset=True, is_email_verified=True)
        WorkspaceMember.objects.filter(member=inactive).update(is_active=False)
        inactive_token = APIToken.objects.create(user=inactive, workspace=workspace, user_type=1)
        human_prefix = _user(workspace, AGENT, username="agent_human_name")
        # An already-applied broad 0131 could have incorrectly marked this human as an account.
        User.objects.filter(pk=human_prefix.pk).update(
            bot_type=AGENT_BOT_TYPE, is_password_autoset=True, is_email_verified=True
        )
        human_email = human_prefix.email
        falsely_minted = APIToken.objects.create(user=human_prefix, workspace=workspace, user_type=1)
        human_personal = APIToken.objects.create(user=human_prefix, user_type=0)

        with mock.patch.object(migration, "_legacy_role_cutoff", return_value=cutoff):
            migration.clean_up_legacy_agents(django_apps, SimpleNamespace(connection=connection))

        for invite in (legacy_workspace, legacy_project):
            invite.refresh_from_db()
            assert invite.role == GUEST
        current_invite.refresh_from_db()
        assert current_invite.role == AGENT
        inactive.refresh_from_db()
        assert inactive.bot_type == AGENT_BOT_TYPE
        assert inactive.email.endswith("@agents.test-workspace.local") and not inactive.is_email_verified
        real_owner = User.objects.create(email=real_owner_email, username=uuid4().hex)
        assert real_owner.bot_type is None and real_owner.email == real_owner_email
        human_prefix.refresh_from_db()
        assert human_prefix.bot_type is None and human_prefix.email == human_email and human_prefix.is_email_verified
        for token in (compromised, unscoped, inactive_token, falsely_minted):
            assert not APIToken.objects.get(pk=token.pk).is_active
        for token in (personal, valid, human_personal):
            assert APIToken.objects.get(pk=token.pk).is_active

    def test_0132_caps_stale_project_roles_and_deactivates_orphan_rows(self, workspace):
        migration = importlib.import_module("plane.db.migrations.0132_jp_agent_security_cleanup")
        project = Project.objects.create(name="Legacy", identifier="LEG", workspace=workspace)
        for workspace_role in (ADMIN, MEMBER, GUEST):
            human = _user(workspace, workspace_role)
            ProjectMember.objects.create(project=project, member=human, role=AGENT)
        inactive = _user(workspace, AGENT)
        WorkspaceMember.objects.filter(member=inactive).update(is_active=False)
        ProjectMember.objects.create(project=project, member=inactive, role=AGENT)
        migration.cap_stale_agent_project_roles(django_apps, SimpleNamespace(connection=connection))
        for row in ProjectMember.objects.filter(project=project).exclude(member=inactive):
            role = WorkspaceMember.objects.get(workspace=workspace, member_id=row.member_id).role
            assert row.role == min(role, MEMBER) and row.is_active
        orphan = ProjectMember.objects.get(project=project, member=inactive)
        assert orphan.role == GUEST and not orphan.is_active


@pytest.mark.unit
class TestAgentAssetPayload:
    @pytest.mark.parametrize(
        "asset_ids",
        ({str(uuid4()): 1}, str(uuid4()), [], [None], ["not-a-uuid"]),
        ids=("mapping", "uuid", "empty", "null", "invalid"),
    )
    def test_malformed_asset_lists_are_denied(self, asset_ids):
        from plane.app.permissions.agent import AgentDenied, check_comment_asset_link

        with pytest.raises(AgentDenied) as exc:
            check_comment_asset_link(SimpleNamespace(data={"asset_ids": asset_ids}), SimpleNamespace(kwargs={}))
        assert exc.value.detail["code"] == "AGENT_FIELD_NOT_ALLOWED"


@pytest.mark.unit
@pytest.mark.django_db
class TestAgentDetection:
    def test_combined_membership_check_uses_one_query_and_caches_the_result(
        self, workspace, private_project, django_assert_num_queries
    ):
        from plane.app.permissions.agent import is_agent_request

        agent = _user(workspace, AGENT)
        ProjectMember.objects.create(project=private_project, member=agent, role=AGENT)
        view = SimpleNamespace(kwargs={"slug": SLUG, "project_id": private_project.id})
        for user, expected in ((agent, True), (_user(workspace, MEMBER), False)):
            request = SimpleNamespace(user=user)
            with django_assert_num_queries(1):
                assert is_agent_request(request, view) is expected
            with django_assert_num_queries(0):
                assert is_agent_request(request, view) is expected
