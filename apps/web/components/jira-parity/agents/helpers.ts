/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: pure helpers for the agents settings page (owned by the agents feature).
// Type-only imports keep this module runnable by `tsx --test` (see helpers.test.ts).
import type { TWorkspaceAgent, TWorkspaceAgentToken } from "@plane/types";

const firstString = (value: unknown): string | undefined => {
  if (typeof value === "string" && value.trim()) return value;
  if (Array.isArray(value)) return value.map(firstString).find((item) => item !== undefined);
  return undefined;
};

/**
 * Best human-readable message of an API error body: `{error}`, `{detail}`, `{message}` or the first
 * DRF field error (`{"display_name": ["..."]}`); `fallback` otherwise.
 */
export const getAgentApiErrorMessage = (error: unknown, fallback: string): string => {
  if (typeof error === "string" && error.trim()) return error;
  if (!error || typeof error !== "object") return fallback;
  const record = error as Record<string, unknown>;
  for (const key of ["error", "detail", "message"]) {
    const message = firstString(record[key]);
    if (message) return message;
  }
  for (const value of Object.values(record)) {
    const message = firstString(value);
    if (message) return message;
  }
  return fallback;
};

/** Whether the token is active and not past its expiry date. */
export const isAgentTokenUsable = (token: Pick<TWorkspaceAgentToken, "is_active" | "expired_at">, now = new Date()) =>
  token.is_active && (!token.expired_at || new Date(token.expired_at).getTime() > now.getTime());

/** Usable tokens first, then newest first. */
export const sortAgentTokens = (tokens: TWorkspaceAgentToken[], now: Date = new Date()): TWorkspaceAgentToken[] =>
  // oxlint-disable-next-line unicorn/no-array-sort -- sorts a copy; web targets ES2022 (no toSorted)
  [...tokens].sort((a, b) => {
    const usableDelta = Number(isAgentTokenUsable(b, now)) - Number(isAgentTokenUsable(a, now));
    if (usableDelta !== 0) return usableDelta;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

/** Tokens that can still be used (active and not expired), newest first. */
export const getActiveAgentTokens = (agent: Pick<TWorkspaceAgent, "tokens">, now: Date = new Date()) =>
  sortAgentTokens(agent.tokens ?? [], now).filter((token) => isAgentTokenUsable(token, now));

/** Single uppercase letter for the avatar fallback. */
export const getAgentInitial = (agent: Pick<TWorkspaceAgent, "member">): string =>
  (agent.member.display_name || agent.member.first_name || agent.member.email || "?").trim().charAt(0).toUpperCase() ||
  "?";

/** Builds the POST body of the create form (empty optional fields are omitted). */
export const buildAgentCreatePayload = (form: {
  displayName: string;
  email: string;
  generateToken: boolean;
  tokenLabel: string;
}) => {
  const payload: {
    display_name: string;
    generate_token: boolean;
    email?: string;
    token_label?: string;
  } = {
    display_name: form.displayName.trim(),
    generate_token: form.generateToken,
  };
  const email = form.email.trim();
  if (email) payload.email = email;
  const tokenLabel = form.tokenLabel.trim();
  if (form.generateToken && tokenLabel) payload.token_label = tokenLabel;
  return payload;
};
