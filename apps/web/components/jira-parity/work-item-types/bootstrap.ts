/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity data bootstrap for the work-item-types feature (owned by that feature).
// These hooks are called unconditionally by JiraParityWorkspaceDataLoader / JiraParityProjectDataLoader
// (components/jira-parity/data-loaders.tsx).
import useSWR from "swr";
// plane imports
import { JP_WORK_ITEM_TYPES_SWR_KEY } from "@plane/constants";
// hooks
import { useWorkItemTypes } from "@/hooks/store/jira-parity/use-work-item-types";

/**
 * Runs once the workspace is loaded (mounted in layouts/auth-layout/workspace-wrapper.tsx, keyed by workspace).
 * The store holds one workspace, so every mount reloads it: own SWR key (a finished settings-page request must not
 * stand in for it) and no dedupe window.
 */
export function useWorkItemTypesWorkspaceBootstrap(workspaceSlug: string): void {
  const { fetchWorkItemTypes } = useWorkItemTypes();

  useSWR(
    workspaceSlug ? [JP_WORK_ITEM_TYPES_SWR_KEY(workspaceSlug), "bootstrap"] : null,
    workspaceSlug ? () => fetchWorkItemTypes(workspaceSlug) : null,
    { revalidateOnMount: true, dedupingInterval: 0, revalidateOnFocus: false }
  );
}

/**
 * Runs once the project is loaded and accessible (mounted in layouts/auth-layout/project-wrapper.tsx).
 * Work item types are workspace-level and enabled in every project, so the workspace list is enough.
 */
export function useWorkItemTypesProjectBootstrap(_workspaceSlug: string, _projectId: string): void {
  // nothing project-specific to load
}
