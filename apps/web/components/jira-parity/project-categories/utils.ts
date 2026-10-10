/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: pure UI helpers of the project-categories feature (no imports, so Node can run them directly:
// `node --test components/jira-parity/project-categories/utils.test.mjs` from apps/web).

/**
 * First human readable message of an API error thrown by the services (`error.response.data`):
 * `{error}`, `{detail}`, DRF field errors (`{name: ["..."]}`) or a plain string; `fallback` otherwise.
 */
export const getProjectCategoryErrorMessage = (error: unknown, fallback: string): string => {
  if (typeof error === "string" && error.trim()) return error;
  if (!error || typeof error !== "object") return fallback;
  const record = error as Record<string, unknown>;
  for (const key of ["error", "detail"]) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  for (const value of Object.values(record)) {
    if (typeof value === "string" && value.trim()) return value;
    if (Array.isArray(value)) {
      const message = value.find((item): item is string => typeof item === "string" && item.trim() !== "");
      if (message) return message;
    }
  }
  return fallback;
};

export type TCategorizedProjectGroup<C> = {
  /** null for the "Uncategorized" group */
  category: C | null;
  projectIds: string[];
};

/**
 * Groups project ids by category for the projects list: one group per category that has matching projects (in the
 * given category order), then the uncategorized projects. Project order inside a group follows `projectIds`.
 */
export const groupProjectIdsByCategory = <C extends { id: string }>(
  projectIds: string[],
  categories: C[],
  getProjectCategoryId: (projectId: string) => string | null | undefined
): TCategorizedProjectGroup<C>[] => {
  const byCategory = new Map<string, string[]>();
  const uncategorized: string[] = [];
  const knownCategoryIds = new Set(categories.map((category) => category.id));

  for (const projectId of projectIds) {
    const categoryId = getProjectCategoryId(projectId);
    if (!categoryId || !knownCategoryIds.has(categoryId)) {
      uncategorized.push(projectId);
      continue;
    }
    const group = byCategory.get(categoryId);
    if (group) group.push(projectId);
    else byCategory.set(categoryId, [projectId]);
  }

  const groups: TCategorizedProjectGroup<C>[] = categories
    .filter((category) => byCategory.has(category.id))
    .map((category) => ({ category, projectIds: byCategory.get(category.id) ?? [] }));
  if (uncategorized.length > 0) groups.push({ category: null, projectIds: uncategorized });
  return groups;
};
