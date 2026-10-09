/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: unit tests for the pure workflow helpers.
// apps/web has no test runner, so this file is self-contained (no node/vitest imports, so it also
// type-checks under the web tsconfig). Run it with:
//   pnpm --filter @plane/i18n exec tsx --test <abs path to this file>
// The fixtures sort fresh arrays for order-insensitive comparisons; web targets ES2022 (no toSorted).
/* oxlint-disable unicorn/no-array-sort */
import type { TMyStateTransitions, TStateTransitionRule } from "@plane/types";
import {
  ANY_STATE_KEY,
  getAllowedTargetStateIds,
  getRoleEpicScope,
  getRulesSignature,
  getWorkflowCellKey,
  hasTransitionsForState,
  isWorkflowDropAllowed,
  parseWorkflowCellKey,
  rulesToWorkflowDraft,
  setRoleExcludeEpics,
  toggleWorkflowCell,
  WORKFLOW_AGENT_ROLE,
  workflowDraftToRules,
} from "./helpers";

type TCase = { name: string; run: () => void };
const cases: TCase[] = [];
const test = (name: string, run: () => void) => cases.push({ name, run });

const fail = (message: string): never => {
  throw new Error(message);
};
const assertEqual = <T>(actual: T, expected: T, message = "") => {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) fail(`${message} expected ${e} but got ${a}`);
};
const sorted = (values: Set<string> | null) => (values === null ? null : [...values].sort());

// fixtures
const TODO = "todo";
const IN_PROGRESS = "in-progress";
const IN_REVIEW = "in-review";
const DONE = "done";

const AGENT_TRANSITIONS: TMyStateTransitions = {
  restricted: true,
  role: 10,
  epic_locked: true,
  transitions: { [TODO]: [IN_PROGRESS], [IN_PROGRESS]: [IN_REVIEW], [IN_REVIEW]: [], [DONE]: [] },
};

// --- getAllowedTargetStateIds ---------------------------------------------------------------
test("unrestricted users get null (no filtering)", () => {
  assertEqual(getAllowedTargetStateIds({ restricted: false }, TODO, false), null);
  assertEqual(getAllowedTargetStateIds(undefined, TODO, false), null);
});

test("agents can move To Do -> In Progress and keep the current state", () => {
  assertEqual(sorted(getAllowedTargetStateIds(AGENT_TRANSITIONS, TODO, false)), [IN_PROGRESS, TODO].sort());
  assertEqual(sorted(getAllowedTargetStateIds(AGENT_TRANSITIONS, IN_PROGRESS, false)), [IN_PROGRESS, IN_REVIEW]);
});

test("agents cannot move out of In Review / Done", () => {
  assertEqual(sorted(getAllowedTargetStateIds(AGENT_TRANSITIONS, IN_REVIEW, false)), [IN_REVIEW]);
  assertEqual(sorted(getAllowedTargetStateIds(AGENT_TRANSITIONS, DONE, false)), [DONE]);
});

test("epics are locked for agents", () => {
  assertEqual(sorted(getAllowedTargetStateIds(AGENT_TRANSITIONS, TODO, true)), [TODO]);
});

test("epics follow the map when not epic-locked", () => {
  const memberRules: TMyStateTransitions = { ...AGENT_TRANSITIONS, role: 15, epic_locked: false };
  assertEqual(sorted(getAllowedTargetStateIds(memberRules, TODO, true)), [IN_PROGRESS, TODO].sort());
});

test("epics use epic_transitions when the server sends them", () => {
  const memberRules: TMyStateTransitions = {
    ...AGENT_TRANSITIONS,
    role: 15,
    epic_locked: false,
    epic_transitions: { [TODO]: [DONE] },
  };
  assertEqual(sorted(getAllowedTargetStateIds(memberRules, TODO, true)), [DONE, TODO].sort());
  assertEqual(sorted(getAllowedTargetStateIds(memberRules, TODO, false)), [IN_PROGRESS, TODO].sort());
});

test("unknown from-state only allows the current state", () => {
  assertEqual(sorted(getAllowedTargetStateIds(AGENT_TRANSITIONS, "unknown", false)), ["unknown"]);
});

// --- isWorkflowDropAllowed ------------------------------------------------------------------
const agentCanTransition = (from: string, to: string) =>
  !!getAllowedTargetStateIds(AGENT_TRANSITIONS, from, false)?.has(to);

