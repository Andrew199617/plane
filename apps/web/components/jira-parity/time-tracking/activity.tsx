/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: "set the original / remaining estimate to 1d 4h" activity rows (activity fields
// "original_estimate" / "remaining_estimate", values in minutes), rendered by
// components/issues/issue-detail/issue-activity/activity/activity-list.tsx. Owned by the time-tracking feature.
import { observer } from "mobx-react";
// plane imports
import { HourglassOutline, TimeTrackingOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
// components
import {
  IssueActivityBlockComponent,
  IssueLink,
} from "@/components/issues/issue-detail/issue-activity/activity/actions";
// hooks
import { useTimeTracking } from "@/hooks/store/jira-parity/use-time-tracking";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// local imports
import { formatDuration } from "./duration";
import { isTimeTrackingField, parseActivityMinutes } from "./utils";

type TTimeTrackingActivityProps = {
  activityId: string;
  showIssue?: boolean;
  ends: "top" | "bottom" | undefined;
};

export const TimeTrackingActivity = observer(function TimeTrackingActivity(props: TTimeTrackingActivityProps) {
  const { activityId, showIssue = true, ends } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const {
    activity: { getActivityById },
  } = useIssueDetail();
  const { config } = useTimeTracking();
  // derived values
  const activity = getActivityById(activityId);

  if (!activity || !isTimeTrackingField(activity.field)) return <></>;

  const field = activity.field;
  const newMinutes = parseActivityMinutes(activity.new_value);
  const Icon = field === "original_estimate" ? TimeTrackingOutline : HourglassOutline;

  return (
    <IssueActivityBlockComponent
      icon={<Icon className="h-3.5 w-3.5 text-secondary" aria-hidden="true" />}
      activityId={activityId}
      ends={ends}
    >
      <>
        {newMinutes === null
          ? t(`jp_time_tracking.activity.${field}_removed`)
          : t(`jp_time_tracking.activity.${field}_set`, { value: formatDuration(newMinutes, config) })}
        {showIssue && <> </>}
        {showIssue && <IssueLink activityId={activityId} />}.
      </>
    </IssueActivityBlockComponent>
  );
});
