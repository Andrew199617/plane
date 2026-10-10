# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity importer: `import_jira_csv` and `setup_jira_parity` management commands."""

import csv
import io
import json
from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
import pytz
from crum import impersonate
from django.core.management import CommandError, call_command
from django.db import transaction

from plane.db.models import (
    Cycle,
    CycleIssue,
    Issue,
    IssueActivity,
    IssueAssignee,
    IssueRelation,
    IssueSequence,
    IssueSubscriber,
    Project,
    ProjectCategory,
    ProjectIdentifier,
    ProjectMember,
    State,
    Team,
    User,
    Workspace,
    WorkspaceMember,
)
from plane.celery import app as celery_app
from plane.license.models import InstanceConfiguration
from plane.utils.jira_parity.importer.config import CONFIG_ENV_VAR, TIMEZONE_ENV_VAR
from plane.utils.jira_parity.importer.csv_reader import read_jira_csv
from plane.utils.jira_parity.importer.importer import JiraCsvImporter, JiraImportError

# Synthetic workspace config (a real workspace keeps its own in a private --config file).
CONFIG = {
    "timezone": "Europe/Berlin",
    "categories": [
        {"name": "QA", "description": "Quality assurance.", "emoji": 129514},
        {"name": "Product", "description": "Customer-facing apps."},
        {"name": "Platform"},
        {"name": "Research"},
    ],
    "projects": {
        "TES": {"name": "Test Project", "category": "QA", "emoji": 129514},
        "ABC": {"name": "Example App", "category": "Product"},
    },
    "skip_projects": ["IDEA"],
    "name_replacements": {"Draft": "Final"},
}

HEADERS = [
    "Summary",
    "Issue key",
    "Issue id",
    "Issue Type",
    "Status",
    "Status category",
    "Project key",
    "Project name",
    "Project lead",
    "Project description",
    "Priority",
    "Assignee",
    "Reporter",
    "Created",
    "Updated",
    "Resolved",
    "Due date",
    "Description",
    "Watchers",
    "Watchers",
    "Original estimate",
    "Remaining Estimate",
    "Inward issue link (Blocks)",
    "Outward issue link (Blocks)",
    "Outward issue link (Relates)",
    "Custom field (Rank)",
    "Sprint",
    "Parent key",
]

