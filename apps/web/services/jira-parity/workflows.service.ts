/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: workflows (owned by the workflows feature)
import { API_BASE_URL } from "@plane/constants";
import type { IProject, TMyStateTransitions, TStateTransitionReplacePayload, TStateTransitionRule } from "@plane/types";
import { APIService } from "@/services/api.service";

export class WorkflowsService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  /** GET /api/workspaces/<slug>/projects/<project_id>/state-transitions/ */
  async listTransitions(workspaceSlug: string, projectId: string): Promise<TStateTransitionRule[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/state-transitions/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** PUT /api/workspaces/<slug>/projects/<project_id>/state-transitions/ — replaces all rules. */
  async replaceTransitions(
    workspaceSlug: string,
    projectId: string,
    rules: TStateTransitionReplacePayload
  ): Promise<TStateTransitionRule[]> {
    return this.put(`/api/workspaces/${workspaceSlug}/projects/${projectId}/state-transitions/`, rules)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** GET /api/workspaces/<slug>/projects/<project_id>/state-transitions/me/ */
  async getMyTransitions(workspaceSlug: string, projectId: string): Promise<TMyStateTransitions> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/state-transitions/me/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** PATCH /api/workspaces/<slug>/projects/<project_id>/ {is_workflow_enabled} */
  async setWorkflowEnabled(workspaceSlug: string, projectId: string, isEnabled: boolean): Promise<IProject> {
    return this.patch(`/api/workspaces/${workspaceSlug}/projects/${projectId}/`, { is_workflow_enabled: isEnabled })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
