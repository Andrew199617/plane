/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: master board layouts (kanban / list / spreadsheet) on the CATEGORY_BOARD issue store.
// Kanban and list reuse the CE base roots (they read the store type from IssuesStoreContext); the spreadsheet is a
// copy of the workspace-views spreadsheet root bound to this store.
import { useCallback, useEffect } from "react";
import { observer } from "mobx-react";
// plane imports
import { ALL_ISSUES, EIssueFilterType, EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import type { IIssueDisplayFilterOptions } from "@plane/types";
import { EIssueLayoutTypes, EIssuesStoreType } from "@plane/types";
// components
import { IssueLayoutHOC } from "@/components/issues/issue-layouts/issue-layout-HOC";
import { BaseKanBanRoot } from "@/components/issues/issue-layouts/kanban/base-kanban-root";
import { BaseListRoot } from "@/components/issues/issue-layouts/list/base-list-root";
import type { TRenderQuickActions } from "@/components/issues/issue-layouts/list/list-view-types";
import { AllIssueQuickActions } from "@/components/issues/issue-layouts/quick-action-dropdowns";
import { SpreadsheetView } from "@/components/issues/issue-layouts/spreadsheet/spreadsheet-view";
// hooks
import { useIssues } from "@/hooks/store/use-issues";
import { useUserPermissions } from "@/hooks/store/user";
import { useIssuesActions } from "@/hooks/use-issues-actions";

type TCategoryBoardLayoutProps = {
  workspaceSlug: string;
  categoryId: string;
};

/** Work items are editable inline where the viewer is a project admin or member. */
const useCanEditPropertiesBasedOnProject = (workspaceSlug: string) => {
  const { allowPermissions } = useUserPermissions();
  return useCallback(
    (projectId: string) =>
      allowPermissions(
        [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
        EUserPermissionsLevel.PROJECT,
        workspaceSlug,
        projectId
      ),
    [allowPermissions, workspaceSlug]
  );
};

export const CategoryBoardKanBanLayout = observer(function CategoryBoardKanBanLayout(props: TCategoryBoardLayoutProps) {
  const { workspaceSlug, categoryId } = props;
  const canEditPropertiesBasedOnProject = useCanEditPropertiesBasedOnProject(workspaceSlug);
  return (
    <BaseKanBanRoot
      QuickActions={AllIssueQuickActions}
      canEditPropertiesBasedOnProject={canEditPropertiesBasedOnProject}
      viewId={categoryId}
    />
  );
});

export const CategoryBoardListLayout = observer(function CategoryBoardListLayout(props: TCategoryBoardLayoutProps) {
  const { workspaceSlug, categoryId } = props;
  const canEditPropertiesBasedOnProject = useCanEditPropertiesBasedOnProject(workspaceSlug);
  return (
    <BaseListRoot
      QuickActions={AllIssueQuickActions}
      canEditPropertiesBasedOnProject={canEditPropertiesBasedOnProject}
      viewId={categoryId}
    />
  );
});

export const CategoryBoardSpreadsheetLayout = observer(function CategoryBoardSpreadsheetLayout(
  props: TCategoryBoardLayoutProps
) {
  const { workspaceSlug, categoryId } = props;
  // store hooks
  const {
    issuesFilter: { getIssueFilters, updateFilters },
    issues: { getPaginationData, groupedIssueIds },
  } = useIssues(EIssuesStoreType.CATEGORY_BOARD);
  const { fetchIssues, fetchNextIssues, updateIssue, removeIssue, archiveIssue } = useIssuesActions(
    EIssuesStoreType.CATEGORY_BOARD
  );
  const canEditPropertiesBasedOnProject = useCanEditPropertiesBasedOnProject(workspaceSlug);
  // derived values
  const issueFilters = getIssueFilters(categoryId);

  // the spreadsheet is a flat, paginated list (ordering changes re-fetch through the filter store)
  useEffect(() => {
    void fetchIssues("init-loader", { canGroup: false, perPageCount: 100 }, categoryId);
  }, [fetchIssues, categoryId]);

  const canEditProperties = useCallback(
    (projectId: string | undefined) => (projectId ? canEditPropertiesBasedOnProject(projectId) : false),
    [canEditPropertiesBasedOnProject]
  );

  const handleDisplayFiltersUpdate = useCallback(
    (updatedDisplayFilter: Partial<IIssueDisplayFilterOptions>) => {
      void updateFilters(
        workspaceSlug,
        undefined,
        EIssueFilterType.DISPLAY_FILTERS,
        { ...updatedDisplayFilter },
        categoryId
      );
    },
    [updateFilters, workspaceSlug, categoryId]
  );

  const renderQuickActions: TRenderQuickActions = useCallback(
    ({ issue, parentRef, customActionButton, placement, portalElement }) => (
      <AllIssueQuickActions
        parentRef={parentRef}
        customActionButton={customActionButton}
        issue={issue}
        handleDelete={async () => removeIssue(issue.project_id, issue.id)}
        handleUpdate={async (data) => updateIssue && updateIssue(issue.project_id, issue.id, data)}
        handleArchive={async () => archiveIssue && archiveIssue(issue.project_id, issue.id)}
        portalElement={portalElement}
        readOnly={!canEditProperties(issue.project_id ?? undefined)}
        placements={placement}
      />
    ),
    [canEditProperties, removeIssue, updateIssue, archiveIssue]
  );

  const issueIds = groupedIssueIds?.[ALL_ISSUES];
  const nextPageResults = getPaginationData(ALL_ISSUES, undefined)?.nextPageResults;

  return (
    <IssueLayoutHOC layout={EIssueLayoutTypes.SPREADSHEET}>
      <SpreadsheetView
        displayProperties={issueFilters?.displayProperties ?? {}}
        displayFilters={issueFilters?.displayFilters ?? {}}
        handleDisplayFilterUpdate={handleDisplayFiltersUpdate}
        issueIds={Array.isArray(issueIds) ? issueIds : []}
        quickActions={renderQuickActions}
        updateIssue={updateIssue}
        canEditProperties={canEditProperties}
        canLoadMoreIssues={!!nextPageResults}
        loadMoreIssues={() => void fetchNextIssues()}
        isWorkspaceLevel
      />
    </IssueLayoutHOC>
  );
});

type TCategoryBoardActiveLayoutProps = TCategoryBoardLayoutProps & {
  activeLayout: EIssueLayoutTypes | undefined;
};

export function CategoryBoardActiveLayout(props: TCategoryBoardActiveLayoutProps) {
  const { activeLayout, ...rest } = props;
  switch (activeLayout) {
    case EIssueLayoutTypes.LIST:
      return <CategoryBoardListLayout {...rest} />;
    case EIssueLayoutTypes.SPREADSHEET:
      return <CategoryBoardSpreadsheetLayout {...rest} />;
    case EIssueLayoutTypes.KANBAN:
    default:
      return <CategoryBoardKanBanLayout {...rest} />;
  }
}
