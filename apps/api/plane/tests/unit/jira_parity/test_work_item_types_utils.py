# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity work item types: seeding, defaults and hierarchy rules (plane.utils.work_item_types)."""

import uuid

import pytest

from plane.db.models import DraftIssue, Issue, IssueType, Project, ProjectIssueType, Workspace
from plane.utils import work_item_types as wit
from plane.utils.jira_parity.project_hooks import run_project_created_hooks


@pytest.fixture
def project(db, workspace, create_user):
    return Project.objects.create(name="Alpha", identifier="ALP", workspace=workspace, created_by=create_user)


@pytest.fixture
def other_workspace(db, create_user):
    return Workspace.objects.create(name="Other", owner=create_user, slug="other-workspace")


def _types(workspace):
    return {t.name: t for t in IssueType.objects.filter(workspace=workspace)}


def _issue(project, name, issue_type=None, parent=None):
    return Issue.objects.create(name=name, project=project, workspace=project.workspace, type=issue_type, parent=parent)


@pytest.mark.unit
class TestEnsureWorkspaceWorkItemTypes:
    @pytest.mark.django_db
    def test_creates_the_five_standard_types(self, workspace):
        result = wit.ensure_workspace_work_item_types(workspace)

        assert [t.name for t in result] == ["Task", "Story", "Bug", "Sub-task", "Epic"]
        types = _types(workspace)
        assert set(types) == {"Task", "Story", "Bug", "Sub-task", "Epic"}
        assert [name for name, t in types.items() if t.is_default] == ["Task"]
        assert types["Epic"].is_epic and types["Epic"].level == 1 and not types["Epic"].is_sub_task
        assert types["Sub-task"].is_sub_task and types["Sub-task"].level == -1 and not types["Sub-task"].is_epic
        for name in ("Task", "Story", "Bug"):
            assert not types[name].is_epic and not types[name].is_sub_task and types[name].level == 0
        assert all(t.is_active for t in types.values())
        colors = {name: t.logo_props["icon"]["color"] for name, t in types.items()}
        assert colors == {
            "Task": "#4BADE8",
            "Story": "#E97F33",
            "Bug": "#E5493A",
            "Sub-task": "#4BADE8",
            "Epic": "#904EE2",
        }
        assert types["Task"].logo_props == {
            "in_use": "icon",
            "icon": {"name": "check_box", "color": "#4BADE8", "background_color": "#4BADE8"},
        }
        assert types["Story"].logo_props["icon"]["name"] == "priority"  # exclamation-in-box glyph

    @pytest.mark.django_db
    def test_idempotent_and_keeps_user_edits(self, workspace):
        wit.ensure_workspace_work_item_types(workspace)
        bug = IssueType.objects.get(workspace=workspace, name="Bug")
        bug.description = "Custom"
        bug.logo_props = {"in_use": "icon", "icon": {"name": "pest_control", "color": "#000000"}}
        bug.save()
        IssueType.objects.filter(workspace=workspace, name="Story").update(is_active=False)

        wit.ensure_workspace_work_item_types(workspace)

        assert IssueType.objects.filter(workspace=workspace).count() == 5
        bug.refresh_from_db()
        assert bug.description == "Custom"
        assert bug.logo_props["icon"]["name"] == "pest_control"
        assert IssueType.objects.get(workspace=workspace, name="Story").is_active is False

    @pytest.mark.django_db
    def test_renamed_flagged_types_are_not_duplicated(self, workspace):
        wit.ensure_workspace_work_item_types(workspace)
        IssueType.objects.filter(workspace=workspace, name="Epic").update(name="Initiative")
        IssueType.objects.filter(workspace=workspace, name="Sub-task").update(name="Child")
        IssueType.objects.filter(workspace=workspace, name="Task").update(name="Chore")

        wit.ensure_workspace_work_item_types(workspace)

        assert set(_types(workspace)) == {"Chore", "Story", "Bug", "Child", "Initiative"}

    @pytest.mark.django_db
    def test_repairs_flags_and_keeps_a_single_valid_default(self, workspace):
        IssueType.objects.create(workspace=workspace, name="epic", is_default=True)
        IssueType.objects.create(workspace=workspace, name="Story", is_default=True)

        wit.ensure_workspace_work_item_types(workspace)

        types = _types(workspace)
        assert set(types) == {"Task", "Story", "Bug", "Sub-task", "epic"}
        assert types["epic"].is_epic and types["epic"].level == 1 and not types["epic"].is_default
        # an existing valid default wins over Task
        assert [name for name, t in types.items() if t.is_default] == ["Story"]

    @pytest.mark.django_db
    def test_workspace_without_types_gets_task_default_lazily(self, workspace):
        default_type = wit.get_default_type(workspace)
        assert default_type.name == "Task"
        assert IssueType.objects.filter(workspace=workspace).count() == 5
        # no lazy seeding when seeding is disabled
        assert wit.get_default_type(uuid.uuid4(), seed=False) is None


