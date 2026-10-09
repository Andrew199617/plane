# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity workflows: null targets, creation, Triage, non-members, agent detection and state merges."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from plane.app.permissions.agent import is_agent_request
from plane.db.models import (
    Issue,
    IssueActivity,
    IssueType,
    IssueView,
    Project,
    ProjectMember,
    ProjectUserProperty,
    State,
    StateTransition,
    User,
    Workspace,
    WorkspaceMember,
)
from plane.db.models.state import DEFAULT_STATES
from plane.utils import workflow

ADMIN, MEMBER, AGENT, GUEST = 20, 15, 10, 5


def _user(workspace, workspace_role):
    user = User.objects.create(email=f"{uuid4().hex[:10]}@plane.so", username=uuid4().hex[:12])
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=workspace_role)
    return user


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="G2 Workflow", identifier="GTW", workspace=workspace)
    # BaseModel.save() takes created_by from the request user (none in tests)
    Project.objects.filter(pk=project.pk).update(created_by=create_user)
    project.refresh_from_db()
    ProjectMember.objects.create(project=project, member=create_user, role=ADMIN)
    return project


@pytest.fixture
def states(project):
    State.objects.bulk_create(
        [
            State(
                name=s["name"],
                color=s["color"],
                project=project,
                sequence=s["sequence"],
                workspace=project.workspace,
                group=s["group"],
                default=s.get("default", False),
            )
            for s in DEFAULT_STATES
        ]
    )
    return {s.name: s for s in State.all_state_objects.filter(project=project)}


@pytest.fixture
def member(workspace, project):
    user = _user(workspace, MEMBER)
    ProjectMember.objects.create(project=project, member=user, role=MEMBER)
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


@pytest.mark.unit
@pytest.mark.django_db
class TestDefaultState:
    def test_matches_ensure_default_state(self, project, states):
        assert workflow.get_default_state_id(project.id) == states["To Do"].id
        State.objects.filter(project=project).update(default=False)
        # no default flag: the first non-triage state, like Issue._ensure_default_state
        assert workflow.get_default_state_id(project.id) == states["To Do"].id
        assert _issue(project, None).state_id == states["To Do"].id
        assert workflow.get_default_state_id(uuid4()) is None


@pytest.mark.unit
@pytest.mark.django_db
class TestNullTarget:
    def test_null_is_a_move_to_the_default_state(self, project, states, member, restricted):
        done = _issue(project, states["Done"])
        with pytest.raises(workflow.StateTransitionNotAllowed) as exc:
            workflow.assert_state_change_allowed(issue=done, validated_data={"state": None}, user=member)
        assert exc.value.detail["code"] == workflow.STATE_TRANSITION_NOT_ALLOWED
        assert exc.value.detail["to_state_id"] == str(states["To Do"].id)
        # no state key, or already in the default state: nothing to check
        workflow.assert_state_change_allowed(issue=done, validated_data={"name": "x"}, user=member)
        todo = _issue(project, states["To Do"])
        workflow.assert_state_change_allowed(issue=todo, validated_data={"state": None}, user=member)

    def test_unrestricted_roles_may_send_null(self, project, states, member, create_user):
        done = _issue(project, states["Done"])
        workflow.assert_state_change_allowed(issue=done, validated_data={"state": None}, user=member)
        Project.objects.filter(pk=project.pk).update(is_workflow_enabled=True)
        workflow.assert_state_change_allowed(issue=done, validated_data={"state": None}, user=create_user)

    def test_agent_null_on_epic(self, project, states, workspace):
        epic_type = IssueType.objects.create(workspace=workspace, name="Epic", is_epic=True)
        epic = _issue(project, states["In Progress"], type=epic_type)
        with pytest.raises(workflow.StateTransitionNotAllowed) as exc:
            workflow.assert_state_change_allowed(issue=epic, validated_data={"state": None}, role=AGENT)
        assert exc.value.detail["code"] == workflow.AGENT_EPIC_STATE_CHANGE_FORBIDDEN


