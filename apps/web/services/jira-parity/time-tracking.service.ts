/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: time tracking (owned by the time-tracking feature)
// original_estimate / remaining_estimate are plain Issue fields: update them through the regular
// issue update flow (issueOperations.update / issue store updateIssue). Add dedicated calls here if needed.
import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

export class TimeTrackingService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }
}