ROWS = [
    # TES = configured Jira project (name/category/logo from the --config file); key 3 is a gap
    {
        "Summary": "Epic one",
        "Issue key": "TES-1",
        "Issue id": "1001",
        "Issue Type": "Epic",
        "Status": "To Do",
        "Status category": "To Do",
        "Priority": "High",
        "Created": "01/Jan/25 9:00 AM",
        "Updated": "02/Jan/25 10:00 AM",
        "Custom field (Rank)": "0|i0005:",
    },
    {
        "Summary": "Done task",
        "Issue key": "TES-2",
        "Issue id": "1002",
        "Issue Type": "Task",
        "Status": "Done",
        "Status category": "Done",
        "Priority": "Highest",
        "Assignee": "Test User",
        "Created": "03/Jan/25 9:00 AM",
        "Updated": "06/Jan/25 9:00 AM",
        "Resolved": "05/Jan/25 3:30 PM",
        "Description": "*bold* text\n* item",
        "Watchers": "Test User",
        "Custom field (Rank)": "0|i0001:",
        "Sprint": "Sprint 1",
        "Parent key": "TES-1",
        "Outward issue link (Blocks)": "",
    },
    {
        "Summary": "Sub-task with estimate",
        "Issue key": "TES-4",
        "Issue id": "1004",
        "Issue Type": "Sub-task",
        "Status": "To Do",
        "Status category": "To Do",
        "Priority": "Lowest",
        "Created": "04/Jan/25 9:00 AM",
        "Updated": "04/Jan/25 9:00 AM",
        "Due date": "27/Sep/25 12:00 AM",
        "Original estimate": "14400",
        "Remaining Estimate": "7200",
        "Custom field (Rank)": "0|i0003:",
        "Sprint": "Sprint 2",
        "Parent key": "TES-2",
    },
    {
        "Summary": "Won't fix, linked",
        "Issue key": "TES-5",
        "Issue id": "1005",
        "Issue Type": "Task",
        "Status": "Won't Fix",
        "Status category": "Done",
        "Priority": "",
        "Assignee": "Second Person",
        "Reporter": "Ghost Person",
        "Created": "05/Jan/25 9:00 AM",
        "Updated": "07/Jan/25 9:00 AM",
        "Outward issue link (Relates)": "TES-4",
        "Outward issue link (Blocks)": "TES-2",
        "Custom field (Rank)": "0|i0002:",
    },
    # OTH = unconfigured project: name/description from the CSV with the configured Draft -> Final rename
    {
        "Summary": "Cross-project child",
        "Issue key": "OTH-1",
        "Issue id": "2001",
        "Issue Type": "Task",
        "Status": "In Progress",
        "Status category": "In Progress",
        "Project name": "Draft Other",
        "Project description": "Draft project for others.",
        "Priority": "Medium",
        "Created": "06/Jan/25 9:00 AM",
        "Updated": "06/Jan/25 9:30 AM",
        "Sprint": "Sprint 1",
        "Parent key": "TES-1",
    },
    # IDEA is skipped by the config
    {
        "Summary": "An idea",
        "Issue key": "IDEA-1",
        "Issue id": "3001",
        "Issue Type": "Idea",
        "Status": "Parking lot",
        "Status category": "To Do",
        "Created": "06/Jan/25 9:00 AM",
        "Updated": "06/Jan/25 9:00 AM",
    },
]

TODAY = "2026-10-07"


def _write_csv(path, rows=ROWS):
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADERS)
        for row in rows:
            values = []
            watchers_seen = 0
            for header in HEADERS:
                if header == "Watchers":
                    values.append(row.get("Watchers", "") if watchers_seen == 0 else "")
                    watchers_seen += 1
                elif header == "Project key":
                    values.append(row["Issue key"].split("-")[0])
                elif header == "Reporter":
                    values.append(row.get("Reporter", "Test User"))
                elif header == "Project lead":
                    values.append("Test User")
                else:
                    values.append(row.get(header, ""))
            writer.writerow(values)
    return str(path)


def _import(csv_path, **options):
    out = io.StringIO()
    call_command(
        "import_jira_csv",
        workspace="test-workspace",
        csv=[csv_path],
        timezone="UTC",
        today=TODAY,
        stdout=out,
        **options,
    )
    return out.getvalue()


def _issue(key):
    identifier, number = key.split("-")
    return Issue.objects.get(project__identifier=identifier, sequence_id=int(number))


@pytest.fixture
def second_user(db, workspace):
    user = User.objects.create(
        email=f"second-{uuid4().hex[:6]}@plane.so", username=uuid4().hex[:12], first_name="Second", last_name="Person"
    )
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
    return user


@pytest.fixture
def csv_path(tmp_path):
    return _write_csv(tmp_path / "jira.csv")


@pytest.fixture(autouse=True)
def config_path(tmp_path, monkeypatch):
    """Every command in this module reads the synthetic config through $JIRA_PARITY_CONFIG."""
    path = tmp_path / "jira-parity.json"
    path.write_text(json.dumps(CONFIG), encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV_VAR, str(path))
    monkeypatch.delenv(TIMEZONE_ENV_VAR, raising=False)
    return str(path)


