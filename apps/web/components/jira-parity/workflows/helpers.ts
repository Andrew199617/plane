/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: pure workflow helpers (owned by the workflows feature).
// Type-only imports keep this module runnable by `tsx --test` (see helpers.test.ts).
import type { TMyStateTransitions, TStateTransitionRule } from "@plane/types";

/**
 * States the current user may move a work item to from `fromStateId` (the current state is always
 * included), or `null` when the user is unrestricted.
 */
export const getAllowedTargetStateIds = (
  myTransitions: TMyStateTransitions | undefined,
  fromStateId: string,
  isEpic: boolean
): Set<string> | null => {
  if (!myTransitions || !myTransitions.restricted) return null;
  if (isEpic && myTransitions.epic_locked) return new Set([fromStateId]);
  const transitions =
    isEpic && myTransitions.epic_transitions ? myTransitions.epic_transitions : myTransitions.transitions;
  return new Set([fromStateId, ...(transitions?.[fromStateId] ?? [])]);
};

export type TWorkflowDropContext = {
  /** Display grouping of the layout. */
  groupBy: string | null | undefined;
  subGroupBy: string | null | undefined;
  sourceGroupId: string | undefined;
  destinationGroupId: string | undefined;
  sourceSubGroupId?: string | undefined;
  destinationSubGroupId?: string | undefined;
  /** True when the user may only change the state of work items (agents). */
  isStateOnlyUser: boolean;
  /** Workflow check for a state change (from -> to). */
  canTransition: (fromStateId: string, toStateId: string) => boolean;
};

/**
 * Decides whether a kanban/list drop is allowed by the workflow.
 * - Non-state groupings are unaffected for regular users.
 * - State-only users (agents) may only change the state: any other grouping change, or a pure reorder, is blocked.
 */
export const isWorkflowDropAllowed = (context: TWorkflowDropContext): boolean => {
  const {
    groupBy,
    subGroupBy,
    sourceGroupId,
    destinationGroupId,
    sourceSubGroupId,
    destinationSubGroupId,
    isStateOnlyUser,
    canTransition,
  } = context;

  const isGroupedByState = groupBy === "state";
  const isSubGroupedByState = subGroupBy === "state";
  const groupChanged = !!sourceGroupId && !!destinationGroupId && sourceGroupId !== destinationGroupId;
  const subGroupChanged =
    !!subGroupBy && !!sourceSubGroupId && !!destinationSubGroupId && sourceSubGroupId !== destinationSubGroupId;

  if (isStateOnlyUser) {
    const changesOtherField = (groupChanged && !isGroupedByState) || (subGroupChanged && !isSubGroupedByState);
    const changesState = (groupChanged && isGroupedByState) || (subGroupChanged && isSubGroupedByState);
    if (changesOtherField || !changesState) return false;
  }

  if (groupChanged && isGroupedByState && sourceGroupId && destinationGroupId)
    return canTransition(sourceGroupId, destinationGroupId);
  if (subGroupChanged && isSubGroupedByState && sourceSubGroupId && destinationSubGroupId)
    return canTransition(sourceSubGroupId, destinationSubGroupId);
  return true;
};

// ---------------------------------------------------------------------------------------------
// Settings matrix (draft) <-> rules
// ---------------------------------------------------------------------------------------------

/** Key used for the "any state" (from_state_id = null) row. */
export const ANY_STATE_KEY = "__any__";

/** Roles that can be edited in the workflow matrix (admins always bypass workflows). */
export const WORKFLOW_EDITABLE_ROLES = [15, 10, 5] as const;

/** Admins (20) always bypass the workflow; the API rejects rules that list them. */
const WORKFLOW_ADMIN_ROLE = 20;

/** Per role: cell key (`from::to`) -> exclude_epics. */
export type TWorkflowRoleDraft = Record<string, boolean>;
/** role -> cells */
export type TWorkflowDraft = Record<number, TWorkflowRoleDraft>;

export const getWorkflowCellKey = (fromStateId: string | null, toStateId: string): string =>
  `${fromStateId ?? ANY_STATE_KEY}::${toStateId}`;

export const parseWorkflowCellKey = (key: string): { fromStateId: string | null; toStateId: string } => {
  const [from, to] = key.split("::");
  return { fromStateId: from === ANY_STATE_KEY ? null : from, toStateId: to };
};

/** Builds the editable draft (one entry per editable role) from the stored rules. */
export const rulesToWorkflowDraft = (
  rules: TStateTransitionRule[],
  roles: readonly number[] = WORKFLOW_EDITABLE_ROLES
): TWorkflowDraft => {
  const draft: TWorkflowDraft = {};
  for (const role of roles) draft[role] = {};
  for (const rule of rules) {
    if (!rule.to_state_id) continue;
    for (const role of rule.roles ?? []) {
      if (!draft[role]) continue;
      const key = getWorkflowCellKey(rule.from_state_id, rule.to_state_id);
      // a pair stored both with and without epics is treated as applying to epics
      const current = draft[role][key];
      draft[role][key] = current === undefined ? rule.exclude_epics : current && rule.exclude_epics;
    }
  }
  return draft;
};

