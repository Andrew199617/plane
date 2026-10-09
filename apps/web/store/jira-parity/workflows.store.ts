/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: workflows store (owned by the workflows feature)
import { set } from "lodash-es";
import { action, makeObservable, observable, runInAction } from "mobx";
import { computedFn } from "mobx-utils";
// plane imports
import type { TIssue, TMyStateTransitions, TStateTransitionRule } from "@plane/types";
// services
import { WorkflowsService } from "@/services/jira-parity/workflows.service";
// store
import type { CoreRootStore } from "@/store/root.store";
// local imports
import { getAllowedTargetStateIds, hasTransitionsForState } from "@/components/jira-parity/workflows/helpers";

export interface IWorkflowsStore {
  // observables (keyed by project id)
  transitionRulesMap: Record<string, TStateTransitionRule[]>;
  myTransitionsMap: Record<string, TMyStateTransitions>;
  // computed actions
  getTransitionRules: (projectId: string | null | undefined) => TStateTransitionRule[] | undefined;
  getMyTransitions: (projectId: string | null | undefined) => TMyStateTransitions | undefined;
  /** Whether a work item is an epic, derived from its work item type (never from an `is_epic` payload flag). */
  isWorkItemEpic: (workItem: Pick<TIssue, "type_id"> | null | undefined) => boolean;
  /**
   * States the current user may move a work item to from `fromStateId` (always includes `fromStateId`).
   * `null` means unrestricted (no filtering).
   */
  getAllowedStateIds: (
    projectId: string | null | undefined,
    fromStateId: string | null | undefined,
    isEpic?: boolean
  ) => Set<string> | null;
  /** Whether the current user may move a work item from `fromStateId` to `toStateId`. */
  canTransition: (
    projectId: string | null | undefined,
    fromStateId: string | null | undefined,
    toStateId: string | null | undefined,
    isEpic?: boolean
  ) => boolean;
  // fetch actions
  fetchTransitionRules: (workspaceSlug: string, projectId: string) => Promise<TStateTransitionRule[]>;
  fetchMyTransitions: (workspaceSlug: string, projectId: string) => Promise<TMyStateTransitions>;
  /**
   * Loads the current user's transitions once per project (concurrent callers share one request). Refetches once
   * when `fromStateId` is missing from the loaded map (a state created after the load).
   */
  ensureMyTransitions: (
    workspaceSlug: string,
    projectId: string,
    fromStateId?: string | null
  ) => Promise<TMyStateTransitions | undefined>;
  // actions
  replaceTransitionRules: (
    workspaceSlug: string,
    projectId: string,
    rules: TStateTransitionRule[]
  ) => Promise<TStateTransitionRule[]>;
  setWorkflowEnabled: (workspaceSlug: string, projectId: string, isEnabled: boolean) => Promise<void>;
}

export class WorkflowsStore implements IWorkflowsStore {
  // observables
  transitionRulesMap: Record<string, TStateTransitionRule[]> = {};
  myTransitionsMap: Record<string, TMyStateTransitions> = {};
  // root store
  rootStore: CoreRootStore;
  // services
  service: WorkflowsService;

  constructor(rootStore: CoreRootStore) {
    makeObservable(this, {
      transitionRulesMap: observable,
      myTransitionsMap: observable,
      fetchTransitionRules: action,
      fetchMyTransitions: action,
      replaceTransitionRules: action,
      setWorkflowEnabled: action,
    });
    this.rootStore = rootStore;
    this.service = new WorkflowsService();
  }

  getTransitionRules = computedFn((projectId: string | null | undefined) =>
    projectId ? this.transitionRulesMap[projectId] : undefined
  );

  getMyTransitions = computedFn((projectId: string | null | undefined) =>
    projectId ? this.myTransitionsMap[projectId] : undefined
  );

  isWorkItemEpic = (workItem: Pick<TIssue, "type_id"> | null | undefined): boolean => {
    if (!workItem?.type_id) return false;
    return !!this.rootStore.jiraParity?.workItemTypes?.getWorkItemTypeById(workItem.type_id)?.is_epic;
  };

