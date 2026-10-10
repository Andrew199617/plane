/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: time tracking store (owned by the time-tracking feature)
import { makeObservable, observable } from "mobx";
// plane imports
import { JP_TIME_TRACKING_DAYS_PER_WEEK, JP_TIME_TRACKING_HOURS_PER_DAY } from "@plane/constants";
import type { TTimeTrackingConfig } from "@plane/types";
// store
import type { CoreRootStore } from "@/store/root.store";

export interface ITimeTrackingStore {
  // observables
  config: TTimeTrackingConfig;
}

export class TimeTrackingStore implements ITimeTrackingStore {
  // observables
  config: TTimeTrackingConfig = {
    hoursPerDay: JP_TIME_TRACKING_HOURS_PER_DAY,
    daysPerWeek: JP_TIME_TRACKING_DAYS_PER_WEEK,
  };
  // root store
  rootStore: CoreRootStore;

  constructor(rootStore: CoreRootStore) {
    makeObservable(this, {
      config: observable,
    });
    this.rootStore = rootStore;
  }
}
