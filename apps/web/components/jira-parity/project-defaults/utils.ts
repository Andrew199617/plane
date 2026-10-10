/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity project lead / default assignee helpers (dependency-free so `node --test` can import them).

/** Project.default_assignee / project_lead are ids in list payloads and may be user objects elsewhere. */
export const getProjectUserId = (value: unknown): string | null => {
  if (!value) return null;
  if (typeof value === "string") return value;
  if (typeof value === "object" && "id" in value && typeof value.id === "string" && value.id) return value.id;
  return null;
};

/**
 * The assignee the create-work-item modal should pre-fill, or null.
 * `projectMemberIds` null means the project members are not loaded yet: trust the server, which keeps
 * the default assignee a project member.
 */
export const getPrefillAssigneeId = (defaultAssignee: unknown, projectMemberIds: string[] | null): string | null => {
  const defaultAssigneeId = getProjectUserId(defaultAssignee);
  if (!defaultAssigneeId) return null;
  if (projectMemberIds !== null && !projectMemberIds.includes(defaultAssigneeId)) return null;
  return defaultAssigneeId;
};
