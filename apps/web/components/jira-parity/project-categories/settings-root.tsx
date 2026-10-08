/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: workspace settings > Project categories (owned by the project-categories feature).
// Admins create / rename / delete categories, assign projects (a project belongs to at most one category) and
// reorder them (drag or the move buttons); the order drives the sidebar "Boards", the projects list and pickers.
import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import useSWR from "swr";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import {
  BoardOutline,
  ChevronDownOutline,
  ChevronUpOutline,
  DeleteOutline,
  EditOutline,
  GripOutline,
} from "@makeplane/propel/icons";
import { Sortable } from "@plane/blocks/common";
import { Loader } from "@plane/blocks/skeleton";
import { setToast } from "@plane/blocks/toast";
import { EUserPermissions, EUserPermissionsLevel, JP_PROJECT_CATEGORIES_SWR_KEY } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { TProjectCategory } from "@plane/types";
import { isEqual, sortBy } from "lodash-es";
// components
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { ProjectSelect } from "@/components/dropdowns/project/project-select";
// hooks
import { useProjectCategories } from "@/hooks/store/jira-parity/use-project-categories";
import { useProject } from "@/hooks/store/use-project";
import { useUserPermissions } from "@/hooks/store/user";
// local imports
import { ProjectCategoryIcon } from "./category-select";
import { ProjectCategoryDeleteModal, ProjectCategoryFormModal } from "./settings-modals";
import { getProjectCategoryErrorMessage } from "./utils";

type TProjectCategoriesSettingsRootProps = {
  workspaceSlug: string;
};

type TProjectCategoryRowProps = {
  workspaceSlug: string;
  category: TProjectCategory;
  index: number;
  total: number;
  onEdit: () => void;
  onDelete: () => void;
  onMove: (toIndex: number) => void;
};

