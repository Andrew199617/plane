# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity work item types: internal CRUD endpoints, issue payloads/writes (app + v1)."""

import json
import uuid
from unittest import mock

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    DraftIssue,
    Issue,
    IssueActivity,
    IssueType,
    Project,
    ProjectIssueType,
    ProjectMember,
    State,
    User,
    Workspace,
    WorkspaceMember,
)
from plane.utils.work_item_types import ensure_workspace_work_item_types, seed_project_work_item_types

CONTRACT_KEYS = {
    "id",
    "name",
    "description",
    "logo_props",
    "is_epic",
    "is_sub_task",
    "is_default",
    "is_active",
    "level",
    "workspace_id",
}


@pytest.fixture(autouse=True)
def _reset_api_key_throttle_cache():
    cache.delete_pattern("api_key:*")
    yield
    cache.delete_pattern("api_key:*")


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Alpha", identifier="ALP", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    State.objects.create(name="To Do", project=project, workspace=workspace, group="unstarted", default=True)
    return project


@pytest.fixture
def types(workspace, project):
    types = {t.name: t for t in ensure_workspace_work_item_types(workspace)}
    # what run_project_created_hooks does for projects created through the API
    seed_project_work_item_types(project)
    return types


@pytest.fixture
def member_client(db, workspace, project):
    member = User.objects.create(
        email="member@plane.so", username=f"member_{uuid.uuid4().hex[:8]}", first_name="Mem", last_name="Ber"
    )
    WorkspaceMember.objects.create(workspace=workspace, member=member, role=15)
    ProjectMember.objects.create(project=project, member=member, role=15, is_active=True)
    client = APIClient()
    client.force_authenticate(user=member)
    return client


def _types_url(slug, pk=None):
    return f"/api/workspaces/{slug}/work-item-types/" + (f"{pk}/" if pk else "")


def _issues_url(slug, project_id, pk=None):
    return f"/api/workspaces/{slug}/projects/{project_id}/issues/" + (f"{pk}/" if pk else "")


def _make_issue(project, name, issue_type, parent=None):
    return Issue.objects.create(name=name, project=project, workspace=project.workspace, type=issue_type, parent=parent)


# ---------------------------------------------------------------- type CRUD


