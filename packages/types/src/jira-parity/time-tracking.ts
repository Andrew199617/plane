/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: time tracking (owned by the time-tracking feature)

/** Estimate in minutes (Issue.original_estimate / Issue.remaining_estimate), null when unset. */
export type TTimeEstimateMinutes = number | null;

/** Time tracking fields carried by work items (also declared as optional fields on TBaseIssue). */
export type TIssueTimeTracking = {
  original_estimate: TTimeEstimateMinutes;
  remaining_estimate: TTimeEstimateMinutes;
};

/** Jira-like duration settings used to format/parse "1w 2d 4h 30m". */
export type TTimeTrackingConfig = {
  hoursPerDay: number;
  daysPerWeek: number;
};
