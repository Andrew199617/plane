/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: work item type icon rendered before the work item key by IssueIdentifier
// (components/issues/issue-detail/issue-identifier.tsx), so it shows up in list, kanban, spreadsheet,
// calendar, gantt, peek, relations, sub-work items, parent pickers, search and recents.
import { observer } from "mobx-react";
// plane imports
import { Tooltip } from "@makeplane/propel/components/tooltip";
import type { TIssueIdentifierSize } from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useWorkItemTypes } from "@/hooks/store/jira-parity/use-work-item-types";
// local imports
import { WorkItemTypeIcon } from "./icons";

const ICON_SIZE_CLASS: Record<TIssueIdentifierSize, string> = {
  xs: "size-3.5",
  sm: "size-3.5",
  md: "size-4",
  lg: "size-4",
};

/** Horizontal space (px) the icon + gap adds before an identifier of size `xs` (list key column width). */
export const JP_WORK_ITEM_TYPE_IDENTIFIER_ICON_WIDTH = 20;

type TWorkItemTypeIdentifierIconProps = {
  workItemTypeId: string;
  size?: TIssueIdentifierSize;
  className?: string;
};

export const WorkItemTypeIdentifierIcon = observer(function WorkItemTypeIdentifierIcon(
  props: TWorkItemTypeIdentifierIconProps
) {
  const { workItemTypeId, size = "lg", className } = props;
  // store hooks
  const { getWorkItemTypeById } = useWorkItemTypes();
  // derived values
  const workItemType = getWorkItemTypeById(workItemTypeId);

  // types are loaded once per workspace; render nothing until then (or for an unknown type)
  if (!workItemType) return null;

  return (
    <Tooltip label={workItemType.name}>
      <span className={cn("inline-flex shrink-0 items-center", className)} data-testid="work-item-type-icon">
        <WorkItemTypeIcon workItemType={workItemType} className={ICON_SIZE_CLASS[size]} withTitle />
      </span>
    </Tooltip>
  );
});
