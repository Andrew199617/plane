/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity data bootstrap for the workflows feature (owned by that feature).
// These hooks are called unconditionally by JiraParityWorkspaceDataLoader / JiraParityProjectDataLoader
// (components/jira-parity/data-loaders.tsx).
import useSWR from "swr";
// plane imports
import { JP_MY_STATE_TRANSITIONS_SWR_KEY } from "@plane/constants";
// hooks
import { useWorkflows } from "@/hooks/store/jira-parity/use-workflows";

/** Runs once the workspace is loaded (mounted in layouts/auth-layout/workspace-wrapper.tsx). */
export function useWorkflowsWorkspaceBootstrap(_workspaceSlug: string): void {
  // Workspace-level boards resolve transitions lazily per project (StateSelect fetches on open).
}

/**
 * Runs once the project is loaded and accessible (mounted in layouts/auth-layout/project-wrapper.tsx, keyed by
 * project). Loads the current user's allowed state transitions, used by state dropdowns and kanban/list drag;
 * refetched on every visit of the project so rules or states changed meanwhile apply.
 */
export function useWorkflowsProjectBootstrap(workspaceSlug: string, projectId: string): void {
  const { fetchMyTransitions } = useWorkflows();

  useSWR(
    workspaceSlug && projectId ? JP_MY_STATE_TRANSITIONS_SWR_KEY(projectId) : null,
    workspaceSlug && projectId ? () => fetchMyTransitions(workspaceSlug, projectId) : null,
    { revalidateOnMount: true, revalidateOnFocus: false, shouldRetryOnError: false }
  );
}
