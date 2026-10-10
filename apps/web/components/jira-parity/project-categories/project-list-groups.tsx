/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: projects list (/:workspaceSlug/projects) grouped by project category (owned by the project-categories
// feature). Wraps the upstream card grid of components/project/card-list.tsx: one collapsible section per category
// (with its master board link), then "Uncategorized". Without categories the grid renders flat, as upstream.
import { useState } from "react";
import type { ReactNode } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { BoardOutline, ChevronDownOutline, ChevronRightOutline } from "@makeplane/propel/icons";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { TProjectCategory } from "@plane/types";
// hooks
import { useProjectCategories } from "@/hooks/store/jira-parity/use-project-categories";
import { useProject } from "@/hooks/store/use-project";
import { useWorkspace } from "@/hooks/store/use-workspace";
// local imports
import { ProjectCategoryIcon } from "./category-select";
import { groupProjectIdsByCategory } from "./utils";

const COLLAPSED_STORAGE_KEY = "jp_projects_list_collapsed_categories";
const UNCATEGORIZED_KEY = "uncategorized";

const readCollapsed = (): string[] => {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(COLLAPSED_STORAGE_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((key): key is string => typeof key === "string") : [];
  } catch {
    return [];
  }
};

const writeCollapsed = (keys: string[]) => {
  try {
    window.localStorage.setItem(COLLAPSED_STORAGE_KEY, JSON.stringify(keys));
  } catch {
    // storage unavailable: collapse state is kept in memory only
  }
};

type TProjectCategoryCardGroupsProps = {
  projectIds: string[];
  /** Renders the upstream card grid for a list of project ids. */
  children: (projectIds: string[]) => ReactNode;
};

type TProjectCategorySectionProps = {
  category: TProjectCategory | null;
  projectIds: string[];
  isCollapsed: boolean;
  onToggle: () => void;
  children: ReactNode;
};

const ProjectCategorySection = observer(function ProjectCategorySection(props: TProjectCategorySectionProps) {
  const { category, projectIds, isCollapsed, onToggle, children } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { currentWorkspace } = useWorkspace();
  // derived values
  const title = category?.name ?? t("jp_categories.projects_list.uncategorized");
  const sectionId = `jp-project-category-${category?.id ?? UNCATEGORIZED_KEY}`;

  return (
    <section className="flex flex-col gap-4" data-testid={`projects-category-section-${category?.name ?? "none"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-subtle pb-2">
        <button
          type="button"
          className="flex min-w-0 items-center gap-2 text-left"
          onClick={onToggle}
          aria-expanded={!isCollapsed}
          aria-controls={sectionId}
        >
          {isCollapsed ? (
            <ChevronRightOutline className="size-3.5 shrink-0 text-tertiary" />
          ) : (
            <ChevronDownOutline className="size-3.5 shrink-0 text-tertiary" />
          )}
          {category && <ProjectCategoryIcon category={category} className="size-4 shrink-0 text-secondary" />}
          <span className="truncate text-body-sm-semibold text-primary">{title}</span>
          <span className="shrink-0 text-body-xs-regular text-tertiary">
            {t("jp_categories.projects_list.projects_count", { count: projectIds.length })}
          </span>
        </button>
        {category && currentWorkspace?.slug && (
          <Link
            href={`/${currentWorkspace.slug}/boards/${category.id}`}
            className="flex h-7 items-center gap-1.5 rounded-md border border-subtle px-2 text-body-xs-medium text-secondary hover:bg-layer-1-hover"
          >
            <BoardOutline className="size-3.5" />
            {t("jp_categories.projects_list.open_board")}
          </Link>
        )}
      </div>
      {!isCollapsed && <div id={sectionId}>{children}</div>}
    </section>
  );
});

export const ProjectCategoryCardGroups = observer(function ProjectCategoryCardGroups(
  props: TProjectCategoryCardGroupsProps
) {
  const { projectIds, children } = props;
  // states
  const [collapsedKeys, setCollapsedKeys] = useState<string[]>(readCollapsed);
  // store hooks
  const { sortedCategories } = useProjectCategories();
  const { getPartialProjectById } = useProject();

  // no categories: upstream flat grid
  if (sortedCategories.length === 0) return <>{children(projectIds)}</>;

  const groups = groupProjectIdsByCategory(
    projectIds,
    sortedCategories,
    (projectId) => getPartialProjectById(projectId)?.category_id
  );

  const toggle = (key: string) => {
    const next = collapsedKeys.includes(key) ? collapsedKeys.filter((item) => item !== key) : [...collapsedKeys, key];
    setCollapsedKeys(next);
    writeCollapsed(next);
  };

  return (
    <div className="flex flex-col gap-8">
      {groups.map((group) => {
        const key = group.category?.id ?? UNCATEGORIZED_KEY;
        return (
          <ProjectCategorySection
            key={key}
            category={group.category}
            projectIds={group.projectIds}
            isCollapsed={collapsedKeys.includes(key)}
            onToggle={() => toggle(key)}
          >
            {children(group.projectIds)}
          </ProjectCategorySection>
        );
      })}
    </div>
  );
});
