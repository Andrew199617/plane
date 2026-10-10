# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Master board column scope, scoped work item type counts and the sprint-by-name / type filters."""

import json
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework import status

from plane.db.models import Cycle, CycleIssue, Issue, IssueType, Project, ProjectMember, State
from plane.tests.unit.jira_parity import test_project_categories_api as categories_api
from plane.tests.unit.jira_parity.test_project_categories_api import ISSUES_URL, _client, _ids, _issue_ids, _project
from plane.utils.issue_filters import _jp_cycle_names, issue_filters

# Fixtures shared with the master board tests
board = categories_api.board
guest = categories_api.guest
member = categories_api.member


def _board_get(client, workspace, board, **params):
    return client.get(ISSUES_URL.format(slug=workspace.slug, pk=board["category"].id), params)


# ---------------------------------------------------------------- B4/D4: master board columns


@pytest.mark.contract
class TestBoardColumnsFollowProjectAccess:
    @pytest.mark.django_db
    def test_state_name_columns_skip_projects_the_guest_is_not_in(self, workspace, board, guest):
        # guest is only in AA (Backlog / To Do / In Progress); BB adds In Review / Done
        response = _board_get(_client(guest), workspace, board, group_by="state__name")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert list(response.data["results"]) == ["To Do", "In Progress", "Backlog"]

    @pytest.mark.django_db
    def test_project_bound_group_ids_skip_hidden_projects(self, workspace, board, guest):
        p1, p2, _ = board["projects"]
        client = _client(guest)
        hidden_states = {str(state_id) for state_id in State.objects.filter(project=p2).values_list("id", flat=True)}
        p1_cycles = {str(cycle_id) for cycle_id in Cycle.objects.filter(project=p1).values_list("id", flat=True)}

        response = _board_get(client, workspace, board, group_by="project_id")
        assert set(response.data["results"]) == {str(p1.id)}

        response = _board_get(client, workspace, board, group_by="state_id")
        assert set(response.data["results"]) and not set(response.data["results"]) & hidden_states

        response = _board_get(client, workspace, board, group_by="cycle_id", sub_group_by="project_id")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert set(response.data["results"]) == p1_cycles | {"None"}

    @pytest.mark.django_db
    def test_workspace_member_outside_the_projects_gets_no_columns(self, workspace, board, member):
        response = _board_get(_client(member), workspace, board, group_by="state__name")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["results"] == {}
        assert response.data["total_count"] == 0

    @pytest.mark.django_db
    def test_project_members_still_get_every_column(self, session_client, workspace, board):
        response = _board_get(session_client, workspace, board, group_by="state__name")
        assert list(response.data["results"]) == ["To Do", "In Progress", "In Review", "Done", "Backlog"]


# ---------------------------------------------------------------- B4/D4: work item type counts


def _types_url(slug, pk=None):
    return f"/api/workspaces/{slug}/work-item-types/" + (f"{pk}/" if pk else "")


@pytest.fixture
def typed_issues(db, workspace, create_user, member, guest):
    """A Bug type used twice in a project shared with member + guest and twice in a private project."""
    bug = IssueType.objects.create(workspace=workspace, name="Count Bug")
    shared = _project(workspace, "SH", members=[(create_user, 20), (member, 15), (guest, 5)])
    private = _project(workspace, "PR", members=[(create_user, 20)])
    for project, author in ((shared, create_user), (shared, guest), (private, create_user), (private, create_user)):
        issue = Issue(name="typed", project=project, workspace=workspace, type=bug)
        issue.save(created_by_id=author.id)
    return {"bug": bug, "shared": shared, "private": private}


def _count(response, type_id):
    return next(row["issue_count"] for row in response.data if str(row["id"]) == str(type_id))


@pytest.mark.contract
class TestWorkItemTypeCountsAreScoped:
    @pytest.mark.django_db
    def test_admin_sees_workspace_wide_counts(self, session_client, workspace, typed_issues):
        response = session_client.get(_types_url(workspace.slug))
        assert response.status_code == status.HTTP_200_OK, response.data
        assert _count(response, typed_issues["bug"].id) == 4

    @pytest.mark.django_db
    def test_member_counts_only_projects_they_are_in(self, workspace, typed_issues, member):
        client = _client(member)
        bug = typed_issues["bug"]
        assert _count(client.get(_types_url(workspace.slug)), bug.id) == 2
        assert client.get(_types_url(workspace.slug, bug.id)).data["issue_count"] == 2

        shared = typed_issues["shared"]
        response = client.get(f"/api/workspaces/{workspace.slug}/projects/{shared.id}/work-item-types/")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert _count(response, bug.id) == 2

    @pytest.mark.django_db
    def test_restricted_guest_counts_only_own_work_items(self, workspace, typed_issues, guest):
        bug = typed_issues["bug"]
        assert _count(_client(guest).get(_types_url(workspace.slug)), bug.id) == 1

        Project.objects.filter(pk=typed_issues["shared"].pk).update(guest_view_all_features=True)
        assert _count(_client(guest).get(_types_url(workspace.slug)), bug.id) == 2

    @pytest.mark.django_db
    def test_inactive_membership_counts_nothing(self, workspace, typed_issues, member):
        ProjectMember.objects.filter(project=typed_issues["shared"], member=member).update(is_active=False)
        assert _count(_client(member).get(_types_url(workspace.slug)), typed_issues["bug"].id) == 0

    @pytest.mark.django_db
    def test_deleted_project_counts_nothing_before_membership_cleanup(self, workspace, typed_issues, member):
        # Project deletion is asynchronous: project members and work items can survive briefly.
        Project.objects.filter(pk=typed_issues["shared"].pk).update(deleted_at=timezone.now())
        assert _count(_client(member).get(_types_url(workspace.slug)), typed_issues["bug"].id) == 0

    @pytest.mark.django_db
    def test_delete_still_blocked_by_workspace_wide_usage(self, session_client, workspace, typed_issues):
        response = session_client.delete(_types_url(workspace.slug, typed_issues["bug"].id))
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "WORK_ITEM_TYPE_IN_USE"


