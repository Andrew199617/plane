/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: agents (owned by the agents feature)
import { API_BASE_URL } from "@plane/constants";
import type {
  TWorkspaceAgent,
  TWorkspaceAgentCreatePayload,
  TWorkspaceAgentCreateResponse,
  TWorkspaceAgentTokenCreatePayload,
  TWorkspaceAgentTokenCreateResponse,
  TWorkspaceAgentUpdatePayload,
} from "@plane/types";
import { APIService } from "@/services/api.service";

export class AgentsService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  /** GET /api/workspaces/<slug>/agents/ */
  async list(workspaceSlug: string): Promise<TWorkspaceAgent[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/agents/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** POST /api/workspaces/<slug>/agents/ — the response carries the token once. */
  async create(workspaceSlug: string, data: TWorkspaceAgentCreatePayload): Promise<TWorkspaceAgentCreateResponse> {
    return this.post(`/api/workspaces/${workspaceSlug}/agents/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** PATCH /api/workspaces/<slug>/agents/<user_id>/ */
  async update(workspaceSlug: string, userId: string, data: TWorkspaceAgentUpdatePayload): Promise<TWorkspaceAgent> {
    return this.patch(`/api/workspaces/${workspaceSlug}/agents/${userId}/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** DELETE /api/workspaces/<slug>/agents/<user_id>/ (deactivates the agent and its tokens) */
  async destroy(workspaceSlug: string, userId: string): Promise<void> {
    return this.delete(`/api/workspaces/${workspaceSlug}/agents/${userId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** POST /api/workspaces/<slug>/agents/<user_id>/tokens/ — returns {token} once. */
  async createToken(
    workspaceSlug: string,
    userId: string,
    data: TWorkspaceAgentTokenCreatePayload = {}
  ): Promise<TWorkspaceAgentTokenCreateResponse> {
    return this.post(`/api/workspaces/${workspaceSlug}/agents/${userId}/tokens/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** DELETE /api/workspaces/<slug>/agents/<user_id>/tokens/<token_id>/ */
  async revokeToken(workspaceSlug: string, userId: string, tokenId: string): Promise<void> {
    return this.delete(`/api/workspaces/${workspaceSlug}/agents/${userId}/tokens/${tokenId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
