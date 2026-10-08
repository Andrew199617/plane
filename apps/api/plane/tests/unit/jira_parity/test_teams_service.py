# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity teams: service layer (plane.utils.teams)."""

from uuid import uuid4

import pytest
from django.utils import timezone

from plane.db.models import Project, ProjectMember, ProjectUserProperty, Team, User, Workspace, WorkspaceMember
from plane.db.models.team import TeamMember, TeamProject, TeamProvisionedMember
from plane.utils import teams as svc
from plane.utils.jira_parity import project_hooks
from plane.utils.project_membership import ensure_project_member


def _user(workspace, role=15, *, active=True, email=None):
    user = User.objects.create(email=email or f"{uuid4().hex[:10]}@plane.so", username=uuid4().hex[:12])
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=role, is_active=active)
    return user


def _owner():
    return User.objects.create(email=f"{uuid4().hex[:10]}@plane.so", username=uuid4().hex[:12])


def _project(workspace, identifier, **kwargs):
    return Project.objects.create(name=f"Project {identifier}", identifier=identifier, workspace=workspace, **kwargs)


def _team(workspace, name="Devs", role=15, auto_join=False):
    return Team.objects.create(workspace=workspace, name=name, default_project_role=role, auto_join=auto_join)


def _pm(project, user):
    return ProjectMember.objects.filter(project=project, member=user).first()


@pytest.fixture
def project(db, workspace, create_user):
    project = _project(workspace, "TMA")
    ProjectMember.objects.create(project=project, member=create_user, role=20)
    return project


@pytest.mark.unit
class TestResolveProjectRole:
    @pytest.mark.parametrize(
        "workspace_role,team_role,expected",
        [
            (20, 5, 20),
            (20, 10, 20),
            (5, 20, 5),
            (10, 20, 10),
            (10, 15, 10),
            (15, 20, 20),
            (15, 5, 5),
            (15, 15, 15),
            (15, 10, 10),
        ],
    )
    def test_table(self, workspace_role, team_role, expected):
        assert svc.resolve_project_role(workspace_role, team_role) == expected

    def test_allowed_roles(self):
        assert svc.allowed_project_roles() == {20, 15, 10, 5}


@pytest.mark.unit
@pytest.mark.django_db
class TestProvisioning:
    def test_add_members_and_link_project(self, workspace, project):
        member, guest, agent = _user(workspace, 15), _user(workspace, 5), _user(workspace, 10)
        team = _team(workspace, role=15)
        svc.add_team_members(team, [member.id, guest.id, agent.id])
        svc.link_team_projects(team, [project.id])

        assert TeamProject.objects.filter(team=team, project=project).exists()
        assert (_pm(project, member).role, _pm(project, member).is_active) == (15, True)
        assert _pm(project, guest).role == 5
        assert _pm(project, agent).role == 10
        for user in (member, guest, agent):
            assert ProjectUserProperty.objects.filter(project=project, user=user).count() == 1
            assert TeamProvisionedMember.objects.filter(project=project, member=user).exists()

    def test_workspace_admin_always_project_admin(self, workspace, project):
        admin = _user(workspace, 20)
        team = _team(workspace, role=5)
        svc.add_team_members(team, [admin.id])
        svc.link_team_projects(team, [project.id])
        assert _pm(project, admin).role == 20

    def test_highest_role_across_teams(self, workspace, project):
        user = _user(workspace, 15)
        low, high = _team(workspace, "Low", role=5), _team(workspace, "High", role=20)
        for team in (low, high):
            svc.add_team_members(team, [user.id])
            svc.link_team_projects(team, [project.id])
        assert svc.desired_team_roles(project)[user.id] == 20
        assert _pm(project, user).role == 20

    def test_existing_membership_upgraded_never_downgraded_and_not_marked(self, workspace, project):
        manual, upgraded = _user(workspace, 15), _user(workspace, 15)
        ensure_project_member(project, manual, 15)
        ensure_project_member(project, upgraded, 5)
        team = _team(workspace, role=15)
        svc.add_team_members(team, [manual.id, upgraded.id])
        svc.link_team_projects(team, [project.id])
        assert _pm(project, manual).role == 15
        assert _pm(project, upgraded).role == 15
        assert not TeamProvisionedMember.objects.filter(project=project).exists()

        low = _team(workspace, "Low", role=5)
        svc.add_team_members(low, [manual.id])
        svc.link_team_projects(low, [project.id])
        assert _pm(project, manual).role == 15

    def test_inactive_workspace_member_not_provisioned(self, workspace, project):
        gone = _user(workspace, 15, active=False)
        team = _team(workspace)
        TeamMember.objects.create(team=team, member=gone)
        svc.link_team_projects(team, [project.id])
        assert _pm(project, gone) is None

    def test_add_non_workspace_member_rejected(self, workspace):
        other_ws = Workspace.objects.create(name="Other", slug="other-ws", owner=_owner())
        outsider = _user(other_ws, 15)
        team = _team(workspace)
        with pytest.raises(svc.TeamMembershipError) as exc:
            svc.add_team_members(team, [outsider.id])
        assert exc.value.invalid_ids == [str(outsider.id)]
        assert not TeamMember.objects.filter(team=team).exists()

    def test_all_projects_skips_archived_and_other_workspaces(self, workspace, project):
        archived = _project(workspace, "ARC", archived_at=timezone.now())
        other_ws = Workspace.objects.create(name="Other", slug="other-ws2", owner=_owner())
        foreign = _project(other_ws, "FOR")
        team = _team(workspace)
        linked = svc.link_team_projects(team, all_projects=True)
        assert [p.id for p in linked] == [project.id]
        svc.link_team_projects(team, [foreign.id])
        assert set(TeamProject.objects.filter(team=team).values_list("project_id", flat=True)) == {project.id}
        assert not TeamProject.objects.filter(project=archived).exists()

    def test_role_change_applies_but_skips_lead(self, workspace, project):
        member, lead = _user(workspace, 15), _user(workspace, 15)
        project.project_lead = lead
        project.save()
        team = _team(workspace, role=15)
        svc.add_team_members(team, [member.id, lead.id])
        svc.link_team_projects(team, [project.id])
        assert _pm(project, lead).role == 15

        team.default_project_role = 5
        team.save()
        svc.update_team_settings(team, role_changed=True)
        assert _pm(project, member).role == 5
        assert _pm(project, lead).role == 15

    def test_auto_join_enable_links_all_projects(self, workspace, project):
        second = _project(workspace, "TMB")
        user = _user(workspace, 15)
        team = _team(workspace)
        svc.add_team_members(team, [user.id])
        team.auto_join = True
        team.save()
        svc.update_team_settings(team, auto_join_enabled=True)
        assert _pm(project, user).is_active and _pm(second, user).is_active

    def test_sync_team_memberships_repairs_linked_projects_only(self, workspace, project):
        second, unlinked = _project(workspace, "TMC"), _project(workspace, "TMD")
        user = _user(workspace, 15)
        team = _team(workspace, role=15)
        svc.add_team_members(team, [user.id])
        svc.link_team_projects(team, [project.id, second.id])
        # memberships removed by hand are restored by a sync
        ProjectMember.objects.filter(member=user).update(is_active=False)

        result = svc.sync_team_memberships(team, projects=[second, unlinked.id])
        assert result == {second.id: [user.id]}
        assert _pm(second, user).is_active and not _pm(project, user).is_active
        assert _pm(unlinked, user) is None

        assert svc.sync_team_memberships(team) == {project.id: [user.id]}
        assert _pm(project, user).is_active


