/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: project categories & master boards (owned by the project-categories feature)
import type { TLogoProps } from "../common";

/** GET /api/workspaces/<slug>/project-categories/[<id>/] */
export type TProjectCategory = {
  id: string;
  name: string;
  description: string;
  sort_order: number;
  logo_props: TLogoProps;
  project_ids: string[];
};

/** Body for POST / PATCH /api/workspaces/<slug>/project-categories/[<id>/] */
export type TProjectCategoryPayload = Partial<
  Pick<TProjectCategory, "name" | "description" | "sort_order" | "logo_props" | "project_ids">
>;

/** Row of GET /api/workspaces/<slug>/project-categories/<id>/cycles/ (distinct by name across the category's projects). */
export type TProjectCategoryCycle = {
  name: string;
  start_date: string | null;
  end_date: string | null;
  project_ids: string[];
};

/**
 * Master-board quick filters that are not part of the rich filter expression (project, work item type, priority,
 * assignee, ... are rich filters):
 * - cycle_names: sprint (cycle) NAMES across the category's projects, sent as `cycle_name=<a>,<b>`
 */
export type TCategoryBoardQuickFilters = {
  cycle_names: string[];
};
