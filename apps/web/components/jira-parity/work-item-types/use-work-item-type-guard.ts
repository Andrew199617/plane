/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: hierarchy guard for changing the type of an existing work item in place
// (sidebar, peek, spreadsheet, header switcher). Owned by the work-item-types feature.
import { useCallback } from "react";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { TWorkItemType } from "@plane/types";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// local imports
import { getWorkItemTypeHierarchyError } from "./rules";

/**
 * Returns `getOptionDisabledReason` for WorkItemTypeSelect: a Sub-task needs a parent and cannot have
 * sub-work items, so it is disabled (with a reason) when the work item does not qualify.
 */
export const useWorkItemTypeOptionGuard = (issueId: string | undefined) => {
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  // derived values
  const issue = issueId ? getIssueById(issueId) : undefined;
  const hasParent = !!issue?.parent_id;
  const hasChildren = (issue?.sub_issues_count ?? 0) > 0;

  return useCallback(
    (workItemType: TWorkItemType): string | undefined => {
      const error = getWorkItemTypeHierarchyError(workItemType, { hasParent, hasChildren });
      if (error === "sub_task_requires_parent") return t("jp_work_item_types.select.needs_parent");
      if (error === "sub_task_cannot_have_children") return t("jp_work_item_types.select.has_children");
      return undefined;
    },
    [hasParent, hasChildren, t]
  );
};

/** Maps a server error (400/403 body) of a type change to a readable message. */
export const getWorkItemTypeUpdateErrorMessage = (error: unknown, fallback: string): string => {
  if (!error || typeof error !== "object") return fallback;
  const data = error as Record<string, unknown>;
  for (const key of ["type_id", "type", "parent_id", "parent", "error", "detail"]) {
    const value = data[key];
    if (typeof value === "string" && value) return value;
    if (Array.isArray(value) && typeof value[0] === "string") return value[0];
  }
  return fallback;
};