@pytest.mark.unit
@pytest.mark.django_db
class TestDeprovisioning:
    def test_remove_member_deactivates_team_only_memberships(self, workspace, project):
        provisioned, manual = _user(workspace, 15), _user(workspace, 15)
        ensure_project_member(project, manual, 15)
        team = _team(workspace)
        svc.add_team_members(team, [provisioned.id, manual.id])
        svc.link_team_projects(team, [project.id])

        svc.remove_team_member(team, provisioned.id)
        svc.remove_team_member(team, manual.id)
        assert _pm(project, provisioned).is_active is False
        assert _pm(project, manual).is_active is True
        assert not TeamMember.objects.filter(team=team).exists()
        assert not TeamProvisionedMember.objects.filter(project=project).exists()

    def test_still_covered_by_another_team_is_kept(self, workspace, project):
        user = _user(workspace, 15)
        first, second = _team(workspace, "A"), _team(workspace, "B")
        for team in (first, second):
            svc.add_team_members(team, [user.id])
            svc.link_team_projects(team, [project.id])
        svc.unlink_team_project(first, project.id)
        assert _pm(project, user).is_active
        assert TeamProvisionedMember.objects.filter(project=project, member=user).exists()
        svc.remove_team_member(second, user.id)
        assert _pm(project, user).is_active is False

    def test_protected_users_are_never_deactivated(self, workspace, project):
        lead, assignee, ws_admin, ws_agent = (
            _user(workspace, 15),
            _user(workspace, 15),
            _user(workspace, 20),
            _user(workspace, 10),
        )
        team = _team(workspace)
        svc.add_team_members(team, [lead.id, assignee.id, ws_admin.id, ws_agent.id])
        svc.link_team_projects(team, [project.id])
        project.project_lead = lead
        project.default_assignee = assignee
        project.save()
        svc.unlink_team_project(team, project.id)
        for user in (lead, assignee, ws_admin, ws_agent):
            assert _pm(project, user).is_active, user.email
        # markers are dropped: the memberships are now ordinary ones
        assert not TeamProvisionedMember.objects.filter(project=project).exists()

    def test_last_project_admin_is_kept(self, workspace, create_user):
        lone = _project(workspace, "SOLO")
        admin_member = _user(workspace, 15)
        team = _team(workspace, role=20)
        svc.add_team_members(team, [admin_member.id])
        svc.link_team_projects(team, [lone.id])
        assert _pm(lone, admin_member).role == 20
        svc.remove_team_member(team, admin_member.id)
        assert _pm(lone, admin_member).is_active

    def test_flags_keep_memberships(self, workspace, project):
        user, other = _user(workspace, 15), _user(workspace, 15)
        team = _team(workspace)
        svc.add_team_members(team, [user.id, other.id])
        svc.link_team_projects(team, [project.id])
        svc.remove_team_member(team, user.id, remove_from_projects=False)
        assert _pm(project, user).is_active
        assert not TeamProvisionedMember.objects.filter(project=project, member=user).exists()
        svc.unlink_team_project(team, project.id, remove_members=False)
        assert _pm(project, other).is_active

    def test_delete_team(self, workspace, project):
        user = _user(workspace, 15)
        team = _team(workspace)
        svc.add_team_members(team, [user.id])
        svc.link_team_projects(team, [project.id])
        svc.delete_team(team)
        assert not Team.all_objects.filter(pk=team.pk).exists()
        assert not TeamMember.all_objects.filter(team_id=team.pk).exists()
        assert not TeamProject.all_objects.filter(team_id=team.pk).exists()
        assert _pm(project, user).is_active is False

    def test_delete_team_keep_memberships(self, workspace, project):
        user = _user(workspace, 15)
        team = _team(workspace)
        svc.add_team_members(team, [user.id])
        svc.link_team_projects(team, [project.id])
        svc.delete_team(team, remove_from_projects=False)
        assert _pm(project, user).is_active

    def test_re_adding_reprovisions(self, workspace, project):
        user = _user(workspace, 15)
        team = _team(workspace)
        svc.add_team_members(team, [user.id])
        svc.link_team_projects(team, [project.id])
        svc.remove_team_member(team, user.id)
        assert _pm(project, user).is_active is False
        svc.add_team_members(team, [user.id])
        assert _pm(project, user).is_active
        assert ProjectMember.objects.filter(project=project, member=user).count() == 1


