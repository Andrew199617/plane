/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// plane imports
import { StateSelect as StateSelectBlock } from "@plane/blocks/property-select";
import type { StateOption } from "@plane/blocks/property-select";
import type { SelectPaginationParams, SelectTooltip, SelectTooltipOverride, SelectVariant } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { IState, TPaginatedResponse } from "@plane/types";
// components
import { getJiraParityForbiddenMessage } from "@/components/jira-parity/workflows/errors";
// hooks
import { useProjectState } from "@/hooks/store/use-project-state";
import { useIsAgent } from "@/hooks/store/jira-parity/use-is-agent";
import { useWorkflows } from "@/hooks/store/jira-parity/use-workflows";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";

type StateSelectWebProps = {
  /**
   * Jira-parity: the work item whose state this dropdown changes. Used to detect epics for the
   * workflow, and lets agents change the state along their allowed transitions even when the
   * surrounding (read-only) surface passes `disabled`.
   */
  workItemId?: string;
  /** Jira-parity: show every state (e.g. when picking the state of a new work item). */
  disableWorkflowFilter?: boolean;
  /** Project whose states are offered. */
  projectId: string | undefined;
  /** Current state id (`null` / `undefined` when none). */
  value: string | null | undefined;
  /** Emits the next state id. */
  onChange: (stateId: string) => void;
  variant: SelectVariant;
  disabled?: boolean;
  placeholder?: string;
  onClose?: () => void;
  className?: string;
  tooltip?: SelectTooltip;
  appendElement?: ReactNode;
  /** Forwarded to the block's trigger — see `StateSelectProps["testId"]` doc comment. */
  testId?: string;
  /** Tab order of the trigger, for forms that sequence focus explicitly (`ETabIndices`). */
  tabIndex?: number;
};

const toOption = (state: IState): StateOption => ({
  id: state.id,
  name: state.name,
  color: state.color,
  group: state.group,
  order: state.order,
});

/**
 * Web binding for the presentational `StateSelect` block. Resolves the project's states from the
 * project-state store (fetched on first open when the project has not been loaded yet), filters them
 * by the search query and maps the selected id to a `StateOption`.
 *
 * CE change: EE reads a paginated state "lite" resource with workflow gating (`typeId`,
 * `isForWorkItemCreation`, `scopedProjectIds`); CE has neither, so the whole project list is served
 * as one page.
 *
 * Jira-parity: `allowedStateIds` comes from the current user's allowed transitions (workflows store),
 * using `value` as the from-state.
 */
export const StateSelect = observer(function StateSelect(props: StateSelectWebProps) {
  const {
    projectId,
    value,
    onChange,
    variant,
    disabled,
    placeholder,
    onClose,
    className,
    tooltip,
    appendElement,
    testId,
    tabIndex,
    workItemId,
    disableWorkflowFilter = false,
  } = props;
  // router params
  const { workspaceSlug } = useParams();
  // store hooks
  const { getProjectStateIds, getStateById, fetchProjectStates } = useProjectState();
  // translation
  const { t } = useTranslation();
  // jira-parity: workflow gating
  const { getAllowedStateIds, getMyTransitions, ensureMyTransitions, isWorkItemEpic } = useWorkflows();
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  const isAgent = useIsAgent(projectId);
  const workItem = workItemId ? getIssueById(workItemId) : undefined;
  const allowedStateIds = disableWorkflowFilter ? null : getAllowedStateIds(projectId, value, isWorkItemEpic(workItem));
  const canAgentChangeState =
    isAgent && !!workItem && !workItem.archived_at && (allowedStateIds === null || allowedStateIds.size > 1);
  const isDisabled = !!disabled && !canAgentChangeState;
  const hasMyTransitions = !!getMyTransitions(projectId);

  // jira-parity: agents only get an enabled dropdown once their transitions are known, so load them up
  // front on surfaces outside the project pages (workspace views, boards); requests are shared per project.
  useEffect(() => {
    if (!isAgent || disableWorkflowFilter || hasMyTransitions || !workspaceSlug || !projectId) return;
    void ensureMyTransitions(workspaceSlug.toString(), projectId);
  }, [isAgent, disableWorkflowFilter, hasMyTransitions, workspaceSlug, projectId, ensureMyTransitions]);

  // jira-parity: callers whose update promise rejects (list/kanban chips, spreadsheet) get a toast; the
  // issue store has already rolled the optimistic change back.
  const handleChange = useCallback(
    (stateId: string) => {
      const result: unknown = onChange(stateId);
      if (result instanceof Promise) {
        result.catch((error: unknown) => {
          setToast({
            type: "error",
            title: t("common.error.label"),
            message:
              getJiraParityForbiddenMessage(error) ??
              t("entity.update.failed", { entity: t("issue.label", { count: 1 }) }),
          });
        });
      }
    },
    [onChange, t]
  );
  const resolvedTooltip = useMemo<SelectTooltipOverride | undefined>(() => {
    if (!tooltip) return undefined;
    const override = typeof tooltip === "object" ? tooltip : undefined;
    return {
      heading: override?.heading ?? t("common.state"),
      emptyContent: override?.emptyContent ?? t("common.none"),
    };
  }, [tooltip, t]);

  const getValues = useCallback(
    async ({ search }: SelectPaginationParams): Promise<TPaginatedResponse<StateOption[]>> => {
      if (!workspaceSlug || !projectId) return { results: [] };
      let stateIds = getProjectStateIds(projectId);
      if (!stateIds) {
        await fetchProjectStates(workspaceSlug.toString(), projectId);
        stateIds = getProjectStateIds(projectId);
      }
      // jira-parity: outside project pages the transitions may not be loaded yet
      if (!disableWorkflowFilter && !getMyTransitions(projectId)) {
        await ensureMyTransitions(workspaceSlug.toString(), projectId);
      }
      const query = search?.trim().toLowerCase();
      const results = (stateIds ?? [])
        .map((stateId) => getStateById(stateId))
        .filter((state): state is IState => !!state)
        .filter((state) => !query || state.name.toLowerCase().includes(query))
        .map(toOption);
      return { results, next_page_results: false };
    },
    [
      workspaceSlug,
      projectId,
      getProjectStateIds,
      fetchProjectStates,
      getStateById,
      disableWorkflowFilter,
      getMyTransitions,
      ensureMyTransitions,
    ]
  );

  // Resolved in the observer render (not in a memo) so MobX re-renders when the state loads.
  const selectedState = value ? getStateById(value) : undefined;
  const selected = selectedState ? toOption(selectedState) : null;

  return (
    <StateSelectBlock
      getValues={getValues}
      value={selected}
      onChange={handleChange}
      variant={variant}
      disabled={isDisabled}
      allowedStateIds={allowedStateIds}
      placeholder={placeholder ?? t("state")}
      onClose={onClose}
      className={className}
      tooltip={resolvedTooltip}
      appendElement={appendElement}
      testId={testId}
      tabIndex={tabIndex}
    />
  );
});
