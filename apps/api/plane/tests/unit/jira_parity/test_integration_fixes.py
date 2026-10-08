# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Regression tests for fixes made while integrating the jira-parity features."""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from plane.bgtasks import issue_automation_task
from plane.db.models import Issue, Project, State


def _project_with_states(workspace, identifier, close_in=0):
    project = Project.objects.create(name=f"Project {identifier}", identifier=identifier, workspace=workspace)
    if close_in:
        Project.objects.filter(pk=project.pk).update(close_in=close_in)
    states = {}
    for name, group in (("To Do", "unstarted"), ("Won't Fix", "cancelled")):
        states[name] = State.objects.create(
            name=name, group=group, color="#000000", project=project, workspace=workspace
        )
    return project, states


@pytest.mark.unit
@pytest.mark.django_db
class TestCloseOldIssuesScopedFallback:
    def test_uses_the_projects_own_cancelled_state(self, workspace):
        # created first, so an unscoped `.first()` could pick this project's state
        _project_with_states(workspace, "AAA")
        project, states = _project_with_states(workspace, "BBB", close_in=1)
        issue = Issue.objects.create(name="Old", project=project, workspace=workspace, state=states["To Do"])
        Issue.objects.filter(pk=issue.pk).update(updated_at=timezone.now() - timedelta(days=60))

        with mock.patch.object(issue_automation_task.issue_activity, "delay"):
            issue_automation_task.close_old_issues()

        issue.refresh_from_db()
        assert issue.state_id == states["Won't Fix"].id

    def test_project_without_cancelled_state_is_skipped(self, workspace):
        project = Project.objects.create(name="No cancel", identifier="NOC", workspace=workspace)
        Project.objects.filter(pk=project.pk).update(close_in=1)
        todo = State.objects.create(name="To Do", group="unstarted", color="#000", project=project, workspace=workspace)
        issue = Issue.objects.create(name="Old", project=project, workspace=workspace, state=todo)
        Issue.objects.filter(pk=issue.pk).update(updated_at=timezone.now() - timedelta(days=60))

        with mock.patch.object(issue_automation_task.issue_activity, "delay"):
            issue_automation_task.close_old_issues()

        issue.refresh_from_db()
        assert issue.state_id == todo.id


def _workspace_user(workspace, role, prefix):
    from uuid import uuid4

    from plane.db.models import User, WorkspaceMember

    user = User.objects.create(email=f"{prefix}-{uuid4().hex[:8]}@plane.so", username=f"{prefix}_{uuid4().hex[:8]}")
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=role)
    return user


@pytest.mark.contract
@pytest.mark.django_db
class TestV1ProjectMemberAgentRole:
    def _setup(self, workspace, create_user):
        from plane.db.models import ProjectMember

        project = Project.objects.create(name="V1 Members", identifier="VMB", workspace=workspace)
        ProjectMember.objects.create(project=project, member=create_user, role=20)
        return project, f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/members/"

    def test_agent_role_only_for_workspace_agents(self, api_key_client, workspace, create_user):
        project, url = self._setup(workspace, create_user)
        agent = _workspace_user(workspace, 10, "agent")
        member = _workspace_user(workspace, 15, "member")

        response = api_key_client.post(url, {"member": str(agent.id), "role": 10}, format="json")
        assert response.status_code == 201, response.data
        response = api_key_client.post(url, {"member": str(member.id), "role": 10}, format="json")
        assert response.status_code == 400, response.data
        other_agent = _workspace_user(workspace, 10, "agent2")
        response = api_key_client.post(url, {"member": str(other_agent.id), "role": 15}, format="json")
        assert response.status_code == 400, response.data
        response = api_key_client.post(url, {"member": str(member.id), "role": 7}, format="json")
        assert response.status_code == 400, response.data


@pytest.mark.contract
@pytest.mark.django_db
class TestInvitedAgentOnboarding:
    def test_accepting_an_agent_invite_joins_projects_and_agents_team(self, workspace, create_user):
        from uuid import uuid4

        from rest_framework.test import APIClient

        from plane.db.models import ProjectMember, User, WorkspaceMemberInvite
        from plane.db.models.team import TeamMember
        from plane.utils.teams import seed_default_teams

        project = Project.objects.create(name="Invite Target", identifier="INV", workspace=workspace)
        agents_team = seed_default_teams(workspace)["Agents"]
        invited = User.objects.create(email=f"bot-{uuid4().hex[:8]}@plane.so", username=f"bot_{uuid4().hex[:8]}")
        invite = WorkspaceMemberInvite.objects.create(
            workspace=workspace, email=invited.email, role=10, token=uuid4().hex
        )
        client = APIClient()
        client.force_authenticate(user=invited)
        response = client.post(
            "/api/users/me/workspaces/invitations/", {"invitations": [str(invite.id)]}, format="json"
        )
        assert response.status_code == 204, response.data
        assert ProjectMember.objects.get(project=project, member=invited, is_active=True).role == 10
        assert TeamMember.objects.filter(team=agents_team, member=invited).exists()

    def test_non_agent_invite_is_untouched(self, workspace):
        from uuid import uuid4

        from plane.db.models import ProjectMember, User, WorkspaceMember
        from plane.utils.agent import onboard_invited_agent

        project = Project.objects.create(name="Invite Member", identifier="INM", workspace=workspace)
        member = User.objects.create(email=f"m-{uuid4().hex[:8]}@plane.so", username=f"m_{uuid4().hex[:8]}")
        WorkspaceMember.objects.create(workspace=workspace, member=member, role=15)
        assert onboard_invited_agent(member, [workspace.id]) == []
        assert not ProjectMember.objects.filter(project=project, member=member).exists()
