/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: project categories store (owned by the project-categories feature)
import { isEqual, set, sortBy } from "lodash-es";
import { action, computed, makeObservable, observable, runInAction } from "mobx";
import { computedFn } from "mobx-utils";
// plane imports
import { JP_PROJECT_CATEGORY_SORT_ORDER_GAP } from "@plane/constants";
import type { TProjectCategory, TProjectCategoryCycle, TProjectCategoryPayload } from "@plane/types";
// services
import { ProjectCategoriesService } from "@/services/jira-parity/project-categories.service";
// store
import { computeReorderedSortOrders, getCategoryProjectIds } from "@/store/jira-parity/category-board/helpers";
import type { CoreRootStore } from "@/store/root.store";

export interface IProjectCategoriesStore {
  // observables
  categoryMap: Record<string, TProjectCategory>;
  fetchedWorkspaceSlug: string | null;
  cyclesMap: Record<string, TProjectCategoryCycle[]>;
  // computed
  sortedCategories: TProjectCategory[];
  // computed actions
  getCategoryById: (categoryId: string | null | undefined) => TProjectCategory | undefined;
  getProjectIdsByCategoryId: (categoryId: string | null | undefined) => string[];
  getCategoryIdByProjectId: (projectId: string | null | undefined) => string | null;
  getCategoryCycles: (categoryId: string | null | undefined) => TProjectCategoryCycle[] | undefined;
  // fetch actions
  fetchProjectCategories: (workspaceSlug: string) => Promise<TProjectCategory[]>;
  fetchCategoryCycles: (workspaceSlug: string, categoryId: string) => Promise<TProjectCategoryCycle[]>;
  // CRUD actions
  createCategory: (workspaceSlug: string, data: TProjectCategoryPayload) => Promise<TProjectCategory>;
  updateCategory: (
    workspaceSlug: string,
    categoryId: string,
    data: TProjectCategoryPayload
  ) => Promise<TProjectCategory>;
  deleteCategory: (workspaceSlug: string, categoryId: string) => Promise<void>;
  moveCategory: (workspaceSlug: string, categoryId: string, toIndex: number) => Promise<void>;
  setCategoryProjects: (workspaceSlug: string, categoryId: string, projectIds: string[]) => Promise<void>;
  setProjectCategory: (workspaceSlug: string, projectId: string, categoryId: string | null) => Promise<void>;
}

export class ProjectCategoriesStore implements IProjectCategoriesStore {
  // observables
  categoryMap: Record<string, TProjectCategory> = {};
  fetchedWorkspaceSlug: string | null = null;
  cyclesMap: Record<string, TProjectCategoryCycle[]> = {};
  // root store
  rootStore: CoreRootStore;
  // services
  service: ProjectCategoriesService;

  constructor(rootStore: CoreRootStore) {
    makeObservable(this, {
      categoryMap: observable,
      fetchedWorkspaceSlug: observable.ref,
      cyclesMap: observable,
      sortedCategories: computed,
      fetchProjectCategories: action,
      fetchCategoryCycles: action,
      createCategory: action,
      updateCategory: action,
      deleteCategory: action,
      moveCategory: action,
      setCategoryProjects: action,
      setProjectCategory: action,
    });
    this.rootStore = rootStore;
    this.service = new ProjectCategoriesService();
  }

  get sortedCategories() {
    return sortBy(Object.values(this.categoryMap), ["sort_order", (category) => category.name.toLowerCase()]);
  }

  getCategoryById = computedFn((categoryId: string | null | undefined) =>
    categoryId ? this.categoryMap[categoryId] : undefined
  );

  /** Active (non-archived) projects of the category in the current workspace. */
  getProjectIdsByCategoryId = computedFn((categoryId: string | null | undefined): string[] => {
    if (!categoryId) return [];
    const category = this.categoryMap[categoryId];
    const { projectMap, workspaceProjectIds } = this.rootStore.projectRoot.project;
    const projects = (workspaceProjectIds ?? []).map((projectId) => projectMap[projectId]).filter(Boolean);
    if (projects.length === 0) return category?.project_ids ?? [];
    return getCategoryProjectIds(categoryId, category?.project_ids, projects);
  });

  getCategoryIdByProjectId = computedFn((projectId: string | null | undefined): string | null => {
    if (!projectId) return null;
    const project = this.rootStore.projectRoot.project.projectMap[projectId];
    if (project && project.category_id !== undefined) return project.category_id ?? null;
    return Object.values(this.categoryMap).find((category) => category.project_ids?.includes(projectId))?.id ?? null;
  });

  getCategoryCycles = computedFn((categoryId: string | null | undefined) =>
    categoryId ? this.cyclesMap[categoryId] : undefined
  );

  fetchProjectCategories = async (workspaceSlug: string) => {
    const categories = await this.service.list(workspaceSlug);
    runInAction(() => {
      this.categoryMap = Object.fromEntries(categories.map((category) => [category.id, category]));
      this.fetchedWorkspaceSlug = workspaceSlug;
    });
    return categories;
  };

