/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: unit tests for the pure agents-page helpers.
// apps/web has no test runner, so this file is self-contained (no node/vitest imports, so it also
// type-checks under the web tsconfig). Run it with:
//   pnpm --filter @plane/i18n exec tsx --test <abs path to this file>
import type { TWorkspaceAgent, TWorkspaceAgentToken } from "@plane/types";
import {
  buildAgentCreatePayload,
  getActiveAgentTokens,
  getAgentApiErrorMessage,
  getAgentEmailDomain,
  getAgentInitial,
  isAgentTokenUsable,
  sortAgentTokens,
} from "./helpers";

type TCase = { name: string; run: () => void };
const cases: TCase[] = [];
const test = (name: string, run: () => void) => cases.push({ name, run });

const assertEqual = <T>(actual: T, expected: T, message = "") => {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) throw new Error(`${message} expected ${e} but got ${a}`);
};

// fixtures
const NOW = new Date("2026-10-07T12:00:00Z");
const makeToken = (id: string, overrides: Partial<TWorkspaceAgentToken> = {}): TWorkspaceAgentToken => ({
  id,
  label: `token ${id}`,
  last_used: null,
  expired_at: null,
  is_active: true,
  created_at: "2026-10-01T00:00:00Z",
  ...overrides,
});
const makeAgent = (tokens: TWorkspaceAgentToken[], memberOverrides: Partial<TWorkspaceAgent["member"]> = {}) =>
  ({
    id: "wm-1",
    role: 10,
    project_count: 3,
    tokens,
    member: {
      id: "user-1",
      display_name: "claude-dev",
      first_name: "",
      last_name: "",
      email: "claude-dev@agents.example.local",
      avatar_url: null,
      ...memberOverrides,
    },
  }) satisfies TWorkspaceAgent;

// --- error messages -------------------------------------------------------------------------
test("error messages prefer {error}, then {detail}, then DRF field errors", () => {
  assertEqual(getAgentApiErrorMessage({ error: "Only admins", code: "X" }, "fallback"), "Only admins");
  assertEqual(getAgentApiErrorMessage({ detail: "Not found." }, "fallback"), "Not found.");
  assertEqual(getAgentApiErrorMessage({ email: ["Email already in use"] }, "fallback"), "Email already in use");
  assertEqual(getAgentApiErrorMessage({ error: ["first", "second"] }, "fallback"), "first");
});

test("error messages fall back for empty or unknown bodies", () => {
  assertEqual(getAgentApiErrorMessage(undefined, "fallback"), "fallback");
  assertEqual(getAgentApiErrorMessage({}, "fallback"), "fallback");
  assertEqual(getAgentApiErrorMessage({ error: "  " }, "fallback"), "fallback");
  assertEqual(getAgentApiErrorMessage("plain text", "fallback"), "plain text");
});

// --- tokens ---------------------------------------------------------------------------------
test("a token is usable while active and not expired", () => {
  assertEqual(isAgentTokenUsable(makeToken("a"), NOW), true);
  assertEqual(isAgentTokenUsable(makeToken("b", { is_active: false }), NOW), false);
  assertEqual(isAgentTokenUsable(makeToken("c", { expired_at: "2026-10-06T00:00:00Z" }), NOW), false);
  assertEqual(isAgentTokenUsable(makeToken("d", { expired_at: "2026-12-01T00:00:00Z" }), NOW), true);
});

test("tokens sort usable first, then newest first", () => {
  const tokens = [
    makeToken("old", { created_at: "2026-09-01T00:00:00Z" }),
    makeToken("revoked", { is_active: false, created_at: "2026-10-05T00:00:00Z" }),
    makeToken("new", { created_at: "2026-10-03T00:00:00Z" }),
  ];
  assertEqual(
    sortAgentTokens(tokens, NOW).map((token) => token.id),
    ["new", "old", "revoked"]
  );
  // the input is not mutated
  assertEqual(
    tokens.map((token) => token.id),
    ["old", "revoked", "new"]
  );
});

test("active tokens exclude revoked and expired ones", () => {
  const agent = makeAgent([
    makeToken("a"),
    makeToken("b", { is_active: false }),
    makeToken("c", { expired_at: "2026-01-01T00:00:00Z" }),
  ]);
  assertEqual(
    getActiveAgentTokens(agent, NOW).map((token) => token.id),
    ["a"]
  );
  assertEqual(getActiveAgentTokens({ tokens: undefined as unknown as TWorkspaceAgentToken[] }, NOW).length, 0);
});

// --- display --------------------------------------------------------------------------------
test("agent initial uses the display name, then first name, then email", () => {
  assertEqual(getAgentInitial(makeAgent([])), "C");
  assertEqual(getAgentInitial(makeAgent([], { display_name: "", first_name: "zed" })), "Z");
  assertEqual(getAgentInitial(makeAgent([], { display_name: "", email: "bot@x.local" })), "B");
});

// --- create payload -------------------------------------------------------------------------
test("create payload trims and omits empty optional fields", () => {
  assertEqual(buildAgentCreatePayload({ displayName: "  Claude Dev ", generateToken: true, tokenLabel: "" }), {
    display_name: "Claude Dev",
    generate_token: true,
  });
  assertEqual(buildAgentCreatePayload({ displayName: "Claude Dev", generateToken: true, tokenLabel: " CI " }), {
    display_name: "Claude Dev",
    generate_token: true,
    token_label: "CI",
  });
});

test("create payload never carries an email (the API generates a placeholder)", () => {
  const form = { displayName: "A", generateToken: true, tokenLabel: "", email: "someone@example.com" };
  assertEqual("email" in buildAgentCreatePayload(form), false);
});

test("create payload drops the token label when no token is generated", () => {
  assertEqual(buildAgentCreatePayload({ displayName: "A", generateToken: false, tokenLabel: "CI" }), {
    display_name: "A",
    generate_token: false,
  });
});

test("agent email domain mirrors the API placeholder domain", () => {
  assertEqual(getAgentEmailDomain("My-Workspace"), "agents.my-workspace.local");
});

// --- runner ---------------------------------------------------------------------------------
let failed = 0;
for (const testCase of cases) {
  try {
    testCase.run();
    console.log(`ok - ${testCase.name}`);
  } catch (error) {
    failed += 1;
    console.error(`not ok - ${testCase.name}\n  ${(error as Error).message}`);
  }
}
console.log(`${cases.length - failed}/${cases.length} agents helper tests passed`);
if (failed > 0) throw new Error(`${failed} agents helper test(s) failed`);
