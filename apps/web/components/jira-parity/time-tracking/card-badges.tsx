/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: read-only "Original estimate" / "Remaining estimate" badges on list and kanban cards,
// driven by the display properties of the same name (mounted in issue-layouts/properties/all-properties.tsx).
import { observer } from "mobx-react";
// plane imports
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { EstimateOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { IIssueDisplayProperties, TIssue } from "@plane/types";
// components
import { WithDisplayPropertiesHOC } from "@/components/issues/issue-layouts/properties/with-display-properties-HOC";
// hooks
import { useTimeTracking } from "@/hooks/store/jira-parity/use-time-tracking";
// local imports
import { formatDuration } from "./duration";
import { TIME_TRACKING_FIELDS } from "./utils";

type TTimeTrackingCardBadgesProps = {
  issue: Pick<TIssue, "original_estimate" | "remaining_estimate">;
  displayProperties: IIssueDisplayProperties;
  isMobile?: boolean;
};

export const TimeTrackingCardBadges = observer(function TimeTrackingCardBadges(props: TTimeTrackingCardBadgesProps) {
  const { issue, displayProperties, isMobile = false } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { config } = useTimeTracking();

  return (
    <>
      {TIME_TRACKING_FIELDS.map((field) => {
        const value = formatDuration(issue[field], config);
        return (
          <WithDisplayPropertiesHOC
            key={field}
            displayProperties={displayProperties}
            displayPropertyKey={field}
            shouldRenderProperty={(properties) => !!properties[field] && value !== ""}
          >
            <Tooltip label={`${t(`jp_time_tracking.${field}`)}: ${value}`} disabled={isMobile}>
              <div
                className="flex h-5 flex-shrink-0 items-center justify-center gap-1.5 overflow-hidden rounded-sm border-[0.5px] border-strong px-2.5 py-1"
                data-testid={`card-${field.replace("_", "-")}`}
              >
                <EstimateOutline className="h-3 w-3 flex-shrink-0" />
                <div className="text-caption-sm-regular">{value}</div>
              </div>
            </Tooltip>
          </WithDisplayPropertiesHOC>
        );
      })}
    </>
  );
});