@pytest.mark.unit
@pytest.mark.django_db
class TestImportJiraCsv:
    def test_projects_created_like_the_api(self, workspace, create_user, second_user, csv_path):
        output = _import(csv_path)
        assert "Import committed." in output

        tes = Project.objects.get(workspace=workspace, identifier="TES")
        oth = Project.objects.get(workspace=workspace, identifier="OTH")
        assert not Project.objects.filter(identifier="IDEA").exists()
        assert tes.name == "Test Project" and tes.category.name == "QA"
        assert tes.logo_props == {"in_use": "emoji", "emoji": {"value": "129514"}}
        assert oth.name == "Final Other" and oth.description == "Final project for others."
        assert oth.category_id is None
        assert ProjectCategory.objects.filter(workspace=workspace).count() == 4
        for project in (tes, oth):
            assert ProjectIdentifier.objects.filter(project=project, name=project.identifier).exists()
            assert project.cycle_view and project.module_view
            assert project.external_source == "jira"
            assert project.project_lead_id == create_user.id
            assert project.default_assignee_id == create_user.id
            assert ProjectMember.objects.get(project=project, member=create_user).role == 20
            assert set(State.objects.filter(project=project).values_list("name", flat=True)) >= {
                "To Do",
                "In Progress",
                "In Review",
                "Done",
                "Won't Fix",
            }
        assert ProjectMember.objects.get(project=tes, member=second_user, is_active=True).role == 15

    def test_keys_types_states_priorities(self, workspace, create_user, second_user, csv_path):
        _import(csv_path)
        tes = Project.objects.get(workspace=workspace, identifier="TES")
        assert sorted(Issue.objects.filter(project=tes).values_list("sequence_id", flat=True)) == [1, 2, 4, 5]
        assert IssueSequence.objects.filter(project=tes).order_by("-sequence").first().sequence == 5
        assert Issue.objects.create(project=tes, name="native").sequence_id == 6

        assert _issue("TES-1").type.name == "Epic"
        assert _issue("TES-4").type.name == "Sub-task"
        assert _issue("TES-2").state.name == "Done"
        assert _issue("TES-5").state.name == "Won't Fix"
        assert _issue("OTH-1").state.name == "In Progress"
        assert _issue("TES-1").state.name == "To Do"
        assert [_issue(k).priority for k in ("TES-1", "TES-2", "TES-4", "TES-5")] == [
            "high",
            "highest",
            "lowest",
            "medium",
        ]

    def test_fields_and_timestamps(self, workspace, create_user, second_user, csv_path):
        _import(csv_path)
        utc = pytz.utc
        epic, done, sub, wont = (_issue(k) for k in ("TES-1", "TES-2", "TES-4", "TES-5"))
        assert epic.created_at == utc.localize(datetime(2025, 1, 1, 9, 0))
        assert epic.updated_at == utc.localize(datetime(2025, 1, 2, 10, 0))
        assert done.completed_at == utc.localize(datetime(2025, 1, 5, 15, 30))
        assert wont.completed_at is None
        assert sub.original_estimate == 240 and sub.remaining_estimate == 120
        assert epic.original_estimate is None
        assert sub.target_date == date(2025, 9, 27)
        assert done.description_html == "<p><strong>bold</strong> text</p><ul><li><p>item</p></li></ul>"
        assert epic.description_html == "<p></p>"
        assert epic.created_by_id == create_user.id
        assert wont.created_by_id == create_user.id  # unmapped reporter -> acting user
        # Rank order: TES-2 < TES-5 < TES-4 < TES-1
        orders = [_issue(k).sort_order for k in ("TES-2", "TES-5", "TES-4", "TES-1")]
        assert orders == sorted(orders) and len(set(orders)) == 4

    def test_hierarchy_relations_people(self, workspace, create_user, second_user, csv_path):
        _import(csv_path)
        epic, done, sub, wont, child = (_issue(k) for k in ("TES-1", "TES-2", "TES-4", "TES-5", "OTH-1"))
        assert done.parent_id == epic.id
        assert sub.parent_id == done.id
        assert child.parent_id == epic.id  # cross-project parent kept
        assert IssueRelation.objects.filter(
            issue__in=[child, epic], related_issue__in=[child, epic], relation_type="relates_to"
        ).exists()
        relates = IssueRelation.objects.filter(issue__in=[sub, wont], related_issue__in=[sub, wont])
        assert relates.count() == 1 and relates.first().relation_type == "relates_to"
        assert IssueRelation.objects.filter(issue=done, related_issue=wont, relation_type="blocked_by").exists()
        assert IssueRelation.objects.count() == 3

        assert list(IssueAssignee.objects.filter(issue=done).values_list("assignee_id", flat=True)) == [create_user.id]
        assert list(IssueAssignee.objects.filter(issue=wont).values_list("assignee_id", flat=True)) == [second_user.id]
        assert not IssueAssignee.objects.filter(issue=epic).exists()
        assert list(IssueSubscriber.objects.filter(issue=done).values_list("subscriber_id", flat=True)) == [
            create_user.id
        ]

    def test_sprints_become_cycles_with_shared_dates(self, workspace, create_user, second_user, csv_path):
        _import(csv_path)
        sprint1 = Cycle.objects.filter(name="Sprint 1").order_by("project__identifier")
        assert [c.project.identifier for c in sprint1] == ["OTH", "TES"]
        assert len({(c.start_date, c.end_date) for c in sprint1}) == 1
        today = date.fromisoformat(TODAY)
        first = sprint1.first()
        assert first.start_date == pytz.utc.localize(datetime(2026, 10, 7, 0, 0, 1))
        assert first.end_date.date() == today + timedelta(days=13)
        sprint2 = Cycle.objects.get(name="Sprint 2")
        assert sprint2.project.identifier == "TES"
        assert sprint2.start_date.date() == today + timedelta(days=14)
        assert sprint2.start_date > first.end_date
        assert CycleIssue.objects.get(issue=_issue("TES-2")).cycle.name == "Sprint 1"
        assert CycleIssue.objects.get(issue=_issue("TES-4")).cycle_id == sprint2.id
        assert CycleIssue.objects.get(issue=_issue("OTH-1")).cycle.project.identifier == "OTH"

    def test_activity(self, workspace, create_user, second_user, csv_path):
        _import(csv_path)
        epic = _issue("TES-1")
        created = IssueActivity.objects.filter(verb="created", field__isnull=True)
        assert created.count() == 5
        assert created.get(issue=epic).created_at == epic.created_at
        state_change = IssueActivity.objects.get(issue=_issue("TES-2"), field="state")
        assert state_change.new_value == "Done" and state_change.old_value == "To Do"
        assert state_change.created_at == pytz.utc.localize(datetime(2025, 1, 5, 15, 30))
        assert IssueActivity.objects.filter(issue=_issue("TES-4"), field="cycles", new_value="Sprint 2").exists()

    def test_rerun_is_idempotent(self, workspace, create_user, second_user, csv_path):
        _import(csv_path)
        models = (Project, Issue, Cycle, CycleIssue, IssueRelation, IssueAssignee, IssueSubscriber, IssueActivity)
        before = {model.__name__: model.objects.count() for model in models}
        output = _import(csv_path)
        assert {model.__name__: model.objects.count() for model in models} == before
        assert "TOTAL" in output

    def test_dry_run_writes_nothing(self, workspace, create_user, second_user, csv_path):
        output = _import(csv_path, dry_run=True)
        assert "DRY RUN" in output
        assert not Project.objects.filter(identifier__in=["TES", "OTH"]).exists()
        assert Issue.objects.count() == 0

    def test_rollback_runs_and_rolls_back(self, workspace, create_user, second_user, csv_path):
        output = _import(csv_path, rollback=True)
        assert "ROLLBACK" in output
        assert "TES-6" in output  # next key computed by the full run
        assert not Project.objects.filter(identifier__in=["TES", "OTH"]).exists()
        assert Issue.objects.count() == 0 and Cycle.objects.count() == 0

    def test_refuses_project_with_non_jira_work_items(self, workspace, create_user, second_user, csv_path):
        project = Project.objects.create(workspace=workspace, name="Pre-existing", identifier="TES")
        ProjectMember.objects.create(project=project, member=create_user, role=20)
        Issue.objects.create(project=project, name="native item")
        with pytest.raises(CommandError, match="not imported from Jira"):
            _import(csv_path)
        assert not Project.objects.filter(identifier="OTH").exists()
        assert Issue.objects.filter(external_source="jira").count() == 0

    def test_user_map_and_skip_projects(self, workspace, create_user, second_user, csv_path):
        _import(csv_path, user_map=[f"Ghost Person={second_user.email}"], skip_projects="IDEA,OTH")
        assert not Project.objects.filter(identifier="OTH").exists()
        assert _issue("TES-5").created_by_id == second_user.id
        # only TES-4 <-> TES-5 is related; the cross-project OTH-1 -> TES-1 pair was skipped
        assert IssueRelation.objects.filter(relation_type="relates_to").count() == 1

    def test_rejects_non_admin_actor(self, workspace, second_user, csv_path):
        with pytest.raises(CommandError, match="not an active admin"):
            _import(csv_path, user=second_user.email)

    def test_without_config_names_come_from_the_csv(self, workspace, create_user, csv_path, monkeypatch):
        monkeypatch.delenv(CONFIG_ENV_VAR)
        output = _import(csv_path, skip_projects="IDEA")
        assert "config (none)" in output
        tes = Project.objects.get(workspace=workspace, identifier="TES")
        oth = Project.objects.get(workspace=workspace, identifier="OTH")
        assert tes.name == "TES" and tes.category_id is None
        assert oth.name == "Draft Other"
        assert not ProjectCategory.objects.filter(workspace=workspace).exists()

    def test_missing_config_is_refused(self, workspace, create_user, csv_path, tmp_path):
        with pytest.raises(CommandError, match="Config file not found"):
            _import(csv_path, config=str(tmp_path / "missing.json"))
        assert not Project.objects.filter(identifier="TES").exists()

    def test_reports_work_item_type_rule_violations(self, workspace, create_user, tmp_path):
        orphan = {**ROWS[2], "Parent key": "", "Sprint": ""}
        output = _import(_write_csv(tmp_path / "orphan.csv", [orphan]))
        assert "TES-4: Sub-task without a parent" in output
        assert _issue("TES-4").type.is_sub_task


