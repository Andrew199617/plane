# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Unit tests for the Jira-parity project categories helpers (plane.utils.project_categories),
the master-board legacy filters (plane.utils.issue_filters) and the state__name grouper values."""

import uuid
from datetime import datetime, timezone as dt_timezone

import pytest
from rest_framework import serializers

from plane.db.models import (
    Cycle,
    Project,
    ProjectCategory,
    ProjectMember,
    State,
    Workspace,
)
from plane.utils.grouper import issue_group_values
from plane.utils.issue_filters import issue_filters
from plane.utils.order_queryset import ISSUE_GROUP_BY_ALLOWLIST
from plane.utils.project_categories import (
    ProjectCategoryIdField,
    apply_category_mapping,
    category_cycles,
    category_group_by_allowlist,
    category_group_values,
    category_project_ids,
    delete_category,
    order_state_names,
    set_category_projects,
    state_name_group_values,
)


# ---------------------------------------------------------------- pure helpers


@pytest.mark.unit
class TestOrderStateNames:
    def test_standard_names_first_then_by_group_sequence_and_name(self):
        rows = [
            ("Done", "completed", 40000),
            ("QA", "started", 25000),
            ("To Do", "unstarted", 10000),
            ("Backlog", "backlog", 5000),
            ("In Review", "started", 30000),
            ("Won’t Fix", "cancelled", 50000),
            ("In Progress", "started", 20000),
            ("To Do", "unstarted", 99),  # same name in another project -> one column
            ("Blocked", "started", 25000),
            (None, "started", 1),
        ]
        assert order_state_names(rows) == [
            "To Do",
            "In Progress",
            "In Review",
            "Done",
            "Won’t Fix",
            "Backlog",
            "Blocked",
            "QA",
        ]

    def test_names_stay_exact(self):
        # Issues are grouped by the exact name, so differently spelled names are distinct columns
        assert order_state_names([("to do", "unstarted", 1), ("To Do", "unstarted", 2)]) == ["to do", "To Do"]

    def test_group_by_allowlist(self):
        allowed = category_group_by_allowlist()
        assert "state__name" in allowed
        assert "type_id" in allowed
        assert frozenset(ISSUE_GROUP_BY_ALLOWLIST) <= allowed
        assert "created_by__password" not in allowed
        # the shared allowlist itself is not widened
        assert "state__name" not in ISSUE_GROUP_BY_ALLOWLIST


@pytest.mark.unit
class TestMasterBoardIssueFilters:
    def test_state_name(self):
        assert issue_filters({"state_name": "To Do,In Review"}, "GET") == {"state__name__in": ["To Do", "In Review"]}
        assert issue_filters({"state_name": "null"}, "GET") == {}
        assert issue_filters({"state_name": ["Done"]}, "POST") == {"state__name__in": ["Done"]}

    def test_cycle_name(self):
        assert issue_filters({"cycle_name": "Sprint 1, Sprint 2"}, "GET") == {
            "issue_cycle__cycle__name__in": ["Sprint 1", "Sprint 2"],
            "issue_cycle__cycle__deleted_at__isnull": True,
            "issue_cycle__deleted_at__isnull": True,
        }
        assert issue_filters({"cycle_name": "None"}, "GET") == {
            "issue_cycle__cycle_id__isnull": True,
            "issue_cycle__deleted_at__isnull": True,
        }
        assert issue_filters({"cycle_name": ""}, "GET") == {}

    def test_project_category(self):
        category_id = uuid.uuid4()
        assert issue_filters({"project_category": f"{category_id},null,bad"}, "GET") == {
            "project__category_id__in": [category_id]
        }
        assert issue_filters({"project_category": "bad"}, "GET") == {}


# ---------------------------------------------------------------- DB helpers


@pytest.fixture
def other_workspace(db, create_user):
    return Workspace.objects.create(name="Other", owner=create_user, slug="other-workspace")


def _project(workspace, identifier, category=None, **extra):
    return Project.objects.create(
        name=f"Project {identifier}", identifier=identifier, workspace=workspace, category=category, **extra
    )


def _states(project, names):
    groups = {
        "To Do": "unstarted",
        "In Progress": "started",
        "In Review": "started",
        "Done": "completed",
        "Won't Fix": "cancelled",
        "Backlog": "backlog",
    }
    return {
        name: State.objects.create(
            name=name,
            project=project,
            workspace=project.workspace,
            group=groups.get(name, "started"),
            color="#000000",
            sequence=(index + 1) * 1000,
        )
        for index, name in enumerate(names)
    }


@pytest.mark.unit
class TestStateNameGroupValues:
    @pytest.mark.django_db
    def test_scoped_to_category_projects(self, workspace):
        game = ProjectCategory.objects.create(workspace=workspace, name="Game")
        p1 = _project(workspace, "AA", category=game)
        p2 = _project(workspace, "BB", category=game)
        outsider = _project(workspace, "CC")
        _states(p1, ["Done", "To Do", "In Progress"])
        _states(p2, ["To Do", "In Review", "Won't Fix", "QA"])
        _states(outsider, ["Outside"])
        State.objects.create(
            name="Triage", project=p1, workspace=workspace, group="triage", color="#000", is_triage=True
        )

        expected = ["To Do", "In Progress", "In Review", "Done", "Won't Fix", "QA"]
        assert state_name_group_values(slug=workspace.slug, project_ids=[p1.id, p2.id]) == expected
        assert state_name_group_values(slug=workspace.slug, filters={"project__category_id__in": [game.id]}) == expected
        # through the shared grouper entry point (legacy project_category filter)
        filters = issue_filters({"project_category": str(game.id)}, "GET")
        assert issue_group_values(field="state__name", slug=workspace.slug, filters=filters) == expected
        assert issue_group_values(field="state__name", slug=workspace.slug, project_id=outsider.id) == ["Outside"]
        assert "Outside" in issue_group_values(field="state__name", slug=workspace.slug)
        assert "Triage" not in issue_group_values(field="state__name", slug=workspace.slug)

    @pytest.mark.django_db
    def test_category_group_values_limits_project_groups(self, workspace, create_user):
        game = ProjectCategory.objects.create(workspace=workspace, name="Game")
        p1 = _project(workspace, "AA", category=game)
        outsider = _project(workspace, "CC")
        s1 = _states(p1, ["To Do"])["To Do"]
        _states(outsider, ["To Do"])
        cycle = Cycle.objects.create(name="Sprint 1", project=p1, workspace=workspace, owned_by=create_user)
        Cycle.objects.create(name="Sprint 1", project=outsider, workspace=workspace, owned_by=create_user)

        values = lambda field: category_group_values(field=field, slug=workspace.slug, project_ids=[p1.id])  # noqa: E731
        assert values("project_id") == [p1.id]
        assert values("state_id") == [s1.id]
        assert values("cycle_id") == [cycle.id, "None"]
        assert values("state__name") == ["To Do"]
        # delegated to the shared grouper
        assert values("state__group") == issue_group_values(field="state__group", slug=workspace.slug)


@pytest.mark.unit
class TestCategoryProjectsAndCycles:
    @pytest.mark.django_db
    def test_set_category_projects_replaces_active_projects(self, workspace):
        game = ProjectCategory.objects.create(workspace=workspace, name="Game")
        p1 = _project(workspace, "AA", category=game)
        p2 = _project(workspace, "BB")
        archived = _project(workspace, "CC", category=game, archived_at=datetime.now(dt_timezone.utc))

        set_category_projects(game, [p2.id])
        assert Project.objects.get(pk=p1.pk).category_id is None
        assert Project.objects.get(pk=p2.pk).category_id == game.id
        # archived projects are not part of the replace set
        assert Project.objects.get(pk=archived.pk).category_id == game.id
        assert category_project_ids(game.id) == [p2.id]
        assert set(category_project_ids(game.id, include_archived=True)) == {p2.id, archived.id}

    @pytest.mark.django_db
    def test_category_cycles_distinct_by_name(self, workspace, create_user):
        p1 = _project(workspace, "AA")
        p2 = _project(workspace, "BB")
        p3 = _project(workspace, "CC")

        def cycle(name, project, start, end):
            return Cycle.objects.create(
                name=name,
                project=project,
                workspace=workspace,
                owned_by=create_user,
                start_date=datetime(2026, 1, start, tzinfo=dt_timezone.utc) if start else None,
                end_date=datetime(2026, 1, end, tzinfo=dt_timezone.utc) if end else None,
            )

        cycle("Sprint 2", p1, 15, 28)
        cycle("Sprint 1", p1, 1, 14)
        cycle("Sprint 1", p2, 2, 13)
        cycle("Backlog sprint", p2, None, None)
        cycle("Sprint 9", p3, 1, 2)  # not in scope

        rows = category_cycles([p1.id, p2.id])
        assert [row["name"] for row in rows] == ["Sprint 1", "Sprint 2", "Backlog sprint"]
        sprint_1 = rows[0]
        assert sprint_1["start_date"] == datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
        assert sprint_1["end_date"] == datetime(2026, 1, 14, tzinfo=dt_timezone.utc)
        assert sprint_1["project_ids"] == sorted([str(p1.id), str(p2.id)])
        assert rows[2]["start_date"] is None

    @pytest.mark.django_db
    def test_delete_category_is_synchronous(self, workspace):
        from plane.db.models import IssueView

        game = ProjectCategory.objects.create(workspace=workspace, name="Game")
        p1 = _project(workspace, "AA", category=game)
        archived = _project(workspace, "BB", category=game, archived_at=datetime.now(dt_timezone.utc))
        board = IssueView.objects.create(
            workspace=workspace, name="Game Board", category=game, owned_by=workspace.owner
        )

        delete_category(game)

        assert Project.objects.get(pk=p1.pk).category_id is None
        assert Project.objects.get(pk=archived.pk).category_id is None
        assert not ProjectCategory.objects.filter(pk=game.pk).exists()
        assert ProjectCategory.all_objects.get(pk=game.pk).deleted_at is not None
        assert IssueView.all_objects.get(pk=board.pk).deleted_at is not None
        # the name is free again
        ProjectCategory.objects.create(workspace=workspace, name="Game")


@pytest.mark.unit
class TestApplyCategoryMapping:
    @pytest.mark.django_db
    def test_idempotent_mapping(self, workspace):
        existing = ProjectCategory.objects.create(workspace=workspace, name="alpha", sort_order=5)
        abc = _project(workspace, "ABC")
        xyz = _project(workspace, "XYZ")
        qrs = _project(workspace, "QRS")
        categories = ["Alpha", "Beta", "Gamma", "Delta"]
        mapping = {"ABC": "Alpha", "XYZ": "Beta", "QRS": "Gamma", "NOPE": "Delta"}

        assert apply_category_mapping(workspace)["created"] == []  # nothing configured, nothing created

        first = apply_category_mapping(workspace, categories, mapping)
        assert first["created"] == ["Beta", "Gamma", "Delta"]
        assert set(first["assigned"]) == {"ABC", "XYZ", "QRS"}
        assert first["unknown_identifiers"] == ["NOPE"]
        assert Project.objects.get(pk=abc.pk).category_id == existing.id  # matched ignoring case
        assert Project.objects.get(pk=xyz.pk).category.name == "Beta"
        assert Project.objects.get(pk=qrs.pk).category.name == "Gamma"
        assert list(
            ProjectCategory.objects.filter(workspace=workspace).order_by("sort_order").values_list("name", flat=True)
        ) == ["alpha", "Beta", "Gamma", "Delta"]

        second = apply_category_mapping(workspace, categories, mapping)
        assert second["created"] == []
        assert second["assigned"] == {}
        assert set(second["unchanged"]) == {"ABC", "XYZ", "QRS"}
        assert ProjectCategory.objects.filter(workspace=workspace).count() == 4

    @pytest.mark.django_db
    def test_overwrite_false_keeps_existing_category(self, workspace):
        other = ProjectCategory.objects.create(workspace=workspace, name="Other")
        ai = _project(workspace, "AI", category=other)
        result = apply_category_mapping(workspace, ["Game"], {"AI": "Game"}, overwrite=False)
        assert result["unchanged"] == ["AI"]
        assert Project.objects.get(pk=ai.pk).category_id == other.id


@pytest.mark.unit
class TestProjectCategoryIdField:
    @pytest.mark.django_db
    def test_scoped_to_context_workspace(self, workspace, other_workspace):
        mine = ProjectCategory.objects.create(workspace=workspace, name="Game")
        foreign = ProjectCategory.objects.create(workspace=other_workspace, name="Game")

        class _Serializer(serializers.Serializer):
            category_id = ProjectCategoryIdField(source="category")

        ok = _Serializer(data={"category_id": str(mine.id)}, context={"workspace_id": workspace.id})
        assert ok.is_valid(), ok.errors
        assert ok.validated_data["category"] == mine

        bad = _Serializer(data={"category_id": str(foreign.id)}, context={"workspace_id": workspace.id})
        assert not bad.is_valid()
        assert "category_id" in bad.errors

        cleared = _Serializer(data={"category_id": None}, context={"workspace_id": workspace.id})
        assert cleared.is_valid(), cleared.errors
        assert cleared.validated_data["category"] is None

        no_context = _Serializer(data={"category_id": str(mine.id)})
        assert not no_context.is_valid()

    @pytest.mark.django_db
    def test_member_project_scope_helper(self, workspace, create_user):
        from plane.utils.project_categories import member_project_ids

        p1 = _project(workspace, "AA")
        p2 = _project(workspace, "BB")
        ProjectMember.objects.create(project=p1, member=create_user, workspace=workspace, role=20)
        ProjectMember.objects.create(project=p2, member=create_user, workspace=workspace, role=20, is_active=False)
        assert member_project_ids([p1.id, p2.id], create_user) == [p1.id]
