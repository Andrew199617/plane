# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity agent-workflow backend: plane.utils.workflow and plane.utils.agent services."""

from uuid import uuid4

import pytest
from django.core.management import call_command

from plane.db.models import (
    APIToken,
    Issue,
    IssueType,
    Project,
    ProjectMember,
    State,
    StateTransition,
    User,
    UserNotificationPreference,
    WorkspaceMember,
)
from plane.db.models.state import DEFAULT_STATES
from plane.utils import agent as agent_service
from plane.utils import workflow

ADMIN, MEMBER, AGENT, GUEST = 20, 15, 10, 5


def _user(workspace, workspace_role):
    user = User.objects.create(email=f"{uuid4().hex[:10]}@plane.so", username=uuid4().hex[:12])
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=workspace_role)
    return user


def _standard_states(project):
    State.objects.bulk_create(
        [
            State(
                name=state["name"],
                color=state["color"],
                project=project,
                sequence=state["sequence"],
                workspace=project.workspace,
                group=state["group"],
                default=state.get("default", False),
            )
            for state in DEFAULT_STATES
        ]
    )
    return {state.name: state for state in State.all_state_objects.filter(project=project)}


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Agent Workflow", identifier="AWF", workspace=workspace)
    ProjectMember.objects.create(project=project, member=create_user, role=ADMIN)
    return project


@pytest.fixture
def states(project):
    return _standard_states(project)


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
def epic_type(workspace):
    return IssueType.objects.create(workspace=workspace, name="Epic", is_epic=True)


def _issue(project, state, issue_type=None, name="Work item"):
    return Issue.objects.create(name=name, project=project, workspace=project.workspace, state=state, type=issue_type)


def _ids(*states):
    return sorted(str(state.id) for state in states)


@pytest.mark.unit
class TestNormalize:
    def test_state_names(self):
        assert workflow.normalize_state_name("To Do") == workflow.normalize_state_name("Todo") == "todo"
        assert workflow.normalize_state_name("Won't Fix") == "wontfix"
        assert workflow.normalize_state_name(None) == ""

    def test_standard_specs_follow_default_states(self):
        specs = workflow.standard_state_specs()
        assert [spec["name"] for spec in specs] == ["To Do", "In Progress", "In Review", "Done", "Won't Fix"]
        assert [spec["group"] for spec in specs] == ["unstarted", "started", "started", "completed", "cancelled"]
        assert specs[0]["default"] is True


@pytest.mark.unit
@pytest.mark.django_db
class TestEffectiveRole:
    def test_roles(self, project, create_user, agent, member, guest, workspace):
        assert workflow.get_effective_project_role(create_user, project.id) == ADMIN
        assert workflow.get_effective_project_role(agent, project.id) == AGENT
        assert workflow.get_effective_project_role(member, project.id) == MEMBER
        assert workflow.get_effective_project_role(guest, project.id) == GUEST
        outsider = _user(workspace, MEMBER)
        assert workflow.get_effective_project_role(outsider, project.id) is None

    def test_workspace_admin_is_admin_and_workspace_agent_is_pinned(self, project, workspace):
        ws_admin = _user(workspace, ADMIN)
        ProjectMember.objects.create(project=project, member=ws_admin, role=MEMBER)
        assert workflow.get_effective_project_role(ws_admin, project.id) == ADMIN
        ws_agent = _user(workspace, AGENT)
        ProjectMember.objects.create(project=project, member=ws_agent, role=MEMBER)  # incoherent row
        assert workflow.get_effective_project_role(ws_agent, project.id) == AGENT


