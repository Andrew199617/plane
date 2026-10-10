/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: work item types (owned by the work-item-types feature)
import type { TWorkItemTypeIconKey } from "@plane/types";

/** SWR key for the workspace work item types list. */
export const JP_WORK_ITEM_TYPES_SWR_KEY = (workspaceSlug: string) => `JP_WORK_ITEM_TYPES_${workspaceSlug}`;

/** SWR key for the work item types enabled in a project. */
export const JP_PROJECT_WORK_ITEM_TYPES_SWR_KEY = (projectId: string) => `JP_PROJECT_WORK_ITEM_TYPES_${projectId}`;

/** Jira-like colors for the standard work item types (by name). */
export const JP_WORK_ITEM_TYPE_COLORS: Record<string, string> = {
  Task: "#4BADE8",
  "Sub-task": "#4BADE8",
  Story: "#E97F33",
  Bug: "#E5493A",
  Epic: "#904EE2",
};

/** Fallback color of a work item type without a usable logo color. */
export const JP_DEFAULT_WORK_ITEM_TYPE_COLOR = "#4BADE8";

/** Jira glyphs offered by the work item type icon picker, in display order. */
export const JP_WORK_ITEM_TYPE_ICON_KEYS: TWorkItemTypeIconKey[] = ["task", "story", "bug", "sub_task", "epic"];

/** Default color of each Jira glyph. */
export const JP_WORK_ITEM_TYPE_ICON_DEFAULT_COLORS: Record<TWorkItemTypeIconKey, string> = {
  task: "#4BADE8",
  sub_task: "#4BADE8",
  story: "#E97F33",
  bug: "#E5493A",
  epic: "#904EE2",
};

/**
 * Material Symbols ligature stored in `logo_props.icon.name` for each Jira glyph. The web app maps it
 * back to its own SVG glyph; other renderers (generic `Logo`) still draw a close Material icon.
 */
export const JP_WORK_ITEM_TYPE_ICON_LOGO_NAMES: Record<TWorkItemTypeIconKey, string> = {
  task: "check_box",
  sub_task: "subdirectory_arrow_right",
  story: "priority_high",
  bug: "bug_report",
  epic: "bolt",
};

/** `logo_props.icon.name` values (lowercase) recognised as a Jira glyph. */
export const JP_WORK_ITEM_TYPE_ICON_ALIASES: Record<string, TWorkItemTypeIconKey> = {
  // task
  task: "task",
  check_box: "task",
  check_box_outlined: "task",
  task_alt: "task",
  checkbox: "task",
  // sub-task
  sub_task: "sub_task",
  subtask: "sub_task",
  "sub-task": "sub_task",
  subdirectory_arrow_right: "sub_task",
  account_tree: "sub_task",
  // story
  story: "story",
  priority_high: "story",
  priority: "story",
  bookmark: "story",
  error: "story",
  // bug
  bug: "bug",
  bug_report: "bug",
  pest_control: "bug",
  // epic
  epic: "epic",
  bolt: "epic",
  flash_on: "epic",
};

/** Color presets offered by the work item type color picker (Jira palette first). */
export const JP_WORK_ITEM_TYPE_COLOR_PRESETS: string[] = [
  "#4BADE8",
  "#E97F33",
  "#E5493A",
  "#904EE2",
  "#63BA3C",
  "#2684FF",
  "#FFAB00",
  "#00B8D9",
  "#FF5630",
  "#6554C0",
  "#36B37E",
  "#6B778C",
];
