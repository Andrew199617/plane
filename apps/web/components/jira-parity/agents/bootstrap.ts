/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity data bootstrap for the agents feature (owned by that feature).
// These hooks are called unconditionally by JiraParityWorkspaceDataLoader / JiraParityProjectDataLoader
// (components/jira-parity/data-loaders.tsx). Use useSWR + this feature's store to load data.

/** Runs once the workspace is loaded (mounted in layouts/auth-layout/workspace-wrapper.tsx). */
export function useAgentsWorkspaceBootstrap(_workspaceSlug: string): void {
  // no-op until the feature implements it
}

/** Runs once the project is loaded and accessible (mounted in layouts/auth-layout/project-wrapper.tsx). */
export function useAgentsProjectBootstrap(_workspaceSlug: string, _projectId: string): void {
  // no-op until the feature implements it
}
