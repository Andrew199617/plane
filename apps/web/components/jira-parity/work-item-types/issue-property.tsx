/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: "Type" row in the issue detail sidebar + peek overview (owned by the work-item-types feature).
// Rendered through <JiraParityIssueProperties/>.
import { observer } from "mobx-react";
// plane imports
import { WorkItemsOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
// components
import { SidebarPropertyListItem } from "@/components/common/layout/sidebar/property-list-item";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// local imports
import type { TJiraParityIssuePropertyProps } from "../types";
import { WorkItemTypeSelect } from "./type-select";
import { useWorkItemTypeOptionGuard } from "./use-work-item-type-guard";

export const WorkItemTypeIssueProperty = observer(function WorkItemTypeIssueProperty(
  props: TJiraParityIssuePropertyProps
) {
  const { workspaceSlug, projectId, issueId, disabled, issueOperations } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  const getOptionDisabledReason = useWorkItemTypeOptionGuard(issueId);
  // derived values
  const issue = getIssueById(issueId);

  if (!issue) return null;

  return (
    <SidebarPropertyListItem icon={WorkItemsOutline} label={t("jp_work_item_types.property_label")}>
      <WorkItemTypeSelect
        testId="work-item-type-select"
        value={issue.type_id}
        onChange={(workItemTypeId) =>
          issueOperations.update(workspaceSlug, projectId, issueId, { type_id: workItemTypeId })
        }
        getOptionDisabledReason={getOptionDisabledReason}
        disabled={disabled}
        variant="select-ghost-md"
        tooltip
      />
    </SidebarPropertyListItem>
  );
});
