/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity sprints: pure helpers (no runtime imports, unit-tested with Node's runner in helpers.test.mjs).
// Sprint states are explicit and never date-driven: future (UPCOMING / DRAFT), active (CURRENT), closed (COMPLETED).
import type { ICycle, TSprintMoveTarget } from "@plane/types";

export type TSprintState = "future" | "active" | "closed";

export type TSprintDuration = "1w" | "2w" | "3w" | "4w" | "custom";

export const SPRINT_DURATIONS: TSprintDuration[] = ["1w", "2w", "3w", "4w", "custom"];

export const DEFAULT_SPRINT_DURATION: TSprintDuration = "2w";

/** i18n key of a duration option label. */
export const SPRINT_DURATION_I18N: Record<TSprintDuration, string> = {
  "1w": "jp_sprints.duration.one_week",
  "2w": "jp_sprints.duration.two_weeks",
  "3w": "jp_sprints.duration.three_weeks",
  "4w": "jp_sprints.duration.four_weeks",
  custom: "jp_sprints.duration.custom",
};

const DURATION_WEEKS: Record<Exclude<TSprintDuration, "custom">, number> = { "1w": 1, "2w": 2, "3w": 3, "4w": 4 };

const DATE_KEY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;
const DAY_MS = 24 * 60 * 60 * 1000;

const pad = (value: number) => String(value).padStart(2, "0");

/** `YYYY-MM-DD` of a local calendar day. */
export const toDateKey = (date: Date): string =>
  `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

/** Local midnight of a `YYYY-MM-DD` key (also accepts an ISO datetime and keeps its date part); null if invalid. */
export const parseDateKey = (value: string | null | undefined): Date | null => {
  if (!value) return null;
  const match = DATE_KEY_PATTERN.exec(value.slice(0, 10));
  if (!match) return null;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null;
  return date;
};

/** Normalises a date-ish value (`YYYY-MM-DD`, ISO datetime) to a `YYYY-MM-DD` key, or null. */
export const normalizeDateKey = (value: string | null | undefined): string | null => {
  const date = parseDateKey(value);
  return date ? toDateKey(date) : null;
};

/** Adds whole calendar days to a `YYYY-MM-DD` key (DST-safe). */
export const addDaysToKey = (key: string, days: number): string | null => {
  const date = parseDateKey(key);
  if (!date) return null;
  return toDateKey(new Date(date.getFullYear(), date.getMonth(), date.getDate() + days));
};

/** Calendar days from `startKey` to `endKey` (0 when equal, negative when the end is before the start). */
export const daysBetweenKeys = (startKey: string, endKey: string): number | null => {
  const start = parseDateKey(startKey);
  const end = parseDateKey(endKey);
  if (!start || !end) return null;
  const startUtc = Date.UTC(start.getFullYear(), start.getMonth(), start.getDate());
  const endUtc = Date.UTC(end.getFullYear(), end.getMonth(), end.getDate());
  return Math.round((endUtc - startUtc) / DAY_MS);
};

/** End date of a sprint: start + duration - 1 day (null for "custom" or an invalid start). */
export const getSprintEndDate = (startKey: string | null | undefined, duration: TSprintDuration): string | null => {
  if (!startKey || duration === "custom") return null;
  return addDaysToKey(startKey, DURATION_WEEKS[duration] * 7 - 1);
};

/** Duration option matching planned dates (1-4 whole weeks), else "custom"; the default when a date is missing. */
export const inferSprintDuration = (
  startKey: string | null | undefined,
  endKey: string | null | undefined
): TSprintDuration => {
  if (!startKey || !endKey) return DEFAULT_SPRINT_DURATION;
  const days = daysBetweenKeys(startKey, endKey);
  if (days === null) return DEFAULT_SPRINT_DURATION;
  const match = (Object.keys(DURATION_WEEKS) as Exclude<TSprintDuration, "custom">[]).find(
    (duration) => DURATION_WEEKS[duration] * 7 === days + 1
  );
  return match ?? "custom";
};

/** True when both dates are set and the end is on or after the start. */
export const isValidSprintRange = (startKey: string | null | undefined, endKey: string | null | undefined): boolean => {
  if (!startKey || !endKey) return false;
  const days = daysBetweenKeys(startKey, endKey);
  return days !== null && days >= 0;
};

export type TStartSprintFormValues = {
  name: string;
  description: string;
  duration: TSprintDuration;
  start_date: string;
  end_date: string | null;
};

/**
 * Initial values of the Start sprint form: the sprint's own name / goal / planned dates when it has them (duration
 * inferred), else today + the default duration.
 */
export const getStartSprintDefaults = (
  cycle: Pick<ICycle, "name" | "description" | "start_date" | "end_date"> | null | undefined,
  todayKey: string
): TStartSprintFormValues => {
  const plannedStart = normalizeDateKey(cycle?.start_date);
  const plannedEnd = normalizeDateKey(cycle?.end_date);
  const hasPlannedRange = isValidSprintRange(plannedStart, plannedEnd);
  const start = plannedStart ?? todayKey;
  return {
    name: cycle?.name ?? "",
    description: cycle?.description ?? "",
    duration: hasPlannedRange ? inferSprintDuration(plannedStart, plannedEnd) : DEFAULT_SPRINT_DURATION,
    start_date: start,
    end_date: hasPlannedRange ? plannedEnd : getSprintEndDate(start, DEFAULT_SPRINT_DURATION),
  };
};

type TSprintLike = Pick<ICycle, "status" | "archived_at"> & Partial<Pick<ICycle, "started_at" | "completed_at">>;

/** Sprint state from the server status (with the explicit timestamps as a fallback). */
export const getSprintState = (cycle: TSprintLike | null | undefined): TSprintState => {
  const status = cycle?.status?.toLowerCase();
  if (status === "completed" || cycle?.completed_at) return "closed";
  if (status === "current" || cycle?.started_at) return "active";
  return "future";
};

export const isFutureSprint = (cycle: TSprintLike | null | undefined) =>
  !!cycle && !cycle.archived_at && getSprintState(cycle) === "future";

export const isActiveSprint = (cycle: TSprintLike | null | undefined) =>
  !!cycle && !cycle.archived_at && getSprintState(cycle) === "active";

export const isClosedSprint = (cycle: TSprintLike | null | undefined) => !!cycle && getSprintState(cycle) === "closed";

type TOrderableSprint = Pick<ICycle, "id" | "name" | "sort_order" | "start_date">;

/** Future sprints in backlog order: sort order, then planned start (undated last), then name. */
export const sortFutureSprints = <T extends TOrderableSprint>(cycles: T[]): T[] =>
  // oxlint-disable-next-line unicorn/no-array-sort -- sorts a copy; web targets ES2022 (no toSorted)
  [...cycles].sort((a, b) => {
    const bySortOrder = (a.sort_order ?? 0) - (b.sort_order ?? 0);
    if (bySortOrder !== 0) return bySortOrder;
    const aStart = normalizeDateKey(a.start_date);
    const bStart = normalizeDateKey(b.start_date);
    if (aStart !== bStart) {
      if (!aStart) return 1;
      if (!bStart) return -1;
      return aStart < bStart ? -1 : 1;
    }
    return a.name.localeCompare(b.name);
  });

/** Default "move open work items to" target: the first future sprint, else a new sprint. */
export const getDefaultMoveTarget = (futureSprintIds: string[]): TSprintMoveTarget => futureSprintIds[0] ?? "new";

type TSprintCounts = Partial<
  Pick<
    ICycle,
    "total_issues" | "completed_issues" | "cancelled_issues" | "backlog_issues" | "unstarted_issues" | "started_issues"
  >
>;

/** Done (completed + cancelled groups) vs open (backlog + unstarted + started) work items of a sprint. */
export const getSprintIssueSummary = (cycle: TSprintCounts | null | undefined): { done: number; open: number } => {
  const done = (cycle?.completed_issues ?? 0) + (cycle?.cancelled_issues ?? 0);
  const hasGroupCounts =
    cycle?.backlog_issues !== undefined || cycle?.unstarted_issues !== undefined || cycle?.started_issues !== undefined;
  const open = hasGroupCounts
    ? (cycle?.backlog_issues ?? 0) + (cycle?.unstarted_issues ?? 0) + (cycle?.started_issues ?? 0)
    : Math.max(0, (cycle?.total_issues ?? 0) - done);
  return { done, open };
};

/** Human-readable message of a failed start / complete request (server `error`, then DRF shapes, then fallback). */
export const getSprintErrorMessage = (error: unknown, fallback: string): string => {
  if (!error || typeof error !== "object") return fallback;
  const data = error as Record<string, unknown>;
  for (const key of ["error", "detail", "name", "start_date", "end_date", "move_to", "non_field_errors"]) {
    const value = data[key];
    if (typeof value === "string" && value.trim()) return value;
    if (Array.isArray(value) && typeof value[0] === "string") return value[0];
  }
  return fallback;
};
