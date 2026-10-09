/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity data bootstrap for the project-categories feature (owned by that feature).
// These hooks are called unconditionally by JiraParityWorkspaceDataLoader / JiraParityProjectDataLoader
// (components/jira-parity/data-loaders.tsx).
import useSWR from "swr";
// plane imports
import { JP_PROJECT_CATEGORIES_SWR_KEY } from "@plane/constants";
// hooks
import { useProjectCategories } from "@/hooks/store/jira-parity/use-project-categories";

/**
 * Runs once the workspace is loaded: categories feed the sidebar boards, the projects list and the pickers.
 * The loader is keyed by workspace and the store holds one workspace, so every mount reloads it: own SWR key
 * (a finished settings-page request must not stand in for it) and no dedupe window.
 */
export function useProjectCategoriesWorkspaceBootstrap(workspaceSlug: string): void {
  const { fetchProjectCategories } = useProjectCategories();
  useSWR(
    workspaceSlug ? [JP_PROJECT_CATEGORIES_SWR_KEY(workspaceSlug), "bootstrap"] : null,
    workspaceSlug ? () => fetchProjectCategories(workspaceSlug) : null,
    {
      revalidateOnMount: true,
      dedupingInterval: 0,
      revalidateOnFocus: false,
      shouldRetryOnError: false,
    }
  );
}

/** Runs once the project is loaded and accessible (mounted in layouts/auth-layout/project-wrapper.tsx). */
export function useProjectCategoriesProjectBootstrap(_workspaceSlug: string, _projectId: string): void {
  // categories are workspace-level data, nothing to load per project
}
