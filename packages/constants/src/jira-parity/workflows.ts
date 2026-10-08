/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: workflows (owned by the workflows feature)

/** `code` values of HTTP 403 responses for forbidden state transitions / agent writes. */
export const JP_FORBIDDEN_CODES = {
  STATE_TRANSITION_NOT_ALLOWED: "STATE_TRANSITION_NOT_ALLOWED",
  AGENT_EPIC_STATE_CHANGE_FORBIDDEN: "AGENT_EPIC_STATE_CHANGE_FORBIDDEN",
  AGENT_FIELD_NOT_ALLOWED: "AGENT_FIELD_NOT_ALLOWED",
} as const;

/** SWR key for a project's transition rules (settings page). */
export const JP_PROJECT_STATE_TRANSITIONS_SWR_KEY = (projectId: string) => `JP_PROJECT_STATE_TRANSITIONS_${projectId}`;

/** SWR key for the current user's allowed transitions in a project. */
export const JP_MY_STATE_TRANSITIONS_SWR_KEY = (projectId: string) => `JP_MY_STATE_TRANSITIONS_${projectId}`;