@pytest.mark.unit
@pytest.mark.django_db
class TestAutoJoinAndSeed:
    def test_project_created_hook(self, workspace, create_user):
        member = _user(workspace, 15)
        team = _team(workspace, role=15, auto_join=True)
        _team(workspace, "Manual", role=20)
        svc.add_team_members(team, [create_user.id, member.id])

        new_project = _project(workspace, "HOOK")
        ProjectMember.objects.create(project=new_project, member=create_user, role=20)
        results = project_hooks.run_project_created_hooks(new_project, create_user)
        assert results["teams"] is True
        assert list(TeamProject.objects.filter(project=new_project).values_list("team_id", flat=True)) == [team.id]
        assert _pm(new_project, create_user).role == 20
        assert _pm(new_project, member).role == 15

    def test_apply_auto_join_skips_archived(self, workspace):
        team = _team(workspace, auto_join=True)
        archived = _project(workspace, "ARCH", archived_at=timezone.now())
        assert svc.apply_auto_join_teams(archived) == []
        assert not TeamProject.objects.filter(team=team).exists()

    def test_seed_default_teams_idempotent(self, workspace, project, create_user):
        agent = _user(workspace, 10)
        _user(workspace, 15)
        first = svc.seed_default_teams(workspace)
        second = svc.seed_default_teams(workspace)
        assert {name: team.id for name, team in first.items()} == {name: team.id for name, team in second.items()}
        devs, agents = second["Devs"], second["Agents"]
        assert (devs.default_project_role, devs.auto_join) == (20, True)
        assert (agents.default_project_role, agents.auto_join) == (10, True)
        assert list(TeamMember.objects.filter(team=devs).values_list("member_id", flat=True)) == [create_user.id]
        assert list(TeamMember.objects.filter(team=agents).values_list("member_id", flat=True)) == [agent.id]
        assert _pm(project, agent).role == 10
        assert Team.objects.filter(workspace=workspace).count() == 2

    def test_add_member_to_default_teams(self, workspace, project):
        member = _user(workspace, 15)
        assert svc.add_member_to_default_teams(workspace, [member.id]) == {}  # teams not seeded yet
        teams = svc.seed_default_teams(workspace)
        late_agent, late_admin = _user(workspace, 10), _user(workspace, 20)

        result = svc.add_member_to_default_teams(workspace, [late_agent.id, late_admin.id, member.id])
        assert result == {"Devs": [late_admin.id], "Agents": [late_agent.id]}
        assert TeamMember.objects.filter(team=teams["Agents"], member=late_agent).exists()
        assert not TeamMember.objects.filter(member=member).exists()
        assert _pm(project, late_agent).role == 10 and _pm(project, late_admin).role == 20
        # idempotent
        assert svc.add_member_to_default_teams(workspace, [late_agent.id]) == {}
