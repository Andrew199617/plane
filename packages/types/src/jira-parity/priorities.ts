/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: priorities (owned by the priorities feature)
import type { TIssuePriorities } from "../issues";

/** Jira priority keys, ordered highest -> lowest. `medium` is the default. Same union as `TIssuePriorities`. */
export type TJiraPriority = TIssuePriorities;
