/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity time tracking helpers shared by the sidebar rows, spreadsheet columns and activity.
import type { TIssue } from "@plane/types";

export type TTimeTrackingField = "original_estimate" | "remaining_estimate";

export const TIME_TRACKING_FIELDS: TTimeTrackingField[] = ["original_estimate", "remaining_estimate"];

export const isTimeTrackingField = (field: string | null | undefined): field is TTimeTrackingField =>
  field === "original_estimate" || field === "remaining_estimate";

/** Issue update payload for one estimate field (minutes, null clears it). */
export const getTimeTrackingPayload = (field: TTimeTrackingField, minutes: number | null): Partial<TIssue> =>
  field === "original_estimate" ? { original_estimate: minutes } : { remaining_estimate: minutes };

/** Activity old/new values are minutes as strings ("" when unset). */
export const parseActivityMinutes = (value: string | null | undefined): number | null => {
  if (value === null || value === undefined || value.trim() === "") return null;
  const minutes = Number(value);
  return Number.isFinite(minutes) && minutes >= 0 ? minutes : null;
};
