# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Tests for the Jira-parity backend scaffold: roles, priorities, membership helper, hooks."""

import importlib
from unittest import mock

import pytest

from plane.db.models import (
    DraftIssue,
    Issue,
    IssueVersion,
    Project,
    ProjectMember,
    ProjectUserProperty,
    User,
    WorkspaceMember,
)
from plane.utils.jira_parity import project_hooks
from plane.utils.project_membership import ensure_project_member


# ---------------------------------------------------------------- roles


@pytest.mark.unit
class TestUnifiedRole:
    def test_single_role_enum(self):
        from plane.app.permissions import ROLE as app_role
        from plane.db.models.project import ROLE as db_role
        from plane.utils.permissions import ROLE as utils_role

        assert app_role is db_role is utils_role
        assert [r.value for r in db_role] == [20, 15, 10, 5]
        assert db_role.AGENT.value == 10

    def test_role_choices_include_agent(self):
        from plane.db.models import ProjectMemberInvite, WorkspaceMemberInvite

        for model in (ProjectMember, ProjectMemberInvite, WorkspaceMember, WorkspaceMemberInvite):
            assert dict(model._meta.get_field("role").choices) == {
                20: "Admin",
                15: "Member",
                10: "Agent",
                5: "Guest",
            }


# ---------------------------------------------------------------- priorities


@pytest.mark.unit
class TestPriorities:
    def test_priority_choices_and_default(self):
        expected = ["highest", "high", "medium", "low", "lowest"]
        for model in (Issue, DraftIssue, IssueVersion):
            field = model._meta.get_field("priority")
            assert [key for key, _ in field.choices] == expected
            assert field.default == "medium"
            assert [key for key, _ in model.PRIORITY_CHOICES] == expected

    def test_migration_remaps_filter_trees(self):
        migration = importlib.import_module("plane.db.migrations.0124_jp_priorities")
        tree = {
            "filters": {"priority": ["urgent", "high", "none"], "state": ["x"]},
            "rich_filters": {"and": [{"priority__in": "urgent,none,medium"}, {"or": [{"priority": "none"}]}]},
            "display_filters": {"order_by": "priority", "group_by": "priority"},
            "display_properties": {"priority": True},
        }
        out = migration.remap_priority_tree(tree, migration.FORWARD_MAP)
        assert out["filters"]["priority"] == ["highest", "high", "medium"]
        assert out["filters"]["state"] == ["x"]
        # duplicates collapse (none -> medium + medium)
        assert out["rich_filters"]["and"][0]["priority__in"] == "highest,medium"
        assert out["rich_filters"]["and"][1]["or"][0]["priority"] == "medium"
        assert out["display_filters"] == {"order_by": "priority", "group_by": "priority"}
        assert out["display_properties"] == {"priority": True}

        back = migration.remap_priority_tree(out, migration.BACKWARD_MAP)
        assert back["filters"]["priority"] == ["urgent", "high", "medium"]


# ---------------------------------------------------------------- membership helper


@pytest.fixture
def project(db, workspace, create_user):
    return Project.objects.create(name="Scaffold", identifier="SCF", workspace=workspace)


@pytest.fixture
def other_user(db):
    return User.objects.create(email="other-scaffold@plane.so", username="other_scaffold")


@pytest.mark.unit
class TestEnsureProjectMember:
    @pytest.mark.django_db
    def test_creates_member_and_user_property(self, project, other_user):
        member = ensure_project_member(project, other_user, 15)
        assert member.role == 15 and member.is_active
        assert member.workspace_id == project.workspace_id
        assert ProjectUserProperty.objects.filter(project=project, user=other_user).count() == 1

    @pytest.mark.django_db
    def test_idempotent(self, project, other_user):
        first = ensure_project_member(project, other_user, 15)
        second = ensure_project_member(project, other_user.id, 15)
        assert first.id == second.id
        assert ProjectMember.objects.filter(project=project, member=other_user).count() == 1

    @pytest.mark.django_db
    def test_reactivates_inactive_row(self, project, other_user):
        member = ensure_project_member(project, other_user, 15)
        ProjectMember.objects.filter(id=member.id).update(is_active=False)
        again = ensure_project_member(project, other_user, 10)
        assert again.id == member.id
        again.refresh_from_db()
        assert again.is_active and again.role == 10

    @pytest.mark.django_db
    def test_never_downgrades_active_admin(self, project, other_user):
        ensure_project_member(project, other_user, 20)
        member = ensure_project_member(project, other_user, 10)
        member.refresh_from_db()
        assert member.role == 20 and member.is_active

    @pytest.mark.django_db
    @pytest.mark.parametrize("requested", [15, 10, 5])
    def test_reactivation_drops_stale_admin_role(self, project, other_user, requested):
        # e.g. a project admin removed from the workspace and re-invited as a guest or an agent
        member = ensure_project_member(project, other_user, 20)
        ProjectMember.objects.filter(id=member.id).update(is_active=False)
        member = ensure_project_member(project, other_user, requested, update_role=False)
        member.refresh_from_db()
        assert member.role == requested and member.is_active

    @pytest.mark.django_db
    def test_update_role_flag(self, project, other_user):
        ensure_project_member(project, other_user, 15)
        kept = ensure_project_member(project, other_user, 10, update_role=False)
        assert kept.role == 15
        changed = ensure_project_member(project, other_user, 10)
        changed.refresh_from_db()
        assert changed.role == 10
        upgraded = ensure_project_member(project, other_user, 20)
        upgraded.refresh_from_db()
        assert upgraded.role == 20

    @pytest.mark.django_db
    def test_reuses_existing_user_property(self, project, other_user):
        ProjectUserProperty.objects.create(workspace=project.workspace, project=project, user=other_user)
        member = ensure_project_member(project, other_user, 15)
        assert ProjectMember.objects.filter(id=member.id, is_active=True, role=15).exists()
        assert ProjectUserProperty.objects.filter(project=project, user=other_user).count() == 1


# ---------------------------------------------------------------- project-created hooks


HOOK_TARGETS = [
    "plane.utils.work_item_types.seed_project_work_item_types",
    "plane.utils.workflow.seed_project_workflow",
    "plane.utils.agent.sync_agent_memberships",
    "plane.utils.teams.apply_auto_join_teams",
    "plane.utils.project_defaults.apply_project_lead_defaults",
]


@pytest.mark.unit
class TestProjectCreatedHooks:
    @pytest.mark.django_db
    def test_calls_every_hook_in_order(self, project, create_user):
        calls = []
        patches = [
            mock.patch(target, side_effect=lambda *a, _t=target, **k: calls.append(_t)) for target in HOOK_TARGETS
        ]
        for p in patches:
            p.start()
        try:
            results = project_hooks.run_project_created_hooks(project, create_user)
        finally:
            for p in patches:
                p.stop()
        assert calls == HOOK_TARGETS
        assert all(results.values()) and len(results) == 5

    @pytest.mark.django_db
    def test_failing_hook_does_not_block_others(self, project, create_user):
        with (
            mock.patch(HOOK_TARGETS[1], side_effect=RuntimeError("boom")),
            mock.patch(HOOK_TARGETS[4]) as last,
        ):
            results = project_hooks.run_project_created_hooks(project, create_user)
        assert results["workflow"] is False
        assert results["project_defaults"] is True
        last.assert_called_once_with(project, create_user)

    @pytest.mark.django_db
    def test_stub_hooks_are_noops(self, project, create_user):
        results = project_hooks.run_project_created_hooks(project, create_user)
        assert set(results) == {"work_item_types", "workflow", "agents", "teams", "project_defaults"}
