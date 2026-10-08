/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: agent accounts (owned by the agents feature)

export type TWorkspaceAgentMember = {
  id: string;
  display_name: string;
  first_name: string;
  last_name: string;
  email: string;
  avatar_url: string | null;
};

export type TWorkspaceAgentToken = {
  id: string;
  label: string;
  last_used: string | null;
  expired_at: string | null;
  is_active: boolean;
  created_at: string;
};

/** Row returned by GET /api/workspaces/<slug>/agents/ (`id` is the workspace member id, `member.id` the user id). */
export type TWorkspaceAgent = {
  id: string;
  member: TWorkspaceAgentMember;
  role: number;
  project_count: number;
  tokens: TWorkspaceAgentToken[];
};

/** Body for POST /api/workspaces/<slug>/agents/ */
export type TWorkspaceAgentCreatePayload = {
  display_name: string;
  email?: string;
  first_name?: string;
  last_name?: string;
  generate_token?: boolean;
  token_label?: string;
};

/** 201 response of POST /api/workspaces/<slug>/agents/ — `token` is only returned once. */
export type TWorkspaceAgentCreateResponse = TWorkspaceAgent & {
  token?: string;
};

/** Body for PATCH /api/workspaces/<slug>/agents/<user_id>/ */
export type TWorkspaceAgentUpdatePayload = Partial<
  Pick<TWorkspaceAgentMember, "display_name" | "first_name" | "last_name">
>;

/** Body for POST /api/workspaces/<slug>/agents/<user_id>/tokens/ */
export type TWorkspaceAgentTokenCreatePayload = {
  label?: string;
};

/** Response of POST /api/workspaces/<slug>/agents/<user_id>/tokens/ — `token` is only returned once. */
export type TWorkspaceAgentTokenCreateResponse = Partial<TWorkspaceAgentToken> & {
  token: string;
};
