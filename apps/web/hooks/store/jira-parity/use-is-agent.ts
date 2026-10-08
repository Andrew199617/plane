/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: agent role helper (owned by the agents feature)
import { useParams } from "next/navigation";
// hooks
import { useUserPermissions } from "@/hooks/store/user";

/**
 * Returns whether the current user is an agent (role 10).
 * With a `projectId` (or a project in the route) it checks the project role, otherwise the workspace role.
 * Must be called from an observer component to stay reactive.
 */
export const useIsAgent = (projectId?: string | null): boolean => {
  const { workspaceSlug, projectId: routerProjectId } = useParams();
  const { isAgentInProject, isAgentInWorkspace } = useUserPermissions();

  const resolvedWorkspaceSlug = workspaceSlug?.toString();
  const resolvedProjectId = projectId ?? routerProjectId?.toString();

  if (resolvedProjectId) return isAgentInProject(resolvedWorkspaceSlug, resolvedProjectId);
  return isAgentInWorkspace(resolvedWorkspaceSlug);
};