@pytest.mark.unit
@pytest.mark.django_db
class TestTransitions:
    def test_agent_default_fallback_without_rules(self, project, states):
        todo, progress, review, done = (states[n] for n in ("To Do", "In Progress", "In Review", "Done"))
        assert workflow.allowed_target_state_ids(project.id, todo.id, AGENT) == _ids(progress)
        assert workflow.allowed_target_state_ids(project.id, progress.id, AGENT) == _ids(review)
        assert workflow.allowed_target_state_ids(project.id, review.id, AGENT) == []
        assert workflow.allowed_target_state_ids(project.id, done.id, AGENT) == []
        issue = _issue(project, todo)
        assert workflow.is_transition_allowed(
            project_id=project.id, issue=issue, to_state_id=progress.id, role=AGENT
        ) == (True, None)
        assert workflow.is_transition_allowed(project_id=project.id, issue=issue, to_state_id=done.id, role=AGENT) == (
            False,
            workflow.STATE_TRANSITION_NOT_ALLOWED,
        )

    def test_agent_never_moves_epics(self, project, states, epic_type):
        issue = _issue(project, states["To Do"], epic_type)
        assert workflow.is_epic_issue(issue)
        assert workflow.is_transition_allowed(
            project_id=project.id, issue=issue, to_state_id=states["In Progress"].id, role=AGENT
        ) == (False, workflow.AGENT_EPIC_STATE_CHANGE_FORBIDDEN)
        assert workflow.allowed_target_state_ids(project.id, states["To Do"].id, AGENT, epic=True) == []

    def test_epic_detected_by_flag_not_name(self, project, states, workspace):
        # epic-ness comes from IssueType.is_epic (same as the web types store), never the name
        task = IssueType.objects.create(workspace=workspace, name="Task", is_default=True)
        named = IssueType.objects.create(workspace=workspace, name="epic")
        flagged = IssueType.objects.create(workspace=workspace, name="Initiative", is_epic=True)
        assert workflow.is_epic_issue(_issue(project, states["To Do"], flagged))
        assert not workflow.is_epic_issue(_issue(project, states["To Do"], named))
        assert not workflow.is_epic_issue(_issue(project, states["To Do"], task))
        assert not workflow.is_epic_issue(None)

    def test_admin_and_same_state_and_system_are_unrestricted(self, project, states, epic_type):
        issue = _issue(project, states["To Do"], epic_type)
        assert workflow.is_transition_allowed(
            project_id=project.id, issue=issue, to_state_id=states["Done"].id, role=ADMIN
        ) == (True, None)
        assert workflow.allowed_target_state_ids(project.id, states["To Do"].id, ADMIN) is None
        # same state: a kanban reorder is never a transition
        assert workflow.is_transition_allowed(
            project_id=project.id, issue=issue, to_state_id=states["To Do"].id, role=AGENT
        ) == (True, None)
        # no actor (celery, management commands)
        assert workflow.is_transition_allowed(project_id=project.id, issue=issue, to_state_id=states["Done"].id) == (
            True,
            None,
        )

    def test_role_derived_from_user(self, project, states, agent, member, create_user, workspace):
        issue = _issue(project, states["To Do"])
        done = states["Done"].id
        assert workflow.is_transition_allowed(project_id=project.id, issue=issue, to_state_id=done, user=create_user)[0]
        assert workflow.is_transition_allowed(project_id=project.id, issue=issue, to_state_id=done, user=member)[0]
        assert not workflow.is_transition_allowed(project_id=project.id, issue=issue, to_state_id=done, user=agent)[0]
        outsider = _user(workspace, MEMBER)
        assert not workflow.is_transition_allowed(project_id=project.id, issue=issue, to_state_id=done, user=outsider)[
            0
        ]

    def test_member_unrestricted_until_rules_exist_and_workflow_enabled(self, project, states):
        todo, progress, done = states["To Do"], states["In Progress"], states["Done"]
        issue = _issue(project, todo)
        StateTransition.objects.create(
            project=project, workspace=project.workspace, from_state=todo, to_state=progress, roles=[MEMBER]
        )
        # rules only bind members while the project's workflow is enabled
        assert workflow.allowed_target_state_ids(project.id, todo.id, MEMBER) is None
        Project.objects.filter(pk=project.pk).update(is_workflow_enabled=True)
        assert workflow.allowed_target_state_ids(project.id, todo.id, MEMBER) == _ids(progress)
        assert (
            workflow.is_transition_allowed(project_id=project.id, issue=issue, to_state_id=done.id, role=MEMBER)[0]
            is False
        )
        assert workflow.is_transition_allowed(project_id=project.id, issue=issue, to_state_id=progress.id, role=MEMBER)[
            0
        ]
        # guests have no rules -> unrestricted (upstream behaviour)
        assert workflow.allowed_target_state_ids(project.id, todo.id, GUEST) is None

    def test_any_state_rule_and_exclude_epics(self, project, states, epic_type):
        Project.objects.filter(pk=project.pk).update(is_workflow_enabled=True)
        StateTransition.objects.create(
            project=project,
            workspace=project.workspace,
            from_state=None,
            to_state=states["Done"],
            roles=[MEMBER],
            exclude_epics=True,
        )
        StateTransition.objects.create(
            project=project, workspace=project.workspace, from_state=None, to_state=states["Won't Fix"], roles=[MEMBER]
        )
        assert workflow.allowed_target_state_ids(project.id, states["In Review"].id, MEMBER) == _ids(
            states["Done"], states["Won't Fix"]
        )
        assert workflow.allowed_target_state_ids(project.id, states["In Review"].id, MEMBER, epic=True) == _ids(
            states["Won't Fix"]
        )
        epic = _issue(project, states["In Review"], epic_type)
        assert not workflow.is_transition_allowed(
            project_id=project.id, issue=epic, to_state_id=states["Done"].id, role=MEMBER
        )[0]

    def test_agent_rules_replace_the_fallback_and_apply_when_workflow_disabled(self, project, states):
        StateTransition.objects.create(
            project=project,
            workspace=project.workspace,
            from_state=states["In Review"],
            to_state=states["Done"],
            roles=[AGENT],
        )
        assert project.is_workflow_enabled is False
        assert workflow.allowed_target_state_ids(project.id, states["To Do"].id, AGENT) == []
        assert workflow.allowed_target_state_ids(project.id, states["In Review"].id, AGENT) == _ids(states["Done"])

    def test_inactive_rules_and_deleted_states_are_ignored(self, project, states):
        StateTransition.objects.create(
            project=project,
            workspace=project.workspace,
            from_state=states["To Do"],
            to_state=states["Done"],
            roles=[AGENT],
            is_active=False,
        )
        # inactive rule only -> fallback applies
        assert workflow.allowed_target_state_ids(project.id, states["To Do"].id, AGENT) == _ids(states["In Progress"])

    def test_leaving_triage_counts_as_leaving_the_default_state(self, project, states):
        Project.objects.filter(pk=project.pk).update(is_workflow_enabled=True)
        StateTransition.objects.create(
            project=project,
            workspace=project.workspace,
            from_state=states["To Do"],
            to_state=states["In Progress"],
            roles=[MEMBER],
        )
        issue = _issue(project, states["Triage"])
        # Triage -> default state (what accepting does) is always allowed
        assert workflow.is_transition_allowed(
            project_id=project.id, issue=issue, to_state_id=states["To Do"].id, role=MEMBER
        )[0]
        # any other target follows the rules of the default state
        assert workflow.is_transition_allowed(
            project_id=project.id, issue=issue, to_state_id=states["In Progress"].id, role=MEMBER
        )[0]
        assert workflow.is_transition_allowed(
            project_id=project.id, issue=issue, to_state_id=states["Done"].id, role=MEMBER
        ) == (False, workflow.STATE_TRANSITION_NOT_ALLOWED)
        with pytest.raises(workflow.StateTransitionNotAllowed) as exc:
            workflow.assert_state_transition_allowed(issue=issue, to_state_id=states["Done"], role=MEMBER)
        assert exc.value.detail["allowed_state_ids"] == _ids(states["In Progress"])
        assert not workflow.is_transition_allowed(
            project_id=project.id, issue=issue, to_state_id=states["Done"].id, role=AGENT
        )[0]

    def test_assert_raises_403_payload(self, project, states, agent):
        issue = _issue(project, states["To Do"])
        with pytest.raises(workflow.StateTransitionNotAllowed) as exc:
            workflow.assert_state_transition_allowed(issue=issue, to_state_id=states["Done"], user=agent)
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "STATE_TRANSITION_NOT_ALLOWED"
        assert exc.value.detail["allowed_state_ids"] == _ids(states["In Progress"])
        assert "To Do" in exc.value.detail["error"] and "Done" in exc.value.detail["error"]
        # State instance, id, str and invalid ids
        workflow.assert_state_transition_allowed(issue=issue, to_state_id=states["In Progress"], user=agent)
        workflow.assert_state_transition_allowed(issue=issue, to_state_id=str(states["In Progress"].id), user=agent)
        workflow.assert_state_transition_allowed(issue=issue, to_state_id=None, user=agent)
        workflow.assert_state_transition_allowed(issue=issue, to_state_id="not-a-uuid", user=agent)

    def test_my_transitions(self, project, states, agent, member, create_user):
        assert workflow.get_my_transitions(project.id, create_user) == {"restricted": False}
        assert workflow.get_my_transitions(project.id, member) == {"restricted": False}
        mine = workflow.get_my_transitions(project.id, agent)
        assert mine["restricted"] is True and mine["role"] == AGENT and mine["epic_locked"] is True
        assert mine["transitions"][str(states["To Do"].id)] == _ids(states["In Progress"])
        assert mine["transitions"][str(states["In Progress"].id)] == _ids(states["In Review"])
        assert mine["transitions"][str(states["Done"].id)] == []
        assert str(states["Triage"].id) not in mine["transitions"]
        assert all(targets == [] for targets in mine["epic_transitions"].values())


