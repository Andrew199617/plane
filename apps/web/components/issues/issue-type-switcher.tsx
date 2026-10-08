/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// store hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// components
import { WorkItemTypeSwitcher } from "@/components/jira-parity/work-item-types/type-switcher";

export type TIssueTypeSwitcherProps = {
  issueId: string;
  disabled: boolean;
};

export const IssueTypeSwitcher = observer(function IssueTypeSwitcher(props: TIssueTypeSwitcherProps) {
  const { issueId, disabled } = props;
  // router
  const { workspaceSlug } = useParams();
  // store hooks
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  // derived values
  const issue = getIssueById(issueId);

  if (!issue || !issue.project_id) return <></>;

  // jira-parity: type icon (with a "change type" menu) + identifier
  return (
    <WorkItemTypeSwitcher
      workspaceSlug={workspaceSlug?.toString() ?? ""}
      projectId={issue.project_id}
      issueId={issueId}
      disabled={disabled}
    />
  );
});