@pytest.mark.contract
class TestWorkItemTypeEndpoints:
    @pytest.mark.django_db
    def test_list_lazily_seeds_and_matches_contract(self, session_client, workspace):
        response = session_client.get(_types_url(workspace.slug))

        assert response.status_code == status.HTTP_200_OK, response.data
        assert [t["name"] for t in response.data] == ["Epic", "Bug", "Story", "Task", "Sub-task"]
        for item in response.data:
            assert CONTRACT_KEYS <= set(item)
            assert item["workspace_id"] == workspace.id or str(item["workspace_id"]) == str(workspace.id)
            assert item["issue_count"] == 0
        assert [t["name"] for t in response.data if t["is_default"]] == ["Task"]

    @pytest.mark.django_db
    def test_members_can_read_but_not_write(self, member_client, workspace, types):
        assert member_client.get(_types_url(workspace.slug)).status_code == status.HTTP_200_OK
        assert member_client.get(_types_url(workspace.slug, types["Bug"].id)).status_code == status.HTTP_200_OK
        response = member_client.post(_types_url(workspace.slug), {"name": "Spike"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        response = member_client.patch(_types_url(workspace.slug, types["Bug"].id), {"name": "x"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        response = member_client.delete(_types_url(workspace.slug, types["Bug"].id))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_admin_creates_a_type_enabled_in_every_project(self, session_client, workspace, project, types):
        logo = {"in_use": "icon", "icon": {"name": "science", "color": "#00875A"}}
        response = session_client.post(
            _types_url(workspace.slug),
            {"name": " Spike ", "description": "Research", "logo_props": logo},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["name"] == "Spike"
        assert response.data["level"] == 0
        assert response.data["is_default"] is False
        assert response.data["logo_props"] == logo
        assert ProjectIssueType.objects.filter(project=project, issue_type_id=response.data["id"]).exists()

    @pytest.mark.django_db
    def test_create_validation(self, session_client, workspace, types):
        duplicate = session_client.post(_types_url(workspace.slug), {"name": "task"}, format="json")
        assert duplicate.status_code == status.HTTP_400_BAD_REQUEST
        assert "name" in duplicate.data

        both = session_client.post(
            _types_url(workspace.slug), {"name": "Weird", "is_epic": True, "is_sub_task": True}, format="json"
        )
        assert both.status_code == status.HTTP_400_BAD_REQUEST

        missing = session_client.post(_types_url(workspace.slug), {"description": "no name"}, format="json")
        assert missing.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_create_sub_task_type_derives_level(self, session_client, workspace, types):
        response = session_client.post(
            _types_url(workspace.slug), {"name": "Checklist item", "is_sub_task": True}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["level"] == -1

    @pytest.mark.django_db
    def test_default_type_rules(self, session_client, workspace, project, types):
        task_url = _types_url(workspace.slug, types["Task"].id)
        assert session_client.patch(task_url, {"is_active": False}, format="json").status_code == 400
        assert session_client.patch(task_url, {"is_default": False}, format="json").status_code == 400
        sub_task_url = _types_url(workspace.slug, types["Sub-task"].id)
        assert session_client.patch(sub_task_url, {"is_default": True}, format="json").status_code == 400

        response = session_client.patch(
            _types_url(workspace.slug, types["Bug"].id), {"is_default": True}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["is_default"] is True
        assert list(IssueType.objects.filter(workspace=workspace, is_default=True).values_list("name", flat=True)) == [
            "Bug"
        ]
        project_defaults = ProjectIssueType.objects.filter(project=project, is_default=True)
        assert list(project_defaults.values_list("issue_type__name", flat=True)) == ["Bug"]

    @pytest.mark.django_db
    def test_patch_updates_editable_fields(self, session_client, workspace, types):
        response = session_client.patch(
            _types_url(workspace.slug, types["Story"].id),
            {"name": "User story", "is_active": False, "level": 7},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["name"] == "User story"
        assert response.data["is_active"] is False
        assert response.data["level"] == 0  # derived from the flags

    @pytest.mark.django_db
    def test_sub_task_flag_is_locked_while_in_use(self, session_client, workspace, project, types):
        _make_issue(project, "bug", types["Bug"])
        response = session_client.patch(
            _types_url(workspace.slug, types["Bug"].id), {"is_sub_task": True}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "is_sub_task" in response.data

    @pytest.mark.django_db
    def test_delete_rules(self, session_client, workspace, project, types):
        default = session_client.delete(_types_url(workspace.slug, types["Task"].id))
        assert default.status_code == status.HTTP_400_BAD_REQUEST
        assert default.data["code"] == "WORK_ITEM_TYPE_IS_DEFAULT"

        _make_issue(project, "bug", types["Bug"])
        in_use = session_client.delete(_types_url(workspace.slug, types["Bug"].id))
        assert in_use.status_code == status.HTTP_400_BAD_REQUEST
        assert in_use.data["code"] == "WORK_ITEM_TYPE_IN_USE"

        ok = session_client.delete(_types_url(workspace.slug, types["Story"].id))
        assert ok.status_code == status.HTTP_204_NO_CONTENT
        assert not IssueType.objects.filter(pk=types["Story"].id).exists()
        assert not ProjectIssueType.objects.filter(issue_type_id=types["Story"].id).exists()
        names = [t["name"] for t in session_client.get(_types_url(workspace.slug)).data]
        assert "Story" not in names
        # the name can be reused after a delete
        again = session_client.post(_types_url(workspace.slug), {"name": "Story"}, format="json")
        assert again.status_code == status.HTTP_201_CREATED, again.data

    @pytest.mark.django_db
    def test_unknown_type_is_404(self, session_client, workspace, types):
        other = Workspace.objects.create(name="Other", owner=workspace.owner, slug="other-ws")
        foreign = ensure_workspace_work_item_types(other)[0]
        assert session_client.get(_types_url(workspace.slug, foreign.id)).status_code == 404
        assert (
            session_client.patch(_types_url(workspace.slug, foreign.id), {"name": "x"}, format="json").status_code
            == 404
        )

    @pytest.mark.django_db
    def test_project_list_returns_active_enabled_types_and_self_heals(self, session_client, workspace, project, types):
        IssueType.objects.filter(pk=types["Story"].id).update(is_active=False)
        url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/work-item-types/"

        response = session_client.get(url)

        assert response.status_code == status.HTTP_200_OK, response.data
        assert sorted(t["name"] for t in response.data) == ["Bug", "Epic", "Sub-task", "Task"]
        assert ProjectIssueType.objects.filter(project=project).count() == 5
        project.refresh_from_db()
        assert project.is_issue_type_enabled is True


# ---------------------------------------------------------------- app issue payloads & writes


@pytest.mark.contract
class TestAppIssueTypeWrites:
    @pytest.mark.django_db
    def test_create_defaults_to_task_and_returns_type_id(self, session_client, workspace, project, types):
        response = session_client.post(_issues_url(workspace.slug, project.id), {"name": "No type"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert str(response.data["type_id"]) == str(types["Task"].id)

    @pytest.mark.django_db
    def test_create_with_type_id(self, session_client, workspace, project, types):
        response = session_client.post(
            _issues_url(workspace.slug, project.id), {"name": "Bug", "type_id": str(types["Bug"].id)}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert Issue.objects.get(pk=response.data["id"]).type_id == types["Bug"].id

    @pytest.mark.django_db
    def test_sub_task_rules_on_create(self, session_client, workspace, project, types):
        url = _issues_url(workspace.slug, project.id)
        orphan = session_client.post(url, {"name": "Sub", "type_id": str(types["Sub-task"].id)}, format="json")
        assert orphan.status_code == status.HTTP_400_BAD_REQUEST
        assert "parent_id" in orphan.data
        assert orphan.data["code"] == ["SUB_TASK_REQUIRES_PARENT"]

        parent = _make_issue(project, "Parent", types["Task"])
        ok = session_client.post(
            url, {"name": "Sub", "type_id": str(types["Sub-task"].id), "parent_id": str(parent.id)}, format="json"
        )
        assert ok.status_code == status.HTTP_201_CREATED, ok.data

        under_sub_task = session_client.post(
            url, {"name": "Child", "type_id": str(types["Task"].id), "parent_id": ok.data["id"]}, format="json"
        )
        assert under_sub_task.status_code == status.HTTP_400_BAD_REQUEST
        assert under_sub_task.data["code"] == ["SUB_TASK_CANNOT_BE_PARENT"]

    @pytest.mark.django_db
    def test_patch_rules(self, session_client, workspace, project, types):
        parent = _make_issue(project, "Parent", types["Story"])
        sub_task = _make_issue(project, "Sub", types["Sub-task"], parent=parent)
        url = _issues_url(workspace.slug, project.id, sub_task.id)

        assert session_client.patch(url, {"parent_id": None}, format="json").status_code == 400

        other = Workspace.objects.create(name="Other", owner=workspace.owner, slug="other-ws")
        foreign = ensure_workspace_work_item_types(other)[1]
        response = session_client.patch(url, {"type_id": str(foreign.id)}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "type_id" in response.data

        assert session_client.patch(url, {"type_id": None, "name": "Renamed"}, format="json").status_code == 204
        sub_task.refresh_from_db()
        assert sub_task.type_id == types["Sub-task"].id and sub_task.name == "Renamed"

        assert session_client.patch(url, {"type_id": str(types["Task"].id)}, format="json").status_code == 204
        sub_task.refresh_from_db()
        assert sub_task.type_id == types["Task"].id

        # Story with children cannot become a Sub-task
        story_url = _issues_url(workspace.slug, project.id, parent.id)
        response = session_client.patch(story_url, {"type_id": str(types["Sub-task"].id)}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_list_detail_and_group_by_type(self, session_client, workspace, project, types):
        bug = _make_issue(project, "Bug", types["Bug"])
        task = _make_issue(project, "Task", types["Task"])
        url = _issues_url(workspace.slug, project.id)

        detail = session_client.get(_issues_url(workspace.slug, project.id, bug.id))
        assert detail.status_code == status.HTTP_200_OK, detail.data
        assert str(detail.data["type_id"]) == str(types["Bug"].id)

        listing = session_client.get(url)
        assert listing.status_code == status.HTTP_200_OK, listing.data
        by_id = {str(i["id"]): str(i["type_id"]) for i in listing.data["results"]}
        assert by_id == {str(bug.id): str(types["Bug"].id), str(task.id): str(types["Task"].id)}

        grouped = session_client.get(url, {"group_by": "type_id"})
        assert grouped.status_code == status.HTTP_200_OK, grouped.data
        groups = grouped.data["results"]
        assert {str(types["Bug"].id), str(types["Task"].id), "None"} <= {str(k) for k in groups}
        assert groups[str(types["Bug"].id)]["total_results"] == 1

    @pytest.mark.django_db
    def test_sub_issue_add_under_a_sub_task_is_rejected(self, session_client, workspace, project, types):
        parent = _make_issue(project, "Parent", types["Task"])
        sub_task = _make_issue(project, "Sub", types["Sub-task"], parent=parent)
        loose = _make_issue(project, "Loose", types["Task"])
        url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{sub_task.id}/sub-issues/"

        response = session_client.post(url, {"sub_issue_ids": [str(loose.id)]}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "SUB_TASK_CANNOT_BE_PARENT"
        loose.refresh_from_db()
        assert loose.parent_id is None

        ok = session_client.post(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{parent.id}/sub-issues/",
            {"sub_issue_ids": [str(loose.id)]},
            format="json",
        )
        assert ok.status_code == status.HTTP_200_OK, ok.data


@pytest.mark.contract
class TestAppIssueTypeQueries:
    @pytest.fixture
    def issues(self, project, types):
        return {
            "bug": _make_issue(project, "B item", types["Bug"]),
            "task": _make_issue(project, "T item", types["Task"]),
            "epic": _make_issue(project, "E item", types["Epic"]),
        }

    @staticmethod
    def _ids(response):
        assert response.status_code == status.HTTP_200_OK, response.data
        return [str(item["id"]) for item in response.data["results"]]

    @pytest.mark.django_db
    def test_rich_filter_type_id(self, session_client, workspace, project, types, issues):
        url = _issues_url(workspace.slug, project.id)
        only_bug = session_client.get(url, {"filters": json.dumps({"type_id__in": str(types["Bug"].id)})})
        assert self._ids(only_bug) == [str(issues["bug"].id)]

        two = session_client.get(url, {"filters": json.dumps({"type_id__in": f"{types['Bug'].id},{types['Epic'].id}"})})
        assert set(self._ids(two)) == {str(issues["bug"].id), str(issues["epic"].id)}

        exact = session_client.get(url, {"filters": json.dumps({"type_id": str(types["Task"].id)})})
        assert self._ids(exact) == [str(issues["task"].id)]

    @pytest.mark.django_db
    def test_legacy_issue_type_param(self, session_client, workspace, project, types, issues):
        url = _issues_url(workspace.slug, project.id)
        assert self._ids(session_client.get(url, {"issue_type": str(types["Epic"].id)})) == [str(issues["epic"].id)]
        Issue.all_objects.filter(pk=issues["task"].pk).update(type=None)
        assert self._ids(session_client.get(url, {"issue_type": "None"})) == [str(issues["task"].id)]

    @pytest.mark.django_db
    def test_group_page_for_one_type(self, session_client, workspace, project, types, issues):
        # per-group "load more": group_by is dropped, the group's id is sent as issue_type and the
        # cursor asks for the group's next page (`<per_page>:1:0`)
        second_bug = _make_issue(project, "B2 item", types["Bug"])
        url = _issues_url(workspace.slug, project.id)
        first = self._ids(
            session_client.get(url, {"issue_type": str(types["Bug"].id), "cursor": "1:0:0", "per_page": 1})
        )
        second = self._ids(
            session_client.get(url, {"issue_type": str(types["Bug"].id), "cursor": "1:1:0", "per_page": 1})
        )
        assert sorted(first + second) == sorted([str(issues["bug"].id), str(second_bug.id)])

    @pytest.mark.django_db
    def test_order_by_type_name(self, session_client, workspace, project, types, issues):
        url = _issues_url(workspace.slug, project.id)
        ascending = self._ids(session_client.get(url, {"order_by": "type__name"}))
        assert ascending == [str(issues["bug"].id), str(issues["epic"].id), str(issues["task"].id)]
        descending = self._ids(session_client.get(url, {"order_by": "-type__name"}))
        assert descending == list(reversed(ascending))

    @pytest.mark.django_db
    def test_archived_list_includes_epics(self, session_client, workspace, project, types, issues):
        done = State.objects.create(name="Done", project=project, workspace=workspace, group="completed")
        Issue.all_objects.filter(pk__in=[issues["epic"].pk, issues["bug"].pk]).update(
            state=done, archived_at=timezone.now()
        )
        url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/archived-issues/"
        assert set(self._ids(session_client.get(url))) == {str(issues["epic"].id), str(issues["bug"].id)}

    @pytest.mark.django_db
    def test_draft_keeps_a_workspace_scoped_type(self, session_client, workspace, project, types):
        url = f"/api/workspaces/{workspace.slug}/draft-issues/"
        response = session_client.post(
            url, {"name": "Draft bug", "project_id": str(project.id), "type_id": str(types["Bug"].id)}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        draft = DraftIssue.objects.get(name="Draft bug")
        assert draft.type_id == types["Bug"].id

        other = Workspace.objects.create(name="Other", owner=workspace.owner, slug="other-ws")
        foreign = ensure_workspace_work_item_types(other)[2]
        response = session_client.post(
            url, {"name": "Bad draft", "project_id": str(project.id), "type_id": str(foreign.id)}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "type_id" in response.data

    @pytest.mark.django_db
    def test_workspace_creation_seeds_the_standard_types(self, session_client):
        with mock.patch("plane.app.views.workspace.base.workspace_seed.delay") as seed_delay:
            response = session_client.post("/api/workspaces/", {"name": "Fresh", "slug": "fresh-ws"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        seed_delay.assert_called_once()
        names = set(IssueType.objects.filter(workspace__slug="fresh-ws").values_list("name", flat=True))
        assert names == {"Task", "Story", "Bug", "Sub-task", "Epic"}


@pytest.mark.unit
class TestWorkItemTypeActivity:
    def _run(self, issue, requested, current, actor):
        from plane.bgtasks.issue_activities_task import update_issue_activity

        activities = []
        update_issue_activity(
            requested_data=json.dumps(requested),
            current_instance=json.dumps(current),
            issue_id=issue.id,
            project_id=issue.project_id,
            workspace_id=issue.workspace_id,
            actor_id=actor.id,
            issue_activities=activities,
            epoch=1.0,
        )
        return [activity for activity in activities if activity.field == "type"]

    @pytest.mark.django_db
    def test_type_change_is_recorded_once(self, project, types, create_user):
        issue = _make_issue(project, "Item", types["Task"])
        current = {"type_id": str(types["Task"].id)}

        (activity,) = self._run(issue, {"type_id": str(types["Bug"].id)}, current, create_user)
        assert (activity.old_value, activity.new_value) == ("Task", "Bug")
        assert activity.old_identifier == types["Task"].id and activity.new_identifier == types["Bug"].id
        assert activity.verb == "updated"

        # v1 payloads: name in `type` / `type_name` (several keys -> still one activity)
        both = self._run(issue, {"type": "epic", "type_name": "Epic"}, current, create_user)
        assert len(both) == 1 and both[0].new_value == "Epic"

    @pytest.mark.django_db
    def test_no_activity_without_a_change(self, project, types, create_user):
        issue = _make_issue(project, "Item", types["Task"])
        current = {"type_id": str(types["Task"].id)}
        assert self._run(issue, {"type_id": str(types["Task"].id)}, current, create_user) == []
        assert self._run(issue, {"type_id": None}, current, create_user) == []
        assert self._run(issue, {"name": "renamed"}, current, create_user) == []

    @pytest.mark.django_db
    def test_first_type_on_an_untyped_item(self, project, types, create_user):
        issue = _make_issue(project, "Item", types["Task"])
        (activity,) = self._run(issue, {"type_id": str(types["Story"].id)}, {"type_id": None}, create_user)
        assert activity.old_value is None and activity.new_value == "Story"
        IssueActivity.objects.bulk_create([activity])  # the model accepts the row as built


# ---------------------------------------------------------------- public API v1


@pytest.mark.contract
class TestV1IssueTypes:
    def _url(self, workspace, project, pk=None):
        return f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/issues/" + (f"{pk}/" if pk else "")

    @pytest.mark.django_db
    def test_create_by_type_name_and_type_alias(self, api_key_client, workspace, project, types):
        response = api_key_client.post(self._url(workspace, project), {"name": "a", "type_name": "bug"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert str(response.data["type_id"]) == str(types["Bug"].id)
        assert response.data["type_name"] == "Bug"

        response = api_key_client.post(self._url(workspace, project), {"name": "b", "type": "Epic"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert str(response.data["type_id"]) == str(types["Epic"].id)

        response = api_key_client.post(self._url(workspace, project), {"name": "c"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["type_name"] == "Task"

    @pytest.mark.django_db
    def test_v1_validation(self, api_key_client, workspace, project, types):
        unknown = api_key_client.post(self._url(workspace, project), {"name": "a", "type_name": "Nope"}, format="json")
        assert unknown.status_code == status.HTTP_400_BAD_REQUEST
        assert "type_name" in unknown.data

        orphan = api_key_client.post(
            self._url(workspace, project), {"name": "a", "type_id": str(types["Sub-task"].id)}, format="json"
        )
        assert orphan.status_code == status.HTTP_400_BAD_REQUEST

        other = Workspace.objects.create(name="Other", owner=workspace.owner, slug="other-ws")
        foreign = ensure_workspace_work_item_types(other)[2]
        response = api_key_client.post(
            self._url(workspace, project), {"name": "a", "type_id": str(foreign.id)}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_v1_patch_and_list_carry_type_name(self, api_key_client, workspace, project, types):
        parent = _make_issue(project, "Parent", types["Story"])
        issue = _make_issue(project, "Item", types["Task"])

        response = api_key_client.patch(
            self._url(workspace, project, issue.id),
            {"type_name": "Sub-task", "parent": str(parent.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        issue.refresh_from_db()
        assert issue.type_id == types["Sub-task"].id and issue.parent_id == parent.id

        listing = api_key_client.get(self._url(workspace, project))
        assert listing.status_code == status.HTTP_200_OK, listing.data
        names = {str(i["id"]): i["type_name"] for i in listing.data["results"]}
        assert names == {str(parent.id): "Story", str(issue.id): "Sub-task"}

    @pytest.mark.django_db
    def test_v1_list_filters_by_type(self, api_key_client, workspace, project, types):
        epic = _make_issue(project, "Epic", types["Epic"])
        bug = _make_issue(project, "Bug", types["Bug"])

        def ids(params):
            response = api_key_client.get(self._url(workspace, project), params)
            assert response.status_code == status.HTTP_200_OK, response.data
            return {str(item["id"]) for item in response.data["results"]}

        assert ids({"type": "epic"}) == {str(epic.id)}
        assert ids({"type_name": "Bug"}) == {str(bug.id)}
        assert ids({"type_id": str(types["Bug"].id)}) == {str(bug.id)}
        assert ids({"type": f"Epic,{types['Bug'].id}"}) == {str(epic.id), str(bug.id)}
        assert ids({"type": "Nope"}) == set()
        assert ids({}) == {str(epic.id), str(bug.id)}
