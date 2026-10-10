/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: project categories & master boards (owned by the project-categories feature)
import type { AxiosRequestConfig } from "axios";
import { API_BASE_URL } from "@plane/constants";
import type { TIssuesResponse, TProjectCategory, TProjectCategoryCycle, TProjectCategoryPayload } from "@plane/types";
import { APIService } from "@/services/api.service";

export class ProjectCategoriesService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  /** GET /api/workspaces/<slug>/project-categories/ */
  async list(workspaceSlug: string): Promise<TProjectCategory[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/project-categories/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** GET /api/workspaces/<slug>/project-categories/<id>/ */
  async retrieve(workspaceSlug: string, categoryId: string): Promise<TProjectCategory> {
    return this.get(`/api/workspaces/${workspaceSlug}/project-categories/${categoryId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** POST /api/workspaces/<slug>/project-categories/ */
  async create(workspaceSlug: string, data: TProjectCategoryPayload): Promise<TProjectCategory> {
    return this.post(`/api/workspaces/${workspaceSlug}/project-categories/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** PATCH /api/workspaces/<slug>/project-categories/<id>/ */
  async update(workspaceSlug: string, categoryId: string, data: TProjectCategoryPayload): Promise<TProjectCategory> {
    return this.patch(`/api/workspaces/${workspaceSlug}/project-categories/${categoryId}/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** DELETE /api/workspaces/<slug>/project-categories/<id>/ */
  async destroy(workspaceSlug: string, categoryId: string): Promise<void> {
    return this.delete(`/api/workspaces/${workspaceSlug}/project-categories/${categoryId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * GET /api/workspaces/<slug>/project-categories/<id>/issues/
   * Same params/response as the workspace issues endpoint (grouped + paginated), scoped to the category's
   * projects; additionally supports group_by/sub_group_by "state__name" and cycle_name=<name>[,<name>].
   */
  async getIssues(
    workspaceSlug: string,
    categoryId: string,
    params: Record<string, unknown>,
    config: AxiosRequestConfig = {}
  ): Promise<TIssuesResponse> {
    return this.get(`/api/workspaces/${workspaceSlug}/project-categories/${categoryId}/issues/`, { params }, config)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** GET /api/workspaces/<slug>/project-categories/<id>/cycles/ — distinct cycles (sprints) by name. */
  async listCycles(workspaceSlug: string, categoryId: string): Promise<TProjectCategoryCycle[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/project-categories/${categoryId}/cycles/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
