/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: work item header "[type icon] KEY-123" with a Jira-like "change type" menu on the icon.
// Rendered by components/issues/issue-type-switcher.tsx (detail page + peek overview).
import { observer } from "mobx-react";
// plane imports
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
// components
import { IssueIdentifier } from "@/components/issues/issue-detail/issue-identifier";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useWorkItemTypes } from "@/hooks/store/jira-parity/use-work-item-types";
// local imports
import { WorkItemTypeSelect } from "./type-select";
import { getWorkItemTypeUpdateErrorMessage, useWorkItemTypeOptionGuard } from "./use-work-item-type-guard";

type TWorkItemTypeSwitcherProps = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled: boolean;
};

export const WorkItemTypeSwitcher = observer(function WorkItemTypeSwitcher(props: TWorkItemTypeSwitcherProps) {
  const { workspaceSlug, projectId, issueId, disabled } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const {
    issue: { getIssueById },
    updateIssue,
  } = useIssueDetail();
  const { getWorkItemTypeById } = useWorkItemTypes();
  const getOptionDisabledReason = useWorkItemTypeOptionGuard(issueId);
  // derived values
  const issue = getIssueById(issueId);
  const hasKnownType = !!getWorkItemTypeById(issue?.type_id);

  const handleChange = async (workItemTypeId: string) => {
    const nextType = getWorkItemTypeById(workItemTypeId);
    try {
      await updateIssue(workspaceSlug, projectId, issueId, { type_id: workItemTypeId });
      setToast({
        type: "success",
        title: t("jp_work_item_types.toast.type_changed.title"),
        message: t("jp_work_item_types.toast.type_changed.message", { type: nextType?.name ?? "" }),
      });
    } catch (error) {
      setToast({
        type: "error",
        title: t("jp_work_item_types.toast.type_change_failed.title"),
        message: getWorkItemTypeUpdateErrorMessage(error, t("jp_work_item_types.toast.type_change_failed.message")),
      });
    }
  };

  if (!issue) return null;

  return (
    <div className="flex items-center gap-1">
      {hasKnownType && (
        <WorkItemTypeSelect
          testId="work-item-type-switcher"
          value={issue.type_id}
          onChange={handleChange}
          getOptionDisabledReason={getOptionDisabledReason}
          disabled={disabled}
          variant="icon-md"
          showLabel={false}
          tooltip
        />
      )}
      <IssueIdentifier
        issueId={issueId}
        projectId={projectId}
        size="md"
        enableClickToCopyIdentifier
        // the switcher draws the type icon itself; fall back to the identifier's icon otherwise
        displayProperties={{ key: true, issue_type: !hasKnownType }}
      />
    </div>
  );
});
