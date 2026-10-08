/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity group-by column registry (scaffold-owned), spread into getGroupByColumns
// (components/issues/issue-layouts/utils.tsx). The column builders are owned by their features.
//
// Both keys are real group-by options: they are part of TIssueGroupByOptions (packages/types), the
// exhaustive records ISSUE_GROUP_BY_KEY / ISSUE_FILTER_DEFAULT_DATA (web + space base-issues stores) and
// EIssueGroupByToServerOptions / EIssueGroupBYServerToProperty / EServerGroupByToFilterOptions /
// ISSUE_GROUP_BY_OPTIONS (packages/constants). "state__name" is offered on category master boards only.
import type { IGroupByColumn, TGetColumns } from "@plane/types";
import { getWorkItemTypeGroupByColumns } from "./work-item-types/group-by";

export type TJiraParityGroupByKey = "issue_type";

export const JIRA_PARITY_GROUP_BY_COLUMNS: Record<
  TJiraParityGroupByKey,
  (params: TGetColumns) => IGroupByColumn[] | undefined
> = {
  issue_type: getWorkItemTypeGroupByColumns,
};
