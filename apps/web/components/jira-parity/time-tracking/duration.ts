/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-style durations ("1w 2d 4h 30m") for Issue.original_estimate / remaining_estimate (stored in minutes).
// Kept dependency-free (type-only imports) so `node --test duration.test.mjs` can import it directly.
import type { TTimeTrackingConfig } from "@plane/types";

type TDurationUnit = "w" | "d" | "h" | "m";

/** Jira defaults: 1d = 8h, 1w = 5d. */
export const DEFAULT_DURATION_CONFIG: TTimeTrackingConfig = { hoursPerDay: 8, daysPerWeek: 5 };

/** Issue.original_estimate / remaining_estimate are PositiveIntegerField (Postgres integer). */
export const MAX_ESTIMATE_MINUTES = 2147483647;

const UNIT_ALIASES: Record<string, TDurationUnit> = {
  w: "w",
  wk: "w",
  wks: "w",
  week: "w",
  weeks: "w",
  d: "d",
  day: "d",
  days: "d",
  h: "h",
  hr: "h",
  hrs: "h",
  hour: "h",
  hours: "h",
  m: "m",
  min: "m",
  mins: "m",
  minute: "m",
  minutes: "m",
};

const SEPARATOR_REGEX = /^[\s,]*$/;
const NUMBER_ONLY_REGEX = /^\d+(?:[.,]\d+)?$/;

const toNumber = (value: string): number => Number.parseFloat(value.replace(",", "."));

export const getUnitMinutes = (unit: TDurationUnit, config: TTimeTrackingConfig = DEFAULT_DURATION_CONFIG): number => {
  switch (unit) {
    case "w":
      return 60 * config.hoursPerDay * config.daysPerWeek;
    case "d":
      return 60 * config.hoursPerDay;
    case "h":
      return 60;
    default:
      return 1;
  }
};

export type TParseDurationResult = { ok: true; minutes: number | null } | { ok: false };

/**
 * Parse a Jira-style duration into minutes.
 * - "" (or whitespace) -> { ok: true, minutes: null } (clears the estimate)
 * - "1w 2d 4h 30m", "4h30m", "1.5h", "2 days, 3 hours" -> minutes (rounded)
 * - a bare number is minutes, like Jira's default time unit ("90" -> 90)
 * - anything else -> { ok: false }
 */
export const parseDuration = (
  input: string | null | undefined,
  config: TTimeTrackingConfig = DEFAULT_DURATION_CONFIG
): TParseDurationResult => {
  const text = (input ?? "").trim().toLowerCase();
  if (text === "") return { ok: true, minutes: null };

  let total = 0;
  if (NUMBER_ONLY_REGEX.test(text)) {
    total = toNumber(text);
  } else {
    const tokenRegex = /(\d+(?:[.,]\d+)?)\s*([a-z]+)/g;
    let lastIndex = 0;
    let tokenCount = 0;
    let match: RegExpExecArray | null;
    while ((match = tokenRegex.exec(text)) !== null) {
      if (!SEPARATOR_REGEX.test(text.slice(lastIndex, match.index))) return { ok: false };
      const unit = UNIT_ALIASES[match[2]];
      if (!unit) return { ok: false };
      total += toNumber(match[1]) * getUnitMinutes(unit, config);
      lastIndex = tokenRegex.lastIndex;
      tokenCount += 1;
    }
    if (tokenCount === 0 || !SEPARATOR_REGEX.test(text.slice(lastIndex))) return { ok: false };
  }

  const minutes = Math.round(total);
  if (!Number.isFinite(minutes) || minutes < 0 || minutes > MAX_ESTIMATE_MINUTES) return { ok: false };
  return { ok: true, minutes };
};

/**
 * Format minutes as a Jira-style duration: 3630 -> "1w 2d 4h 30m" (8h days, 5d weeks), 0 -> "0m".
 * null / undefined / invalid -> "" (callers render their own placeholder).
 */
export const formatDuration = (
  minutes: number | null | undefined,
  config: TTimeTrackingConfig = DEFAULT_DURATION_CONFIG
): string => {
  if (minutes === null || minutes === undefined || !Number.isFinite(minutes) || minutes < 0) return "";
  let remaining = Math.round(minutes);
  if (remaining === 0) return "0m";

  const parts: string[] = [];
  for (const unit of ["w", "d", "h", "m"] as const) {
    const size = getUnitMinutes(unit, config);
    if (size <= 0) continue;
    const count = Math.floor(remaining / size);
    if (count > 0) {
      parts.push(`${count}${unit}`);
      remaining -= count * size;
    }
  }
  return parts.join(" ");
};
