/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: agents (owned by the agents feature)

/** Numeric role of an agent account (workspace + project). */
export const JP_AGENT_ROLE = 10;

/** SWR key for the workspace agents list. */
export const JP_AGENTS_SWR_KEY = (workspaceSlug: string) => `JP_AGENTS_${workspaceSlug}`;
