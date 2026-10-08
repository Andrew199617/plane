/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity data bootstrap for the teams feature (owned by that feature).
// These hooks are called unconditionally by JiraParityWorkspaceDataLoader / JiraParityProjectDataLoader
// (components/jira-parity/data-loaders.tsx).
import useSWR from "swr";
// plane imports
import { JP_TEAMS_SWR_KEY } from "@plane/constants";
// hooks
import { useTeams } from "@/hooks/store/jira-parity/use-teams";

/**
 * Runs once the workspace is loaded (mounted in layouts/auth-layout/workspace-wrapper.tsx).
 * Loads the workspace teams (used by the Teams settings page and the member-row team badges).
 */
export function useTeamsWorkspaceBootstrap(workspaceSlug: string): void {
  const { fetchTeams } = useTeams();
  useSWR(
    workspaceSlug ? JP_TEAMS_SWR_KEY(workspaceSlug) : null,
    workspaceSlug ? () => fetchTeams(workspaceSlug) : null,
    { revalidateIfStale: false, revalidateOnFocus: false, shouldRetryOnError: false }
  );
}

/** Runs once the project is loaded and accessible (mounted in layouts/auth-layout/project-wrapper.tsx). */
export function useTeamsProjectBootstrap(_workspaceSlug: string, _projectId: string): void {
  // no-op until the feature implements it
}
