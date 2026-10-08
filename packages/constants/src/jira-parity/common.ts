/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity shared constants (scaffold-owned)

/**
 * Central toggle that hides the CE upsell UI (edition badge, "Pro" upgrade badges,
 * bulk-operations upgrade banner, billing settings nav).
 */
export const JP_HIDE_UPSELL = true;

/** Numeric roles used across workspace/project members and invites. */
export const JP_ROLES = {
  ADMIN: 20,
  MEMBER: 15,
  AGENT: 10,
  GUEST: 5,
} as const;