test("agent drop along an allowed transition is allowed", () => {
  assertEqual(
    isWorkflowDropAllowed({
      groupBy: "state",
      subGroupBy: undefined,
      sourceGroupId: TODO,
      destinationGroupId: IN_PROGRESS,
      isStateOnlyUser: true,
      canTransition: agentCanTransition,
    }),
    true
  );
});

test("agent drop along a forbidden transition is blocked", () => {
  assertEqual(
    isWorkflowDropAllowed({
      groupBy: "state",
      subGroupBy: undefined,
      sourceGroupId: TODO,
      destinationGroupId: DONE,
      isStateOnlyUser: true,
      canTransition: agentCanTransition,
    }),
    false
  );
});

test("agent reorder within a column is blocked", () => {
  assertEqual(
    isWorkflowDropAllowed({
      groupBy: "state",
      subGroupBy: undefined,
      sourceGroupId: TODO,
      destinationGroupId: TODO,
      isStateOnlyUser: true,
      canTransition: agentCanTransition,
    }),
    false
  );
});

test("agent drop that changes another field (priority grouping) is blocked", () => {
  assertEqual(
    isWorkflowDropAllowed({
      groupBy: "priority",
      subGroupBy: undefined,
      sourceGroupId: "high",
      destinationGroupId: "low",
      isStateOnlyUser: true,
      canTransition: () => true,
    }),
    false
  );
  assertEqual(
    isWorkflowDropAllowed({
      groupBy: "state",
      subGroupBy: "priority",
      sourceGroupId: TODO,
      destinationGroupId: IN_PROGRESS,
      sourceSubGroupId: "high",
      destinationSubGroupId: "low",
      isStateOnlyUser: true,
      canTransition: agentCanTransition,
    }),
    false
  );
});

test("agent state change through the sub-grouping is checked", () => {
  assertEqual(
    isWorkflowDropAllowed({
      groupBy: "priority",
      subGroupBy: "state",
      sourceGroupId: "high",
      destinationGroupId: "high",
      sourceSubGroupId: TODO,
      destinationSubGroupId: IN_PROGRESS,
      isStateOnlyUser: true,
      canTransition: agentCanTransition,
    }),
    true
  );
});

const deny = () => false;

test("regular users: non-state groupings and reorders are unaffected", () => {
  assertEqual(
    isWorkflowDropAllowed({
      groupBy: "priority",
      subGroupBy: undefined,
      sourceGroupId: "high",
      destinationGroupId: "low",
      isStateOnlyUser: false,
      canTransition: deny,
    }),
    true
  );
  assertEqual(
    isWorkflowDropAllowed({
      groupBy: "state",
      subGroupBy: undefined,
      sourceGroupId: TODO,
      destinationGroupId: TODO,
      isStateOnlyUser: false,
      canTransition: deny,
    }),
    true
  );
  assertEqual(
    isWorkflowDropAllowed({
      groupBy: "state",
      subGroupBy: undefined,
      sourceGroupId: TODO,
      destinationGroupId: DONE,
      isStateOnlyUser: false,
      canTransition: deny,
    }),
    false
  );
});

// --- "state__name" grouping (category master boards) ----------------------------------------
const STATE_IDS_BY_NAME: Record<string, string> = {
  "To Do": TODO,
  "In Progress": IN_PROGRESS,
  "In Review": IN_REVIEW,
  Done: DONE,
};
const getStateIdByName = (stateName: string) => STATE_IDS_BY_NAME[stateName];

test("agent drop between state-name columns resolves the names and checks the transition", () => {
  const checked: string[] = [];
  assertEqual(
    isWorkflowDropAllowed({
      groupBy: "state__name",
      subGroupBy: undefined,
      sourceGroupId: "To Do",
      destinationGroupId: "In Progress",
      isStateOnlyUser: true,
      canTransition: (from, to) => {
        checked.push(`${from}->${to}`);
        return agentCanTransition(from, to);
      },
      getStateIdByName,
    }),
    true
  );
  assertEqual(checked, [`${TODO}->${IN_PROGRESS}`]);
  assertEqual(
    isWorkflowDropAllowed({
      groupBy: "state__name",
      subGroupBy: undefined,
      sourceGroupId: "To Do",
      destinationGroupId: "Done",
      isStateOnlyUser: true,
      canTransition: agentCanTransition,
      getStateIdByName,
    }),
    false
  );
});

