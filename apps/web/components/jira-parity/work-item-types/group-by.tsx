/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: group-by "issue_type" columns, wired into getGroupByColumns (issue-layouts/utils.tsx)
// (owned by the work-item-types feature). Returning undefined renders no groups.
import type { IGroupByColumn, TGetColumns } from "@plane/types";
// store
import { store } from "@/lib/store-context";
// local imports
import { WorkItemTypeIcon } from "./icons";

/** One column per active work item type (plus inactive ones), payload `{ type_id }` so drops change the type. */
export const getWorkItemTypeGroupByColumns = (_params: TGetColumns): IGroupByColumn[] | undefined => {
  const { workItemTypes } = store.jiraParity.workItemTypes;
  if (workItemTypes.length === 0) return undefined;

  return workItemTypes.map((workItemType) => ({
    id: workItemType.id,
    name: workItemType.name,
    icon: <WorkItemTypeIcon workItemType={workItemType} className="size-3.5" />,
    payload: { type_id: workItemType.id },
  }));
};
