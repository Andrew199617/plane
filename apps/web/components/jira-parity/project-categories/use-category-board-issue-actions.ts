/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: issue actions of a project-category master board (EIssuesStoreType.CATEGORY_BOARD), plugged into
// useIssuesActions (hooks/use-issues-actions.tsx).
import { useCallback, useMemo } from "react";
import { useParams } from "next/navigation";
// plane imports
import type { TSupportedFilterTypeForUpdate } from "@plane/constants";
import type { IssuePaginationOptions, TIssue, TLoader, TSupportedFilterForUpdate } from "@plane/types";
import { EIssuesStoreType } from "@plane/types";
// hooks
import { useIssues } from "@/hooks/store/use-issues";
import type { IssueActions } from "@/hooks/use-issues-actions";

export const useCategoryBoardIssueActions = (): IssueActions => {
  // router
  const { workspaceSlug: routerWorkspaceSlug, categoryId: routerCategoryId } = useParams();
  const workspaceSlug = routerWorkspaceSlug?.toString();
  const categoryId = routerCategoryId?.toString();
  // store hooks
  const { issues, issuesFilter } = useIssues(EIssuesStoreType.CATEGORY_BOARD);

  const fetchIssues = useCallback(
    async (loadType: TLoader, options: IssuePaginationOptions) => {
      if (!workspaceSlug || !categoryId) return;
      return issues.fetchIssues(workspaceSlug, categoryId, loadType, options);
    },
    [issues, workspaceSlug, categoryId]
  );

  const fetchNextIssues = useCallback(
    async (groupId?: string, subGroupId?: string) => {
      if (!workspaceSlug || !categoryId) return;
      return issues.fetchNextIssues(workspaceSlug, categoryId, groupId, subGroupId);
    },
    [issues, workspaceSlug, categoryId]
  );

  const createIssue = useCallback(
    async (projectId: string | undefined | null, data: Partial<TIssue>) => {
      if (!workspaceSlug || !projectId) return;
      return await issues.createIssue(workspaceSlug, projectId, data);
    },
    [issues, workspaceSlug]
  );

  const updateIssue = useCallback(
    async (projectId: string | undefined | null, issueId: string, data: Partial<TIssue>) => {
      if (!workspaceSlug || !projectId) return;
      return await issues.updateIssue(workspaceSlug, projectId, issueId, data);
    },
    [issues, workspaceSlug]
  );

  const removeIssue = useCallback(
    async (projectId: string | undefined | null, issueId: string) => {
      if (!workspaceSlug || !projectId) return;
      return await issues.removeIssue(workspaceSlug, projectId, issueId);
    },
    [issues, workspaceSlug]
  );

  const archiveIssue = useCallback(
    async (projectId: string | undefined | null, issueId: string) => {
      if (!workspaceSlug || !projectId) return;
      return await issues.archiveIssue(workspaceSlug, projectId, issueId);
    },
    [issues, workspaceSlug]
  );

  const updateFilters = useCallback(
    async (projectId: string, filterType: TSupportedFilterTypeForUpdate, filters: TSupportedFilterForUpdate) => {
      if (!workspaceSlug || !categoryId) return;
      return await issuesFilter.updateFilters(workspaceSlug, projectId, filterType, filters, categoryId);
    },
    [issuesFilter, workspaceSlug, categoryId]
  );

  return useMemo(
    () => ({
      fetchIssues,
      fetchNextIssues,
      createIssue,
      updateIssue,
      removeIssue,
      archiveIssue,
      updateFilters,
    }),
    [fetchIssues, fetchNextIssues, createIssue, updateIssue, removeIssue, archiveIssue, updateFilters]
  );
};