test("agent reorder within a state-name column is blocked", () => {
  assertEqual(
    isWorkflowDropAllowed({
      groupBy: "state__name",
      subGroupBy: undefined,
      sourceGroupId: "To Do",
      destinationGroupId: "To Do",
      isStateOnlyUser: true,
      canTransition: agentCanTransition,
      getStateIdByName,
    }),
    false
  );
});

test("agent state change through a state-name sub-grouping is checked", () => {
  const base = {
    groupBy: "priority",
    subGroupBy: "state__name",
    sourceGroupId: "high",
    destinationGroupId: "high",
    sourceSubGroupId: "In Progress",
    isStateOnlyUser: true,
    canTransition: agentCanTransition,
    getStateIdByName,
  };
  assertEqual(isWorkflowDropAllowed({ ...base, destinationSubGroupId: "In Review" }), true);
  assertEqual(isWorkflowDropAllowed({ ...base, destinationSubGroupId: "To Do" }), false);
});

test("restricted members are pre-checked on state-name boards", () => {
  assertEqual(
    isWorkflowDropAllowed({
      groupBy: "state__name",
      subGroupBy: undefined,
      sourceGroupId: "To Do",
      destinationGroupId: "Done",
      isStateOnlyUser: false,
      canTransition: deny,
      getStateIdByName,
    }),
    false
  );
});

test("unresolved state-name columns are left to the drop handler and the server", () => {
  // the work item's project has no "Won't Fix" state: the drop handler reports it
  assertEqual(
    isWorkflowDropAllowed({
      groupBy: "state__name",
      subGroupBy: undefined,
      sourceGroupId: "To Do",
      destinationGroupId: "Won't Fix",
      isStateOnlyUser: true,
      canTransition: deny,
      getStateIdByName,
    }),
    true
  );
  // no resolver: an agent's column change is still a state change, not "another field"
  assertEqual(
    isWorkflowDropAllowed({
      groupBy: "state__name",
      subGroupBy: undefined,
      sourceGroupId: "To Do",
      destinationGroupId: "In Progress",
      isStateOnlyUser: true,
      canTransition: deny,
    }),
    true
  );
});

// --- hasTransitionsForState -----------------------------------------------------------------
test("loaded transitions know every state of the project, not states created later", () => {
  assertEqual(hasTransitionsForState(AGENT_TRANSITIONS, TODO), true);
  assertEqual(hasTransitionsForState(AGENT_TRANSITIONS, DONE), true);
  assertEqual(hasTransitionsForState(AGENT_TRANSITIONS, "created-later"), false);
  assertEqual(hasTransitionsForState({ restricted: false }, "created-later"), true);
});

// --- matrix draft <-> rules -----------------------------------------------------------------
const RULES: TStateTransitionRule[] = [
  { id: "r1", from_state_id: TODO, to_state_id: IN_PROGRESS, roles: [10, 15], exclude_epics: true },
  { id: "r2", from_state_id: IN_PROGRESS, to_state_id: IN_REVIEW, roles: [10], exclude_epics: true },
  { id: "r3", from_state_id: null, to_state_id: DONE, roles: [15, 20], exclude_epics: false },
];

test("cell keys round-trip, including the any-state row", () => {
  assertEqual(parseWorkflowCellKey(getWorkflowCellKey(null, DONE)), { fromStateId: null, toStateId: DONE });
  assertEqual(parseWorkflowCellKey(getWorkflowCellKey(TODO, DONE)), { fromStateId: TODO, toStateId: DONE });
  assertEqual(getWorkflowCellKey(null, DONE).startsWith(ANY_STATE_KEY), true);
});

test("rules -> draft groups cells per role", () => {
  const draft = rulesToWorkflowDraft(RULES);
  assertEqual(
    Object.keys(draft[10]).sort(),
    [getWorkflowCellKey(IN_PROGRESS, IN_REVIEW), getWorkflowCellKey(TODO, IN_PROGRESS)].sort()
  );
  assertEqual(draft[15][getWorkflowCellKey(null, DONE)], false);
  assertEqual(draft[15][getWorkflowCellKey(TODO, IN_PROGRESS)], true);
  assertEqual(Object.keys(draft[5]).length, 0);
});