def _delete_in_plane(key):
    """Delete a work item like the app does (soft delete + related cleanup, run in-process)."""
    original = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    try:
        _issue(key).delete()
    finally:
        celery_app.conf.task_always_eager = original


def _numbers(identifier, number):
    """(work items incl. soft-deleted, sequence rows) holding `number` in the project."""
    return (
        Issue.all_objects.filter(project__identifier=identifier, sequence_id=number).count(),
        IssueSequence.objects.filter(project__identifier=identifier, sequence=number).count(),
    )


def _hard_delete():
    """Purge soft-deleted items like the daily cleanup, leaving their sequence reservations."""
    deleted = Issue.all_objects.filter(deleted_at__isnull=False)
    IssueActivity.all_objects.filter(issue__in=deleted).update(issue=None)
    deleted.delete()


GRANDCHILD = {**ROWS[2], "Summary": "Grandchild", "Issue key": "TES-6", "Issue id": "1006", "Parent key": "TES-4"}


@pytest.mark.unit
@pytest.mark.django_db
class TestImportAfterDeletionsInPlane:
    def test_deleted_item_is_not_recreated(self, workspace, create_user, second_user, csv_path):
        _import(csv_path)
        _delete_in_plane("TES-5")
        output = _import(csv_path)
        assert "TES-5: deleted in Plane after an earlier import; not recreated" in output
        assert not Issue.objects.filter(project__identifier="TES", sequence_id=5).exists()
        assert _numbers("TES", 5) == (1, 1)
        assert output.count("TES-5: deleted in Plane after an earlier import; not recreated") == 1

    def _planned_import(self, workspace, create_user, second_user, tmp_path):
        _import(_write_csv(tmp_path / "first.csv", [row for row in ROWS if row["Issue key"] != "TES-5"]))
        csv_path = _write_csv(tmp_path / "second.csv")
        rows = read_jira_csv(csv_path).rows
        importer = JiraCsvImporter(workspace, create_user, rows, today=date.fromisoformat(TODAY), only_projects=["TES"])
        importer.plan()
        assert [row.key for row in importer.plans["TES"].rows_to_create] == ["TES-5"]
        return importer, csv_path

    def test_item_imported_after_planning_is_not_duplicated(self, workspace, create_user, second_user, tmp_path):
        importer, csv_path = self._planned_import(workspace, create_user, second_user, tmp_path)
        # A second import finishes while the first is waiting to acquire the sequence lock.
        _import(csv_path)
        with transaction.atomic(), impersonate(create_user):
            importer.run()
        assert importer.created_keys == set()
        assert _numbers("TES", 5) == (1, 1)

    def test_item_imported_and_deleted_after_planning_is_not_recreated(
        self, workspace, create_user, second_user, tmp_path
    ):
        importer, csv_path = self._planned_import(workspace, create_user, second_user, tmp_path)
        _import(csv_path)
        _delete_in_plane("TES-5")
        with transaction.atomic(), impersonate(create_user):
            importer.run()
        assert "TES-5: deleted in Plane after an earlier import; not recreated" in importer.warnings
        assert not Issue.objects.filter(project__identifier="TES", sequence_id=5).exists()
        assert _numbers("TES", 5) == (1, 1)

    def test_parent_deleted_after_planning_prevents_new_children(self, workspace, create_user, second_user, tmp_path):
        _import(_write_csv(tmp_path / "first.csv", [row for row in ROWS if row["Issue key"] != "TES-4"]))
        rows = read_jira_csv(_write_csv(tmp_path / "second.csv")).rows
        importer = JiraCsvImporter(workspace, create_user, rows, today=date.fromisoformat(TODAY), only_projects=["TES"])
        importer.plan()
        _delete_in_plane("TES-2")
        with transaction.atomic(), impersonate(create_user):
            importer.run()
        assert "TES-4: not imported, TES-2 (its parent or an ancestor) was deleted in Plane" in importer.warnings
        assert not Issue.all_objects.filter(project__identifier="TES", sequence_id=4).exists()
        assert _numbers("TES", 2) == (1, 1)

    def test_deleted_native_item_still_reserves_its_number(self, workspace, create_user, second_user, tmp_path):
        importer, _ = self._planned_import(workspace, create_user, second_user, tmp_path)
        native = Issue.objects.create(project=Project.objects.get(identifier="TES"), name="native")
        assert native.sequence_id == 5
        _delete_in_plane("TES-5")
        with transaction.atomic(), impersonate(create_user):
            importer.run()
        assert "TES-5: number already used in Plane by a deleted work item; not recreated" in importer.warnings
        assert _numbers("TES", 5) == (1, 1)

    def test_hard_deleted_item_is_not_recreated(self, workspace, create_user, second_user, csv_path):
        _import(csv_path)
        _delete_in_plane("TES-5")
        _hard_delete()
        assert _numbers("TES", 5) == (0, 1)
        output = _import(csv_path)
        assert "TES-5: number already used in Plane by a deleted work item; not recreated" in output
        assert _numbers("TES", 5) == (0, 1)

    def test_hard_deleted_parent_outside_the_import(self, workspace, create_user, second_user, csv_path, tmp_path):
        _import(csv_path)
        _delete_in_plane("TES-1")
        _hard_delete()
        assert _numbers("TES", 1) == (0, 1) and _numbers("OTH", 1) == (0, 1)
        new_child = {**ROWS[4], "Summary": "New child", "Issue key": "OTH-2", "Issue id": "2002"}
        output = _import(_write_csv(tmp_path / "oth.csv", [ROWS[4], new_child]), projects="OTH")
        assert "OTH-1: number already used in Plane by a deleted work item; not recreated" in output
        assert "OTH-2: not imported, TES-1 (its parent or an ancestor) was deleted in Plane" in output
        assert not Issue.all_objects.filter(project__identifier="OTH").exists()
        assert _numbers("OTH", 1) == (0, 1)

    def test_sub_work_items_of_a_deleted_parent_are_skipped(self, workspace, create_user, second_user, tmp_path):
        _import(_write_csv(tmp_path / "first.csv", [row for row in ROWS if row["Issue key"] != "TES-4"]))
        _delete_in_plane("TES-2")
        output = _import(_write_csv(tmp_path / "second.csv", [*ROWS, GRANDCHILD]))
        assert "TES-2: deleted in Plane after an earlier import; not recreated" in output
        assert "TES-4: not imported, TES-2 (its parent or an ancestor) was deleted in Plane" in output
        assert "TES-6: not imported, TES-2 (its parent or an ancestor) was deleted in Plane" in output
        assert sorted(Issue.objects.filter(project__identifier="TES").values_list("sequence_id", flat=True)) == [1, 5]
        assert _numbers("TES", 2) == (1, 1)
        assert not Issue.all_objects.filter(project__identifier="TES", sequence_id__in=[4, 6]).exists()

    def test_deleted_parent_outside_the_import(self, workspace, create_user, second_user, csv_path, tmp_path):
        _import(csv_path)
        _delete_in_plane("TES-1")  # also deletes its sub-work-items, OTH-1 included
        new_child = {**ROWS[4], "Summary": "New child", "Issue key": "OTH-2", "Issue id": "2002"}
        output = _import(_write_csv(tmp_path / "oth.csv", [ROWS[4], new_child]), projects="OTH")
        assert "OTH-1: deleted in Plane after an earlier import; not recreated" in output
        assert "OTH-2: not imported, TES-1 (its parent or an ancestor) was deleted in Plane" in output
        assert not Issue.objects.filter(project__identifier="OTH").exists()

    def test_non_jira_item_created_after_planning_is_refused(self, workspace, create_user, second_user, tmp_path):
        _import(_write_csv(tmp_path / "first.csv", [row for row in ROWS if row["Issue key"] != "TES-5"]))
        rows = read_jira_csv(_write_csv(tmp_path / "second.csv")).rows
        importer = JiraCsvImporter(workspace, create_user, rows, today=date.fromisoformat(TODAY), only_projects=["TES"])
        importer.plan()
        native = Issue.objects.create(project=Project.objects.get(identifier="TES"), name="native")
        assert native.sequence_id == 5
        with pytest.raises(JiraImportError, match="not imported from Jira"):
            with transaction.atomic(), impersonate(create_user):
                importer.run()
        assert list(Issue.objects.filter(project__identifier="TES", sequence_id=5)) == [native]


