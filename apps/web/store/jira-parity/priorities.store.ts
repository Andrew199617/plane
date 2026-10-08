/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: priorities store (owned by the priorities feature)
// plane imports
import { JP_PRIORITY_KEYS } from "@plane/constants";
import type { TJiraPriority } from "@plane/types";
// store
import type { CoreRootStore } from "@/store/root.store";

export interface IPrioritiesStore {
  /** Priority keys ordered highest -> lowest. */
  priorityKeys: TJiraPriority[];
}

export class PrioritiesStore implements IPrioritiesStore {
  priorityKeys: TJiraPriority[] = JP_PRIORITY_KEYS;
  // root store
  rootStore: CoreRootStore;

  constructor(rootStore: CoreRootStore) {
    this.rootStore = rootStore;
  }
}
