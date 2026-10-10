/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity shared component prop types (scaffold-owned)
import type { ComponentProps } from "react";
import type { TSpreadsheetColumn } from "@plane/types";
import type { TIssueOperations } from "@/components/issues/issue-detail/root";

/** Props passed by the issue detail sidebar and the peek overview to the jira-parity property slot. */
export type TJiraParityIssuePropertyProps = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled: boolean;
  /** Same operations object the surrounding sidebar/peek uses (update -> optimistic store update + toast). */
  issueOperations: TIssueOperations;
};

/** Props of a spreadsheet column component registered in SPREADSHEET_COLUMNS. */
export type TJiraParitySpreadsheetColumnProps = ComponentProps<TSpreadsheetColumn>;
