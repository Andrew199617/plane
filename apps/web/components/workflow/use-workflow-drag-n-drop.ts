/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useState } from "react";
import { useParams } from "next/navigation";
import type { TIssueGroupByOptions } from "@plane/types";
// jira-parity
import { isWorkflowDropAllowed as isDropAllowedByWorkflow } from "@/components/jira-parity/workflows/helpers";
import { useWorkflows } from "@/hooks/store/jira-parity/use-workflows";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useProjectState } from "@/hooks/store/use-project-state";
import { useUserPermissions } from "@/hooks/store/user";

/**
 * Jira-parity: workflow-aware drag and drop for the kanban/list layouts.
 * Drops into a state the current user may not move the work item to are disabled (and agents, who may
 * only change the state, cannot change any other grouped property or reorder).
 */
export const useWorkFlowFDragNDrop = (groupBy: TIssueGroupByOptions | undefined, subGroupBy?: TIssueGroupByOptions) => {
  // router
  const { workspaceSlug } = useParams();
  // store hooks
  const { canTransition, isWorkItemEpic } = useWorkflows();
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  const { getStateById } = useProjectState();
  const { isAgentInProject } = useUserPermissions();
  // states
  const [workflowDisabledSource, setWorkflowDisabledSource] = useState<string | undefined>(undefined);
  const [isWorkflowDropDisabled, setIsWorkflowDropDisabled] = useState(false);

  const isWorkflowDropAllowed = useCallback(
    (
      issueId: string | undefined,
      sourceGroupId: string | undefined,
      destinationGroupId: string | undefined,
      sourceSubGroupId?: string,
      destinationSubGroupId?: string
    ): boolean => {
      const issue = issueId ? getIssueById(issueId) : undefined;
      const stateGroupId = groupBy === "state" ? sourceGroupId : subGroupBy === "state" ? sourceSubGroupId : undefined;
      const projectId = issue?.project_id ?? (stateGroupId ? getStateById(stateGroupId)?.project_id : undefined);
      const isStateOnlyUser = !!projectId && isAgentInProject(workspaceSlug?.toString(), projectId);
      const isEpic = isWorkItemEpic(issue);

      return isDropAllowedByWorkflow({
        groupBy,
        subGroupBy,
        sourceGroupId,
        destinationGroupId,
        sourceSubGroupId,
        destinationSubGroupId,
        isStateOnlyUser,
        canTransition: (fromStateId, toStateId) => canTransition(projectId, fromStateId, toStateId, isEpic),
      });
    },
    [groupBy, subGroupBy, workspaceSlug, getIssueById, getStateById, isAgentInProject, isWorkItemEpic, canTransition]
  );

  const handleWorkFlowState = useCallback(
    (
      sourceGroupId: string,
      destinationGroupId: string,
      sourceSubGroupId?: string,
      destinationSubGroupId?: string,
      issueId?: string
    ) => {
      const isAllowed = isWorkflowDropAllowed(
        issueId,
        sourceGroupId,
        destinationGroupId,
        sourceSubGroupId,
        destinationSubGroupId
      );
      setIsWorkflowDropDisabled(!isAllowed);
      setWorkflowDisabledSource(isAllowed ? undefined : sourceGroupId);
    },
    [isWorkflowDropAllowed]
  );

  const resetWorkflowState = useCallback(() => {
    setIsWorkflowDropDisabled(false);
    setWorkflowDisabledSource(undefined);
  }, []);

  // Creation is gated by the regular permission checks (agents cannot create work items).
  const getIsWorkflowWorkItemCreationDisabled = useCallback((_groupId: string, _subGroupId?: string) => false, []);

  return {
    workflowDisabledSource,
    isWorkflowDropDisabled,
    getIsWorkflowWorkItemCreationDisabled,
    handleWorkFlowState,
    isWorkflowDropAllowed,
    resetWorkflowState,
  };
};
