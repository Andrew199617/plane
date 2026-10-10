/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: filters of a project-category master board (/:workspaceSlug/boards/:categoryId).
// Modeled on store/issue/profile/filter.store.ts; filters are keyed by category id and persisted locally.
import { isEmpty, set } from "lodash-es";
import { action, computed, makeObservable, observable, runInAction } from "mobx";
import { computedFn } from "mobx-utils";
// plane imports
import type { TSupportedFilterTypeForUpdate } from "@plane/constants";
import {
  EIssueFilterType,
  ISSUE_DISPLAY_FILTERS_BY_PAGE,
  JP_CATEGORY_BOARD_CYCLE_NAME_PARAM,
  JP_CATEGORY_BOARD_DEFAULT_DISPLAY_FILTERS,
  JP_CATEGORY_BOARD_PAGE_KEY,
  JP_CATEGORY_BOARD_STATE_NAME_PARAM,
  JP_STATE_NAME_GROUP_BY,
} from "@plane/constants";
import type {
  IIssueDisplayFilterOptions,
  IIssueDisplayProperties,
  IIssueFilters,
  IssuePaginationOptions,
  TCategoryBoardQuickFilters,
  TIssueKanbanFilters,
  TIssueParams,
  TSupportedFilterForUpdate,
  TWorkItemFilterExpression,
} from "@plane/types";
import { EIssueLayoutTypes, EIssuesStoreType } from "@plane/types";
// store
import type { IBaseIssueFilterStore } from "@/store/issue/helpers/issue-filter-helper.store";
import { IssueFilterHelperStore } from "@/store/issue/helpers/issue-filter-helper.store";
import type { IIssueRootStore } from "@/store/issue/root.store";
// local imports
import {
  getCategoryBoardCycleNameParam,
  getCategoryBoardQueryParamsByLayout,
  normalizeCategoryBoardQuickFilters,
  sanitizeCategoryBoardDisplayFilters,
} from "./helpers";

const QUICK_FILTERS_STORAGE_KEY = "jp_category_board_quick_filters";

export const EMPTY_CATEGORY_BOARD_QUICK_FILTERS: TCategoryBoardQuickFilters = Object.freeze({
  cycle_names: [],
}) as TCategoryBoardQuickFilters;

type TCategoryBoardFilterParams = Partial<
  Record<
    TIssueParams | typeof JP_CATEGORY_BOARD_CYCLE_NAME_PARAM | typeof JP_CATEGORY_BOARD_STATE_NAME_PARAM,
    string | boolean
  >
>;

export interface ICategoryBoardIssuesFilter extends IBaseIssueFilterStore {
  // observables
  categoryId: string | undefined;
  quickFilters: Record<string, TCategoryBoardQuickFilters>;
  // helpers
  getIssueFilters: (categoryId: string | undefined) => IIssueFilters | undefined;
  getAppliedFilters: (categoryId: string | undefined) => Partial<Record<TIssueParams, string | boolean>> | undefined;
  getQuickFilters: (categoryId: string | undefined) => TCategoryBoardQuickFilters;
  getFilterParams: (
    options: IssuePaginationOptions,
    categoryId: string,
    cursor: string | undefined,
    groupId: string | undefined,
    subGroupId: string | undefined
  ) => TCategoryBoardFilterParams;
  // actions
  fetchFilters: (workspaceSlug: string, categoryId: string) => Promise<void>;
  updateFilterExpression: (
    workspaceSlug: string,
    categoryId: string,
    filters: TWorkItemFilterExpression
  ) => Promise<void>;
  updateFilters: (
    workspaceSlug: string,
    projectId: string | undefined,
    filterType: TSupportedFilterTypeForUpdate,
    filters: TSupportedFilterForUpdate,
    categoryId: string
  ) => Promise<void>;
  updateQuickFilters: (
    workspaceSlug: string,
    categoryId: string,
    quickFilters: Partial<TCategoryBoardQuickFilters>
  ) => void;
}

