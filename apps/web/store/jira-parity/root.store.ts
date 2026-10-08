/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity root store (scaffold-owned). Mounted as `rootStore.jiraParity` in CoreRootStore.
// Each feature owns its own `<feature>.store.ts`; add new slots here only through the integrator.
import type { CoreRootStore } from "@/store/root.store";
import type { IPrioritiesStore } from "./priorities.store";
import { PrioritiesStore } from "./priorities.store";
import type { IProjectCategoriesStore } from "./project-categories.store";
import { ProjectCategoriesStore } from "./project-categories.store";
import type { ITeamsStore } from "./teams.store";
import { TeamsStore } from "./teams.store";
import type { ITimeTrackingStore } from "./time-tracking.store";
import { TimeTrackingStore } from "./time-tracking.store";
import type { IWorkItemTypesStore } from "./work-item-types.store";
import { WorkItemTypesStore } from "./work-item-types.store";

export interface IJiraParityRootStore {
  workItemTypes: IWorkItemTypesStore;
  teams: ITeamsStore;
  projectCategories: IProjectCategoriesStore;
  timeTracking: ITimeTrackingStore;
  priorities: IPrioritiesStore;
}

export class JiraParityRootStore implements IJiraParityRootStore {
  workItemTypes: IWorkItemTypesStore;
  teams: ITeamsStore;
  projectCategories: IProjectCategoriesStore;
  timeTracking: ITimeTrackingStore;
  priorities: IPrioritiesStore;

  constructor(rootStore: CoreRootStore) {
    this.workItemTypes = new WorkItemTypesStore(rootStore);
    this.teams = new TeamsStore(rootStore);
    this.projectCategories = new ProjectCategoriesStore(rootStore);
    this.timeTracking = new TimeTrackingStore(rootStore);
    this.priorities = new PrioritiesStore(rootStore);
  }
}