@pytest.mark.unit
@pytest.mark.django_db
class TestSeedProjectWorkflow:
    def _legacy_states(self, project):
        legacy = [
            ("Backlog", "backlog", 15000, True),
            ("Todo", "unstarted", 25000, False),
            ("In Progress", "started", 35000, False),
            ("Done", "completed", 45000, False),
            ("Cancelled", "cancelled", 55000, False),
            ("Triage", "triage", 65000, False),
        ]
        State.objects.bulk_create(
            [
                State(
                    name=name,
                    group=group,
                    sequence=seq,
                    default=default,
                    color="#60646C",
                    project=project,
                    workspace=project.workspace,
                )
                for name, group, seq, default in legacy
            ]
        )
        return {s.name: s for s in State.all_state_objects.filter(project=project)}

    def test_converts_plane_defaults(self, project):
        old = self._legacy_states(project)
        backlog_issue = _issue(project, old["Backlog"], name="backlog")
        todo_issue = _issue(project, old["Todo"], name="todo")
        cancelled_issue = _issue(project, old["Cancelled"], name="cancelled")
        Project.objects.filter(pk=project.pk).update(default_state=old["Backlog"])
        project.refresh_from_db()

        summary = workflow.seed_project_workflow(project)

        names = list(State.objects.filter(project=project).order_by("sequence").values_list("name", flat=True))
        assert names == ["To Do", "In Progress", "In Review", "Done", "Won't Fix"]
        todo = State.objects.get(project=project, name="To Do")
        assert todo.id == old["Todo"].id and todo.default is True and todo.group == "unstarted"
        assert State.objects.filter(project=project, default=True).count() == 1
        assert State.objects.get(project=project, name="Won't Fix").id == old["Cancelled"].id
        assert State.triage_objects.filter(project=project).count() == 1
        assert not State.objects.filter(project=project, name="Backlog").exists()
        backlog_issue.refresh_from_db()
        todo_issue.refresh_from_db()
        cancelled_issue.refresh_from_db()
        assert backlog_issue.state_id == todo.id and todo_issue.state_id == todo.id
        assert cancelled_issue.state_id == old["Cancelled"].id
        project.refresh_from_db()
        assert project.is_workflow_enabled is True
        assert project.default_state_id == todo.id
        assert summary["merged"] == {"Backlog": 1}
        assert summary["created"] == ["In Review"]
        assert "Todo -> To Do" in summary["renamed"] and "Cancelled -> Won't Fix" in summary["renamed"]

        rules = StateTransition.objects.filter(project=project)
        assert rules.count() == 2
        pairs = {(r.from_state.name, r.to_state.name) for r in rules}
        assert pairs == {("To Do", "In Progress"), ("In Progress", "In Review")}
        assert all(r.roles == [AGENT] and r.exclude_epics for r in rules)

    def test_idempotent_and_keeps_custom_states(self, project, states):
        custom = State.objects.create(
            name="QA", group="started", color="#000000", project=project, workspace=project.workspace
        )
        first = workflow.seed_project_workflow(project)
        before = list(State.all_state_objects.filter(project=project).values_list("id", "name", "sequence", "default"))
        second = workflow.seed_project_workflow(project)
        after = list(State.all_state_objects.filter(project=project).values_list("id", "name", "sequence", "default"))
        assert sorted(before) == sorted(after)
        assert first["rules_changed"] == 2 and second["rules_changed"] == 0
        assert not second["created"] and not second["renamed"] and not second["merged"]
        assert State.objects.filter(pk=custom.pk).exists()
        assert StateTransition.objects.filter(project=project).count() == 2

    def test_adds_agent_role_to_existing_rule(self, project, states):
        rule = StateTransition.objects.create(
            project=project,
            workspace=project.workspace,
            from_state=states["To Do"],
            to_state=states["In Progress"],
            roles=[MEMBER],
            exclude_epics=True,
            is_active=False,
        )
        workflow.seed_project_workflow(project)
        rule.refresh_from_db()
        assert rule.roles == [MEMBER, AGENT] and rule.is_active

    def test_creates_missing_states(self, project):
        workflow.seed_project_workflow(project)
        assert list(State.objects.filter(project=project).order_by("sequence").values_list("name", flat=True)) == [
            "To Do",
            "In Progress",
            "In Review",
            "Done",
            "Won't Fix",
        ]

    def test_replace_project_transitions(self, project, states):
        todo, progress, review = states["To Do"], states["In Progress"], states["In Review"]
        workflow.seed_project_workflow(project)
        kept = StateTransition.objects.get(project=project, from_state=todo, to_state=progress)
        rules = workflow.replace_project_transitions(
            project,
            [
                {"from_state_id": todo.id, "to_state_id": progress.id, "roles": [AGENT], "exclude_epics": True},
                {
                    "from_state_id": str(todo.id),
                    "to_state_id": str(progress.id),
                    "roles": [MEMBER],
                    "exclude_epics": True,
                },
                {"from_state_id": None, "to_state_id": review.id, "roles": [GUEST]},
                {"from_state_id": progress.id, "to_state_id": review.id, "roles": []},
            ],
        )
        assert len(rules) == 2
        kept.refresh_from_db()
        assert kept.roles == [MEMBER, AGENT]
        any_rule = StateTransition.objects.get(project=project, from_state__isnull=True)
        assert any_rule.to_state_id == review.id and any_rule.roles == [GUEST] and not any_rule.exclude_epics
        assert not StateTransition.all_objects.filter(project=project, from_state=progress).exists()

    def test_apply_jira_workflow_command(self, project, workspace):
        self._legacy_states(project)
        call_command("apply_jira_workflow", workspace=workspace.slug, dry_run=True)
        assert State.objects.filter(project=project, name="Backlog").exists()
        call_command("apply_jira_workflow", workspace=workspace.slug, project=["awf"])
        assert not State.objects.filter(project=project, name="Backlog").exists()
        assert State.objects.filter(project=project, name="In Review").exists()
        call_command("apply_jira_workflow", workspace=workspace.slug)
        assert StateTransition.objects.filter(project=project).count() == 2


