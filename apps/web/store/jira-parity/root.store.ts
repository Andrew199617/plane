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
import type { ITimeTrackingStore } from "./time-tracking.store";
import { TimeTrackingStore } from "./time-tracking.store";

export interface IJiraParityRootStore {
  timeTracking: ITimeTrackingStore;
  priorities: IPrioritiesStore;
}

export class JiraParityRootStore implements IJiraParityRootStore {
  timeTracking: ITimeTrackingStore;
  priorities: IPrioritiesStore;

  constructor(rootStore: CoreRootStore) {
    this.timeTracking = new TimeTrackingStore(rootStore);
    this.priorities = new PrioritiesStore(rootStore);
  }
}
