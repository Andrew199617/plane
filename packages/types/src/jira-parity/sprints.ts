/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity sprints (Plane cycles with an explicit Start / Complete lifecycle). Owned by the sprints feature.
import type { ICycle } from "../cycle";

/** Where the open work items of a completed sprint go: the backlog, a new sprint, or a future sprint id. */
export type TSprintMoveTarget = "backlog" | "new" | (string & {});

/** Body of `POST cycles/{id}/start/` (dates are `YYYY-MM-DD`). */
export type TSprintStartPayload = {
  name?: string;
  description?: string;
  start_date: string;
  end_date: string;
};

/** Body of `POST cycles/{id}/complete/`. */
export type TSprintCompletePayload = {
  move_to: TSprintMoveTarget;
};

/** Response of `POST cycles/{id}/complete/`. */
export type TSprintCompleteResponse = {
  cycle: ICycle;
  moved_issues: number;
  moved_to: { id: string; name: string } | null;
  new_sprint: ICycle | null;
};

/** Response of `GET sprints/next-name/`. */
export type TSprintNextName = {
  name: string;
};

/** `code` of a 400 from the start / complete endpoints. */
export type TSprintErrorCode =
  | "SPRINT_ALREADY_STARTED"
  | "SPRINT_COMPLETED"
  | "ACTIVE_SPRINT_EXISTS"
  | "INVALID_DATES"
  | "SPRINT_ARCHIVED"
  | "SPRINT_NOT_STARTED"
  | "INVALID_TARGET";

/** Error body of the start / complete endpoints. */
export type TSprintError = {
  error?: string;
  code?: TSprintErrorCode;
  active_sprint?: { id: string; name: string };
};