export class CategoryBoardIssuesFilter extends IssueFilterHelperStore implements ICategoryBoardIssuesFilter {
  // observables
  categoryId: string | undefined = undefined;
  filters: { [categoryId: string]: IIssueFilters } = {};
  quickFilters: Record<string, TCategoryBoardQuickFilters> = {};
  // root store
  rootIssueStore: IIssueRootStore;

  constructor(rootIssueStore: IIssueRootStore) {
    super();
    makeObservable(this, {
      // observables
      categoryId: observable.ref,
      filters: observable,
      quickFilters: observable,
      // computed
      issueFilters: computed,
      appliedFilters: computed,
      // actions
      fetchFilters: action,
      updateFilters: action,
      updateQuickFilters: action,
    });
    this.rootIssueStore = rootIssueStore;
  }

  get issueFilters() {
    return this.getIssueFilters(this.categoryId);
  }

  get appliedFilters() {
    return this.getAppliedFilters(this.categoryId);
  }

  getIssueFilters = (categoryId: string | undefined) => {
    if (!categoryId) return undefined;
    const categoryFilters = this.filters[categoryId];
    if (isEmpty(categoryFilters)) return undefined;
    return this.computedIssueFilters(categoryFilters);
  };

  getAppliedFilters = (categoryId: string | undefined) => {
    const userFilters = this.getIssueFilters(categoryId);
    if (!userFilters) return undefined;

    const acceptableParams = getCategoryBoardQueryParamsByLayout(
      ISSUE_DISPLAY_FILTERS_BY_PAGE[JP_CATEGORY_BOARD_PAGE_KEY],
      userFilters.displayFilters?.layout
    );
    if (!acceptableParams) return undefined;

    return this.computedFilteredParams(userFilters.richFilters, userFilters.displayFilters, acceptableParams);
  };

  getQuickFilters = computedFn(
    (categoryId: string | undefined): TCategoryBoardQuickFilters =>
      (categoryId ? this.quickFilters[categoryId] : undefined) ?? EMPTY_CATEGORY_BOARD_QUICK_FILTERS
  );

  getFilterParams = computedFn(
    (
      options: IssuePaginationOptions,
      categoryId: string,
      cursor: string | undefined,
      groupId: string | undefined,
      subGroupId: string | undefined
    ): TCategoryBoardFilterParams => {
      const filterParams: Partial<Record<TIssueParams, string | boolean>> = { ...this.getAppliedFilters(categoryId) };
      const quickFilters = this.getQuickFilters(categoryId);

      const paginationParams: TCategoryBoardFilterParams = this.getPaginationParams(
        filterParams,
        options,
        cursor,
        groupId,
        subGroupId
      );

      // a single "status" column is paged by its state NAME (server filter `state_name`); the generic helper maps
      // the group to the `state` (id) param, which cannot carry a name
      const displayFilters = this.getIssueFilters(categoryId)?.displayFilters;
      const stateNameGroupId =
        displayFilters?.group_by === JP_STATE_NAME_GROUP_BY
          ? groupId
          : displayFilters?.sub_group_by === JP_STATE_NAME_GROUP_BY
            ? subGroupId
            : undefined;
      if (stateNameGroupId) {
        delete paginationParams.state;
        paginationParams[JP_CATEGORY_BOARD_STATE_NAME_PARAM] = stateNameGroupId;
      }

      // sprints (cycles) by name across the category's projects
      const cycleNameParam = getCategoryBoardCycleNameParam(quickFilters.cycle_names);
      if (cycleNameParam) paginationParams[JP_CATEGORY_BOARD_CYCLE_NAME_PARAM] = cycleNameParam;

      return paginationParams;
    }
  );

