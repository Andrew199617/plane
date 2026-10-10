/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: spreadsheet "Original estimate" / "Remaining estimate" columns, registered as
// SPREADSHEET_COLUMNS.original_estimate / .remaining_estimate (owned by the time-tracking feature).
import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
// local imports
import type { TJiraParitySpreadsheetColumnProps } from "../types";
import { TimeEstimateInput } from "./time-estimate-input";
import { getTimeTrackingPayload } from "./utils";
import type { TTimeTrackingField } from "./utils";

type TSpreadsheetTimeEstimateCellProps = TJiraParitySpreadsheetColumnProps & { field: TTimeTrackingField };

const SpreadsheetTimeEstimateCell = observer(function SpreadsheetTimeEstimateCell(
  props: TSpreadsheetTimeEstimateCellProps
) {
  const { issue, onChange, onClose, disabled, field } = props;
  // plane hooks
  const { t } = useTranslation();

  return (
    <div className="h-11 border-b-[0.5px] border-subtle">
      <TimeEstimateInput
        testId={`spreadsheet-${field.replace("_", "-")}`}
        value={issue[field]}
        onChange={(minutes) =>
          onChange(issue, getTimeTrackingPayload(field, minutes), { changed_property: field, change_details: minutes })
        }
        label={t(`jp_time_tracking.${field}`)}
        placeholder={t("common.none")}
        disabled={disabled}
        onClose={onClose}
        // `.clickable` is what the table's keyboard navigation clicks on Enter / Space in a focused cell.
        className="clickable"
        variant="table-cell"
      />
    </div>
  );
});

export const SpreadsheetOriginalEstimateColumn = observer(function SpreadsheetOriginalEstimateColumn(
  props: TJiraParitySpreadsheetColumnProps
) {
  return <SpreadsheetTimeEstimateCell {...props} field="original_estimate" />;
});

export const SpreadsheetRemainingEstimateColumn = observer(function SpreadsheetRemainingEstimateColumn(
  props: TJiraParitySpreadsheetColumnProps
) {
  return <SpreadsheetTimeEstimateCell {...props} field="remaining_estimate" />;
});
