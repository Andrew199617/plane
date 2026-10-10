/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: work item types (owned by the work-item-types feature)
import { API_BASE_URL } from "@plane/constants";
import type { TWorkItemType, TWorkItemTypePayload } from "@plane/types";
import { APIService } from "@/services/api.service";

export class WorkItemTypesService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  /** GET /api/workspaces/<slug>/work-item-types/ */
  async list(workspaceSlug: string): Promise<TWorkItemType[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/work-item-types/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** GET /api/workspaces/<slug>/work-item-types/<id>/ */
  async retrieve(workspaceSlug: string, workItemTypeId: string): Promise<TWorkItemType> {
    return this.get(`/api/workspaces/${workspaceSlug}/work-item-types/${workItemTypeId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** POST /api/workspaces/<slug>/work-item-types/ (workspace admin) */
  async create(workspaceSlug: string, data: TWorkItemTypePayload): Promise<TWorkItemType> {
    return this.post(`/api/workspaces/${workspaceSlug}/work-item-types/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** PATCH /api/workspaces/<slug>/work-item-types/<id>/ (workspace admin) */
  async update(workspaceSlug: string, workItemTypeId: string, data: TWorkItemTypePayload): Promise<TWorkItemType> {
    return this.patch(`/api/workspaces/${workspaceSlug}/work-item-types/${workItemTypeId}/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** DELETE /api/workspaces/<slug>/work-item-types/<id>/ (workspace admin) */
  async destroy(workspaceSlug: string, workItemTypeId: string): Promise<void> {
    return this.delete(`/api/workspaces/${workspaceSlug}/work-item-types/${workItemTypeId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** GET /api/workspaces/<slug>/projects/<project_id>/work-item-types/ (types enabled for the project) */
  async listProjectWorkItemTypes(workspaceSlug: string, projectId: string): Promise<TWorkItemType[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/work-item-types/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