  fetchCategoryCycles = async (workspaceSlug: string, categoryId: string) => {
    const cycles = await this.service.listCycles(workspaceSlug, categoryId);
    runInAction(() => {
      set(this.cyclesMap, [categoryId], cycles);
    });
    return cycles;
  };

  createCategory = async (workspaceSlug: string, data: TProjectCategoryPayload) => {
    const category = await this.service.create(workspaceSlug, data);
    runInAction(() => {
      set(this.categoryMap, [category.id], category);
    });
    this.syncProjectsCategory(category.id, category.project_ids ?? []);
    return category;
  };

  updateCategory = async (workspaceSlug: string, categoryId: string, data: TProjectCategoryPayload) => {
    const previous = this.categoryMap[categoryId];
    // optimistic update, rolled back on failure
    if (previous)
      runInAction(() => {
        set(this.categoryMap, [categoryId], { ...previous, ...data });
      });
    try {
      const category = await this.service.update(workspaceSlug, categoryId, data);
      runInAction(() => {
        set(this.categoryMap, [categoryId], { ...previous, ...category });
      });
      return category;
    } catch (error) {
      if (previous)
        runInAction(() => {
          set(this.categoryMap, [categoryId], previous);
        });
      throw error;
    }
  };

  deleteCategory = async (workspaceSlug: string, categoryId: string) => {
    const projectIds = this.getProjectIdsByCategoryId(categoryId);
    await this.service.destroy(workspaceSlug, categoryId);
    runInAction(() => {
      delete this.categoryMap[categoryId];
      delete this.cyclesMap[categoryId];
    });
    // the category's projects become uncategorized (Project.category is SET_NULL)
    const { projectMap } = this.rootStore.projectRoot.project;
    runInAction(() => {
      projectIds.forEach((projectId) => {
        if (projectMap[projectId]?.category_id === categoryId) set(projectMap, [projectId, "category_id"], null);
      });
    });
  };

  moveCategory = async (workspaceSlug: string, categoryId: string, toIndex: number) => {
    const categories = this.sortedCategories;
    const fromIndex = categories.findIndex((category) => category.id === categoryId);
    const updates = computeReorderedSortOrders(categories, fromIndex, toIndex, JP_PROJECT_CATEGORY_SORT_ORDER_GAP);
    if (updates.length === 0) return;
    await Promise.all(
      updates.map((update) => this.updateCategory(workspaceSlug, update.id, { sort_order: update.sort_order }))
    );
  };

  /**
   * Sets exactly which projects belong to the category: PATCH project_ids on the category; if the API does not
   * apply project_ids, falls back to PATCHing category_id on each changed project.
   */
  setCategoryProjects = async (workspaceSlug: string, categoryId: string, projectIds: string[]) => {
    const currentProjectIds = this.getProjectIdsByCategoryId(categoryId);
    const wanted = sortBy([...new Set(projectIds)]);
    const category = await this.updateCategory(workspaceSlug, categoryId, { project_ids: wanted });

    const applied = isEqual(sortBy(category?.project_ids ?? []), wanted);
    if (!applied) {
      const added = wanted.filter((projectId) => !currentProjectIds.includes(projectId));
      const removed = currentProjectIds.filter((projectId) => !wanted.includes(projectId));
      await Promise.all([
        ...added.map((projectId) =>
          this.rootStore.projectRoot.project.updateProject(workspaceSlug, projectId, { category_id: categoryId })
        ),
        ...removed.map((projectId) =>
          this.rootStore.projectRoot.project.updateProject(workspaceSlug, projectId, { category_id: null })
        ),
      ]);
      await this.fetchProjectCategories(workspaceSlug);
    }
    // other categories may have lost projects: keep every category's project_ids in sync
    this.syncProjectsCategory(categoryId, wanted, currentProjectIds);
    if (applied) await this.fetchProjectCategories(workspaceSlug);
  };

  /** Moves one project to a category (or to no category) through the project API. */
  setProjectCategory = async (workspaceSlug: string, projectId: string, categoryId: string | null) => {
    await this.rootStore.projectRoot.project.updateProject(workspaceSlug, projectId, { category_id: categoryId });
    await this.fetchProjectCategories(workspaceSlug);
  };

  /** Mirrors a category membership change on the loaded projects (category_id) and on the other categories. */
  private syncProjectsCategory = (categoryId: string, projectIds: string[], previousProjectIds: string[] = []) => {
    const { projectMap } = this.rootStore.projectRoot.project;
    runInAction(() => {
      projectIds.forEach((projectId) => {
        if (projectMap[projectId]) set(projectMap, [projectId, "category_id"], categoryId);
      });
      previousProjectIds
        .filter((projectId) => !projectIds.includes(projectId))
        .forEach((projectId) => {
          if (projectMap[projectId]?.category_id === categoryId) set(projectMap, [projectId, "category_id"], null);
        });
      Object.values(this.categoryMap).forEach((category) => {
        if (category.id === categoryId) return;
        const remaining = (category.project_ids ?? []).filter((projectId) => !projectIds.includes(projectId));
        if (remaining.length !== (category.project_ids ?? []).length)
          set(this.categoryMap, [category.id, "project_ids"], remaining);
      });
    });
  };
}
