/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity releases (Plane modules = Jira Fix Versions): small pure helpers shared by the list row,
// card, sidebar, quick actions and the Release modal. Type-only imports so `node --test` can load it.
import type { IModule } from "@plane/types";

export type TReleaseLozengeStatus = "unreleased" | "released" | "archived";

type TReleaseLike = Pick<IModule, "status" | "archived_at" | "target_date">;

type TReleaseCounts = Pick<
  IModule,
  "total_issues" | "completed_issues" | "cancelled_issues" | "started_issues" | "unstarted_issues" | "backlog_issues"
>;

/** Local calendar date as "YYYY-MM-DD" (the API's date format). */
export const toPayloadDate = (date: Date): string => {
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
};

/** Released = status "released"; anything else (incl. a missing/legacy value) is unreleased. */
export const isReleaseReleased = (release: Pick<IModule, "status"> | null | undefined): boolean =>
  release?.status === "released";

/** Jira lozenge: ARCHIVED wins over the status (archiving is independent of it). */
export const getReleaseLozengeStatus = (release: Pick<IModule, "status" | "archived_at">): TReleaseLozengeStatus => {
  if (release.archived_at) return "archived";
  return isReleaseReleased(release) ? "released" : "unreleased";
};

/**
 * Overdue = unreleased, not archived, and the release date (`target_date`, "YYYY-MM-DD") is before
 * today's local date.
 */
export const isReleaseOverdue = (release: TReleaseLike | null | undefined, today: Date = new Date()): boolean => {
  if (!release || release.archived_at || isReleaseReleased(release)) return false;
  const releaseDate = release.target_date?.slice(0, 10);
  if (!releaseDate) return false;
  return releaseDate < toPayloadDate(today);
};

const count = (value: number | null | undefined): number => (typeof value === "number" && value > 0 ? value : 0);

/** Unresolved work items = total − completed − cancelled (never negative). */
export const getUnresolvedCount = (release: TReleaseCounts | null | undefined): number => {
  if (!release) return 0;
  return Math.max(0, count(release.total_issues) - count(release.completed_issues) - count(release.cancelled_issues));
};

export type TReleaseProgress = {
  /** completed + cancelled */
  done: number;
  /** started */
  inProgress: number;
  /** unstarted + backlog */
  toDo: number;
  /** done + inProgress + toDo */
  total: number;
  /** Segment widths in % (0 when there is nothing to show); they add up to 100 when total > 0. */
  donePercent: number;
  inProgressPercent: number;
  toDoPercent: number;
};

/** Jira's segmented version progress: done (green), in progress (blue), to do (gray). */
export const getReleaseProgress = (release: TReleaseCounts | null | undefined): TReleaseProgress => {
  const done = count(release?.completed_issues) + count(release?.cancelled_issues);
  const inProgress = count(release?.started_issues);
  const toDo = count(release?.unstarted_issues) + count(release?.backlog_issues);
  const total = done + inProgress + toDo;
  if (total === 0) return { done, inProgress, toDo, total, donePercent: 0, inProgressPercent: 0, toDoPercent: 0 };
  const donePercent = (done / total) * 100;
  const inProgressPercent = (inProgress / total) * 100;
  return {
    done,
    inProgress,
    toDo,
    total,
    donePercent,
    inProgressPercent,
    toDoPercent: Math.max(0, 100 - donePercent - inProgressPercent),
  };
};

/** Release modal default date: the release's own release date, else today ("YYYY-MM-DD"). */
export const getDefaultReleaseDate = (
  release: Pick<IModule, "target_date"> | null | undefined,
  today: Date = new Date()
): string => release?.target_date?.slice(0, 10) || toPayloadDate(today);

/** Parses "YYYY-MM-DD" as a local date (null when missing/invalid). */
export const parsePayloadDate = (value: string | null | undefined): Date | null => {
  const match = value ? /^(\d{4})-(\d{2})-(\d{2})/.exec(value) : null;
  if (!match) return null;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(date.getTime()) ? null : date;
};

/**
 * Where a release's unresolved work items can move to: the other unreleased, non-archived releases
 * of the same project, keeping the caller's order.
 */
export const getMoveTargetReleases = <T extends Pick<IModule, "id" | "project_id" | "status" | "archived_at">>(
  releases: (T | null | undefined)[],
  current: Pick<IModule, "id" | "project_id">
): T[] =>
  releases.filter(
    (release): release is T =>
      !!release &&
      release.id !== current.id &&
      release.project_id === current.project_id &&
      !release.archived_at &&
      !isReleaseReleased(release)
  );

/** i18n keys of the release / unrelease endpoint error codes (400 `{error, code}`). */
export const RELEASE_ERROR_I18N_KEYS: Record<string, string> = {
  RELEASE_ALREADY_RELEASED: "jp_releases.errors.already_released",
  RELEASE_ARCHIVED: "jp_releases.errors.archived",
  INVALID_TARGET: "jp_releases.errors.invalid_target",
  INVALID_DATE: "jp_releases.errors.invalid_date",
  RELEASE_NOT_RELEASED: "jp_releases.errors.not_released",
};

/**
 * Best message for a release/unrelease API error (the service rejects with the response body):
 * a known `code` → its translation, else the server's `error`/`detail` string, else the fallback.
 */
export const getReleaseErrorMessage = (
  error: unknown,
  translate: (key: string) => string,
  fallback: string
): string => {
  if (!error || typeof error !== "object") return fallback;
  const data = error as Record<string, unknown>;
  const code = typeof data.code === "string" ? data.code : undefined;
  if (code && RELEASE_ERROR_I18N_KEYS[code]) return translate(RELEASE_ERROR_I18N_KEYS[code]);
  for (const key of ["error", "detail"]) {
    const value = data[key];
    if (typeof value === "string" && value) return value;
  }
  return fallback;
};

/**
 * Trigger label of a release's "start – release date" range when one end is missing, so a lone
 * release date never reads as a start date: "… - Oct 15, 2026" / "Oct 01, 2026 - …".
 */
export const formatReleaseDateRangeLabel = (formatted: { from: string; to: string }): string => {
  if (!formatted.from && !formatted.to) return "";
  return `${formatted.from || "…"} - ${formatted.to || "…"}`;
};
