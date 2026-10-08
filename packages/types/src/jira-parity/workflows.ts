/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: state transition workflows (owned by the workflows feature)

/**
 * One transition rule of a project.
 * GET/PUT /api/workspaces/<slug>/projects/<project_id>/state-transitions/
 * `from_state_id: null` means "from any state". `roles` are numeric roles (20 Admin, 15 Member, 10 Agent, 5 Guest).
 */
export type TStateTransitionRule = {
  id?: string;
  from_state_id: string | null;
  to_state_id: string;
  roles: number[];
  exclude_epics: boolean;
};

/** PUT body: replaces all rules of the project. */
export type TStateTransitionReplacePayload = TStateTransitionRule[];

/**
 * GET /api/workspaces/<slug>/projects/<project_id>/state-transitions/me/
 * `transitions` maps from_state_id -> allowed to_state_ids for the current user.
 */
export type TMyStateTransitions =
  | {
      restricted: false;
    }
  | {
      restricted: true;
      role: number;
      /** Epics can never change state for this role (agents). */
      epic_locked: boolean;
      /** Allowed targets for work items that are not epics. */
      transitions: Record<string, string[]>;
      /** Allowed targets for epics (rules with exclude_epics=true do not apply to epics). */
      epic_transitions?: Record<string, string[]>;
    };

/** Known `code` values of HTTP 403 responses from forbidden transitions / agent writes. */
export type TJiraParityForbiddenCode =
  | "STATE_TRANSITION_NOT_ALLOWED"
  | "AGENT_EPIC_STATE_CHANGE_FORBIDDEN"
  | "AGENT_FIELD_NOT_ALLOWED";

/** Shape of HTTP 403 error bodies: {"error": "...", "code": "..."} */
export type TJiraParityApiError = {
  error: string;
  code?: TJiraParityForbiddenCode | string;
};
