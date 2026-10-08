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

/** Runs once the workspace is loaded: categories feed the sidebar boards, the projects list and the pickers. */
export function useProjectCategoriesWorkspaceBootstrap(workspaceSlug: string): void {
  const { fetchProjectCategories } = useProjectCategories();
  useSWR(
    workspaceSlug ? JP_PROJECT_CATEGORIES_SWR_KEY(workspaceSlug) : null,
    workspaceSlug ? () => fetchProjectCategories(workspaceSlug) : null,
    { revalidateIfStale: false, revalidateOnFocus: false, shouldRetryOnError: false }
  );
}

/** Runs once the project is loaded and accessible (mounted in layouts/auth-layout/project-wrapper.tsx). */
export function useProjectCategoriesProjectBootstrap(_workspaceSlug: string, _projectId: string): void {
  // categories are workspace-level data, nothing to load per project
}
