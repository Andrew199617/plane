/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: master board header (owned by the project-categories feature): "Boards" > category switcher, the
// category's projects, and the layout / filters / display controls of the CATEGORY_BOARD issue store.
import { useCallback, useMemo } from "react";
import { observer } from "mobx-react";
import { BoardOutline } from "@makeplane/propel/icons";
// plane imports
import { EIssueFilterType, ISSUE_DISPLAY_FILTERS_BY_PAGE, JP_CATEGORY_BOARD_PAGE_KEY } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { BreadcrumbNavigationItem } from "@plane/blocks/breadcrumb";
import { Breadcrumbs, BreadcrumbNavigationSelect } from "@plane/blocks/breadcrumb";
import { Header } from "@plane/blocks/layout";
import type { IIssueDisplayFilterOptions, IIssueDisplayProperties } from "@plane/types";
import { EIssueLayoutTypes, EIssuesStoreType } from "@plane/types";
// components
import { BreadcrumbLink } from "@/components/common/breadcrumb-link";
import { SwitcherLabel } from "@/components/common/switcher-label";
import { DisplayFiltersSelection, FiltersDropdown, LayoutSelection } from "@/components/issues/issue-layouts/filters";
import { WorkItemFiltersToggle } from "@/components/work-item-filters/filters-toggle";
// hooks
import { useProjectCategories } from "@/hooks/store/jira-parity/use-project-categories";
import { useIssues } from "@/hooks/store/use-issues";
import { useAppRouter } from "@/hooks/use-app-router";
// local imports
import { CategoryBoardProjects } from "./board-quick-filters";

const BOARD_LAYOUTS = [EIssueLayoutTypes.LIST, EIssueLayoutTypes.KANBAN, EIssueLayoutTypes.SPREADSHEET];
/** Project chips shown in the header before collapsing into "+N". */
const MAX_HEADER_PROJECTS = 8;

type TCategoryBoardHeaderRootProps = {
  workspaceSlug: string;
  categoryId: string;
};

export const CategoryBoardHeaderRoot = observer(function CategoryBoardHeaderRoot(props: TCategoryBoardHeaderRootProps) {
  const { workspaceSlug, categoryId } = props;
  // router
  const router = useAppRouter();
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { sortedCategories, getCategoryById } = useProjectCategories();
  const {
    issuesFilter: { categoryId: loadedCategoryId, getIssueFilters, updateFilters },
  } = useIssues(EIssuesStoreType.CATEGORY_BOARD);
  // derived values
  const category = getCategoryById(categoryId);
  const issueFilters = loadedCategoryId === categoryId ? getIssueFilters(categoryId) : undefined;
  const activeLayout = issueFilters?.displayFilters?.layout;
  const layoutDisplayFiltersOptions = activeLayout
    ? ISSUE_DISPLAY_FILTERS_BY_PAGE[JP_CATEGORY_BOARD_PAGE_KEY].layoutOptions[activeLayout]
    : undefined;

  const switcherOptions = useMemo<BreadcrumbNavigationItem[]>(
    () =>
      sortedCategories.map((boardCategory) => ({
        key: boardCategory.id,
        label: boardCategory.name,
        content: (
          <SwitcherLabel name={boardCategory.name} logo_props={boardCategory.logo_props} LabelIcon={BoardOutline} />
        ),
      })),
    [sortedCategories]
  );

  const handleDisplayFilters = useCallback(
    (updatedDisplayFilter: Partial<IIssueDisplayFilterOptions>) => {
      void updateFilters(workspaceSlug, undefined, EIssueFilterType.DISPLAY_FILTERS, updatedDisplayFilter, categoryId);
    },
    [updateFilters, workspaceSlug, categoryId]
  );

  const handleDisplayProperties = useCallback(
    (property: Partial<IIssueDisplayProperties>) => {
      void updateFilters(workspaceSlug, undefined, EIssueFilterType.DISPLAY_PROPERTIES, property, categoryId);
    },
    [updateFilters, workspaceSlug, categoryId]
  );

  return (
    <Header>
      <Header.LeftItem>
        <div className="flex min-w-0 items-center gap-4">
          <Breadcrumbs>
            <Breadcrumbs.Item
              component={
                <BreadcrumbLink
                  label={t("jp_categories.board.breadcrumb")}
                  icon={<BoardOutline className="size-4 text-tertiary" />}
                />
              }
            />
            <Breadcrumbs.Item
              component={
                <BreadcrumbNavigationSelect
                  selectedItemKey={categoryId}
                  navigationItems={switcherOptions}
                  onChange={(value: string) => {
                    if (value !== categoryId) router.push(`/${workspaceSlug}/boards/${value}`);
                  }}
                  label={category?.name ?? t("jp_categories.board.title")}
                  icon={<BoardOutline className="size-4 shrink-0 text-tertiary" />}
                  placeholder={t("jp_categories.board.switch_board")}
                  searchPlaceholder={t("common.search.label")}
                  emptyMessage={t("common.search.no_matches_found")}
                  isLast
                />
              }
              isLast
            />
          </Breadcrumbs>
          {category && (
            <CategoryBoardProjects
              workspaceSlug={workspaceSlug}
              categoryId={categoryId}
              maxVisible={MAX_HEADER_PROJECTS}
              className="hidden flex-nowrap overflow-hidden lg:flex"
            />
          )}
        </div>
      </Header.LeftItem>
      <Header.RightItem className="items-center">
        <LayoutSelection
          layouts={BOARD_LAYOUTS}
          onChange={(layout) => handleDisplayFilters({ layout })}
          selectedLayout={activeLayout}
        />
        <WorkItemFiltersToggle entityType={EIssuesStoreType.CATEGORY_BOARD} entityId={categoryId} />
        <FiltersDropdown title={t("common.display")} placement="bottom-end">
          <DisplayFiltersSelection
            layoutDisplayFiltersOptions={layoutDisplayFiltersOptions}
            displayFilters={issueFilters?.displayFilters ?? {}}
            handleDisplayFiltersUpdate={handleDisplayFilters}
            displayProperties={issueFilters?.displayProperties ?? {}}
            handleDisplayPropertiesUpdate={handleDisplayProperties}
          />
        </FiltersDropdown>
      </Header.RightItem>
    </Header>
  );
});
