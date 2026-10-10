/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: original/remaining estimate rows in the issue detail sidebar + peek overview
// (owned by the time-tracking feature). Rendered through <JiraParityIssueProperties/>.
import type { FC, ReactNode } from "react";
import { observer } from "mobx-react";
// plane imports
import { HourglassOutline, TimeTrackingOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// local imports
import type { TJiraParityIssuePropertyProps } from "../types";
import { TimeEstimateInput } from "./time-estimate-input";
import { getTimeTrackingPayload } from "./utils";
import type { TTimeTrackingField } from "./utils";

type TTimeTrackingRow = {
  field: TTimeTrackingField;
  icon: FC<{ className?: string }>;
  /** Short sidebar label (the 120px label column); the field's full name is used for accessibility. */
  rowLabelKey: string;
};

const TIME_TRACKING_ROWS: TTimeTrackingRow[] = [
  { field: "original_estimate", icon: TimeTrackingOutline, rowLabelKey: "jp_time_tracking.time_estimate" },
  { field: "remaining_estimate", icon: HourglassOutline, rowLabelKey: "jp_time_tracking.time_remaining" },
];

/**
 * Same layout as SidebarPropertyListItem (components/common/layout/sidebar/property-list-item.tsx), but the
 * label truncates (with a tooltip) instead of overflowing into the value when a translation is long.
 */
function TimeTrackingPropertyRow(props: {
  icon: FC<{ className?: string }>;
  label: string;
  /** Full field name shown on hover, e.g. "Original estimate". */
  tooltip: string;
  children: ReactNode;
}) {
  const { icon: Icon, label, tooltip, children } = props;
  return (
    <div className="flex items-start gap-2">
      <div className="flex h-7.5 w-30 shrink-0 items-center gap-1.5 text-body-xs-regular text-tertiary" title={tooltip}>
        <Icon className="size-4 shrink-0" />
        <span className="min-w-0 truncate">{label}</span>
      </div>
      <div className="flex min-w-0 grow flex-wrap items-center gap-1">{children}</div>
    </div>
  );
}

export const TimeTrackingIssueProperties = observer(function TimeTrackingIssueProperties(
  props: TJiraParityIssuePropertyProps
) {
  const { workspaceSlug, projectId, issueId, disabled, issueOperations } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  // derived values
  const issue = getIssueById(issueId);

  if (!issue) return null;

  return (
    <>
      {TIME_TRACKING_ROWS.map(({ field, icon, rowLabelKey }) => {
        const label = t(`jp_time_tracking.${field}`);
        return (
          <TimeTrackingPropertyRow key={field} icon={icon} label={t(rowLabelKey)} tooltip={label}>
            <TimeEstimateInput
              testId={`work-item-${field.replace("_", "-")}`}
              value={issue[field]}
              onChange={(minutes) =>
                issueOperations.update(workspaceSlug, projectId, issueId, getTimeTrackingPayload(field, minutes))
              }
              label={label}
              placeholder={disabled ? t("common.none") : t("jp_time_tracking.add_estimate")}
              disabled={disabled}
              variant="select-ghost-md"
            />
          </TimeTrackingPropertyRow>
        );
      })}
    </>
  );
});