@pytest.mark.unit
class TestProjectSeeding:
    @pytest.mark.django_db
    def test_seed_project_links_every_type_and_enables_types(self, workspace, project):
        wit.ensure_workspace_work_item_types(workspace)
        custom = IssueType.objects.create(workspace=workspace, name="Spike")

        wit.seed_project_work_item_types(project)
        wit.seed_project_work_item_types(project)

        links = ProjectIssueType.objects.filter(project=project)
        assert links.count() == 6
        assert links.filter(issue_type=custom).exists()
        assert list(links.filter(is_default=True).values_list("issue_type__name", flat=True)) == ["Task"]
        project.refresh_from_db()
        assert project.is_issue_type_enabled is True

    @pytest.mark.django_db
    def test_seed_project_seeds_types_for_an_empty_workspace(self, workspace, project):
        wit.seed_project_work_item_types(project)
        assert ProjectIssueType.objects.filter(project=project).count() == 5

    @pytest.mark.django_db
    def test_seed_project_does_not_resurrect_deleted_standard_types(self, workspace, project):
        wit.ensure_workspace_work_item_types(workspace)
        IssueType.objects.get(workspace=workspace, name="Story").delete()

        wit.seed_project_work_item_types(project)

        assert not IssueType.objects.filter(workspace=workspace, name="Story").exists()
        assert ProjectIssueType.objects.filter(project=project).count() == 4

    @pytest.mark.django_db
    def test_project_created_hook_runs_the_types_seed(self, workspace, project, create_user):
        results = run_project_created_hooks(project, create_user)
        assert results["work_item_types"] is True
        assert ProjectIssueType.objects.filter(project=project).count() == 5

    @pytest.mark.django_db
    def test_sync_workspace_links_projects_and_backfills(self, workspace, project):
        issue = _issue(project, "Legacy")
        Issue.all_objects.filter(pk=issue.pk).update(type=None)
        draft = DraftIssue.objects.create(name="Draft", workspace=workspace, project=project)
        DraftIssue.all_objects.filter(pk=draft.pk).update(type=None)

        summary = wit.sync_workspace_work_item_types(workspace)

        assert summary["types"] == ["Task", "Story", "Bug", "Sub-task", "Epic"]
        assert summary["backfilled"] == {"issues": 1, "draft_issues": 1}
        issue.refresh_from_db()
        assert issue.type.name == "Task"
        assert ProjectIssueType.objects.filter(project=project).count() == 5
        # idempotent
        again = wit.sync_workspace_work_item_types(workspace)
        assert again["project_links_created"] == 0
        assert again["backfilled"] == {"issues": 0, "draft_issues": 0}


@pytest.mark.unit
class TestIssueDefaultType:
    @pytest.mark.django_db
    def test_new_issue_without_type_gets_the_workspace_default(self, workspace, project):
        issue = _issue(project, "No type")
        assert issue.type.name == "Task"
        assert issue.type.workspace_id == workspace.id

    @pytest.mark.django_db
    def test_explicit_type_is_kept_and_updates_do_not_reassign(self, workspace, project):
        types = {t.name: t for t in wit.ensure_workspace_work_item_types(workspace)}
        issue = _issue(project, "Bug", issue_type=types["Bug"])
        assert issue.type_id == types["Bug"].id

        Issue.all_objects.filter(pk=issue.pk).update(type=None)
        issue.refresh_from_db()
        issue.name = "Renamed"
        issue.save()
        issue.refresh_from_db()
        assert issue.type_id is None  # default only applies to new work items


