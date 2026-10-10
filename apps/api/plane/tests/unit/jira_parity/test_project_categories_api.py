# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Endpoint tests for Jira-parity project categories and master boards:

- /api/workspaces/<slug>/project-categories/ CRUD and permissions
- category_id on the app + v1 project serializers and the project list payload
- /api/workspaces/<slug>/project-categories/<id>/issues/ (flat + grouped, state__name, filters, scope)
- /api/workspaces/<slug>/project-categories/<id>/cycles/
"""

import json
from datetime import datetime, timezone as dt_timezone
from uuid import uuid4

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    Cycle,
    CycleIssue,
    Issue,
    IssueType,
    IssueView,
    Project,
    ProjectCategory,
    ProjectMember,
    State,
    User,
    Workspace,
    WorkspaceMember,
)

CATEGORIES_URL = "/api/workspaces/{slug}/project-categories/"
CATEGORY_URL = "/api/workspaces/{slug}/project-categories/{pk}/"
ISSUES_URL = "/api/workspaces/{slug}/project-categories/{pk}/issues/"
CYCLES_URL = "/api/workspaces/{slug}/project-categories/{pk}/cycles/"

GROUPS = {"To Do": "unstarted", "In Progress": "started", "In Review": "started", "Done": "completed"}


def _user(workspace, role, prefix):
    unique_id = uuid4().hex[:8]
    user = User.objects.create(
        email=f"{prefix}-{unique_id}@plane.so",
        username=f"{prefix}_{unique_id}",
        first_name=prefix.title(),
        last_name="User",
    )
    user.set_password("test-password")
    user.save()
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=role)
    return user


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _project(workspace, identifier, category=None, members=()):
    project = Project.objects.create(
        name=f"Project {identifier}", identifier=identifier, workspace=workspace, category=category
    )
    for member, role in members:
        ProjectMember.objects.create(project=project, member=member, workspace=workspace, role=role)
    return project


def _states(project, names):
    return {
        name: State.objects.create(
            name=name,
            project=project,
            workspace=project.workspace,
            group=GROUPS.get(name, "backlog"),
            color="#000000",
            sequence=(index + 1) * 1000,
        )
        for index, name in enumerate(names)
    }


def _issue(name, project, state, author, **extra):
    issue = Issue(name=name, project=project, workspace=project.workspace, state=state, **extra)
    issue.save(created_by_id=author.id)
    return issue


@pytest.fixture
def member(db, workspace):
    return _user(workspace, 15, "member")


@pytest.fixture
def guest(db, workspace):
    return _user(workspace, 5, "guest")


@pytest.fixture
def agent(db, workspace):
    return _user(workspace, 10, "agent")


@pytest.fixture
def other_workspace(db, create_user):
    workspace = Workspace.objects.create(name="Other", owner=create_user, slug="other-workspace")
    WorkspaceMember.objects.create(workspace=workspace, member=create_user, role=20)
    return workspace


# ---------------------------------------------------------------- category CRUD


@pytest.mark.contract
class TestProjectCategoryCrud:
    @pytest.mark.django_db
    def test_admin_create_list_retrieve(self, session_client, workspace, create_user):
        project = _project(workspace, "AA")
        url = CATEGORIES_URL.format(slug=workspace.slug)

        response = session_client.post(url, {"name": "  Game  ", "description": "Games"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        game = response.data
        assert set(game) == {"id", "name", "description", "sort_order", "logo_props", "project_ids"}
        assert game["name"] == "Game"
        assert game["project_ids"] == []

        response = session_client.post(
            url, {"name": "VSCode", "project_ids": [str(project.id)], "logo_props": {"in_use": "emoji"}}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        vscode = response.data
        assert vscode["project_ids"] == [str(project.id)]
        assert vscode["sort_order"] > game["sort_order"]
        assert Project.objects.get(pk=project.pk).category_id is not None

        response = session_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert [row["name"] for row in response.data] == ["Game", "VSCode"]

        response = session_client.get(CATEGORY_URL.format(slug=workspace.slug, pk=vscode["id"]))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["logo_props"] == {"in_use": "emoji"}

        response = session_client.get(CATEGORY_URL.format(slug=workspace.slug, pk=uuid4()))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.django_db
    def test_validation(self, session_client, workspace, other_workspace):
        url = CATEGORIES_URL.format(slug=workspace.slug)
        assert session_client.post(url, {"name": "Game"}, format="json").status_code == 201

        duplicate = session_client.post(url, {"name": "game"}, format="json")
        assert duplicate.status_code == status.HTTP_400_BAD_REQUEST
        assert "name" in duplicate.data

        assert session_client.post(url, {"name": "   "}, format="json").status_code == 400

        foreign_project = _project(other_workspace, "ZZ")
        response = session_client.post(url, {"name": "Web", "project_ids": [str(foreign_project.id)]}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "project_ids" in response.data
        assert not ProjectCategory.objects.filter(name="Web").exists()

    @pytest.mark.django_db
    def test_patch_renames_and_replaces_projects(self, session_client, workspace):
        game = ProjectCategory.objects.create(workspace=workspace, name="Game")
        ProjectCategory.objects.create(workspace=workspace, name="Website")
        p1 = _project(workspace, "AA", category=game)
        p2 = _project(workspace, "BB")
        url = CATEGORY_URL.format(slug=workspace.slug, pk=game.id)

        response = session_client.patch(url, {"name": "Games", "project_ids": [str(p2.id)]}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["name"] == "Games"
        assert response.data["project_ids"] == [str(p2.id)]
        assert Project.objects.get(pk=p1.pk).category_id is None
        assert Project.objects.get(pk=p2.pk).category_id == game.id

        # renaming onto another category's name is rejected, a no-op rename of itself is fine
        assert session_client.patch(url, {"name": "website"}, format="json").status_code == 400
        assert session_client.patch(url, {"name": "Games", "sort_order": 1}, format="json").status_code == 200
        # PATCH without project_ids leaves projects alone
        assert Project.objects.get(pk=p2.pk).category_id == game.id

    @pytest.mark.django_db
    def test_delete_uncategorizes_projects(self, session_client, workspace):
        game = ProjectCategory.objects.create(workspace=workspace, name="Game")
        project = _project(workspace, "AA", category=game)
        board = IssueView.objects.create(
            workspace=workspace, name="Game Board", category=game, owned_by=workspace.owner
        )

        response = session_client.delete(CATEGORY_URL.format(slug=workspace.slug, pk=game.id))
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert Project.objects.get(pk=project.pk).category_id is None
        assert not ProjectCategory.objects.filter(pk=game.pk).exists()
        assert IssueView.all_objects.get(pk=board.pk).deleted_at is not None
        assert session_client.get(CATEGORIES_URL.format(slug=workspace.slug)).data == []

    @pytest.mark.django_db
    def test_permissions(self, workspace, member, guest, agent, other_workspace):
        game = ProjectCategory.objects.create(workspace=workspace, name="Game")
        list_url = CATEGORIES_URL.format(slug=workspace.slug)
        detail_url = CATEGORY_URL.format(slug=workspace.slug, pk=game.id)

        for user in (member, guest, agent):
            client = _client(user)
            assert client.get(list_url).status_code == status.HTTP_200_OK
            assert client.get(detail_url).status_code == status.HTTP_200_OK
            assert client.post(list_url, {"name": "X"}, format="json").status_code == status.HTTP_403_FORBIDDEN
            assert client.patch(detail_url, {"name": "X"}, format="json").status_code == status.HTTP_403_FORBIDDEN
            assert client.delete(detail_url).status_code == status.HTTP_403_FORBIDDEN

        outsider = _user(other_workspace, 20, "outsider")
        assert _client(outsider).get(list_url).status_code == status.HTTP_403_FORBIDDEN
        # a category of another workspace is not reachable through this workspace's slug
        foreign = ProjectCategory.objects.create(workspace=other_workspace, name="Game")
        response = _client(outsider).get(CATEGORY_URL.format(slug=other_workspace.slug, pk=game.id))
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert ProjectCategory.objects.filter(pk=foreign.pk).exists()


# ---------------------------------------------------------------- project serializers


@pytest.mark.contract
class TestProjectCategoryOnProjects:
    @pytest.mark.django_db
    def test_app_project_category_id_read_write(self, session_client, workspace, create_user, other_workspace):
        game = ProjectCategory.objects.create(workspace=workspace, name="Game")
        foreign = ProjectCategory.objects.create(workspace=other_workspace, name="Game")
        project = _project(workspace, "AA", members=[(create_user, 20)])
        url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/"

        response = session_client.patch(url, {"category_id": str(game.id)}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert str(response.data["category_id"]) == str(game.id)
        assert Project.objects.get(pk=project.pk).category_id == game.id

        response = session_client.get(url)
        assert str(response.data["category_id"]) == str(game.id)

        listed = session_client.get(f"/api/workspaces/{workspace.slug}/projects/")
        assert listed.status_code == status.HTTP_200_OK
        row = next(item for item in listed.data if str(item["id"]) == str(project.id))
        assert str(row["category_id"]) == str(game.id)

        details = session_client.get(f"/api/workspaces/{workspace.slug}/projects/details/")
        row = next(item for item in details.data if str(item["id"]) == str(project.id))
        assert str(row["category_id"]) == str(game.id)

        for key in ("category_id", "category"):
            response = session_client.patch(url, {key: str(foreign.id)}, format="json")
            assert response.status_code == status.HTTP_400_BAD_REQUEST, (key, response.data)
        assert Project.objects.get(pk=project.pk).category_id == game.id

        # a stale `category` sent together with `category_id` (full-object PATCH) does not win
        web = ProjectCategory.objects.create(workspace=workspace, name="Website")
        response = session_client.patch(url, {"category": str(game.id), "category_id": str(web.id)}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert Project.objects.get(pk=project.pk).category_id == web.id

        response = session_client.patch(url, {"category_id": None}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert Project.objects.get(pk=project.pk).category_id is None

    @pytest.mark.django_db
    def test_app_project_create_with_category(self, session_client, workspace):
        game = ProjectCategory.objects.create(workspace=workspace, name="Game")
        response = session_client.post(
            f"/api/workspaces/{workspace.slug}/projects/",
            {"name": "Categorized", "identifier": "CAT", "category_id": str(game.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert str(response.data["category_id"]) == str(game.id)
        assert Project.objects.get(identifier="CAT").category_id == game.id

    @pytest.mark.django_db
    def test_v1_project_category_id(self, api_key_client, workspace, create_user, other_workspace):
        game = ProjectCategory.objects.create(workspace=workspace, name="Game")
        foreign = ProjectCategory.objects.create(workspace=other_workspace, name="Game")
        url = f"/api/v1/workspaces/{workspace.slug}/projects/"

        response = api_key_client.post(
            url, {"name": "Public", "identifier": "PUB", "category_id": str(game.id)}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert str(response.data["category_id"]) == str(game.id)
        project = Project.objects.get(identifier="PUB")
        assert project.category_id == game.id

        response = api_key_client.patch(f"{url}{project.id}/", {"category_id": str(foreign.id)}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        response = api_key_client.patch(f"{url}{project.id}/", {"category_id": None}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["category_id"] is None
        assert Project.objects.get(pk=project.pk).category_id is None


# ---------------------------------------------------------------- master board issues


@pytest.fixture
def board(db, workspace, create_user, guest):
    """Two Game projects (+ one outside the category) with states, issues and a shared sprint."""
    game = ProjectCategory.objects.create(workspace=workspace, name="Game")
    p1 = _project(workspace, "AA", category=game, members=[(create_user, 20), (guest, 5)])
    p2 = _project(workspace, "BB", category=game, members=[(create_user, 20)])
    outside = _project(workspace, "CC", members=[(create_user, 20)])
    s1 = _states(p1, ["Backlog", "To Do", "In Progress"])
    s2 = _states(p2, ["To Do", "In Progress", "In Review", "Done"])
    s3 = _states(outside, ["To Do", "Outside"])

    issues = {
        "a_todo": _issue("A todo", p1, s1["To Do"], create_user, priority="high"),
        "a_progress": _issue("A progress", p1, s1["In Progress"], create_user),
        "a_backlog": _issue("A backlog", p1, s1["Backlog"], create_user),
        "a_guest": _issue("A by guest", p1, s1["To Do"], guest),
        "b_todo": _issue("B todo", p2, s2["To Do"], create_user),
        "b_review": _issue("B review", p2, s2["In Review"], create_user),
        "c_todo": _issue("C todo", outside, s3["To Do"], create_user),
    }

    sprint_a = Cycle.objects.create(
        name="Sprint 1",
        project=p1,
        workspace=workspace,
        owned_by=create_user,
        start_date=datetime(2026, 1, 1, tzinfo=dt_timezone.utc),
        end_date=datetime(2026, 1, 14, tzinfo=dt_timezone.utc),
    )
    sprint_b = Cycle.objects.create(
        name="Sprint 1",
        project=p2,
        workspace=workspace,
        owned_by=create_user,
        start_date=datetime(2026, 1, 1, tzinfo=dt_timezone.utc),
        end_date=datetime(2026, 1, 14, tzinfo=dt_timezone.utc),
    )
    Cycle.objects.create(name="Sprint 2", project=p2, workspace=workspace, owned_by=create_user)
    Cycle.objects.create(name="Other sprint", project=outside, workspace=workspace, owned_by=create_user)
    CycleIssue.objects.create(cycle=sprint_a, issue=issues["a_todo"], project=p1, workspace=workspace)
    CycleIssue.objects.create(cycle=sprint_b, issue=issues["b_review"], project=p2, workspace=workspace)

    return {"category": game, "projects": (p1, p2, outside), "issues": issues}


def _ids(rows):
    return {str(row["id"]) for row in rows}


def _issue_ids(board, *keys):
    return {str(board["issues"][key].id) for key in keys}


ALL_GAME = ("a_todo", "a_progress", "a_backlog", "a_guest", "b_todo", "b_review")


@pytest.mark.contract
class TestCategoryBoardIssues:
    def _get(self, client, workspace, board, **params):
        return client.get(ISSUES_URL.format(slug=workspace.slug, pk=board["category"].id), params)

    @pytest.mark.django_db
    def test_flat_list_is_scoped_to_the_category(self, session_client, workspace, board):
        response = self._get(session_client, workspace, board, cursor="100:0:0", per_page=100)
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["grouped_by"] is None
        assert response.data["total_count"] == len(ALL_GAME)
        assert _ids(response.data["results"]) == _issue_ids(board, *ALL_GAME)
        row = response.data["results"][0]
        for key in ("state_id", "state__group", "state__name", "assignee_ids", "label_ids", "project_id", "cycle_id"):
            assert key in row

    @pytest.mark.django_db
    def test_group_by_state_name(self, session_client, workspace, board):
        response = self._get(session_client, workspace, board, group_by="state__name", per_page=50)
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["grouped_by"] == "state__name"
        results = response.data["results"]
        assert list(results) == ["To Do", "In Progress", "In Review", "Done", "Backlog"]
        assert _ids(results["To Do"]["results"]) == _issue_ids(board, "a_todo", "a_guest", "b_todo")
        assert results["To Do"]["total_results"] == 3
        assert _ids(results["In Review"]["results"]) == _issue_ids(board, "b_review")
        assert results["Done"]["total_results"] == 0
        assert "Outside" not in results

    @pytest.mark.django_db
    def test_sub_group_by_project(self, session_client, workspace, board):
        p1, p2, _ = board["projects"]
        response = self._get(session_client, workspace, board, group_by="state__name", sub_group_by="project_id")
        assert response.status_code == status.HTTP_200_OK, response.data
        results = response.data["results"]
        assert set(results["To Do"]["results"]) == {str(p1.id), str(p2.id)}
        assert _ids(results["To Do"]["results"][str(p2.id)]["results"]) == _issue_ids(board, "b_todo")

        # state__name as the swimlane works too
        response = self._get(session_client, workspace, board, group_by="project_id", sub_group_by="state__name")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert set(response.data["results"]) == {str(p1.id), str(p2.id)}

    @pytest.mark.django_db
    def test_per_group_pagination_and_filters(self, session_client, workspace, board):
        response = self._get(session_client, workspace, board, group_by="state__name", state_name="To Do")
        results = response.data["results"]
        assert _ids(results["To Do"]["results"]) == _issue_ids(board, "a_todo", "a_guest", "b_todo")
        assert results["In Progress"]["total_results"] == 0

        response = self._get(session_client, workspace, board, cycle_name="Sprint 1")
        assert _ids(response.data["results"]) == _issue_ids(board, "a_todo", "b_review")

        rich = json.dumps({"and": [{"cycle_name__in": "Sprint 1"}, {"state_name": "In Review"}]})
        response = self._get(session_client, workspace, board, filters=rich)
        assert response.status_code == status.HTTP_200_OK, response.data
        assert _ids(response.data["results"]) == _issue_ids(board, "b_review")

        p1, _, _ = board["projects"]
        response = self._get(session_client, workspace, board, filters=json.dumps({"project_id": str(p1.id)}))
        assert _ids(response.data["results"]) == _issue_ids(board, "a_todo", "a_progress", "a_backlog", "a_guest")

        response = self._get(session_client, workspace, board, priority="high", group_by="priority")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert _ids(response.data["results"]["high"]["results"]) == _issue_ids(board, "a_todo")

    @pytest.mark.django_db
    def test_work_item_type_filter_and_group(self, session_client, workspace, board):
        bug = IssueType.objects.create(workspace=workspace, name="Board Bug")
        Issue.objects.filter(pk=board["issues"]["b_review"].pk).update(type=bug)

        # rich filter sent by the board's "type" quick filter
        rich = json.dumps({"type_id__in": str(bug.id)})
        response = self._get(session_client, workspace, board, filters=rich)
        assert response.status_code == status.HTTP_200_OK, response.data
        assert _ids(response.data["results"]) == _issue_ids(board, "b_review")
        assert str(response.data["results"][0]["type_id"]) == str(bug.id)

        response = self._get(session_client, workspace, board, group_by="type_id")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert _ids(response.data["results"][str(bug.id)]["results"]) == _issue_ids(board, "b_review")

    @pytest.mark.django_db
    def test_cycle_name_ignores_deleted_cycles(self, session_client, workspace, board):
        p1, _, _ = board["projects"]
        sprint = Cycle.objects.get(project=p1, name="Sprint 1")
        Cycle.objects.filter(pk=sprint.pk).update(deleted_at=datetime(2026, 2, 1, tzinfo=dt_timezone.utc))
        response = self._get(session_client, workspace, board, cycle_name="Sprint 1")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert _ids(response.data["results"]) == _issue_ids(board, "b_review")

    @pytest.mark.django_db
    def test_invalid_group_by(self, session_client, workspace, board):
        for params in (
            {"group_by": "state__name", "sub_group_by": "state__name"},
            {"group_by": "created_by__password"},
            {"group_by": "state_id", "sub_group_by": "workspace__secret"},
        ):
            assert self._get(session_client, workspace, board, **params).status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_guest_and_agent_scope(self, workspace, board, guest, agent):
        # Restricted guest (guest_view_all_features=False) only sees own issues of member projects
        response = self._get(_client(guest), workspace, board)
        assert response.status_code == status.HTTP_200_OK
        assert _ids(response.data["results"]) == _issue_ids(board, "a_guest")

        p1, p2, _ = board["projects"]
        for project in (p1, p2):
            ProjectMember.objects.create(project=project, member=agent, workspace=workspace, role=10)
        response = self._get(_client(agent), workspace, board, group_by="state__name")
        assert response.status_code == status.HTTP_200_OK
        assert sum(group["total_results"] for group in response.data["results"].values()) == len(ALL_GAME)

    @pytest.mark.django_db
    def test_unknown_category_and_outsiders(self, session_client, workspace, board, other_workspace):
        response = session_client.get(ISSUES_URL.format(slug=workspace.slug, pk=uuid4()))
        assert response.status_code == status.HTTP_404_NOT_FOUND
        foreign = ProjectCategory.objects.create(workspace=other_workspace, name="Game")
        response = session_client.get(ISSUES_URL.format(slug=workspace.slug, pk=foreign.id))
        assert response.status_code == status.HTTP_404_NOT_FOUND

        outsider = _user(other_workspace, 20, "outsider")
        response = self._get(_client(outsider), workspace, board)
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.contract
class TestCategoryCycles:
    @pytest.mark.django_db
    def test_cycles_distinct_by_name(self, session_client, workspace, board):
        p1, p2, _ = board["projects"]
        response = session_client.get(CYCLES_URL.format(slug=workspace.slug, pk=board["category"].id))
        assert response.status_code == status.HTTP_200_OK, response.data
        assert [row["name"] for row in response.data] == ["Sprint 1", "Sprint 2"]
        sprint_1 = response.data[0]
        assert sprint_1["project_ids"] == sorted([str(p1.id), str(p2.id)])
        assert sprint_1["start_date"] is not None and sprint_1["end_date"] is not None
        assert response.data[1]["project_ids"] == [str(p2.id)]

    @pytest.mark.django_db
    def test_cycles_follow_project_membership(self, workspace, board, guest, member):
        p1, _, _ = board["projects"]
        url = CYCLES_URL.format(slug=workspace.slug, pk=board["category"].id)
        response = _client(guest).get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == [
            {
                "name": "Sprint 1",
                "start_date": response.data[0]["start_date"],
                "end_date": response.data[0]["end_date"],
                "project_ids": [str(p1.id)],
            }
        ]
        assert _client(member).get(url).data == []


@pytest.mark.contract
class TestCategoryBoardViewLink:
    @pytest.mark.django_db
    def test_views_api_cannot_write_category(self, session_client, workspace, other_workspace):
        own = ProjectCategory.objects.create(workspace=workspace, name="Own")
        foreign = ProjectCategory.objects.create(workspace=other_workspace, name="Foreign")
        url = f"/api/workspaces/{workspace.slug}/views/"
        response = session_client.post(url, {"name": "Board", "category": str(foreign.id)}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        view = IssueView.objects.get(pk=response.data["id"])
        assert view.category_id is None
        response = session_client.patch(f"{url}{view.id}/", {"category": str(own.id)}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        view.refresh_from_db()
        assert view.category_id is None
