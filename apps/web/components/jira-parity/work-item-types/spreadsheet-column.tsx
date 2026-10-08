/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: spreadsheet "Type" column, registered as SPREADSHEET_COLUMNS.issue_type
// (owned by the work-item-types feature).
import { observer } from "mobx-react";
// local imports
import type { TJiraParitySpreadsheetColumnProps } from "../types";
import { WorkItemTypeSelect } from "./type-select";
import { useWorkItemTypeOptionGuard } from "./use-work-item-type-guard";

export const SpreadsheetWorkItemTypeColumn = observer(function SpreadsheetWorkItemTypeColumn(
  props: TJiraParitySpreadsheetColumnProps
) {
  const { issue, onChange, onClose, disabled } = props;
  // hooks
  const getOptionDisabledReason = useWorkItemTypeOptionGuard(issue.id);

  return (
    <div className="h-11 border-b-[0.5px] border-subtle">
      <WorkItemTypeSelect
        testId="spreadsheet-work-item-type-select"
        value={issue.type_id}
        onChange={(workItemTypeId) =>
          onChange(issue, { type_id: workItemTypeId }, { changed_property: "type", change_details: workItemTypeId })
        }
        getOptionDisabledReason={getOptionDisabledReason}
        disabled={disabled}
        onClose={onClose}
        // `.clickable` is what the table's keyboard navigation clicks on Enter / Space in a focused cell.
        className="clickable"
        variant="table-cell"
      />
    </div>
  );
});
