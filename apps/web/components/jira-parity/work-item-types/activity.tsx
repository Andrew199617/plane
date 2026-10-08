/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: "changed the type" activity row (activity field "type"), rendered by
// components/issues/issue-detail/issue-activity/activity/activity-list.tsx. Owned by the work-item-types feature.
import { observer } from "mobx-react";
// plane imports
import { WorkItemsOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
// components
import {
  IssueActivityBlockComponent,
  IssueLink,
} from "@/components/issues/issue-detail/issue-activity/activity/actions";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useWorkItemTypes } from "@/hooks/store/jira-parity/use-work-item-types";
// local imports
import { WorkItemTypeIcon } from "./icons";

type TWorkItemTypeActivityProps = {
  activityId: string;
  showIssue?: boolean;
  ends: "top" | "bottom" | undefined;
};

export const WorkItemTypeActivity = observer(function WorkItemTypeActivity(props: TWorkItemTypeActivityProps) {
  const { activityId, showIssue = true, ends } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const {
    activity: { getActivityById },
  } = useIssueDetail();
  const { getWorkItemTypeById } = useWorkItemTypes();
  // derived values
  const activity = getActivityById(activityId);
  const newType = getWorkItemTypeById(activity?.new_identifier);

  if (!activity) return <></>;

  return (
    <IssueActivityBlockComponent
      icon={
        newType ? (
          <WorkItemTypeIcon workItemType={newType} className="size-3.5" />
        ) : (
          <WorkItemsOutline className="h-3.5 w-3.5 text-secondary" aria-hidden="true" />
        )
      }
      activityId={activityId}
      ends={ends}
    >
      <>
        {activity.old_value ? (
          <>
            {t("jp_work_item_types.activity.changed_from")}{" "}
            <span className="font-medium text-primary">{activity.old_value}</span>{" "}
            {t("jp_work_item_types.activity.to")}{" "}
          </>
        ) : (
          <>{t("jp_work_item_types.activity.set_to")} </>
        )}
        <span className="font-medium text-primary">{activity.new_value}</span>
        {showIssue && <> {t("jp_work_item_types.activity.for")} </>}
        {showIssue && <IssueLink activityId={activityId} />}.
      </>
    </IssueActivityBlockComponent>
  );
});