@pytest.mark.unit
class TestIssueTypeRules:
    @pytest.fixture
    def types(self, workspace):
        return {t.name: t for t in wit.ensure_workspace_work_item_types(workspace)}

    @pytest.mark.django_db
    def test_create_without_type_uses_default(self, workspace, types):
        attrs = wit.validate_issue_type_and_parent({"name": "x"}, workspace_id=workspace.id)
        assert attrs["type"].id == types["Task"].id

    @pytest.mark.django_db
    def test_create_with_null_type_uses_default(self, workspace, project, types):
        attrs = wit.validate_issue_type_and_parent({"type": None}, project_id=project.id)
        assert attrs["type"].id == types["Task"].id

    @pytest.mark.django_db
    def test_sub_task_requires_a_parent(self, workspace, types):
        with pytest.raises(wit.WorkItemTypeRuleError) as exc:
            wit.validate_issue_type_and_parent({"type": types["Sub-task"]}, workspace_id=workspace.id)
        assert exc.value.field == "parent_id"
        assert exc.value.rule_code == wit.SUB_TASK_REQUIRES_PARENT
        assert exc.value.message_dict["parent_id"] == [wit.MSG_SUB_TASK_REQUIRES_PARENT]

    @pytest.mark.django_db
    @pytest.mark.parametrize("parent_type", ["Task", "Story", "Bug", "Epic"])
    def test_sub_task_under_non_sub_task_is_ok(self, workspace, project, types, parent_type):
        parent = _issue(project, "parent", issue_type=types[parent_type])
        attrs = wit.validate_issue_type_and_parent(
            {"type": types["Sub-task"], "parent": parent}, workspace_id=workspace.id
        )
        assert attrs["type"].id == types["Sub-task"].id

    @pytest.mark.django_db
    @pytest.mark.parametrize("child_type", ["Task", "Story", "Bug", "Sub-task", "Epic"])
    def test_nothing_can_be_a_child_of_a_sub_task(self, workspace, project, types, child_type):
        top = _issue(project, "top", issue_type=types["Task"])
        sub_task = _issue(project, "sub", issue_type=types["Sub-task"], parent=top)
        with pytest.raises(wit.WorkItemTypeRuleError) as exc:
            wit.validate_issue_type_and_parent(
                {"type": types[child_type], "parent": sub_task}, workspace_id=workspace.id
            )
        assert exc.value.rule_code == wit.SUB_TASK_CANNOT_BE_PARENT

    @pytest.mark.django_db
    def test_epic_and_standard_parents_are_allowed(self, workspace, project, types):
        epic = _issue(project, "epic", issue_type=types["Epic"])
        task = _issue(project, "task", issue_type=types["Task"])
        wit.validate_issue_type_and_parent({"type": types["Story"], "parent": epic}, workspace_id=workspace.id)
        wit.validate_issue_type_and_parent({"type": types["Epic"], "parent": task}, workspace_id=workspace.id)
        wit.validate_issue_type_and_parent({"parent": epic}, workspace_id=workspace.id)

    @pytest.mark.django_db
    def test_type_from_another_workspace_is_rejected(self, workspace, other_workspace, types):
        foreign = wit.ensure_workspace_work_item_types(other_workspace)[0]
        with pytest.raises(wit.WorkItemTypeRuleError) as exc:
            wit.validate_issue_type_and_parent({"type": foreign}, workspace_id=workspace.id)
        assert exc.value.field == "type_id"
        assert exc.value.rule_code == wit.INVALID_WORK_ITEM_TYPE

    @pytest.mark.django_db
    def test_inactive_type_cannot_be_newly_set_but_can_be_kept(self, workspace, project, types):
        story = types["Story"]
        issue = _issue(project, "story", issue_type=story)
        IssueType.objects.filter(pk=story.pk).update(is_active=False)
        story.refresh_from_db()

        with pytest.raises(wit.WorkItemTypeRuleError) as exc:
            wit.validate_issue_type_and_parent({"type": story}, workspace_id=workspace.id)
        assert exc.value.rule_code == wit.WORK_ITEM_TYPE_INACTIVE

        issue.refresh_from_db()
        attrs = wit.validate_issue_type_and_parent({"type": story, "name": "x"}, instance=issue)
        assert attrs["type"].id == story.id

    @pytest.mark.django_db
    def test_update_null_type_is_ignored(self, project, types):
        issue = _issue(project, "bug", issue_type=types["Bug"])
        attrs = wit.validate_issue_type_and_parent({"type": None, "name": "y"}, instance=issue)
        assert "type" not in attrs

    @pytest.mark.django_db
    def test_update_removing_the_parent_of_a_sub_task_is_rejected(self, project, types):
        top = _issue(project, "top", issue_type=types["Story"])
        sub_task = _issue(project, "sub", issue_type=types["Sub-task"], parent=top)
        with pytest.raises(wit.WorkItemTypeRuleError) as exc:
            wit.validate_issue_type_and_parent({"parent": None}, instance=sub_task)
        assert exc.value.rule_code == wit.SUB_TASK_REQUIRES_PARENT

    @pytest.mark.django_db
    def test_update_to_sub_task_requires_parent_and_no_children(self, project, types):
        top = _issue(project, "top", issue_type=types["Story"])
        _issue(project, "child", issue_type=types["Task"], parent=top)
        epic = _issue(project, "epic", issue_type=types["Epic"])

        with pytest.raises(wit.WorkItemTypeRuleError) as exc:
            wit.validate_issue_type_and_parent({"type": types["Sub-task"], "parent": epic}, instance=top)
        assert exc.value.field == "type_id"
        assert exc.value.rule_code == wit.SUB_TASK_CANNOT_BE_PARENT

        lone = _issue(project, "lone", issue_type=types["Task"])
        with pytest.raises(wit.WorkItemTypeRuleError):
            wit.validate_issue_type_and_parent({"type": types["Sub-task"]}, instance=lone)
        wit.validate_issue_type_and_parent({"type": types["Sub-task"], "parent": epic}, instance=lone)

    @pytest.mark.django_db
    def test_unrelated_update_of_a_legacy_invalid_row_is_not_blocked(self, project, types):
        orphan_sub_task = _issue(project, "legacy", issue_type=types["Task"])
        Issue.all_objects.filter(pk=orphan_sub_task.pk).update(type=types["Sub-task"])
        orphan_sub_task.refresh_from_db()
        # same type + same (null) parent in the payload: nothing changed, no hierarchy check
        attrs = wit.validate_issue_type_and_parent(
            {"name": "renamed", "type": types["Sub-task"], "parent": None}, instance=orphan_sub_task
        )
        assert attrs["name"] == "renamed"

    @pytest.mark.django_db
    def test_type_name_is_resolved_case_insensitively(self, workspace, types):
        attrs = wit.validate_issue_type_and_parent({"type_name": " bug "}, workspace_id=workspace.id)
        assert attrs["type"].id == types["Bug"].id
        assert "type_name" not in attrs
        with pytest.raises(wit.WorkItemTypeRuleError) as exc:
            wit.validate_issue_type_and_parent({"type_name": "Nope"}, workspace_id=workspace.id)
        assert exc.value.field == "type_name"

    @pytest.mark.django_db
    def test_parent_can_have_children_and_epic_helpers(self, project, types):
        top = _issue(project, "top", issue_type=types["Epic"])
        sub_task_parent = _issue(project, "story", issue_type=types["Story"], parent=top)
        sub_task = _issue(project, "sub", issue_type=types["Sub-task"], parent=sub_task_parent)
        wit.validate_parent_can_have_children(top)
        with pytest.raises(wit.WorkItemTypeRuleError) as exc:
            wit.validate_parent_can_have_children(sub_task)
        assert exc.value.as_response_data()["code"] == wit.SUB_TASK_CANNOT_BE_PARENT
        assert wit.is_epic_issue(top) and not wit.is_epic_issue(sub_task)
        assert wit.is_sub_task_issue(sub_task) and not wit.is_sub_task_issue(top)


