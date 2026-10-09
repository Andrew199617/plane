/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: teams store (owned by the teams feature)
import { set, sortBy, unset } from "lodash-es";
import { action, computed, makeObservable, observable, runInAction } from "mobx";
import { computedFn } from "mobx-utils";
// plane imports
import type { TTeam, TTeamPayload, TTeamProjectsPayload } from "@plane/types";
// services
import { TeamsService } from "@/services/jira-parity/teams.service";
// store
import type { CoreRootStore } from "@/store/root.store";

export interface ITeamsStore {
  // observables
  teamMap: Record<string, TTeam>;
  fetchedWorkspaceSlug: string | null;
  // computed
  sortedTeams: TTeam[];
  // computed actions
  getTeamById: (teamId: string | null | undefined) => TTeam | undefined;
  getTeamsByMemberId: (userId: string | null | undefined) => TTeam[];
  getTeamsByProjectId: (projectId: string | null | undefined) => TTeam[];
  // fetch actions
  fetchTeams: (workspaceSlug: string) => Promise<TTeam[]>;
  // crud actions
  createTeam: (workspaceSlug: string, data: TTeamPayload) => Promise<TTeam>;
  updateTeam: (workspaceSlug: string, teamId: string, data: TTeamPayload) => Promise<TTeam>;
  deleteTeam: (workspaceSlug: string, teamId: string, removeFromProjects?: boolean) => Promise<void>;
  addTeamMembers: (workspaceSlug: string, teamId: string, memberIds: string[]) => Promise<TTeam>;
  removeTeamMember: (
    workspaceSlug: string,
    teamId: string,
    userId: string,
    removeFromProjects?: boolean
  ) => Promise<TTeam>;
  addTeamProjects: (workspaceSlug: string, teamId: string, data: TTeamProjectsPayload) => Promise<TTeam>;
  removeTeamProject: (
    workspaceSlug: string,
    teamId: string,
    projectId: string,
    removeMembers?: boolean
  ) => Promise<TTeam>;
}

export class TeamsStore implements ITeamsStore {
  // observables
  teamMap: Record<string, TTeam> = {};
  fetchedWorkspaceSlug: string | null = null;
  // root store
  rootStore: CoreRootStore;
  // services
  service: TeamsService;

  constructor(rootStore: CoreRootStore) {
    makeObservable(this, {
      teamMap: observable,
      fetchedWorkspaceSlug: observable.ref,
      sortedTeams: computed,
      fetchTeams: action,
      createTeam: action,
      updateTeam: action,
      deleteTeam: action,
      addTeamMembers: action,
      removeTeamMember: action,
      addTeamProjects: action,
      removeTeamProject: action,
    });
    this.rootStore = rootStore;
    this.service = new TeamsService();
  }

  get sortedTeams() {
    return sortBy(Object.values(this.teamMap), (team) => team.name.toLowerCase());
  }

  getTeamById = computedFn((teamId: string | null | undefined) => (teamId ? this.teamMap[teamId] : undefined));

  getTeamsByMemberId = computedFn((userId: string | null | undefined) =>
    userId ? this.sortedTeams.filter((team) => team.member_ids.includes(userId)) : []
  );

  getTeamsByProjectId = computedFn((projectId: string | null | undefined) =>
    projectId ? this.sortedTeams.filter((team) => team.project_ids.includes(projectId)) : []
  );

  /** Store the server's copy of a team (every mutation endpoint returns the refreshed team). */
  private upsertTeam = (team: TTeam) => {
    runInAction(() => {
      set(this.teamMap, [team.id], team);
    });
    return team;
  };

  /**
   * Team changes create/reactivate/deactivate project memberships on the server: refresh the
   * stores that cache them (project list + member_role, project permissions, open project roster).
   */
  private refreshMemberships = (workspaceSlug: string) => {
    const { projectRoot, user, router, memberRoot } = this.rootStore;
    void projectRoot.project.fetchPartialProjects(workspaceSlug).catch(() => undefined);
    void user.permission.fetchUserProjectPermissions(workspaceSlug).catch(() => undefined);
    const projectId = router.projectId;
    if (projectId) void memberRoot.project.fetchProjectMembers(workspaceSlug, projectId, true).catch(() => undefined);
  };

  fetchTeams = async (workspaceSlug: string) => {
    // never serve another workspace's teams while this workspace loads
    if (this.fetchedWorkspaceSlug !== workspaceSlug)
      runInAction(() => {
        this.teamMap = {};
        this.fetchedWorkspaceSlug = null;
      });
    const teams = await this.service.list(workspaceSlug);
    // a late response for a workspace the user has left must not replace the current one
    const routedWorkspaceSlug = this.rootStore.router.workspaceSlug;
    if (routedWorkspaceSlug && routedWorkspaceSlug !== workspaceSlug) return teams;
    runInAction(() => {
      this.teamMap = Object.fromEntries(teams.map((team) => [team.id, team]));
      this.fetchedWorkspaceSlug = workspaceSlug;
    });
    return teams;
  };

  createTeam = async (workspaceSlug: string, data: TTeamPayload) => {
    const team = this.upsertTeam(await this.service.create(workspaceSlug, data));
    if (team.member_count > 0 && team.project_count > 0) this.refreshMemberships(workspaceSlug);
    return team;
  };

  updateTeam = async (workspaceSlug: string, teamId: string, data: TTeamPayload) => {
    const team = this.upsertTeam(await this.service.update(workspaceSlug, teamId, data));
    const affectsMemberships = ["default_project_role", "auto_join", "member_ids", "project_ids"].some(
      (key) => key in data
    );
    if (affectsMemberships) this.refreshMemberships(workspaceSlug);
    return team;
  };

  deleteTeam = async (workspaceSlug: string, teamId: string, removeFromProjects = true) => {
    await this.service.destroy(workspaceSlug, teamId, removeFromProjects);
    runInAction(() => {
      unset(this.teamMap, [teamId]);
    });
    if (removeFromProjects) this.refreshMemberships(workspaceSlug);
  };

  addTeamMembers = async (workspaceSlug: string, teamId: string, memberIds: string[]) => {
    const team = this.upsertTeam(await this.service.addMembers(workspaceSlug, teamId, memberIds));
    this.refreshMemberships(workspaceSlug);
    return team;
  };

  removeTeamMember = async (workspaceSlug: string, teamId: string, userId: string, removeFromProjects = true) => {
    const team = this.upsertTeam(await this.service.removeMember(workspaceSlug, teamId, userId, removeFromProjects));
    this.refreshMemberships(workspaceSlug);
    return team;
  };

  addTeamProjects = async (workspaceSlug: string, teamId: string, data: TTeamProjectsPayload) => {
    const team = this.upsertTeam(await this.service.addProjects(workspaceSlug, teamId, data));
    this.refreshMemberships(workspaceSlug);
    return team;
  };

  removeTeamProject = async (workspaceSlug: string, teamId: string, projectId: string, removeMembers = true) => {
    const team = this.upsertTeam(await this.service.removeProject(workspaceSlug, teamId, projectId, removeMembers));
    this.refreshMemberships(workspaceSlug);
    return team;
  };
}