  /**
   * While the current user's transitions are not loaded yet, agents are treated as fully restricted
   * (they can only keep the current state); everyone else is unrestricted until the server says otherwise.
   */
  private isAgentWithoutTransitions = (projectId: string): boolean => {
    const workspaceSlug = this.rootStore.router.workspaceSlug;
    return !!this.rootStore.user?.permission?.isAgentInProject(workspaceSlug, projectId);
  };

  getAllowedStateIds = computedFn(
    (projectId: string | null | undefined, fromStateId: string | null | undefined, isEpic: boolean = false) => {
      if (!projectId || !fromStateId) return null;
      const myTransitions = this.myTransitionsMap[projectId];
      if (!myTransitions) return this.isAgentWithoutTransitions(projectId) ? new Set<string>([fromStateId]) : null;
      return getAllowedTargetStateIds(myTransitions, fromStateId, isEpic);
    }
  );

  canTransition = (
    projectId: string | null | undefined,
    fromStateId: string | null | undefined,
    toStateId: string | null | undefined,
    isEpic: boolean = false
  ): boolean => {
    if (!toStateId || fromStateId === toStateId) return true;
    const allowedStateIds = this.getAllowedStateIds(projectId, fromStateId, isEpic);
    return allowedStateIds === null || allowedStateIds.has(toStateId);
  };

  fetchTransitionRules = async (workspaceSlug: string, projectId: string) => {
    const rules = await this.service.listTransitions(workspaceSlug, projectId);
    runInAction(() => {
      this.transitionRulesMap[projectId] = rules ?? [];
    });
    return rules;
  };

  fetchMyTransitions = async (workspaceSlug: string, projectId: string) => {
    const myTransitions = await this.service.getMyTransitions(workspaceSlug, projectId);
    runInAction(() => {
      this.myTransitionsMap[projectId] = myTransitions;
    });
    return myTransitions;
  };

  private myTransitionsRequests = new Map<string, Promise<TMyStateTransitions | undefined>>();
  /** `projectId:stateId` pairs already refetched for an unknown from-state (at most one refetch each). */
  private unknownFromStateRefetches = new Set<string>();

  ensureMyTransitions = (
    workspaceSlug: string,
    projectId: string,
    fromStateId?: string | null
  ): Promise<TMyStateTransitions | undefined> => {
    const loaded = this.myTransitionsMap[projectId];
    if (loaded) {
      const refetchKey = `${projectId}:${fromStateId}`;
      if (!fromStateId || hasTransitionsForState(loaded, fromStateId) || this.unknownFromStateRefetches.has(refetchKey))
        return Promise.resolve(loaded);
      this.unknownFromStateRefetches.add(refetchKey);
    }
    const pending = this.myTransitionsRequests.get(projectId);
    if (pending) return pending;
    const request = this.fetchMyTransitions(workspaceSlug, projectId)
      .catch(() => undefined)
      .finally(() => this.myTransitionsRequests.delete(projectId));
    this.myTransitionsRequests.set(projectId, request);
    return request;
  };

  replaceTransitionRules = async (workspaceSlug: string, projectId: string, rules: TStateTransitionRule[]) => {
    const response = await this.service.replaceTransitions(workspaceSlug, projectId, rules);
    // the PUT returns the stored rules; fall back to a refetch when the body is not a list
    const storedRules = Array.isArray(response)
      ? response
      : await this.service.listTransitions(workspaceSlug, projectId);
    runInAction(() => {
      this.transitionRulesMap[projectId] = storedRules ?? [];
    });
    // the current user's own allowed transitions may have changed too
    void this.fetchMyTransitions(workspaceSlug, projectId).catch(() => undefined);
    return storedRules;
  };

  setWorkflowEnabled = async (workspaceSlug: string, projectId: string, isEnabled: boolean) => {
    const projectMap = this.rootStore.projectRoot.project.projectMap;
    const previousValue = projectMap?.[projectId]?.is_workflow_enabled;
    runInAction(() => {
      if (projectMap?.[projectId]) set(projectMap, [projectId, "is_workflow_enabled"], isEnabled);
    });
    try {
      await this.service.setWorkflowEnabled(workspaceSlug, projectId, isEnabled);
    } catch (error) {
      runInAction(() => {
        if (projectMap?.[projectId]) set(projectMap, [projectId, "is_workflow_enabled"], previousValue);
      });
      throw error;
    }
    void this.fetchMyTransitions(workspaceSlug, projectId).catch(() => undefined);
  };
}
