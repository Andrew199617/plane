/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: priorities (owned by the priorities feature)
import type { TJiraPriority } from "@plane/types";
import { DEFAULT_ISSUE_PRIORITY, ISSUE_PRIORITIES } from "../issue/common";

/** Jira priority keys ordered highest -> lowest. */
export const JP_PRIORITY_KEYS: TJiraPriority[] = ISSUE_PRIORITIES.map((priority) => priority.key);

/** Default priority for new work items. */
export const JP_DEFAULT_PRIORITY: TJiraPriority = DEFAULT_ISSUE_PRIORITY;

/** i18n key of each priority label (jp-priorities namespace). */
export const JP_PRIORITY_I18N_KEYS: Record<TJiraPriority, string> = {
  highest: "jp_priorities.highest",
  high: "jp_priorities.high",
  medium: "jp_priorities.medium",
  low: "jp_priorities.low",
  lowest: "jp_priorities.lowest",
};

/**
 * Jira (Atlassian) priority colors as hex, for charts and other places that cannot use the
 * theme-aware `text-priority-*` utilities: Highest/High red-orange, Medium amber, Low/Lowest blue.
 */
export const JP_PRIORITY_COLORS: Record<TJiraPriority, string> = {
  highest: "#DE350B",
  high: "#FF7452",
  medium: "#FFAB00",
  low: "#0065FF",
  lowest: "#4C9AFF",
};

/** Chart color for a missing/unknown priority value. */
export const JP_PRIORITY_FALLBACK_COLOR = "#CED4DA";
