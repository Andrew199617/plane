/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: master board quick filter bar (the Jira-like "Sprint" filter: cycles by NAME across the category's
// projects) and the category's project chips shown in the board header. Project / type / priority / assignee / ...
// live in the rich filters row.
import { observer } from "mobx-react";
import Link from "next/link";
import { CyclesOutline } from "@makeplane/propel/icons";
import { Tooltip } from "@makeplane/propel/components/tooltip";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import { Select } from "@plane/blocks/select";
import type { TProjectCategoryCycle } from "@plane/types";
import { EIssuesStoreType } from "@plane/types";
import { cn, renderFormattedDate } from "@plane/utils";
// hooks
import { useProjectCategories } from "@/hooks/store/jira-parity/use-project-categories";
import { useIssues } from "@/hooks/store/use-issues";
import { useProject } from "@/hooks/store/use-project";

type TCategoryBoardQuickFiltersRowProps = {
  workspaceSlug: string;
  categoryId: string;
};

export const CategoryBoardQuickFiltersRow = observer(function CategoryBoardQuickFiltersRow(
  props: TCategoryBoardQuickFiltersRowProps
) {
  const { workspaceSlug, categoryId } = props;
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-subtle px-page-x py-2">
      <CategoryBoardSprintFilter workspaceSlug={workspaceSlug} categoryId={categoryId} />
      {/* on wide screens the projects are shown in the board header */}
      <CategoryBoardProjects workspaceSlug={workspaceSlug} categoryId={categoryId} className="lg:hidden" />
    </div>
  );
});

type TCategoryBoardProjectsProps = TCategoryBoardQuickFiltersRowProps & {
  /** Max project chips before collapsing the rest into a "+N" chip. */
  maxVisible?: number;
  className?: string;
};

/** The category's projects (logo + key), each linking to the project's work items. Shown in the board header. */
export const CategoryBoardProjects = observer(function CategoryBoardProjects(props: TCategoryBoardProjectsProps) {
  const { workspaceSlug, categoryId, maxVisible = Number.POSITIVE_INFINITY, className } = props;
  const { t } = useTranslation();
  const { getProjectIdsByCategoryId } = useProjectCategories();
  const { getPartialProjectById } = useProject();
  const projectIds = getProjectIdsByCategoryId(categoryId);
  const visibleProjectIds = projectIds.slice(0, maxVisible);
  const hiddenProjectNames = projectIds
    .slice(maxVisible)
    .map((projectId) => getPartialProjectById(projectId)?.name)
    .filter(Boolean)
    .join(", ");

  return (
    <div className={cn("flex min-w-0 flex-wrap items-center gap-1.5", className)} data-testid="category-board-projects">
      <span className="text-caption-md-medium text-tertiary">{t("jp_categories.board.projects")}</span>
      {projectIds.length === 0 && (
        <span className="text-caption-md-regular text-placeholder">{t("jp_categories.board.no_projects")}</span>
      )}
      {hiddenProjectNames && (
        <Tooltip label={hiddenProjectNames}>
          <span className="order-last flex h-6 items-center rounded-md border border-subtle bg-layer-2 px-1.5 text-caption-md-medium text-tertiary">
            +{projectIds.length - visibleProjectIds.length}
          </span>
        </Tooltip>
      )}
      {visibleProjectIds.map((projectId) => {
        const project = getPartialProjectById(projectId);
        if (!project) return null;
        return (
          <Tooltip key={projectId} label={project.name}>
            <Link
              href={`/${workspaceSlug}/projects/${projectId}/issues`}
              className="flex h-6 items-center gap-1 rounded-md border border-subtle bg-layer-2 px-1.5 text-caption-md-medium text-secondary hover:bg-layer-2-hover"
            >
              <span className="grid size-4 shrink-0 place-items-center">
                <Logo logo={project.logo_props} size={12} />
              </span>
              <span>{project.identifier}</span>
            </Link>
          </Tooltip>
        );
      })}
    </div>
  );
});

/** Sprint (cycle) filter by NAME: "Sprint 1" matches that sprint in every project of the category. */
export const CategoryBoardSprintFilter = observer(function CategoryBoardSprintFilter(
  props: TCategoryBoardQuickFiltersRowProps
) {
  const { workspaceSlug, categoryId } = props;
  const { t } = useTranslation();
  const { getCategoryCycles } = useProjectCategories();
  const {
    issuesFilter: { getQuickFilters, updateQuickFilters },
  } = useIssues(EIssuesStoreType.CATEGORY_BOARD);
  // derived values
  const cycles = getCategoryCycles(categoryId) ?? [];
  const selectedNames = getQuickFilters(categoryId).cycle_names;

  const describeCycle = (cycle: TProjectCategoryCycle) => {
    const dates =
      cycle.start_date && cycle.end_date
        ? `${renderFormattedDate(cycle.start_date)} - ${renderFormattedDate(cycle.end_date)}`
        : undefined;
    const projects = t("jp_categories.board.projects_count", { count: cycle.project_ids.length });
    return dates ? `${dates} · ${projects}` : projects;
  };

  return (
    <Select<TProjectCategoryCycle>
      multiple
      valueIds={selectedNames}
      onChange={(names) => updateQuickFilters(workspaceSlug, categoryId, { cycle_names: names })}
      getValues={() => cycles}
      getOptionValue={(cycle) => cycle.name}
      getOptionLabel={(cycle) => cycle.name}
      getOptionIcon={() => <CyclesOutline className="size-3.5 shrink-0" />}
      getOptionDescription={describeCycle}
      getOptionPlaceholder={(name) => ({ name, start_date: null, end_date: null, project_ids: [] })}
      placeholder={t("jp_categories.board.sprint")}
      emptyMessage={t("jp_categories.board.no_sprints")}
      pinSelected={false}
    >
      <Select.Trigger<TProjectCategoryCycle>
        variant="pill-md"
        className={cn({ "border-accent-strong text-accent-primary": selectedNames.length > 0 })}
        prependIcon={() => <CyclesOutline className="size-3.5 shrink-0" />}
      >
        {(selected) => (
          <span className="truncate">
            {selected.length === 0
              ? t("jp_categories.board.sprint")
              : selected.length === 1
                ? selected[0].name
                : t("jp_categories.board.sprints_selected", { count: selected.length })}
          </span>
        )}
      </Select.Trigger>
    </Select>
  );
});