@pytest.mark.unit
@pytest.mark.django_db
class TestSetupJiraParity:
    def _setup(self, **options):
        out = io.StringIO()
        call_command("setup_jira_parity", workspace="test-workspace", stdout=out, **options)
        return out.getvalue()

    def test_configures_workspace_and_projects(self, workspace, create_user):
        legacy = Project.objects.create(workspace=workspace, name="Legacy", identifier="ABC")
        ProjectMember.objects.create(project=legacy, member=create_user, role=15)
        for name, group, default in (
            ("Backlog", "backlog", True),
            ("Todo", "unstarted", False),
            ("Done", "completed", False),
        ):
            State.objects.create(project=legacy, workspace=workspace, name=name, group=group, default=default)
        item = Issue.objects.create(
            project=legacy, name="in backlog", state=State.objects.get(project=legacy, name="Backlog")
        )
        backlog_id = item.state_id
        todo_id = State.objects.get(project=legacy, name="Todo").id

        output = self._setup()
        assert "Setup committed." in output

        assert InstanceConfiguration.objects.get(key="ENABLE_SIGNUP").value == "0"
        workspace.refresh_from_db()
        create_user.refresh_from_db()
        legacy.refresh_from_db()
        assert workspace.timezone == "Europe/Berlin"
        assert create_user.user_timezone == "Europe/Berlin"
        assert legacy.timezone == "Europe/Berlin"
        assert set(ProjectCategory.objects.filter(workspace=workspace).values_list("name", flat=True)) == {
            "QA",
            "Product",
            "Platform",
            "Research",
        }
        assert legacy.category.name == "Product"  # configured Jira key ABC
        teams = {team.name: team for team in Team.objects.filter(workspace=workspace)}
        assert teams["Devs"].default_project_role == 20 and teams["Devs"].auto_join
        assert teams["Agents"].default_project_role == 10 and teams["Agents"].auto_join
        assert legacy.project_lead_id == create_user.id
        assert legacy.default_assignee_id == create_user.id
        assert ProjectMember.objects.get(project=legacy, member=create_user).role == 20
        assert set(State.objects.filter(project=legacy).values_list("name", flat=True)) == {
            "Backlog",
            "To Do",
            "In Progress",
            "In Review",
            "Done",
            "Won't Fix",
        }
        item.refresh_from_db()
        # Setup adopts aliases in place, but only the explicit workflow merge command moves items.
        assert item.state_id == backlog_id
        assert item.state.name == "Backlog" and item.state.group == "backlog"
        assert item.state.deleted_at is None
        assert not IssueActivity.objects.filter(issue=item, field="state").exists()
        todo = State.objects.get(project=legacy, name="To Do")
        assert todo.id == todo_id and todo.default is True

    def test_idempotent(self, workspace, create_user):
        Project.objects.create(workspace=workspace, name="Legacy", identifier="XYZ")
        self._setup()
        models = (Project, ProjectMember, ProjectCategory, Team, State)
        before = {model.__name__: model.objects.count() for model in models}
        output = self._setup()
        assert {model.__name__: model.objects.count() for model in models} == before
        assert "ENABLE_SIGNUP already 0" in output

    def test_rollback(self, workspace, create_user):
        output = self._setup(rollback=True)
        assert "ROLLBACK" in output
        assert not ProjectCategory.objects.filter(workspace=workspace).exists()
        assert Workspace.objects.get(pk=workspace.pk).timezone != "Europe/Berlin"

    def test_then_import_uses_categories_and_timezone(self, workspace, create_user, tmp_path):
        self._setup()
        _write_csv(tmp_path / "j.csv")
        _import(str(tmp_path / "j.csv"))
        tes = Project.objects.get(workspace=workspace, identifier="TES")
        assert tes.timezone == "Europe/Berlin"
        assert tes.category.name == "QA"
        assert Team.objects.get(workspace=workspace, name="Devs").team_projects.filter(project=tes).exists()

    def test_without_config_creates_no_categories(self, workspace, create_user, monkeypatch):
        monkeypatch.delenv(CONFIG_ENV_VAR)
        output = self._setup()
        assert "categories] none configured" in output
        assert not ProjectCategory.objects.filter(workspace=workspace).exists()
        assert Workspace.objects.get(pk=workspace.pk).timezone == "UTC"

    def test_explicit_config_and_timezone(self, workspace, create_user, config_path, monkeypatch):
        monkeypatch.delenv(CONFIG_ENV_VAR)
        output = self._setup(config=config_path, timezone="Asia/Tokyo")
        assert f"Config: {config_path}" in output
        assert Workspace.objects.get(pk=workspace.pk).timezone == "Asia/Tokyo"
        assert ProjectCategory.objects.filter(workspace=workspace).count() == 4
