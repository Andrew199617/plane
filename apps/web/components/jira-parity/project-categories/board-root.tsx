/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: master board of a project category, page /:workspaceSlug/boards/:categoryId
// (owned by the project-categories feature). Shows every work item of the category's projects as a Jira-like
// board (kanban / list / spreadsheet), grouped by status (state NAME) across projects.
import { useEffect, useMemo } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import {
  ISSUE_DISPLAY_FILTERS_BY_PAGE,
  JP_CATEGORY_BOARD_PAGE_KEY,
  JP_PROJECT_CATEGORY_CYCLES_SWR_KEY,
} from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { EmptyStateDetailed } from "@plane/blocks/empty-state";
import { EIssuesStoreType } from "@plane/types";
// components
import { IssuePeekOverview } from "@/components/issues/peek-overview";
import { WorkItemFiltersHOC } from "@/components/work-item-filters/filters-hoc/base";
import { WorkItemFiltersRow } from "@/components/work-item-filters/filters-row";
import { KanbanLayoutLoader } from "@/components/ui/loader/layouts/kanban-layout-loader";
// hooks
import { useProjectCategories } from "@/hooks/store/jira-parity/use-project-categories";
import { useIssues } from "@/hooks/store/use-issues";
import { useLabel } from "@/hooks/store/use-label";
import { useMember } from "@/hooks/store/use-member";
import { useAppRouter } from "@/hooks/use-app-router";
import { IssuesStoreContext } from "@/hooks/use-issue-layout-store";
import { useWorkspaceIssueProperties } from "@/hooks/use-workspace-issue-properties";
// local imports
import { CategoryBoardActiveLayout } from "./board-layouts";
import { CategoryBoardQuickFiltersRow } from "./board-quick-filters";

type TCategoryBoardRootProps = {
  workspaceSlug: string;
  categoryId: string;
};

export const CategoryBoardRoot = observer(function CategoryBoardRoot(props: TCategoryBoardRootProps) {
  const { workspaceSlug, categoryId } = props;
  // router
  const router = useAppRouter();
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const {
    issuesFilter: { categoryId: loadedCategoryId, getIssueFilters, fetchFilters, updateFilterExpression },
    issues: { getGroupIssueCount, getIssueLoader },
  } = useIssues(EIssuesStoreType.CATEGORY_BOARD);
  const { fetchedWorkspaceSlug, getCategoryById, getProjectIdsByCategoryId, fetchCategoryCycles } =
    useProjectCategories();
  const {
    workspace: { getWorkspaceMemberIds },
  } = useMember();
  const { getWorkspaceLabelIds } = useLabel();
  // derived values
  const category = getCategoryById(categoryId);
  const isCategoryMissing = fetchedWorkspaceSlug === workspaceSlug && !category;
  const categoryProjectIds = getProjectIdsByCategoryId(categoryId);
  const issueFilters = loadedCategoryId === categoryId ? getIssueFilters(categoryId) : undefined;
  // layouts fetch work items on mount: wait for the board filters and for the category to be known to exist
  const canRenderLayout = !!issueFilters && !!category;
  const activeLayout = issueFilters?.displayFilters?.layout;
  const filtersToShow = ISSUE_DISPLAY_FILTERS_BY_PAGE[JP_CATEGORY_BOARD_PAGE_KEY].filters;
  const issueCount = getGroupIssueCount(undefined, undefined, false);
  const isLoadingIssues = getIssueLoader() === "init-loader" || issueCount === undefined;
  const initialWorkItemFilters = useMemo(
    () =>
      issueFilters
        ? {
            richFilters: issueFilters.richFilters ?? {},
            displayFilters: issueFilters.displayFilters,
            displayProperties: issueFilters.displayProperties,
            kanbanFilters: issueFilters.kanbanFilters,
          }
        : undefined,
    [issueFilters]
  );

  // workspace labels / members etc. used by the cards and filters
  useWorkspaceIssueProperties(workspaceSlug);

  // board filters are local (per viewer, per category): (re)load them whenever the board changes
  useEffect(() => {
    if (workspaceSlug && categoryId) void fetchFilters(workspaceSlug, categoryId);
  }, [fetchFilters, workspaceSlug, categoryId]);

  // sprints (cycles) of the category, by name, for the sprint filter (only once the category is known to exist)
  useSWR(
    workspaceSlug && category ? JP_PROJECT_CATEGORY_CYCLES_SWR_KEY(categoryId) : null,
    workspaceSlug && category ? () => fetchCategoryCycles(workspaceSlug, categoryId) : null,
    { revalidateOnFocus: false, shouldRetryOnError: false }
  );

  if (isCategoryMissing)
    return (
      <EmptyStateDetailed
        title={t("jp_categories.board.not_found_title")}
        description={t("jp_categories.board.not_found_description")}
        assetKey="view"
        actions={[
          {
            label: t("jp_categories.board.go_to_projects"),
            onClick: () => router.push(`/${workspaceSlug}/projects`),
            variant: "primary",
          },
        ]}
      />
    );

  return (
    <IssuesStoreContext.Provider value={EIssuesStoreType.CATEGORY_BOARD}>
      <WorkItemFiltersHOC
        entityId={categoryId}
        entityType={EIssuesStoreType.CATEGORY_BOARD}
        filtersToShowByLayout={filtersToShow}
        initialWorkItemFilters={initialWorkItemFilters}
        updateFilters={updateFilterExpression.bind(updateFilterExpression, workspaceSlug, categoryId)}
        workspaceSlug={workspaceSlug}
        projectIds={categoryProjectIds}
        memberIds={getWorkspaceMemberIds(workspaceSlug)}
        labelIds={getWorkspaceLabelIds(workspaceSlug)}
      >
        {({ filter: boardWorkItemsFilter }) => (
          <div className="h-full overflow-hidden bg-surface-1">
            <div className="flex h-full w-full flex-col">
              <CategoryBoardQuickFiltersRow workspaceSlug={workspaceSlug} categoryId={categoryId} />
              {boardWorkItemsFilter && <WorkItemFiltersRow filter={boardWorkItemsFilter} />}
              <div className="relative h-full w-full overflow-auto">
                {!canRenderLayout ? (
                  <KanbanLayoutLoader />
                ) : (
                  <>
                    <CategoryBoardActiveLayout
                      key={categoryId}
                      activeLayout={activeLayout}
                      workspaceSlug={workspaceSlug}
                      categoryId={categoryId}
                    />
                    {!isLoadingIssues && issueCount === 0 && (
                      <div className="absolute inset-0 grid place-items-center bg-surface-1">
                        <EmptyStateDetailed
                          title={t("jp_categories.board.empty_title")}
                          description={
                            categoryProjectIds.length === 0
                              ? t("jp_categories.board.no_projects_description")
                              : t("jp_categories.board.empty_description")
                          }
                          assetKey="work-item"
                          assetClassName="size-40"
                        />
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
            {/* peek overview */}
            <IssuePeekOverview />
          </div>
        )}
      </WorkItemFiltersHOC>
    </IssuesStoreContext.Provider>
  );
});
