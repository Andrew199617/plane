/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: pure helpers of the project-category master boards (type-only imports, no store / React imports, so
// Node can run them directly: `node --test store/jira-parity/category-board/helpers.test.mjs` from apps/web).
import type { TFilterPropertiesByPageType } from "@plane/constants";
import type {
  IIssueDisplayFilterOptions,
  IState,
  TCategoryBoardQuickFilters,
  TIssueGroupByOptions,
  TIssueParams,
} from "@plane/types";

const BOARD_LAYOUTS = new Set<string>(["list", "kanban", "spreadsheet"]);
const STATE_NAME_GROUP_BY = "state__name";
/** Group-bys whose columns need a "current project" (not available on a cross-project board). */
const PROJECT_ONLY_GROUP_BYS = new Set<TIssueGroupByOptions>(["state", "cycle", "module", "team_project"]);
const STATE_GROUP_RANK: Record<string, number> = {
  triage: 0,
  backlog: 1,
  unstarted: 2,
  started: 3,
  completed: 4,
  cancelled: 5,
};

/** Query params accepted by the board for a layout (mirror of utils' handleIssueQueryParamsByLayout). */
export const getCategoryBoardQueryParamsByLayout = (
  pageConfig: Pick<TFilterPropertiesByPageType, "layoutOptions"> | undefined,
  layout: string | undefined
): TIssueParams[] | null => {
  if (!layout || !pageConfig) return null;
  const layoutOptions = pageConfig.layoutOptions[layout];
  if (!layoutOptions) return null;

  const params: TIssueParams[] = ["filters"];
  Object.keys(layoutOptions.display_filters).forEach((option) => params.push(option as TIssueParams));
  if (layoutOptions.extra_options.access)
    layoutOptions.extra_options.values.forEach((option) => params.push(option as TIssueParams));
  return params;
};

/**
 * Normalizes stored display filters for a cross-project board: supported layouts only, no project-only group-bys,
 * kanban always grouped (default: Jira-like status columns).
 */
export const sanitizeCategoryBoardDisplayFilters = (
  displayFilters: IIssueDisplayFilterOptions
): IIssueDisplayFilterOptions => {
  const sanitized: IIssueDisplayFilterOptions = { ...displayFilters };
  if (!sanitized.layout || !BOARD_LAYOUTS.has(sanitized.layout))
    sanitized.layout = "kanban" as unknown as IIssueDisplayFilterOptions["layout"];
  if (sanitized.group_by && PROJECT_ONLY_GROUP_BYS.has(sanitized.group_by)) sanitized.group_by = STATE_NAME_GROUP_BY;
  if (sanitized.sub_group_by && PROJECT_ONLY_GROUP_BYS.has(sanitized.sub_group_by)) sanitized.sub_group_by = null;
  if (sanitized.layout === "kanban" && !sanitized.group_by) sanitized.group_by = STATE_NAME_GROUP_BY;
  if (sanitized.group_by === sanitized.sub_group_by) sanitized.sub_group_by = null;
  return sanitized;
};

/** Quick filters read back from (untrusted) local storage: unknown shapes become empty filters. */
export const normalizeCategoryBoardQuickFilters = (stored: unknown): TCategoryBoardQuickFilters => {
  const cycleNames = (stored as { cycle_names?: unknown } | null | undefined)?.cycle_names;
  return {
    cycle_names: Array.isArray(cycleNames)
      ? [...new Set(cycleNames.filter((name): name is string => typeof name === "string" && name.trim() !== ""))]
      : [],
  };
};

export type TStateNameColumn = {
  /** state name (column id) */
  name: string;
  /** representative state (first by group rank + sequence) used for the column icon */
  state: IState;
  /** ids of every state carrying this name in the scoped projects */
  stateIds: string[];
};

/** Standard Jira-parity statuses, in board column order (same order as the server's state__name groups). */
const STANDARD_STATE_ORDER = ["to do", "in progress", "in review", "done", "won't fix"];
const normalizeStateName = (name: string) =>
  name.replace(/’/g, "'").split(/\s+/).filter(Boolean).join(" ").toLowerCase();
const standardRankOf = (name: string) => {
  const index = STANDARD_STATE_ORDER.indexOf(normalizeStateName(name));
  return index === -1 ? STANDARD_STATE_ORDER.length : index;
};

/**
 * Distinct state NAMES across the given projects (all projects when `projectIds` is undefined), ordered like Jira
 * columns: standard statuses first (To Do, In Progress, In Review, Done, Won't Fix), then the others by state group
 * (backlog, unstarted, started, completed, cancelled) and sequence. Triage states are never columns.
 */
export const getStateNameColumns = (states: IState[], projectIds: Iterable<string> | undefined): TStateNameColumn[] => {
  const allowedProjectIds = projectIds ? new Set(projectIds) : undefined;
  const columns = new Map<string, TStateNameColumn>();
  const rankOf = (state: IState) => STATE_GROUP_RANK[state.group] ?? 9;

  for (const state of states) {
    // the server may still send the hidden intake "triage" state (not part of TStateGroups)
    if ((state.group as string) === "triage") continue;
    if (allowedProjectIds && !allowedProjectIds.has(state.project_id)) continue;
    const existing = columns.get(state.name);
    if (!existing) {
      columns.set(state.name, { name: state.name, state, stateIds: [state.id] });
      continue;
    }
    existing.stateIds.push(state.id);
    const isBetterRepresentative =
      rankOf(state) < rankOf(existing.state) ||
      (rankOf(state) === rankOf(existing.state) && state.sequence < existing.state.sequence);
    if (isBetterRepresentative) existing.state = state;
  }

  // oxlint-disable-next-line unicorn/no-array-sort -- sorts a copy; web targets ES2022 (no toSorted)
  return [...columns.values()].sort(
    (a, b) =>
      standardRankOf(a.name) - standardRankOf(b.name) ||
      rankOf(a.state) - rankOf(b.state) ||
      a.state.sequence - b.state.sequence ||
      a.name.localeCompare(b.name)
  );
};

/** State of `projectId` named `stateName` (used when a card is dropped on a status column). */
export const findProjectStateByName = (
  states: IState[],
  projectId: string | null | undefined,
  stateName: string
): IState | undefined => {
  if (!projectId) return undefined;
  const projectStates = states.filter((state) => state.project_id === projectId);
  return (
    projectStates.find((state) => state.name === stateName) ??
    projectStates.find((state) => state.name.trim().toLowerCase() === stateName.trim().toLowerCase())
  );
};

/** Projects of a category: live project.category_id when the API returns it, else the category's project_ids. */
export const getCategoryProjectIds = (
  categoryId: string,
  categoryProjectIds: string[] | undefined,
  projects: { id: string; category_id?: string | null; archived_at?: string | null }[]
): string[] => {
  const fromCategory = new Set(categoryProjectIds ?? []);
  const result: string[] = [];
  for (const project of projects) {
    if (project.archived_at) continue;
    const projectCategoryId = project.category_id !== undefined ? project.category_id : undefined;
    const belongs = projectCategoryId !== undefined ? projectCategoryId === categoryId : fromCategory.has(project.id);
    if (belongs) result.push(project.id);
  }
  return result;
};

/** New sort_order values when moving the item at `fromIndex` to `toIndex` (gapped re-numbering). */
export const computeReorderedSortOrders = <T extends { id: string; sort_order: number }>(
  items: T[],
  fromIndex: number,
  toIndex: number,
  gap: number
): { id: string; sort_order: number }[] => {
  if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0 || fromIndex >= items.length || toIndex >= items.length)
    return [];
  const reordered = [...items];
  const [moved] = reordered.splice(fromIndex, 1);
  reordered.splice(toIndex, 0, moved);
  return reordered
    .map((item, index) => ({ id: item.id, sort_order: (index + 1) * gap, previous: item.sort_order }))
    .filter((item) => item.sort_order !== item.previous)
    .map(({ id, sort_order }) => ({ id, sort_order }));
};
