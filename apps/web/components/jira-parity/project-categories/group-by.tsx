/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: group-by "state__name" columns (one column per state NAME across projects), wired into
// getGroupByColumns (issue-layouts/utils.tsx) (owned by the project-categories feature).
// Columns are scoped to the projects of the master board being viewed and ordered like Jira
// (To Do | In Progress | In Review | Done | Won't Fix).
import { EIconSize, JP_STATE_NAME_GROUP_BY } from "@plane/constants";
import { StateGroupIcon } from "@plane/blocks/icons";
import type { IGroupByColumn, TGetColumns, TIssue, TIssueGroupByOptions } from "@plane/types";
// store
import { store } from "@/lib/store-context";
import { findProjectStateByName, getStateNameColumns } from "@/store/jira-parity/category-board/helpers";

/** Category of the master board being viewed (route param, else the last board whose filters were loaded). */
const getActiveCategoryId = (): string | undefined =>
  store.router.query?.categoryId?.toString() ?? store.issue.categoryBoardIssuesFilter.categoryId;

/**
 * Hook for getProjectColumns (issue-layouts/utils.tsx): on a master board (route param `categoryId`) the "project"
 * groups / swimlanes are only the category's projects; everywhere else the ids are returned unchanged.
 */
export const scopeProjectColumnIdsToCategoryBoard = (projectIds: string[]): string[] => {
  const categoryId = store.router.query?.categoryId?.toString();
  if (!categoryId) return projectIds;
  const categoryProjectIds = new Set(store.jiraParity.projectCategories.getProjectIdsByCategoryId(categoryId));
  return projectIds.filter((projectId) => categoryProjectIds.has(projectId));
};

export const getStateNameGroupByColumns = (_params: TGetColumns): IGroupByColumn[] | undefined => {
  const workspaceStates = store.state.workspaceStates;
  if (!workspaceStates) return;

  const categoryId = getActiveCategoryId();
  const projectIds = categoryId ? store.jiraParity.projectCategories.getProjectIdsByCategoryId(categoryId) : undefined;

  return getStateNameColumns(workspaceStates, projectIds && projectIds.length > 0 ? projectIds : undefined).map(
    (column) => ({
      id: column.name,
      name: column.name,
      icon: (
        <div className="size-4 rounded-full">
          <StateGroupIcon
            stateGroup={column.state.group}
            color={column.state.color}
            size={EIconSize.LG}
            percentage={column.state.order}
          />
        </div>
      ),
      // the state id depends on the work item's project; it is resolved on drop / create
      payload: {},
    })
  );
};

/** Id of the state named `stateName` in the project (a "state__name" column resolved for one work item). */
export const getProjectStateIdByName = (projectId: string | null | undefined, stateName: string): string | undefined =>
  findProjectStateByName(Object.values(store.state.stateMap ?? {}), projectId, stateName)?.id;

/** Thrown by resolveStateNameGroupDrop; useGroupIssuesDragNDrop shows it as a translated toast. */
export class StateNameDropError extends Error {
  stateName: string;

  constructor(stateName: string) {
    super(`No state named "${stateName}" in the work item's project`);
    this.name = "StateNameDropError";
    this.stateName = stateName;
  }
}

/**
 * Called by handleGroupDragDrop (issue-layouts/utils.tsx) before the work item is updated: when the board is grouped
 * (or sub-grouped) by state NAME, the dropped column's name is resolved to the state with that name in the work
 * item's own project. Throws a StateNameDropError when that project has no such state.
 */
export const resolveStateNameGroupDrop = (
  updatedIssue: Partial<TIssue>,
  sourceIssue: TIssue,
  groupBy: TIssueGroupByOptions | undefined,
  subGroupBy: TIssueGroupByOptions | undefined,
  source: { groupId: string; subGroupId?: string },
  destination: { groupId: string; subGroupId?: string }
): Partial<TIssue> => {
  let targetStateName: string | undefined;
  if (groupBy === JP_STATE_NAME_GROUP_BY && source.groupId !== destination.groupId)
    targetStateName = destination.groupId;
  else if (
    subGroupBy === JP_STATE_NAME_GROUP_BY &&
    destination.subGroupId &&
    source.subGroupId !== destination.subGroupId
  )
    targetStateName = destination.subGroupId;

  if (!targetStateName) return updatedIssue;

  const targetStateId = getProjectStateIdByName(sourceIssue.project_id, targetStateName);
  if (!targetStateId) throw new StateNameDropError(targetStateName);
  return { ...updatedIssue, state_id: targetStateId };
};
