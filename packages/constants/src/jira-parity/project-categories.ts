/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: project categories & master boards (owned by the project-categories feature)

/** Group-by key (frontend and server) for grouping work items by state NAME across projects. */
export const JP_STATE_NAME_GROUP_BY = "state__name";

/** SWR key for the workspace project categories list. */
export const JP_PROJECT_CATEGORIES_SWR_KEY = (workspaceSlug: string) => `JP_PROJECT_CATEGORIES_${workspaceSlug}`;

/** SWR key for the distinct cycles (sprints) of a category. */
export const JP_PROJECT_CATEGORY_CYCLES_SWR_KEY = (categoryId: string) => `JP_PROJECT_CATEGORY_CYCLES_${categoryId}`;

/** SWR key for the master board filters + first page of work items. */
export const JP_CATEGORY_BOARD_ISSUES_SWR_KEY = (workspaceSlug: string, categoryId: string) =>
  `JP_CATEGORY_BOARD_ISSUES_${workspaceSlug}_${categoryId}`;

/** Page key of ISSUE_DISPLAY_FILTERS_BY_PAGE used by the master boards. */
export const JP_CATEGORY_BOARD_PAGE_KEY = "category_board";

/** Server query param (category issues endpoint) filtering by cycle (sprint) NAME across the category's projects. */
export const JP_CATEGORY_BOARD_CYCLE_NAME_PARAM = "cycle_name";

/** Server query param filtering by state NAME (pages a single "status" column of a master board). */
export const JP_CATEGORY_BOARD_STATE_NAME_PARAM = "state_name";

/** Default display filters of a master board: Jira-like status columns. */
export const JP_CATEGORY_BOARD_DEFAULT_DISPLAY_FILTERS = {
  layout: "kanban",
  group_by: JP_STATE_NAME_GROUP_BY,
  sub_group_by: null,
  order_by: "sort_order",
  sub_issue: true,
  show_empty_groups: true,
} as const;

/** Order of state groups used to order the status (state name) columns of a master board. */
export const JP_STATE_GROUP_ORDER = ["triage", "backlog", "unstarted", "started", "completed", "cancelled"] as const;

/** Sort-order gap used when (re)ordering categories in the settings page. */
export const JP_PROJECT_CATEGORY_SORT_ORDER_GAP = 10000;