@pytest.mark.unit
@pytest.mark.django_db
class TestCreateState:
    def test_restricted_member(self, project, states, member, restricted):
        def check(state):
            workflow.assert_create_state_allowed(project_id=project.id, validated_data={"state": state}, user=member)

        check(None)
        check(states["To Do"])
        check(states["In Progress"])
        with pytest.raises(workflow.StateTransitionNotAllowed) as exc:
            check(states["Done"])
        detail = exc.value.detail
        assert detail["code"] == workflow.STATE_TRANSITION_NOT_ALLOWED
        assert detail["error"] == "You can't create a work item in 'Done'."
        assert detail["from_state_id"] == str(states["To Do"].id)
        assert detail["allowed_state_ids"] == [str(states["In Progress"].id)]

    def test_unrestricted(self, project, states, member, create_user):
        done = {"state": states["Done"]}
        workflow.assert_create_state_allowed(project_id=project.id, validated_data=done, user=member)
        Project.objects.filter(pk=project.pk).update(is_workflow_enabled=True)
        StateTransition.objects.create(
            project=project, workspace=project.workspace, from_state=None, to_state=states["Done"], roles=[GUEST]
        )
        # rules for another role leave members unrestricted; admins are never restricted
        workflow.assert_create_state_allowed(project_id=project.id, validated_data=done, user=member)
        workflow.assert_create_state_allowed(project_id=project.id, validated_data=done, user=create_user)

    def test_epic_rules(self, project, states, member, workspace):
        Project.objects.filter(pk=project.pk).update(is_workflow_enabled=True)
        StateTransition.objects.create(
            project=project,
            workspace=project.workspace,
            from_state=None,
            to_state=states["Done"],
            roles=[MEMBER],
            exclude_epics=True,
        )
        epic_type = IssueType.objects.create(workspace=workspace, name="Epic", is_epic=True)
        workflow.assert_create_state_allowed(
            project_id=project.id, validated_data={"state": states["Done"]}, user=member
        )
        with pytest.raises(workflow.StateTransitionNotAllowed):
            workflow.assert_create_state_allowed(
                project_id=project.id, validated_data={"state": states["Done"], "type": epic_type}, user=member
            )


@pytest.mark.unit
@pytest.mark.django_db
class TestNonMember:
    def test_distinct_code_and_message(self, project, states, workspace):
        outsider = _user(workspace, MEMBER)
        issue = _issue(project, states["To Do"])
        assert project.is_workflow_enabled is False
        assert workflow.is_transition_allowed(
            project_id=project.id, issue=issue, to_state_id=states["Done"].id, user=outsider
        ) == (False, workflow.PROJECT_MEMBERSHIP_REQUIRED)
        with pytest.raises(workflow.StateTransitionNotAllowed) as exc:
            workflow.assert_state_transition_allowed(issue=issue, to_state_id=states["Done"], user=outsider)
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "PROJECT_MEMBERSHIP_REQUIRED"
        assert exc.value.detail["error"] == "Only active project members can change the state of this work item."
        assert exc.value.detail["allowed_state_ids"] == []


@pytest.mark.unit
@pytest.mark.django_db
class TestIsAgentRequest:
    def _check(self, user, **kwargs):
        request = SimpleNamespace(user=user)
        view = SimpleNamespace(kwargs=kwargs)
        with CaptureQueriesContext(connection) as queries:
            result = is_agent_request(request, view)
            assert is_agent_request(request, view) is result  # cached per request
        return result, len(queries)

    def test_one_query_and_same_semantics(self, project, workspace, member):
        project_agent = _user(workspace, MEMBER)  # incoherent rows: project agent only
        ProjectMember.objects.create(project=project, member=project_agent, role=AGENT)
        workspace_agent = _user(workspace, AGENT)  # workspace agent without a project row
        both = {"slug": workspace.slug, "project_id": project.id}
        assert self._check(project_agent, **both) == (True, 1)
        assert self._check(workspace_agent, **both) == (True, 1)
        assert self._check(member, **both) == (False, 1)
        assert self._check(project_agent, project_id=project.id) == (True, 1)
        assert self._check(project_agent, slug=workspace.slug) == (False, 1)
        assert self._check(workspace_agent, workspace_id=workspace.id) == (True, 1)
        assert self._check(workspace_agent) == (False, 0)
        other = Workspace.objects.create(name="Other", owner=member, slug=f"other-{uuid4().hex[:6]}")
        assert self._check(workspace_agent, slug=other.slug) == (False, 1)


