/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: priorities (owned by the priorities feature)
// Priorities are a plain Issue field (keys highest/high/medium/low/lowest); no dedicated endpoints yet.
import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

export class PrioritiesService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }
}