# ---------------------------------------------------------------- D6: sprint by name / type filters


@pytest.mark.unit
class TestCycleNameParsing:
    def test_json_form_is_comma_safe_and_null_means_no_sprint(self):
        assert _jp_cycle_names('["Sprint 1, part 2", null, "None", ""]') == (["Sprint 1, part 2", "None"], True)
        assert _jp_cycle_names('["None"]') == (["None"], False)

    def test_legacy_comma_form(self):
        assert _jp_cycle_names("None, Sprint 1") == (["Sprint 1"], True)
        assert _jp_cycle_names("[Q1] Sprint") == (["[Q1] Sprint"], False)
        assert _jp_cycle_names(None) == ([], False)

    def test_stored_queries_stay_json(self):
        type_id = str(uuid4())
        params = {
            "cycle_name": '["Sprint 1", null]',
            "issue_type": [type_id, "None"],
            "project_category": [str(uuid4())],
        }
        query = issue_filters(params, "POST")
        json.dumps(query)
        assert query["issue_cycle__cycle__name__in"] == ["Sprint 1"]
        assert query["type_id__in"] == [type_id]


@pytest.fixture
def sprints(db, workspace, board, create_user):
    """On top of `board`: b_todo in "Sprint 2", a_progress in "Sprint 3, hotfix", a_backlog in a sprint named None."""
    p1, p2, _ = board["projects"]
    issues = board["issues"]

    def add(name, project, issue):
        cycle = Cycle.objects.filter(project=project, name=name).first() or Cycle.objects.create(
            name=name, project=project, workspace=workspace, owned_by=create_user
        )
        CycleIssue.objects.create(cycle=cycle, issue=issue, project=project, workspace=workspace)

    add("Sprint 2", p2, issues["b_todo"])
    add("Sprint 3, hotfix", p1, issues["a_progress"])
    add("None", p1, issues["a_backlog"])
    return board


@pytest.mark.contract
class TestBoardSprintAndTypeFilters:
    @pytest.mark.django_db
    def test_no_sprint_or_named_sprints(self, session_client, workspace, sprints):
        expected = _issue_ids(sprints, "a_todo", "b_review", "a_guest")
        for value in (json.dumps(["Sprint 1", None]), "None,Sprint 1"):
            response = _board_get(session_client, workspace, sprints, cycle_name=value)
            assert response.status_code == status.HTTP_200_OK, response.data
            assert _ids(response.data["results"]) == expected, value

        # grouped boards apply it too
        response = _board_get(
            session_client, workspace, sprints, cycle_name=json.dumps(["Sprint 1", None]), group_by="state__name"
        )
        assert response.data["total_count"] == len(expected)

    @pytest.mark.django_db
    def test_names_with_commas_and_a_sprint_named_none(self, session_client, workspace, sprints):
        response = _board_get(session_client, workspace, sprints, cycle_name=json.dumps(["Sprint 3, hotfix"]))
        assert _ids(response.data["results"]) == _issue_ids(sprints, "a_progress")

        response = _board_get(session_client, workspace, sprints, cycle_name=json.dumps(["None"]))
        assert _ids(response.data["results"]) == _issue_ids(sprints, "a_backlog")

        response = _board_get(session_client, workspace, sprints, cycle_name=json.dumps([None]))
        assert _ids(response.data["results"]) == _issue_ids(sprints, "a_guest")

        # legacy comma form keeps its "None" = no sprint meaning
        response = _board_get(session_client, workspace, sprints, cycle_name="None")
        assert _ids(response.data["results"]) == _issue_ids(sprints, "a_guest")

    @pytest.mark.django_db
    def test_no_type_or_type_and_combined_with_sprints(self, session_client, workspace, sprints):
        bug = IssueType.objects.create(workspace=workspace, name="Filter Bug")
        story = IssueType.objects.create(workspace=workspace, name="Filter Story")
        issues = sprints["issues"]
        Issue.objects.filter(pk__in=[issues["a_todo"].pk, issues["b_todo"].pk]).update(type=bug)
        Issue.objects.filter(pk=issues["b_review"].pk).update(type=story)
        # new work items get the default type: clear it on the rest
        untyped = [issues[key].pk for key in ("a_progress", "a_backlog", "a_guest")]
        Issue.objects.filter(pk__in=untyped).update(type=None)

        response = _board_get(session_client, workspace, sprints, issue_type=f"None,{bug.id}")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert _ids(response.data["results"]) == _issue_ids(
            sprints, "a_todo", "b_todo", "a_progress", "a_backlog", "a_guest"
        )

        # both OR filters apply together
        response = _board_get(
            session_client,
            workspace,
            sprints,
            issue_type=f"None,{bug.id}",
            cycle_name=json.dumps(["Sprint 1", None]),
        )
        assert _ids(response.data["results"]) == _issue_ids(sprints, "a_todo", "a_guest")