test("draft -> rules round-trips without changes, keeps ids and drops the admin role", () => {
  const rules = workflowDraftToRules(rulesToWorkflowDraft(RULES), RULES);
  assertEqual(getRulesSignature(rules), getRulesSignature(RULES));
  assertEqual(rules.find((rule) => rule.from_state_id === null)?.id, "r3");
  // admins always bypass the workflow and the API rejects role 20 in rules
  assertEqual(rules.find((rule) => rule.from_state_id === null)?.roles, [15]);
});

test("roles outside the matrix (other than admin) are preserved", () => {
  const custom: TStateTransitionRule[] = [
    { id: "c1", from_state_id: TODO, to_state_id: DONE, roles: [12, 15], exclude_epics: false },
  ];
  const draft = rulesToWorkflowDraft(custom);
  delete draft[15][getWorkflowCellKey(TODO, DONE)];
  assertEqual(workflowDraftToRules(draft, custom), [
    { id: "c1", from_state_id: TODO, to_state_id: DONE, roles: [12], exclude_epics: false },
  ]);
});

test("removing and adding cells updates the merged roles", () => {
  const draft = rulesToWorkflowDraft(RULES);
  delete draft[15][getWorkflowCellKey(TODO, IN_PROGRESS)];
  draft[5][getWorkflowCellKey(TODO, IN_PROGRESS)] = true;
  draft[10][getWorkflowCellKey(IN_REVIEW, IN_REVIEW)] = true; // diagonal cells are ignored
  const rules = workflowDraftToRules(draft, RULES);
  const todoToProgress = rules.find((rule) => rule.from_state_id === TODO && rule.to_state_id === IN_PROGRESS);
  assertEqual(todoToProgress?.roles, [10, 5]);
  assertEqual(todoToProgress?.id, "r1");
  assertEqual(
    rules.some((rule) => rule.from_state_id === IN_REVIEW && rule.to_state_id === IN_REVIEW),
    false
  );
});

test("the same pair with and without epics produces two rules", () => {
  const draft = rulesToWorkflowDraft([]);
  draft[15][getWorkflowCellKey(TODO, DONE)] = false;
  draft[10][getWorkflowCellKey(TODO, DONE)] = true;
  const rules = workflowDraftToRules(draft, []);
  assertEqual(rules.length, 2);
  assertEqual(rules.map((rule) => rule.exclude_epics).sort(), [false, true]);
});

// --- matrix editing helpers -----------------------------------------------------------------
test("epic scope of a role", () => {
  assertEqual(getRoleEpicScope(undefined), "empty");
  assertEqual(getRoleEpicScope({}), "empty");
  assertEqual(getRoleEpicScope({ a: true, b: true }), "exclude");
  assertEqual(getRoleEpicScope({ a: false }), "apply");
  assertEqual(getRoleEpicScope({ a: false, b: true }), "mixed");
});

test("setting the epic scope updates every cell of the role", () => {
  assertEqual(setRoleExcludeEpics({ a: false, b: true }, true), { a: true, b: true });
  assertEqual(setRoleExcludeEpics(undefined, false), {});
});

test("toggling cells adds and removes rules and ignores the diagonal", () => {
  const key = getWorkflowCellKey(TODO, DONE);
  const added = toggleWorkflowCell({}, TODO, DONE, true);
  assertEqual(added, { [key]: true });
  assertEqual(toggleWorkflowCell(added, TODO, DONE, false), {});
  assertEqual(toggleWorkflowCell({}, TODO, TODO, false), {});
  assertEqual(toggleWorkflowCell({}, null, TODO, false), { [getWorkflowCellKey(null, TODO)]: false });
});

test("agents rules saved from the matrix keep excluding epics", () => {
  const draft = rulesToWorkflowDraft([]);
  draft[WORKFLOW_AGENT_ROLE] = toggleWorkflowCell(draft[WORKFLOW_AGENT_ROLE], TODO, IN_PROGRESS, true);
  const rules = workflowDraftToRules(draft, []);
  assertEqual(rules, [{ from_state_id: TODO, to_state_id: IN_PROGRESS, roles: [10], exclude_epics: true }]);
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
console.log(`${cases.length - failed}/${cases.length} workflow helper tests passed`);
if (failed > 0) throw new Error(`${failed} workflow helper test(s) failed`);
