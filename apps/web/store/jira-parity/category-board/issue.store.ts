/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: work items of a project-category master board (all work items of the category's projects).
// Modeled on store/issue/profile/issue.store.ts; data comes from GET /api/workspaces/<slug>/project-categories/<id>/issues/
// (same grouped + paginated response as the workspace issues endpoints).
import { action, makeObservable, observable, runInAction } from "mobx";
// plane imports
import type {
  IssuePaginationOptions,
  TIssue,
  TIssuesResponse,
  TLoader,
  TBulkOperationsPayload,
  ViewFlags,
} from "@plane/types";
// services
import { ProjectCategoriesService } from "@/services/jira-parity/project-categories.service";
// store
import type { IBaseIssuesStore } from "@/store/issue/helpers/base-issues.store";
import { BaseIssuesStore } from "@/store/issue/helpers/base-issues.store";
import type { IIssueRootStore } from "@/store/issue/root.store";
// local imports
import type { ICategoryBoardIssuesFilter } from "./filter.store";

export interface ICategoryBoardIssues extends IBaseIssuesStore {
  // observables
  categoryId: string | undefined;
  viewFlags: ViewFlags;
  // actions
  fetchIssues: (
    workspaceSlug: string,
    categoryId: string,
    loadType: TLoader,
    options: IssuePaginationOptions,
    isExistingPaginationOptions?: boolean
  ) => Promise<TIssuesResponse | undefined>;
  fetchIssuesWithExistingPagination: (
    workspaceSlug: string,
    categoryId: string,
    loadType: TLoader
  ) => Promise<TIssuesResponse | undefined>;
  fetchNextIssues: (
    workspaceSlug: string,
    categoryId: string,
    groupId?: string,
    subGroupId?: string
  ) => Promise<TIssuesResponse | undefined>;

  createIssue: (workspaceSlug: string, projectId: string, data: Partial<TIssue>) => Promise<TIssue>;
  updateIssue: (workspaceSlug: string, projectId: string, issueId: string, data: Partial<TIssue>) => Promise<void>;
  archiveIssue: (workspaceSlug: string, projectId: string, issueId: string) => Promise<void>;
  removeBulkIssues: (workspaceSlug: string, projectId: string, issueIds: string[]) => Promise<void>;
  archiveBulkIssues: (workspaceSlug: string, projectId: string, issueIds: string[]) => Promise<void>;
  bulkUpdateProperties: (workspaceSlug: string, projectId: string, data: TBulkOperationsPayload) => Promise<void>;

  quickAddIssue: undefined;
}

export class CategoryBoardIssues extends BaseIssuesStore implements ICategoryBoardIssues {
  // observables
  categoryId: string | undefined = undefined;
  // there is no single project on a master board: quick add is disabled, creation goes through the modal
  viewFlags = {
    enableQuickAdd: false,
    enableIssueCreation: true,
    enableInlineEditing: true,
  };
  // filter store
  issueFilterStore: ICategoryBoardIssuesFilter;
  // services
  categoryService: ProjectCategoriesService;

  constructor(rootIssueStore: IIssueRootStore, issueFilterStore: ICategoryBoardIssuesFilter) {
    super(rootIssueStore, issueFilterStore);
    makeObservable(this, {
      // observables
      categoryId: observable.ref,
      // actions
      fetchIssues: action,
      fetchNextIssues: action,
      fetchIssuesWithExistingPagination: action,
    });
    this.issueFilterStore = issueFilterStore;
    this.categoryService = new ProjectCategoriesService();
  }

  fetchParentStats = () => {};

  updateParentStats = () => {};

  /**
   * Fetches the first page of the board (grouped when the layout groups, flat for the spreadsheet).
   */
  fetchIssues = async (
    workspaceSlug: string,
    categoryId: string,
    loadType: TLoader,
    options: IssuePaginationOptions,
    isExistingPaginationOptions: boolean = false
  ) => {
    let signal: AbortSignal | undefined;
    try {
      runInAction(() => {
        this.setLoader(loadType);
        this.categoryId = categoryId;
      });
      this.clear(!isExistingPaginationOptions);
      signal = this.controller.signal;

      const params = this.issueFilterStore.getFilterParams(options, categoryId, undefined, undefined, undefined);
      const response = await this.categoryService.getIssues(workspaceSlug, categoryId, params, { signal });

      this.onfetchIssues(response, options, workspaceSlug, undefined, undefined, !isExistingPaginationOptions);
      return response;
    } catch (error) {
      // superseded by a newer first-page fetch (filters / layout changed, or React StrictMode re-running the layout
      // effect): that fetch owns the loader now, so this one resolves quietly instead of an unhandled rejection
      if (signal?.aborted) return undefined;
      this.setLoader(undefined);
      throw error;
    }
  };

  /**
   * Fetches the next page (of one group / sub group when given, else of every group).
   */
  fetchNextIssues = async (workspaceSlug: string, categoryId: string, groupId?: string, subGroupId?: string) => {
    const cursorObject = this.getPaginationData(groupId, subGroupId);
    if (!this.paginationOptions || (cursorObject && !cursorObject?.nextPageResults)) return;
    try {
      this.setLoader("pagination", groupId, subGroupId);

      const params = this.issueFilterStore.getFilterParams(
        this.paginationOptions,
        categoryId,
        this.getNextCursor(groupId, subGroupId),
        groupId,
        subGroupId
      );
      const response = await this.categoryService.getIssues(workspaceSlug, categoryId, params);

      this.onfetchNexIssues(response, groupId, subGroupId);
      return response;
    } catch (error) {
      this.setLoader(undefined, groupId, subGroupId);
      throw error;
    }
  };

  /**
   * Re-fetches the first page with the stored pagination options (filters / grouping / ordering changes).
   */
  fetchIssuesWithExistingPagination = async (workspaceSlug: string, categoryId: string, loadType: TLoader) => {
    if (!this.paginationOptions) return;
    return await this.fetchIssues(workspaceSlug, categoryId, loadType, this.paginationOptions, true);
  };

  // Using aliased names as they cannot be overridden in other stores
  archiveBulkIssues = this.bulkArchiveIssues;
  updateIssue = this.issueUpdate;
  archiveIssue = this.issueArchive;

  // a master board has no single project to quick-add into
  quickAddIssue = undefined;
}