@pytest.mark.unit
@pytest.mark.django_db
class TestStateMerge:
    def _legacy(self, project):
        legacy = [
            ("Backlog", "backlog", 15000, True),
            ("Todo", "unstarted", 25000, False),
            ("In Progress", "started", 35000, False),
            ("Done", "completed", 45000, False),
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
        return {s.name: s for s in State.objects.filter(project=project)}

    def test_remap_tree(self):
        mapping = {"a": "t"}
        tree = {
            "state": ["a", "t", "x"],
            "state_id__in": "a,x",
            "and": [{"state_id": "a"}, {"priority": ["a"]}],
            "state_group": ["a"],
        }
        assert workflow.remap_state_filter_tree(tree, mapping) == {
            "state": ["t", "x"],
            "state_id__in": "t,x",
            "and": [{"state_id": "t"}, {"priority": ["a"]}],
            "state_group": ["a"],
        }

    def test_merge_records_activity_and_repoints_filters(self, project, workspace, create_user):
        old = self._legacy(project)
        backlog, todo, progress = str(old["Backlog"].id), str(old["Todo"].id), str(old["In Progress"].id)
        moved = _issue(project, old["Backlog"])
        stays = _issue(project, old["In Progress"])
        view = IssueView.objects.create(
            name="Backlog view",
            workspace=workspace,
            project=project,
            owned_by=create_user,
            filters={"state": [backlog, todo]},
            rich_filters={"and": [{"state_id__in": f"{backlog},{progress}"}]},
        )
        assert view.query == {"state__in": [backlog, todo]}
        untouched = IssueView.objects.create(
            name="Progress view",
            workspace=workspace,
            project=project,
            owned_by=create_user,
            rich_filters={"state_id": progress},
        )
        prop = ProjectUserProperty.objects.get(project=project, user=create_user)  # created with the membership
        ProjectUserProperty.objects.filter(pk=prop.pk).update(rich_filters={"state_id": backlog})
        ProjectMember.objects.filter(project=project, member=create_user).update(
            view_props={"filters": {"state": [backlog]}}
        )

        summary = workflow.seed_project_workflow(project)

        assert summary["merged"] == {"Backlog": 1}
        moved.refresh_from_db()
        assert str(moved.state_id) == todo
        activity = IssueActivity.objects.get(issue=moved, field="state")
        assert (activity.verb, activity.old_value, activity.new_value) == ("updated", "Backlog", "To Do")
        assert (str(activity.old_identifier), str(activity.new_identifier)) == (backlog, todo)
        assert activity.comment == "updated the state to" and activity.actor_id == create_user.id
        assert activity.project_id == project.id and activity.workspace_id == workspace.id
        assert not IssueActivity.objects.filter(issue=stays).exists()

        view.refresh_from_db()
        assert view.filters == {"state": [todo]}
        assert view.query == {"state__in": [todo]}
        assert view.rich_filters == {"and": [{"state_id__in": f"{todo},{progress}"}]}
        untouched.refresh_from_db()
        assert untouched.rich_filters == {"state_id": progress}
        prop.refresh_from_db()
        assert prop.rich_filters == {"state_id": todo}
        member_row = ProjectMember.objects.get(project=project, member=create_user)
        assert member_row.view_props == {"filters": {"state": [todo]}}