  fetchFilters = async (workspaceSlug: string, categoryId: string) => {
    const localFilters = this.handleIssuesLocalFilters.get(
      EIssuesStoreType.CATEGORY_BOARD,
      workspaceSlug,
      categoryId,
      undefined
    );

    const richFilters: TWorkItemFilterExpression = localFilters?.rich_filters ?? {};
    const displayFilters: IIssueDisplayFilterOptions = sanitizeCategoryBoardDisplayFilters(
      this.computedDisplayFilters(
        localFilters?.display_filters,
        JP_CATEGORY_BOARD_DEFAULT_DISPLAY_FILTERS as IIssueDisplayFilterOptions
      )
    );
    const displayProperties: IIssueDisplayProperties = this.computedDisplayProperties(localFilters?.display_properties);
    const kanbanFilters: TIssueKanbanFilters = {
      group_by: localFilters?.kanban_filters?.group_by || [],
      sub_group_by: localFilters?.kanban_filters?.sub_group_by || [],
    };
    const quickFilters = readStoredQuickFilters(workspaceSlug, categoryId);

    runInAction(() => {
      this.categoryId = categoryId;
      set(this.filters, [categoryId, "richFilters"], richFilters);
      set(this.filters, [categoryId, "displayFilters"], displayFilters);
      set(this.filters, [categoryId, "displayProperties"], displayProperties);
      set(this.filters, [categoryId, "kanbanFilters"], kanbanFilters);
      set(this.quickFilters, [categoryId], quickFilters);
    });
  };

  /**
   * NOTE: fallback for the work item filter store (rich filters). Only call it directly when initializing filter
   * instances; regular updates go through the work item filter instance.
   */
  updateFilterExpression: ICategoryBoardIssuesFilter["updateFilterExpression"] = async (
    workspaceSlug,
    categoryId,
    filters
  ) => {
    runInAction(() => {
      set(this.filters, [categoryId, "richFilters"], filters);
    });
    this.handleIssuesLocalFilters.set(
      EIssuesStoreType.CATEGORY_BOARD,
      EIssueFilterType.FILTERS,
      workspaceSlug,
      categoryId,
      undefined,
      { rich_filters: filters }
    );
    await this.rootIssueStore.categoryBoardIssues.fetchIssuesWithExistingPagination(
      workspaceSlug,
      categoryId,
      "mutation"
    );
  };

  updateQuickFilters: ICategoryBoardIssuesFilter["updateQuickFilters"] = (workspaceSlug, categoryId, quickFilters) => {
    const updated: TCategoryBoardQuickFilters = { ...this.getQuickFilters(categoryId), ...quickFilters };
    runInAction(() => {
      set(this.quickFilters, [categoryId], updated);
    });
    writeStoredQuickFilters(workspaceSlug, categoryId, updated);
    void this.rootIssueStore.categoryBoardIssues.fetchIssuesWithExistingPagination(
      workspaceSlug,
      categoryId,
      "mutation"
    );
  };