const getRuleGroupKey = (fromStateId: string | null, toStateId: string, excludeEpics: boolean) =>
  `${getWorkflowCellKey(fromStateId, toStateId)}::${excludeEpics ? 1 : 0}`;

/**
 * Converts the draft back to the PUT payload. Rules are merged per (from, to, exclude_epics) with their
 * roles; role memberships of other non-admin roles not shown in the draft are preserved (Admin is
 * dropped: admins bypass the workflow and the API rejects it), and existing rule ids are kept when the
 * same (from, to, exclude_epics) row still exists.
 */
export const workflowDraftToRules = (
  draft: TWorkflowDraft,
  originalRules: TStateTransitionRule[],
  roles: readonly number[] = WORKFLOW_EDITABLE_ROLES
): TStateTransitionRule[] => {
  const groups = new Map<string, TStateTransitionRule>();
  const addRole = (fromStateId: string | null, toStateId: string, excludeEpics: boolean, role: number) => {
    if (fromStateId !== null && fromStateId === toStateId) return;
    const groupKey = getRuleGroupKey(fromStateId, toStateId, excludeEpics);
    const existing = groups.get(groupKey);
    if (existing) {
      if (!existing.roles.includes(role)) existing.roles.push(role);
      return;
    }
    groups.set(groupKey, {
      from_state_id: fromStateId,
      to_state_id: toStateId,
      roles: [role],
      exclude_epics: excludeEpics,
    });
  };

  for (const rule of originalRules) {
    for (const role of rule.roles ?? []) {
      if (roles.includes(role) || role >= WORKFLOW_ADMIN_ROLE) continue;
      addRole(rule.from_state_id, rule.to_state_id, rule.exclude_epics, role);
    }
  }
  for (const role of roles) {
    for (const [key, excludeEpics] of Object.entries(draft[role] ?? {})) {
      const { fromStateId, toStateId } = parseWorkflowCellKey(key);
      addRole(fromStateId, toStateId, excludeEpics, role);
    }
  }

  const originalIds = new Map<string, string>();
  for (const rule of originalRules) {
    if (rule.id) originalIds.set(getRuleGroupKey(rule.from_state_id, rule.to_state_id, rule.exclude_epics), rule.id);
  }

  const result: TStateTransitionRule[] = [];
  for (const [groupKey, rule] of groups.entries()) {
    const id = originalIds.get(groupKey);
    // oxlint-disable-next-line unicorn/no-array-sort -- sorts a copy; web targets ES2022 (no toSorted)
    const sortedRoles = [...rule.roles].sort((a, b) => b - a);
    const nextRule: TStateTransitionRule = {
      from_state_id: rule.from_state_id,
      to_state_id: rule.to_state_id,
      roles: sortedRoles,
      exclude_epics: rule.exclude_epics,
    };
    result.push(id ? { id, ...nextRule } : nextRule);
  }
  return result;
};

/** Numeric value of the Agent role (agents can never change the state of epics). */
export const WORKFLOW_AGENT_ROLE = 10;

/** How a role's rules apply to epics: no rules, all apply, none apply, or a mix. */
export type TWorkflowEpicScope = "empty" | "apply" | "exclude" | "mixed";

export const getRoleEpicScope = (cells: TWorkflowRoleDraft | undefined): TWorkflowEpicScope => {
  const values = Object.values(cells ?? {});
  if (values.length === 0) return "empty";
  if (values.every((excludeEpics) => excludeEpics)) return "exclude";
  if (values.every((excludeEpics) => !excludeEpics)) return "apply";
  return "mixed";
};

/** Returns a copy of the role's cells with every rule's exclude_epics set to `excludeEpics`. */
export const setRoleExcludeEpics = (cells: TWorkflowRoleDraft | undefined, excludeEpics: boolean): TWorkflowRoleDraft =>
  Object.fromEntries(Object.keys(cells ?? {}).map((key) => [key, excludeEpics]));

/**
 * Toggles one cell of a role. A new cell takes `excludeEpics` (agents always exclude epics). Cells on
 * the diagonal (same state) are ignored: staying in the same state is always allowed.
 */
export const toggleWorkflowCell = (
  cells: TWorkflowRoleDraft | undefined,
  fromStateId: string | null,
  toStateId: string,
  excludeEpics: boolean
): TWorkflowRoleDraft => {
  const next: TWorkflowRoleDraft = { ...cells };
  if (fromStateId !== null && fromStateId === toStateId) return next;
  const key = getWorkflowCellKey(fromStateId, toStateId);
  if (key in next) delete next[key];
  else next[key] = excludeEpics;
  return next;
};

/** Order-insensitive signature of a rule list (Admin entries ignored), used to detect unsaved changes. */
export const getRulesSignature = (rules: TStateTransitionRule[]): string =>
  rules
    .flatMap((rule) =>
      (rule.roles ?? [])
        .filter((role) => role < WORKFLOW_ADMIN_ROLE)
        .map(
          (role) => `${role}|${rule.from_state_id ?? ANY_STATE_KEY}|${rule.to_state_id}|${rule.exclude_epics ? 1 : 0}`
        )
    )
    // oxlint-disable-next-line unicorn/no-array-sort -- sorts a fresh array; web targets ES2022 (no toSorted)
    .sort()
    .join(",");