@pytest.mark.unit
@pytest.mark.django_db
class TestAgentService:
    def test_create_agent_user_joins_projects(self, workspace, project):
        archived = Project.objects.create(name="Old", identifier="OLD", workspace=workspace)
        Project.objects.filter(pk=archived.pk).update(archived_at="2024-01-01T00:00:00Z")
        workspace_member = agent_service.create_agent_user(workspace, "Claude Dev")
        user = workspace_member.member
        assert workspace_member.role == AGENT and user.is_bot is False
        assert user.email == "claude-dev@agents.test-workspace.local" and user.display_name == "Claude Dev"
        assert ProjectMember.objects.get(project=project, member=user).role == AGENT
        assert not ProjectMember.objects.filter(project=archived, member=user).exists()
        assert user.profile.is_onboarded is True
        prefs = UserNotificationPreference.objects.filter(user=user).first()
        assert prefs is None or not (prefs.comment or prefs.state_change or prefs.mention)
        second = agent_service.create_agent_user(workspace, "Claude Dev")
        assert second.member.email == "claude-dev-2@agents.test-workspace.local"

    def test_create_agent_user_validation(self, workspace, create_user):
        with pytest.raises(agent_service.AgentProvisioningError):
            agent_service.create_agent_user(workspace, "  ")
        with pytest.raises(agent_service.AgentProvisioningError):
            agent_service.create_agent_user(workspace, "Dup", email=create_user.email)

    def test_sync_is_idempotent_and_reactivates(self, workspace, project, agent):
        ProjectMember.objects.filter(project=project, member=agent).update(is_active=False)
        other = Project.objects.create(name="Other", identifier="OTH", workspace=workspace)
        assert agent_service.sync_agent_memberships(workspace) == 2
        assert agent_service.sync_agent_memberships(workspace, projects=[other]) == 1
        rows = ProjectMember.objects.filter(member=agent)
        assert rows.count() == 2 and all(row.is_active and row.role == AGENT for row in rows)

    def test_sync_respects_env_toggle(self, workspace, project, agent, monkeypatch):
        other = Project.objects.create(name="Other", identifier="OTH", workspace=workspace)
        monkeypatch.setenv("AGENT_AUTO_JOIN_PROJECTS", "0")
        assert agent_service.sync_agent_memberships(workspace) == 0
        assert not ProjectMember.objects.filter(project=other, member=agent).exists()

    def test_workspace_role_change(self, workspace, project, member):
        other = Project.objects.create(name="Other", identifier="OTH", workspace=workspace)
        workspace_member = WorkspaceMember.objects.get(workspace=workspace, member=member)
        agent_service.apply_agent_workspace_role_change(workspace_member, AGENT)
        assert set(ProjectMember.objects.filter(member=member).values_list("project_id", "role")) == {
            (project.id, AGENT),
            (other.id, AGENT),
        }
        workspace_member.role = AGENT
        agent_service.apply_agent_workspace_role_change(workspace_member, MEMBER)
        assert set(ProjectMember.objects.filter(member=member).values_list("role", flat=True)) == {MEMBER}

    def test_role_mismatch(self):
        assert agent_service.agent_role_mismatch(AGENT, MEMBER)
        assert agent_service.agent_role_mismatch(MEMBER, AGENT)
        assert agent_service.agent_role_mismatch(GUEST, "10")
        assert not agent_service.agent_role_mismatch(AGENT, "10")
        assert not agent_service.agent_role_mismatch(MEMBER, GUEST)

    def test_token_and_deactivate(self, workspace, project):
        workspace_member = agent_service.create_agent_user(workspace, "Bot")
        token = agent_service.create_agent_token(workspace_member.member, workspace, label="ci")
        assert token.user_type == 1 and token.workspace_id == workspace.id and token.token.startswith("plane_api_")
        agent_service.deactivate_agent(workspace_member)
        workspace_member.refresh_from_db()
        assert workspace_member.is_active is False
        assert not ProjectMember.objects.filter(member=workspace_member.member, is_active=True).exists()
        assert not APIToken.objects.filter(user=workspace_member.member, is_active=True).exists()

    def test_agent_joins_and_leaves_default_agents_team(self, workspace, project):
        from plane.db.models.team import TeamMember
        from plane.utils.teams import seed_default_teams

        agents_team = seed_default_teams(workspace)["Agents"]
        workspace_member = agent_service.create_agent_user(workspace, "Team Bot")
        user = workspace_member.member
        assert list(
            TeamMember.objects.filter(workspace_id=workspace.id, member=user).values_list("team_id", flat=True)
        ) == [agents_team.id]
        agent_service.deactivate_agent(workspace_member)
        assert not TeamMember.all_objects.filter(workspace_id=workspace.id, member=user).exists()

    def test_create_agent_without_default_teams(self, workspace, project):
        from plane.db.models.team import TeamMember

        workspace_member = agent_service.create_agent_user(workspace, "Lonely Bot")
        assert not TeamMember.objects.filter(member=workspace_member.member).exists()

    def test_project_created_hook_joins_agents(self, workspace, project, agent):
        new_project = Project.objects.create(name="New", identifier="NEW", workspace=workspace)
        from plane.utils.jira_parity.project_hooks import run_project_created_hooks

        results = run_project_created_hooks(new_project, None)
        assert results["agents"] is True and results["workflow"] is True
        assert ProjectMember.objects.get(project=new_project, member=agent).role == AGENT
        new_project.refresh_from_db()
        assert new_project.is_workflow_enabled is True

    def test_commands(self, workspace, project, capsys):
        call_command("create_agent", workspace=workspace.slug, name="Codex")
        out = capsys.readouterr().out
        assert "token=plane_api_" in out
        user = User.objects.get(display_name="Codex")
        assert ProjectMember.objects.get(project=project, member=user).role == AGENT
        call_command("create_agent", workspace=workspace.slug, name="Codex", no_token=True)
        assert "already exists" in capsys.readouterr().out
        assert User.objects.filter(display_name="Codex").count() == 1
        ProjectMember.objects.filter(member=user).delete(soft=False)
        call_command("sync_agent_memberships", workspace=workspace.slug)
        assert ProjectMember.objects.filter(project=project, member=user, role=AGENT, is_active=True).exists()
