/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: teams (owned by the teams feature)
import { API_BASE_URL } from "@plane/constants";
import type { TTeam, TTeamPayload, TTeamProjectsPayload } from "@plane/types";
import { APIService } from "@/services/api.service";

export class TeamsService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  /** GET /api/workspaces/<slug>/teams/ */
  async list(workspaceSlug: string): Promise<TTeam[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/teams/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** GET /api/workspaces/<slug>/teams/<id>/ */
  async retrieve(workspaceSlug: string, teamId: string): Promise<TTeam> {
    return this.get(`/api/workspaces/${workspaceSlug}/teams/${teamId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** POST /api/workspaces/<slug>/teams/ */
  async create(workspaceSlug: string, data: TTeamPayload): Promise<TTeam> {
    return this.post(`/api/workspaces/${workspaceSlug}/teams/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** PATCH /api/workspaces/<slug>/teams/<id>/ */
  async update(workspaceSlug: string, teamId: string, data: TTeamPayload): Promise<TTeam> {
    return this.patch(`/api/workspaces/${workspaceSlug}/teams/${teamId}/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * DELETE /api/workspaces/<slug>/teams/<id>/[?remove_from_projects=false]
   * removeFromProjects: deactivate project memberships that only existed through this team.
   */
  async destroy(workspaceSlug: string, teamId: string, removeFromProjects = true): Promise<void> {
    return this.delete(`/api/workspaces/${workspaceSlug}/teams/${teamId}/`, undefined, {
      params: { remove_from_projects: removeFromProjects },
    })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** POST /api/workspaces/<slug>/teams/<id>/projects/ {project_ids} | {all_projects: true} */
  async addProjects(workspaceSlug: string, teamId: string, data: TTeamProjectsPayload): Promise<TTeam> {
    return this.post(`/api/workspaces/${workspaceSlug}/teams/${teamId}/projects/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** DELETE /api/workspaces/<slug>/teams/<id>/projects/<project_id>/[?remove_members=false] */
  async removeProject(workspaceSlug: string, teamId: string, projectId: string, removeMembers = true): Promise<TTeam> {
    return this.delete(`/api/workspaces/${workspaceSlug}/teams/${teamId}/projects/${projectId}/`, undefined, {
      params: { remove_members: removeMembers },
    })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** POST /api/workspaces/<slug>/teams/<id>/members/ {member_ids} */
  async addMembers(workspaceSlug: string, teamId: string, memberIds: string[]): Promise<TTeam> {
    return this.post(`/api/workspaces/${workspaceSlug}/teams/${teamId}/members/`, { member_ids: memberIds })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * DELETE /api/workspaces/<slug>/teams/<id>/members/<user_id>/[?remove_from_projects=false]
   * Returns the updated team.
   */
  async removeMember(workspaceSlug: string, teamId: string, userId: string, removeFromProjects = true): Promise<TTeam> {
    return this.delete(`/api/workspaces/${workspaceSlug}/teams/${teamId}/members/${userId}/`, undefined, {
      params: { remove_from_projects: removeFromProjects },
    })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