@pytest.mark.unit
class TestSerializerHelpers:
    def test_normalize_type_name_input(self):
        type_id = str(uuid.uuid4())
        assert wit.normalize_type_name_input({"type": "Bug", "name": "x"}) == {"type_name": "Bug", "name": "x"}
        assert wit.normalize_type_name_input({"type": type_id}) == {"type": type_id}
        assert wit.normalize_type_name_input({"type_name": "Epic"}) == {"type_name": "Epic"}
        assert wit.normalize_type_name_input([1, 2]) == [1, 2]

    def test_type_level(self):
        assert wit.type_level(True, False) == 1
        assert wit.type_level(False, True) == -1
        assert wit.type_level(False, False) == 0

    def test_legacy_issue_type_list_filter(self):
        from plane.utils.issue_filters import issue_filters

        type_id = uuid.uuid4()
        # string ids: stored (POST) view queries are JSON
        assert issue_filters({"issue_type": f"{type_id},not-a-uuid"}, "GET") == {"type_id__in": [str(type_id)]}
        assert issue_filters({"issue_type": "None"}, "GET") == {"type__isnull": True}
        assert issue_filters({"issue_type": [str(type_id)]}, "POST", prefix="issue__") == {
            "issue__type_id__in": [str(type_id)]
        }
        assert issue_filters({"issue_type": ""}, "GET") == {}

    @pytest.mark.django_db
    def test_v1_query_filter_helper(self, workspace, project):
        types = {t.name: t for t in wit.ensure_workspace_work_item_types(workspace)}
        bug = _issue(project, "bug", issue_type=types["Bug"])
        _issue(project, "task", issue_type=types["Task"])
        queryset = Issue.objects.filter(project=project)

        assert wit.filter_issues_by_work_item_type(queryset, {}) is queryset
        assert list(wit.filter_issues_by_work_item_type(queryset, {"type": "BUG"})) == [bug]
        assert list(wit.filter_issues_by_work_item_type(queryset, {"type_id": str(types["Bug"].id)})) == [bug]
        assert not wit.filter_issues_by_work_item_type(queryset, {"type_name": "Nope"}).exists()

    @pytest.mark.django_db
    def test_draft_type_scoping(self, workspace, other_workspace):
        own = wit.ensure_workspace_work_item_types(workspace)[0]
        foreign = wit.ensure_workspace_work_item_types(other_workspace)[0]
        assert wit.validate_draft_work_item_type({"type": own}, workspace_id=workspace.id)["type"] == own
        assert wit.validate_draft_work_item_type({"type": None}, workspace_id=workspace.id) == {"type": None}
        with pytest.raises(wit.WorkItemTypeRuleError):
            wit.validate_draft_work_item_type({"type": foreign}, workspace_id=workspace.id)
