# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity sprints (cycles) and releases (modules).

Sprints: explicit future -> active -> closed lifecycle (start / complete actions), one active sprint per project,
state-based status everywhere, closed sprints are read-only.
Releases: Unreleased / Released statuses, release action that can move unresolved work items, archive any status.
"""

from datetime import timedelta
from importlib import import_module
from uuid import uuid4

import pytest
from django.apps import apps as django_apps
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    Cycle,
    CycleIssue,
    Issue,
    Module,
    ModuleIssue,
    Project,
    ProjectMember,
    State,
    User,
    WorkspaceMember,
)
from plane.utils.jira_parity.sprints import next_sprint_name, parse_sprint_name

BASE = "/api/workspaces/{slug}/projects/{project}"
CYCLES_URL = BASE + "/cycles/"
CYCLE_URL = BASE + "/cycles/{cycle}/"
CYCLE_ISSUES_URL = BASE + "/cycles/{cycle}/cycle-issues/"
CYCLE_ARCHIVE_URL = BASE + "/cycles/{cycle}/archive/"
DATE_CHECK_URL = BASE + "/cycles/date-check/"
START_URL = BASE + "/cycles/{cycle}/start/"
COMPLETE_URL = BASE + "/cycles/{cycle}/complete/"
NEXT_NAME_URL = BASE + "/sprints/next-name/"
MODULES_URL = BASE + "/modules/"
MODULE_URL = BASE + "/modules/{module}/"
MODULE_ARCHIVE_URL = BASE + "/modules/{module}/archive/"
RELEASE_URL = BASE + "/modules/{module}/release/"
UNRELEASE_URL = BASE + "/modules/{module}/unrelease/"

GROUPS = {"To Do": "unstarted", "In Progress": "started", "Done": "completed", "Won't Fix": "cancelled"}


def _user(workspace, role, prefix):
    unique_id = uuid4().hex[:8]
    user = User.objects.create(
        email=f"{prefix}-{unique_id}@plane.so",
        username=f"{prefix}_{unique_id}",
        first_name=prefix.title(),
        last_name="User",
    )
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=role)
    return user


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Sprint Project", identifier="TST", workspace=workspace)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    return project


@pytest.fixture
def states(project):
    return {
        name: State.objects.create(
            name=name, project=project, workspace=project.workspace, group=group, color="#000000", sequence=i * 1000
        )
        for i, (name, group) in enumerate(GROUPS.items(), start=1)
    }


def _url(template, project, **kwargs):
    return template.format(slug=project.workspace.slug, project=project.id, **kwargs)


def _issue(name, project, state, author):
    issue = Issue(name=name, project=project, workspace=project.workspace, state=state)
    issue.save(created_by_id=author.id)
    return issue


def _cycle(project, name, start=None, end=None, **extra):
    return Cycle.objects.create(
        name=name,
        project=project,
        workspace=project.workspace,
        start_date=start,
        end_date=end,
        owned_by=project.workspace.owner,
        **extra,
    )


def _in_cycle(cycle, *issues):
    for issue in issues:
        CycleIssue.objects.create(cycle=cycle, issue=issue, project=cycle.project, workspace=cycle.workspace)


def _module(project, name, **extra):
    return Module.objects.create(name=name, project=project, workspace=project.workspace, **extra)


def _in_module(module, *issues):
    for issue in issues:
        ModuleIssue.objects.create(module=module, issue=issue, project=module.project, workspace=module.workspace)


def _cycle_ids(cycle):
    return set(CycleIssue.objects.filter(cycle=cycle).values_list("issue_id", flat=True))


def _module_ids(module):
    return set(ModuleIssue.objects.filter(module=module).values_list("issue_id", flat=True))


def _statuses(client, project):
    response = client.get(_url(CYCLES_URL, project))
    assert response.status_code == status.HTTP_200_OK, response.data
    return {row["name"]: row["status"] for row in response.data}


# ------------------------------------------------------------------------------------------------- sprint helpers


@pytest.mark.unit
class TestSprintNames:
    def test_parse_sprint_name(self):
        assert parse_sprint_name("LGD Sprint 4") == ("LGD Sprint", 4)
        assert parse_sprint_name("Sprint 12") == ("Sprint", 12)
        assert parse_sprint_name(" ACR sprint 2 ") == ("ACR sprint", 2)
        assert parse_sprint_name("Release 2") == ("Release 2", None)
        assert parse_sprint_name("Sprint") == ("Sprint", None)

    @pytest.mark.django_db
    def test_next_sprint_name(self, session_client, project):
        assert next_sprint_name(project) == "TST Sprint 1"
        _cycle(project, "Sprint 3")
        _cycle(project, "Kickoff")
        assert next_sprint_name(project) == "Sprint 4"
        deleted = _cycle(project, "TST Sprint 7")
        deleted.delete()
        response = session_client.get(_url(NEXT_NAME_URL, project))
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data == {"name": "TST Sprint 8"}


# -------------------------------------------------------------------------------------------- sprint lifecycle


@pytest.mark.contract
class TestSprintStatus:
    @pytest.mark.django_db
    def test_status_follows_lifecycle_not_dates(self, session_client, project):
        now = timezone.now()
        _cycle(project, "Draft")
        _cycle(project, "Future", now - timedelta(days=3), now + timedelta(days=10))  # dates span today
        _cycle(project, "Overdue active", now - timedelta(days=20), now - timedelta(days=6), started_at=now)
        _cycle(
            project,
            "Closed early",
            now - timedelta(days=2),
            now + timedelta(days=12),
            started_at=now - timedelta(days=2),
            completed_at=now,
        )
        assert _statuses(session_client, project) == {
            "Draft": "DRAFT",
            "Future": "UPCOMING",
            "Overdue active": "CURRENT",
            "Closed early": "COMPLETED",
        }

        response = session_client.get(_url(CYCLES_URL, project), {"cycle_view": "current"})
        assert [row["name"] for row in response.data] == ["Overdue active"]
        assert response.data[0]["started_at"] is not None
        assert response.data[0]["completed_at"] is None

    @pytest.mark.django_db
    def test_date_check_allows_overlaps(self, session_client, project):
        now = timezone.now()
        _cycle(project, "Sprint 1", now, now + timedelta(days=13))
        response = session_client.post(
            _url(DATE_CHECK_URL, project),
            {"start_date": now.date().isoformat(), "end_date": (now + timedelta(days=5)).date().isoformat()},
            format="json",
        )
        assert response.data == {"status": True}


@pytest.mark.contract
class TestStartSprint:
    @pytest.mark.django_db
    def test_start_sets_dates_goal_and_state(self, session_client, project):
        sprint = _cycle(project, "TST Sprint 1")
        response = session_client.post(
            _url(START_URL, project, cycle=sprint.id),
            {
                "name": "TST Sprint 1 (renamed)",
                "description": "Ship the login flow",
                "start_date": "2026-01-05",
                "end_date": "2026-01-18",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["status"] == "CURRENT"
        assert response.data["name"] == "TST Sprint 1 (renamed)"
        assert response.data["description"] == "Ship the login flow"
        assert response.data["started_at"] is not None
        assert response.data["completed_at"] is None
        sprint.refresh_from_db()
        assert sprint.started_at is not None
        assert sprint.start_date is not None and sprint.end_date is not None
        assert sprint.start_date < sprint.end_date

    @pytest.mark.django_db
    def test_start_keeps_planned_dates(self, session_client, project):
        now = timezone.now()
        sprint = _cycle(project, "Planned", now + timedelta(days=7), now + timedelta(days=20))
        response = session_client.post(_url(START_URL, project, cycle=sprint.id), {}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["status"] == "CURRENT"

    @pytest.mark.django_db
    def test_only_one_active_sprint(self, session_client, project):
        now = timezone.now()
        active = _cycle(project, "Active", now, now + timedelta(days=13), started_at=now)
        future = _cycle(project, "Next")
        response = session_client.post(
            _url(START_URL, project, cycle=future.id),
            {"start_date": "2026-02-01", "end_date": "2026-02-14"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "ACTIVE_SPRINT_EXISTS"
        assert response.data["active_sprint"] == {"id": str(active.id), "name": "Active"}
        future.refresh_from_db()
        assert future.started_at is None

    @pytest.mark.django_db
    def test_start_errors(self, session_client, project):
        now = timezone.now()
        no_dates = _cycle(project, "No dates")
        response = session_client.post(_url(START_URL, project, cycle=no_dates.id), {}, format="json")
        assert response.data["code"] == "INVALID_DATES"

        backwards = session_client.post(
            _url(START_URL, project, cycle=no_dates.id),
            {"start_date": "2026-02-14", "end_date": "2026-02-01"},
            format="json",
        )
        assert backwards.status_code == status.HTTP_400_BAD_REQUEST
        assert backwards.data["code"] == "INVALID_DATES"

        started = _cycle(project, "Started", now, now + timedelta(days=5), started_at=now)
        response = session_client.post(_url(START_URL, project, cycle=started.id), {}, format="json")
        assert response.data["code"] == "SPRINT_ALREADY_STARTED"

        closed = _cycle(project, "Closed", now, now, started_at=now, completed_at=now)
        response = session_client.post(_url(START_URL, project, cycle=closed.id), {}, format="json")
        assert response.data["code"] == "SPRINT_COMPLETED"

    @pytest.mark.django_db
    def test_guest_cannot_start(self, workspace, project):
        guest = _user(workspace, 5, "guest")
        ProjectMember.objects.create(project=project, member=guest, workspace=workspace, role=5)
        sprint = _cycle(project, "Guarded")
        response = _client(guest).post(
            _url(START_URL, project, cycle=sprint.id),
            {"start_date": "2026-02-01", "end_date": "2026-02-14"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        sprint.refresh_from_db()
        assert sprint.started_at is None


@pytest.mark.contract
class TestCompleteSprint:
    @pytest.fixture
    def active_sprint(self, project, states, create_user):
        now = timezone.now()
        sprint = _cycle(project, "TST Sprint 1", now - timedelta(days=5), now + timedelta(days=8), started_at=now)
        self.done = _issue("Done", project, states["Done"], create_user)
        self.wont_fix = _issue("Won't fix", project, states["Won't Fix"], create_user)
        self.todo = _issue("To do", project, states["To Do"], create_user)
        self.doing = _issue("Doing", project, states["In Progress"], create_user)
        _in_cycle(sprint, self.done, self.wont_fix, self.todo, self.doing)
        return sprint

    @pytest.mark.django_db
    def test_complete_to_backlog(self, session_client, project, active_sprint):
        response = session_client.post(
            _url(COMPLETE_URL, project, cycle=active_sprint.id), {"move_to": "backlog"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["moved_issues"] == 2
        assert response.data["moved_to"] is None
        assert response.data["new_sprint"] is None
        assert response.data["cycle"]["status"] == "COMPLETED"
        assert response.data["cycle"]["completed_at"] is not None
        assert _cycle_ids(active_sprint) == {self.done.id, self.wont_fix.id}

        active_sprint.refresh_from_db()
        assert active_sprint.completed_at is not None
        assert active_sprint.progress_snapshot["total_issues"] == 4
        assert active_sprint.progress_snapshot["completed_issues"] == 1

    @pytest.mark.django_db
    def test_complete_to_future_sprint(self, session_client, project, active_sprint):
        target = _cycle(project, "TST Sprint 2")
        response = session_client.post(
            _url(COMPLETE_URL, project, cycle=active_sprint.id), {"move_to": str(target.id)}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["moved_issues"] == 2
        assert response.data["moved_to"] == {"id": str(target.id), "name": "TST Sprint 2"}
        assert _cycle_ids(target) == {self.todo.id, self.doing.id}
        assert _cycle_ids(active_sprint) == {self.done.id, self.wont_fix.id}

    @pytest.mark.django_db
    def test_complete_to_new_sprint(self, session_client, project, active_sprint):
        response = session_client.post(
            _url(COMPLETE_URL, project, cycle=active_sprint.id), {"move_to": "new"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        new_sprint = response.data["new_sprint"]
        assert new_sprint["name"] == "TST Sprint 2"
        assert new_sprint["status"] == "DRAFT"
        assert response.data["moved_to"]["id"] == str(new_sprint["id"])
        assert _cycle_ids(Cycle.objects.get(pk=new_sprint["id"])) == {self.todo.id, self.doing.id}

    @pytest.mark.django_db
    def test_complete_without_open_issues_creates_nothing(self, session_client, project, states, create_user):
        now = timezone.now()
        sprint = _cycle(project, "Clean", now, now + timedelta(days=13), started_at=now)
        _in_cycle(sprint, _issue("Done", project, states["Done"], create_user))
        response = session_client.post(_url(COMPLETE_URL, project, cycle=sprint.id), {"move_to": "new"}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["moved_issues"] == 0
        assert response.data["new_sprint"] is None
        assert Cycle.objects.filter(project=project).count() == 1

    @pytest.mark.django_db
    def test_invalid_targets(self, session_client, project, active_sprint):
        now = timezone.now()
        closed = _cycle(project, "Old", now, now, started_at=now, completed_at=now)
        other_project = Project.objects.create(name="Other", identifier="OTH", workspace=project.workspace)
        foreign = _cycle(other_project, "Foreign")
        for move_to in (str(closed.id), str(foreign.id), str(active_sprint.id), "nonsense"):
            response = session_client.post(
                _url(COMPLETE_URL, project, cycle=active_sprint.id), {"move_to": move_to}, format="json"
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST, move_to
            assert response.data["code"] == "INVALID_TARGET"
        active_sprint.refresh_from_db()
        assert active_sprint.completed_at is None

    @pytest.mark.django_db
    def test_complete_requires_active_sprint(self, session_client, project):
        future = _cycle(project, "Future")
        response = session_client.post(_url(COMPLETE_URL, project, cycle=future.id), {}, format="json")
        assert response.data["code"] == "SPRINT_NOT_STARTED"


@pytest.mark.contract
class TestClosedSprintRules:
    @pytest.mark.django_db
    def test_closed_sprint_is_read_only(self, session_client, project, states, create_user):
        now = timezone.now()
        closed = _cycle(project, "Closed", now + timedelta(days=1), now + timedelta(days=9), started_at=now)
        closed.completed_at = now
        closed.save()

        response = session_client.patch(_url(CYCLE_URL, project, cycle=closed.id), {"name": "x"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "SPRINT_COMPLETED"

        response = session_client.patch(
            _url(CYCLE_URL, project, cycle=closed.id), {"name": "x", "sort_order": 5}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        closed.refresh_from_db()
        assert closed.name == "Closed" and closed.sort_order == 5

        issue = _issue("Late", project, states["To Do"], create_user)
        response = session_client.post(
            _url(CYCLE_ISSUES_URL, project, cycle=closed.id), {"issues": [str(issue.id)]}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_active_sprint_accepts_work_after_end_date(self, session_client, project, states, create_user):
        now = timezone.now()
        overdue = _cycle(project, "Overdue", now - timedelta(days=20), now - timedelta(days=6), started_at=now)
        issue = _issue("Late", project, states["To Do"], create_user)
        response = session_client.post(
            _url(CYCLE_ISSUES_URL, project, cycle=overdue.id), {"issues": [str(issue.id)]}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert _cycle_ids(overdue) == {issue.id}

        response = session_client.patch(_url(CYCLE_URL, project, cycle=overdue.id), {"end_date": None}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "INVALID_DATES"

    @pytest.mark.django_db
    def test_lifecycle_fields_not_writable(self, session_client, project):
        sprint = _cycle(project, "Future")
        response = session_client.patch(
            _url(CYCLE_URL, project, cycle=sprint.id),
            {"started_at": timezone.now().isoformat(), "completed_at": timezone.now().isoformat()},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        sprint.refresh_from_db()
        assert sprint.started_at is None and sprint.completed_at is None

    @pytest.mark.django_db
    def test_only_closed_sprints_archive(self, session_client, project):
        now = timezone.now()
        active = _cycle(project, "Active", now - timedelta(days=30), now - timedelta(days=16), started_at=now)
        response = session_client.post(_url(CYCLE_ARCHIVE_URL, project, cycle=active.id), {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        closed = _cycle(project, "Closed", now, now + timedelta(days=13), started_at=now, completed_at=now)
        response = session_client.post(_url(CYCLE_ARCHIVE_URL, project, cycle=closed.id), {}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data


# ------------------------------------------------------------------------------------------------------ releases


@pytest.mark.contract
class TestReleases:
    @pytest.mark.django_db
    def test_default_status_and_choices(self, session_client, project):
        response = session_client.post(_url(MODULES_URL, project), {"name": "1.0"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["status"] == "unreleased"
        response = session_client.patch(
            _url(MODULE_URL, project, module=response.data["id"]), {"status": "planned"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_release_defaults_to_today(self, session_client, project):
        release = _module(project, "1.0")
        response = session_client.post(_url(RELEASE_URL, project, module=release.id), {}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["moved_issues"] == 0
        assert response.data["module"]["status"] == "released"
        assert response.data["module"]["target_date"] is not None
        release.refresh_from_db()
        assert release.status == "released"
        assert release.target_date is not None

    @pytest.mark.django_db
    def test_release_moves_unresolved_work(self, session_client, project, states, create_user):
        release = _module(project, "1.0", target_date=timezone.now().date())
        nxt = _module(project, "1.1")
        done = _issue("Done", project, states["Done"], create_user)
        wont_fix = _issue("Won't fix", project, states["Won't Fix"], create_user)
        todo = _issue("To do", project, states["To Do"], create_user)
        doing = _issue("Doing", project, states["In Progress"], create_user)
        _in_module(release, done, wont_fix, todo, doing)
        _in_module(nxt, doing)  # already in the target: must not duplicate

        response = session_client.post(
            _url(RELEASE_URL, project, module=release.id),
            {"release_date": "2026-03-01", "move_to": str(nxt.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["moved_issues"] == 2
        assert str(response.data["module"]["target_date"]) == "2026-03-01"
        assert _module_ids(release) == {done.id, wont_fix.id}
        assert _module_ids(nxt) == {todo.id, doing.id}
        assert ModuleIssue.objects.filter(module=nxt, issue=doing).count() == 1

    @pytest.mark.django_db
    def test_release_errors(self, session_client, project):
        released = _module(project, "0.9", status="released")
        response = session_client.post(_url(RELEASE_URL, project, module=released.id), {}, format="json")
        assert response.data["code"] == "RELEASE_ALREADY_RELEASED"

        release = _module(project, "1.0", start_date=timezone.now().date())
        response = session_client.post(
            _url(RELEASE_URL, project, module=release.id), {"release_date": "2000-01-01"}, format="json"
        )
        assert response.data["code"] == "INVALID_DATE"
        response = session_client.post(
            _url(RELEASE_URL, project, module=release.id), {"move_to": str(released.id)}, format="json"
        )
        assert response.data["code"] == "INVALID_TARGET"

        archived = _module(project, "Old", archived_at=timezone.now())
        response = session_client.post(_url(RELEASE_URL, project, module=archived.id), {}, format="json")
        assert response.data["code"] == "RELEASE_ARCHIVED"
        release.refresh_from_db()
        assert release.status == "unreleased"

    @pytest.mark.django_db
    def test_unrelease(self, session_client, project):
        release = _module(project, "1.0", status="released")
        response = session_client.post(_url(UNRELEASE_URL, project, module=release.id), {}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["module"]["status"] == "unreleased"
        response = session_client.post(_url(UNRELEASE_URL, project, module=release.id), {}, format="json")
        assert response.data["code"] == "RELEASE_NOT_RELEASED"

    @pytest.mark.django_db
    def test_archive_any_status(self, session_client, project):
        release = _module(project, "1.0")
        response = session_client.post(_url(MODULE_ARCHIVE_URL, project, module=release.id), {}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        release.refresh_from_db()
        assert release.archived_at is not None


# ----------------------------------------------------------------------------------------------------- migration


@pytest.mark.unit
class TestMigration:
    @pytest.mark.django_db
    def test_backfill_and_status_mapping(self, project):
        migration = import_module("plane.db.migrations.0133_jp_sprints_releases")
        now = timezone.now()
        running = _cycle(project, "Running", now - timedelta(days=1), now + timedelta(days=5))
        ended = _cycle(project, "Ended", now - timedelta(days=20), now - timedelta(days=6))
        future = _cycle(project, "Future", now + timedelta(days=1), now + timedelta(days=14))
        draft = _cycle(project, "Draft")
        migration.backfill_sprint_states(django_apps, None)
        for cycle in (running, ended, future, draft):
            cycle.refresh_from_db()
        assert running.started_at == running.start_date and running.completed_at is None
        assert ended.started_at == ended.start_date and ended.completed_at == ended.end_date
        assert future.started_at is None and draft.started_at is None

        modules = {name: _module(project, name, status=name) for name in ("completed", "planned", "cancelled")}
        migration.map_module_statuses(django_apps, None)
        assert {name: Module.objects.get(pk=m.pk).status for name, m in modules.items()} == {
            "completed": "released",
            "planned": "unreleased",
            "cancelled": "unreleased",
        }