  updateFilters: ICategoryBoardIssuesFilter["updateFilters"] = async (
    workspaceSlug,
    _projectId,
    type,
    filters,
    categoryId
  ) => {
    const issueFilters = this.getIssueFilters(categoryId);
    if (!issueFilters) return;

    try {
      switch (type) {
        case EIssueFilterType.DISPLAY_FILTERS: {
          const updatedDisplayFilters = { ...(filters as IIssueDisplayFilterOptions) };
          const nextDisplayFilters: IIssueDisplayFilterOptions = {
            ...issueFilters.displayFilters,
            ...updatedDisplayFilters,
          };

          // sub_group_by needs a group_by, and must differ from it
          if (nextDisplayFilters.group_by === null) updatedDisplayFilters.sub_group_by = null;
          if (
            nextDisplayFilters.layout === EIssueLayoutTypes.KANBAN &&
            nextDisplayFilters.group_by === nextDisplayFilters.sub_group_by
          )
            updatedDisplayFilters.sub_group_by = null;
          // kanban always needs columns: default to Jira-like status columns
          if (nextDisplayFilters.layout === EIssueLayoutTypes.KANBAN && !nextDisplayFilters.group_by)
            updatedDisplayFilters.group_by = JP_STATE_NAME_GROUP_BY;

          runInAction(() => {
            Object.keys(updatedDisplayFilters).forEach((key) => {
              set(
                this.filters,
                [categoryId, "displayFilters", key],
                updatedDisplayFilters[key as keyof IIssueDisplayFilterOptions]
              );
            });
          });

          const categoryBoardIssues = this.rootIssueStore.categoryBoardIssues;
          // layout changes: the new layout root fetches its own (grouped or flat) first page
          if (this.getShouldClearIssues(updatedDisplayFilters)) categoryBoardIssues.clear(true);
          if (this.getShouldReFetchIssues(updatedDisplayFilters))
            void categoryBoardIssues.fetchIssuesWithExistingPagination(workspaceSlug, categoryId, "mutation");

          this.handleIssuesLocalFilters.set(
            EIssuesStoreType.CATEGORY_BOARD,
            type,
            workspaceSlug,
            categoryId,
            undefined,
            {
              display_filters: this.filters[categoryId]?.displayFilters,
            }
          );
          break;
        }
        case EIssueFilterType.DISPLAY_PROPERTIES: {
          const updatedDisplayProperties = filters as IIssueDisplayProperties;
          runInAction(() => {
            Object.keys(updatedDisplayProperties).forEach((key) => {
              set(
                this.filters,
                [categoryId, "displayProperties", key],
                updatedDisplayProperties[key as keyof IIssueDisplayProperties]
              );
            });
          });
          this.handleIssuesLocalFilters.set(
            EIssuesStoreType.CATEGORY_BOARD,
            type,
            workspaceSlug,
            categoryId,
            undefined,
            {
              display_properties: this.filters[categoryId]?.displayProperties,
            }
          );
          break;
        }
        case EIssueFilterType.KANBAN_FILTERS: {
          const updatedKanbanFilters = filters as TIssueKanbanFilters;
          runInAction(() => {
            Object.keys(updatedKanbanFilters).forEach((key) => {
              set(
                this.filters,
                [categoryId, "kanbanFilters", key],
                updatedKanbanFilters[key as keyof TIssueKanbanFilters]
              );
            });
          });
          this.handleIssuesLocalFilters.set(
            EIssuesStoreType.CATEGORY_BOARD,
            type,
            workspaceSlug,
            categoryId,
            undefined,
            {
              kanban_filters: this.filters[categoryId]?.kanbanFilters,
            }
          );
          break;
        }
        default:
          break;
      }
    } catch (error) {
      void this.fetchFilters(workspaceSlug, categoryId);
      throw error;
    }
  };
}

// ---- per-viewer persistence of the quick filters (sprint / type) ----

const quickFiltersStorageKey = (workspaceSlug: string, categoryId: string) => `${workspaceSlug}:${categoryId}`;

function readAllStoredQuickFilters(): Record<string, unknown> {
  try {
    const raw = window.localStorage.getItem(QUICK_FILTERS_STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function readStoredQuickFilters(workspaceSlug: string, categoryId: string): TCategoryBoardQuickFilters {
  return normalizeCategoryBoardQuickFilters(
    readAllStoredQuickFilters()[quickFiltersStorageKey(workspaceSlug, categoryId)]
  );
}

function writeStoredQuickFilters(workspaceSlug: string, categoryId: string, quickFilters: TCategoryBoardQuickFilters) {
  try {
    const all = readAllStoredQuickFilters();
    all[quickFiltersStorageKey(workspaceSlug, categoryId)] = quickFilters;
    window.localStorage.setItem(QUICK_FILTERS_STORAGE_KEY, JSON.stringify(all));
  } catch {
    // storage unavailable (private mode / blocked): filters stay in memory only
  }
}