/** Project picker of a category: selections are committed when the dropdown closes (one request per edit). */
const ProjectCategoryProjectsSelect = observer(function ProjectCategoryProjectsSelect(props: {
  workspaceSlug: string;
  category: TProjectCategory;
}) {
  const { workspaceSlug, category } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { getProjectIdsByCategoryId, setCategoryProjects } = useProjectCategories();
  // derived values
  const projectIds = getProjectIdsByCategoryId(category.id);
  // states
  const [draftProjectIds, setDraftProjectIds] = useState<string[]>(projectIds);
  const [isSaving, setIsSaving] = useState(false);

  // follow server / other-category changes while not editing
  useEffect(() => {
    if (!isSaving) setDraftProjectIds(projectIds);
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [projectIds.join(",")]);

  const commit = async () => {
    if (isEqual(sortBy(draftProjectIds), sortBy(projectIds))) return;
    setIsSaving(true);
    try {
      await setCategoryProjects(workspaceSlug, category.id, draftProjectIds);
      setToast({
        type: "success",
        title: t("jp_categories.settings.toast.projects_updated"),
        message: t("jp_categories.settings.projects_count", { count: draftProjectIds.length }),
      });
    } catch (error) {
      setDraftProjectIds(projectIds);
      setToast({
        type: "error",
        title: t("jp_categories.settings.toast.error"),
        message: getProjectCategoryErrorMessage(error, t("jp_categories.settings.toast.save_failed")),
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <ProjectSelect
      multiple
      projectList="all"
      variant="select-md"
      value={draftProjectIds}
      onChange={setDraftProjectIds}
      onClose={() => void commit()}
      disabled={isSaving}
      placeholder={t("jp_categories.settings.projects_placeholder")}
      className="w-full"
    />
  );
});

const ProjectCategoryRow = observer(function ProjectCategoryRow(props: TProjectCategoryRowProps) {
  const { workspaceSlug, category, index, total, onEdit, onDelete, onMove } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { getProjectIdsByCategoryId } = useProjectCategories();
  // derived values
  const projectCount = getProjectIdsByCategoryId(category.id).length;

  return (
    <div
      className="group flex items-start gap-3 bg-layer-1 px-4 py-3"
      data-testid={`project-category-row-${category.name}`}
    >
      <span className="mt-1.5 cursor-grab text-placeholder" aria-hidden>
        <GripOutline className="size-3.5" />
      </span>
      <span className="mt-1 grid size-6 shrink-0 place-items-center rounded-md bg-layer-2">
        <ProjectCategoryIcon category={category} className="size-3.5" />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 flex-col">
            <span className="truncate text-body-sm-medium text-primary">{category.name}</span>
            <span className="truncate text-body-xs-regular text-tertiary">
              {category.description?.trim() || t("jp_categories.settings.no_description")}
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <span className="mr-2 text-body-xs-regular text-tertiary">
              {t("jp_categories.settings.projects_count", { count: projectCount })}
            </span>
            <Link
              href={`/${workspaceSlug}/boards/${category.id}`}
              className="flex h-7 items-center gap-1.5 rounded-md border border-subtle px-2 text-body-xs-medium text-secondary hover:bg-layer-1-hover"
            >
              <BoardOutline className="size-3.5" />
              {t("jp_categories.settings.open_board")}
            </Link>
            <Tooltip label={t("jp_categories.settings.move_up")}>
              <IconButton
                variant="ghost"
                size="sm"
                icon={<Icon icon={ChevronUpOutline} />}
                disabled={index === 0}
                onClick={() => onMove(index - 1)}
                aria-label={t("jp_categories.settings.move_up")}
              />
            </Tooltip>
            <Tooltip label={t("jp_categories.settings.move_down")}>
              <IconButton
                variant="ghost"
                size="sm"
                icon={<Icon icon={ChevronDownOutline} />}
                disabled={index === total - 1}
                onClick={() => onMove(index + 1)}
                aria-label={t("jp_categories.settings.move_down")}
              />
            </Tooltip>
            <Tooltip label={t("jp_categories.settings.edit")}>
              <IconButton
                variant="ghost"
                size="sm"
                icon={<Icon icon={EditOutline} />}
                onClick={onEdit}
                aria-label={t("jp_categories.settings.edit")}
                data-testid={`project-category-edit-${category.name}`}
              />
            </Tooltip>
            <Tooltip label={t("jp_categories.settings.delete")}>
              <IconButton
                variant="ghost"
                size="sm"
                icon={<Icon icon={DeleteOutline} />}
                onClick={onDelete}
                aria-label={t("jp_categories.settings.delete")}
                data-testid={`project-category-delete-${category.name}`}
              />
            </Tooltip>
          </div>
        </div>
        <ProjectCategoryProjectsSelect workspaceSlug={workspaceSlug} category={category} />
      </div>
    </div>
  );
});

export const ProjectCategoriesSettingsRoot = observer(function ProjectCategoriesSettingsRoot(
  props: TProjectCategoriesSettingsRootProps
) {
  const { workspaceSlug } = props;
  // states
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingCategoryId, setEditingCategoryId] = useState<string | null>(null);
  const [deletingCategoryId, setDeletingCategoryId] = useState<string | null>(null);
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { sortedCategories, fetchedWorkspaceSlug, fetchProjectCategories, getCategoryById, moveCategory } =
    useProjectCategories();
  const { workspaceProjectIds, getProjectById } = useProject();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  // derived values
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  const isLoaded = fetchedWorkspaceSlug === workspaceSlug;
  const uncategorizedCount = (workspaceProjectIds ?? []).filter((projectId) => {
    const project = getProjectById(projectId);
    return project && !project.archived_at && !project.category_id;
  }).length;
  // always refresh on open (the workspace bootstrap shares this key)
  const { error, isLoading } = useSWR(
    workspaceSlug ? JP_PROJECT_CATEGORIES_SWR_KEY(workspaceSlug) : null,
    workspaceSlug ? () => fetchProjectCategories(workspaceSlug) : null,
    { revalidateOnFocus: false, revalidateOnMount: true }
  );

  const handleMove = async (categoryId: string, toIndex: number) => {
    try {
      await moveCategory(workspaceSlug, categoryId, toIndex);
    } catch (moveError) {
      setToast({
        type: "error",
        title: t("jp_categories.settings.toast.error"),
        message: getProjectCategoryErrorMessage(moveError, t("jp_categories.settings.toast.reorder_failed")),
      });
      void fetchProjectCategories(workspaceSlug);
    }
  };

  if (workspaceUserInfo && !isAdmin) return <NotAuthorizedView section="settings" className="h-auto" />;

  if (!isLoaded && (isLoading || !error))
    return (
      <Loader className="flex flex-col gap-2">
        <Loader.Item height="72px" />
        <Loader.Item height="72px" />
        <Loader.Item height="72px" />
      </Loader>
    );

  if (!isLoaded && error)
    return <p className="text-body-sm-regular text-danger-primary">{t("jp_categories.settings.load_failed")}</p>;

  return (
    <div className="flex flex-col gap-4" data-testid="project-categories-settings">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-body-xs-regular text-tertiary">
          {t("jp_categories.settings.uncategorized_count", { count: uncategorizedCount })}
        </p>
        <Button
          variant="primary"
          size="md"
          stretch="auto"
          label={t("jp_categories.settings.add")}
          onClick={() => setIsCreateOpen(true)}
          data-testid="project-category-add"
        />
      </div>
      {sortedCategories.length === 0 ? (
        <div className="flex flex-col items-center gap-1 rounded-md border border-dashed border-subtle px-4 py-8 text-center">
          <p className="text-body-sm-medium text-secondary">{t("jp_categories.settings.empty_title")}</p>
          <p className="text-body-xs-regular text-tertiary">{t("jp_categories.settings.empty_description")}</p>
        </div>
      ) : (
        <div className="divide-y divide-subtle overflow-hidden rounded-lg border border-subtle">
          <Sortable
            data={sortedCategories}
            keyExtractor={(category) => category.id}
            onChange={(reordered, movedCategory) => {
              if (!movedCategory) return;
              const toIndex = reordered.findIndex((category) => category.id === movedCategory.id);
              if (toIndex >= 0) void handleMove(movedCategory.id, toIndex);
            }}
            render={(category, index) => (
              <ProjectCategoryRow
                workspaceSlug={workspaceSlug}
                category={category}
                index={index}
                total={sortedCategories.length}
                onEdit={() => setEditingCategoryId(category.id)}
                onDelete={() => setDeletingCategoryId(category.id)}
                onMove={(toIndex) => void handleMove(category.id, toIndex)}
              />
            )}
          />
        </div>
      )}
      <ProjectCategoryFormModal
        workspaceSlug={workspaceSlug}
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
      />
      <ProjectCategoryFormModal
        workspaceSlug={workspaceSlug}
        category={getCategoryById(editingCategoryId)}
        isOpen={!!editingCategoryId}
        onClose={() => setEditingCategoryId(null)}
      />
      <ProjectCategoryDeleteModal
        workspaceSlug={workspaceSlug}
        category={getCategoryById(deletingCategoryId)}
        isOpen={!!deletingCategoryId}
        onClose={() => setDeletingCategoryId(null)}
      />
    </div>
  );
});
