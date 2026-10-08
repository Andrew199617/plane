/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity teams: small pure helpers shared by the teams settings components.

/**
 * Best human-readable message of a teams API error body. The service rejects with
 * `error.response.data`, i.e. `{error}` (409 duplicate name / 400 invalid ids) or DRF serializer
 * errors (`{name: ["..."]}`, `{default_project_role: ["..."]}`).
 */
export const getTeamErrorMessage = (error: unknown, fallback: string): string => {
  if (!error || typeof error !== "object") return fallback;
  const data = error as Record<string, unknown>;
  for (const key of ["error", "name", "default_project_role", "description", "logo_props", "detail"]) {
    const value = data[key];
    if (typeof value === "string" && value) return value;
    if (Array.isArray(value) && typeof value[0] === "string") return value[0];
  }
  return fallback;
};

/** True when both id lists hold the same ids (order-insensitive). */
export const isSameIdSet = (a: string[], b: string[]): boolean => {
  if (a.length !== b.length) return false;
  const set = new Set(a);
  return b.every((id) => set.has(id));
};

/** Case-insensitive match of a team against a search query (name and description). */
export const teamMatchesQuery = (team: { name: string; description?: string | null }, query: string): boolean => {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return team.name.toLowerCase().includes(q) || (team.description ?? "").toLowerCase().includes(q);
};
