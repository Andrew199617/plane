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

export interface IJiraParityRootStore {
  priorities: IPrioritiesStore;
}

export class JiraParityRootStore implements IJiraParityRootStore {
  priorities: IPrioritiesStore;

  constructor(rootStore: CoreRootStore) {
    this.priorities = new PrioritiesStore(rootStore);
  }
}
