/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: work item types store (owned by the work-item-types feature).
// Types are workspace-level and enabled in every project, so one list serves every project.
import { action, computed, makeObservable, observable, runInAction } from "mobx";
import { computedFn } from "mobx-utils";
// plane imports
import type { TWorkItemType, TWorkItemTypePayload } from "@plane/types";
// components
import { sortWorkItemTypes } from "@/components/jira-parity/work-item-types/rules";
// services
import { WorkItemTypesService } from "@/services/jira-parity/work-item-types.service";
// store
import type { CoreRootStore } from "@/store/root.store";

export interface IWorkItemTypesStore {
  // observables
  workItemTypeMap: Record<string, TWorkItemType>;
  fetchedWorkspaceSlug: string | null;
  // computed
  /** Every type of the loaded workspace, sorted (default first, standard, Epic, Sub-task). */
  workItemTypes: TWorkItemType[];
  /** Active types only (the ones that can be picked for a work item). */
  activeWorkItemTypes: TWorkItemType[];
  /** The workspace default type (Task). */
  defaultWorkItemType: TWorkItemType | undefined;
  // computed actions
  getWorkItemTypeById: (workItemTypeId: string | null | undefined) => TWorkItemType | undefined;
  /** Whether the type is an Epic. Use this instead of `issue.is_epic` (never sent by CE web). */
  isEpicWorkItemType: (workItemTypeId: string | null | undefined) => boolean;
  /** Whether the type is a Sub-task (requires a parent, cannot have children). */
  isSubTaskWorkItemType: (workItemTypeId: string | null | undefined) => boolean;
  /** Types enabled in a project (all active workspace types: types are managed at workspace level). */
  getProjectWorkItemTypes: (projectId: string | null | undefined) => TWorkItemType[];
  // actions
  fetchWorkItemTypes: (workspaceSlug: string) => Promise<TWorkItemType[]>;
  updateWorkItemType: (
    workspaceSlug: string,
    workItemTypeId: string,
    data: TWorkItemTypePayload
  ) => Promise<TWorkItemType>;
}

export class WorkItemTypesStore implements IWorkItemTypesStore {
  // observables
  workItemTypeMap: Record<string, TWorkItemType> = {};
  fetchedWorkspaceSlug: string | null = null;
  // root store
  rootStore: CoreRootStore;
  // services
  service: WorkItemTypesService;
  private latestFetchId = 0;

  constructor(rootStore: CoreRootStore) {
    makeObservable(this, {
      workItemTypeMap: observable,
      fetchedWorkspaceSlug: observable.ref,
      workItemTypes: computed,
      activeWorkItemTypes: computed,
      defaultWorkItemType: computed,
      fetchWorkItemTypes: action,
      updateWorkItemType: action,
    });
    this.rootStore = rootStore;
    this.service = new WorkItemTypesService();
  }

  get workItemTypes() {
    if (this.rootStore.router.workspaceSlug && this.fetchedWorkspaceSlug !== this.rootStore.router.workspaceSlug)
      return [];
    return sortWorkItemTypes(Object.values(this.workItemTypeMap));
  }

  get activeWorkItemTypes() {
    return this.workItemTypes.filter((workItemType) => workItemType.is_active);
  }

  get defaultWorkItemType() {
    return (
      this.activeWorkItemTypes.find((workItemType) => workItemType.is_default) ??
      this.activeWorkItemTypes.find((workItemType) => !workItemType.is_epic && !workItemType.is_sub_task)
    );
  }

  getWorkItemTypeById = computedFn((workItemTypeId: string | null | undefined) => {
    if (this.rootStore.router.workspaceSlug && this.fetchedWorkspaceSlug !== this.rootStore.router.workspaceSlug)
      return undefined;
    return workItemTypeId ? this.workItemTypeMap[workItemTypeId] : undefined;
  });

  isEpicWorkItemType = computedFn((workItemTypeId: string | null | undefined) =>
    Boolean(this.getWorkItemTypeById(workItemTypeId)?.is_epic)
  );

  isSubTaskWorkItemType = computedFn((workItemTypeId: string | null | undefined) =>
    Boolean(this.getWorkItemTypeById(workItemTypeId)?.is_sub_task)
  );

  getProjectWorkItemTypes = computedFn((_projectId: string | null | undefined) => this.activeWorkItemTypes);

  fetchWorkItemTypes = async (workspaceSlug: string) => {
    // Background revalidation for a route we have left must not clear the active workspace.
    if (this.rootStore.router.workspaceSlug && this.rootStore.router.workspaceSlug !== workspaceSlug)
      return this.service.list(workspaceSlug);
    const fetchId = ++this.latestFetchId;
    // never serve another workspace's types while this workspace loads
    if (this.fetchedWorkspaceSlug !== workspaceSlug)
      runInAction(() => {
        this.workItemTypeMap = {};
        this.fetchedWorkspaceSlug = null;
      });
    const workItemTypes = await this.service.list(workspaceSlug);
    // a late response for a workspace the user has left must not replace the current one
    const routedWorkspaceSlug = this.rootStore.router.workspaceSlug;
    if (fetchId !== this.latestFetchId || (routedWorkspaceSlug && routedWorkspaceSlug !== workspaceSlug))
      return workItemTypes;
    runInAction(() => {
      this.workItemTypeMap = Object.fromEntries(workItemTypes.map((workItemType) => [workItemType.id, workItemType]));
      this.fetchedWorkspaceSlug = workspaceSlug;
    });
    return workItemTypes;
  };

  updateWorkItemType = async (workspaceSlug: string, workItemTypeId: string, data: TWorkItemTypePayload) => {
    const workItemType = await this.service.update(workspaceSlug, workItemTypeId, data);
    if (this.fetchedWorkspaceSlug !== workspaceSlug || this.rootStore.router.workspaceSlug !== workspaceSlug)
      return workItemType;
    runInAction(() => {
      this.workItemTypeMap[workItemType.id] = workItemType;
      // keep a single default across the map when the server moved it
      if (workItemType.is_default) {
        for (const other of Object.values(this.workItemTypeMap)) {
          if (other.id !== workItemType.id && other.is_default)
            this.workItemTypeMap[other.id] = { ...other, is_default: false };
        }
      }
    });
    return workItemType;
  };
}
