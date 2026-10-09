/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: unit tests for the master board (project category) store helpers. apps/web has no test runner, so
// these use Node's built-in runner (Node >= 23.6 strips the TypeScript types of helpers.ts natively):
//   node --test store/jira-parity/category-board/helpers.test.mjs   (from apps/web)
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  computeReorderedSortOrders,
  findProjectStateByName,
  getCategoryBoardCycleNameParam,
  getCategoryBoardQueryParamsByLayout,
  getCategoryProjectIds,
  getStateNameColumns,
  normalizeCategoryBoardQuickFilters,
  sanitizeCategoryBoardDisplayFilters,
} from "./helpers.ts";

const makeState = (overrides) => ({
  color: "#000000",
  default: false,
  description: "",
  workspace_id: "ws",
  order: 0,
  ...overrides,
});

const STATES = [
  // project A (standard Jira-parity states, created in a different order than the columns)
  makeState({ id: "a-done", name: "Done", group: "completed", project_id: "A", sequence: 40000 }),
  makeState({ id: "a-todo", name: "To Do", group: "unstarted", project_id: "A", sequence: 10000 }),
  makeState({ id: "a-review", name: "In Review", group: "started", project_id: "A", sequence: 30000 }),
  makeState({ id: "a-progress", name: "In Progress", group: "started", project_id: "A", sequence: 20000 }),
  makeState({ id: "a-wontfix", name: "Won't Fix", group: "cancelled", project_id: "A", sequence: 50000 }),
  makeState({ id: "a-triage", name: "Triage", group: "triage", project_id: "A", sequence: 1 }),
  // project B: same names plus a custom one
  makeState({ id: "b-todo", name: "To Do", group: "unstarted", project_id: "B", sequence: 10000 }),
  makeState({ id: "b-blocked", name: "Blocked", group: "started", project_id: "B", sequence: 25000 }),
  makeState({ id: "b-progress", name: "In Progress", group: "started", project_id: "B", sequence: 20000 }),
  // project C (other category): Plane defaults
  makeState({ id: "c-backlog", name: "Backlog", group: "backlog", project_id: "C", sequence: 1000 }),
];

describe("getStateNameColumns", () => {
  test("one column per state name across the scoped projects, in Jira column order", () => {
    const columns = getStateNameColumns(STATES, ["A", "B"]);
    assert.deepEqual(
      columns.map((column) => column.name),
      ["To Do", "In Progress", "In Review", "Done", "Won't Fix", "Blocked"]
    );
    const todo = columns.find((column) => column.name === "To Do");
    assert.deepEqual(todo.stateIds.toSorted(), ["a-todo", "b-todo"]);
  });

  test("skips states of projects outside the category and triage states", () => {
    const names = new Set(getStateNameColumns(STATES, ["A"]).map((column) => column.name));
    assert.ok(!names.has("Backlog"));
    assert.ok(!names.has("Blocked"));
    assert.ok(!names.has("Triage"));
  });

  test("without a project scope every project contributes; non-standard names follow state group order", () => {
    const names = getStateNameColumns(STATES, undefined).map((column) => column.name);
    assert.deepEqual(names, ["To Do", "In Progress", "In Review", "Done", "Won't Fix", "Backlog", "Blocked"]);
  });

  test("the representative state is the earliest by group then sequence", () => {
    const states = [
      makeState({ id: "x2", name: "Doing", group: "started", project_id: "X", sequence: 500 }),
      makeState({ id: "y1", name: "Doing", group: "started", project_id: "Y", sequence: 100 }),
    ];
    const [column] = getStateNameColumns(states, undefined);
    assert.equal(column.state.id, "y1");
    assert.deepEqual(column.stateIds, ["x2", "y1"]);
  });

  test("matches standard names ignoring case, extra spaces and curly apostrophes", () => {
    const states = [
      makeState({ id: "w", name: "won’t  fix", group: "cancelled", project_id: "X", sequence: 1 }),
      makeState({ id: "d", name: "DONE", group: "completed", project_id: "X", sequence: 2 }),
      makeState({ id: "t", name: "to do", group: "unstarted", project_id: "X", sequence: 3 }),
    ];
    assert.deepEqual(
      getStateNameColumns(states, undefined).map((column) => column.name),
      ["to do", "DONE", "won’t  fix"]
    );
  });
});

describe("findProjectStateByName", () => {
  test("resolves a column name to the state of the work item's own project", () => {
    assert.equal(findProjectStateByName(STATES, "B", "In Progress")?.id, "b-progress");
    assert.equal(findProjectStateByName(STATES, "A", "In Progress")?.id, "a-progress");
  });

  test("falls back to a case-insensitive match", () => {
    assert.equal(findProjectStateByName(STATES, "A", "in review ")?.id, "a-review");
  });

  test("returns undefined when the project lacks the status or no project is given", () => {
    assert.equal(findProjectStateByName(STATES, "B", "In Review"), undefined);
    assert.equal(findProjectStateByName(STATES, null, "To Do"), undefined);
  });
});

describe("sanitizeCategoryBoardDisplayFilters", () => {
  test("defaults to a kanban grouped by status", () => {
    assert.deepEqual(sanitizeCategoryBoardDisplayFilters({}), { layout: "kanban", group_by: "state__name" });
  });

  test("replaces project-only group-bys and unsupported layouts", () => {
    const sanitized = sanitizeCategoryBoardDisplayFilters({
      layout: "calendar",
      group_by: "cycle",
      sub_group_by: "module",
    });
    assert.equal(sanitized.layout, "kanban");
    assert.equal(sanitized.group_by, "state__name");
    assert.equal(sanitized.sub_group_by, null);
  });

  test("keeps supported settings and drops a sub group equal to the group", () => {
    const sanitized = sanitizeCategoryBoardDisplayFilters({
      layout: "kanban",
      group_by: "priority",
      sub_group_by: "priority",
      order_by: "-created_at",
    });
    assert.equal(sanitized.group_by, "priority");
    assert.equal(sanitized.sub_group_by, null);
    assert.equal(sanitized.order_by, "-created_at");
  });

  test("a list may be ungrouped", () => {
    const sanitized = sanitizeCategoryBoardDisplayFilters({ layout: "list", group_by: null });
    assert.equal(sanitized.layout, "list");
    assert.equal(sanitized.group_by, null);
  });
});

describe("getCategoryBoardQueryParamsByLayout", () => {
  const pageConfig = {
    layoutOptions: {
      kanban: {
        display_properties: [],
        display_filters: { group_by: [], sub_group_by: [], order_by: [], type: [] },
        extra_options: { access: true, values: ["show_empty_groups", "sub_issue"] },
      },
      spreadsheet: {
        display_properties: [],
        display_filters: { order_by: [], type: [] },
        extra_options: { access: false, values: ["sub_issue"] },
      },
    },
  };

  test("collects filters, display filters and accessible extra options", () => {
    assert.deepEqual(getCategoryBoardQueryParamsByLayout(pageConfig, "kanban"), [
      "filters",
      "group_by",
      "sub_group_by",
      "order_by",
      "type",
      "show_empty_groups",
      "sub_issue",
    ]);
    assert.deepEqual(getCategoryBoardQueryParamsByLayout(pageConfig, "spreadsheet"), ["filters", "order_by", "type"]);
  });

  test("unknown layouts or configs yield null", () => {
    assert.equal(getCategoryBoardQueryParamsByLayout(pageConfig, "calendar"), null);
    assert.equal(getCategoryBoardQueryParamsByLayout(undefined, "kanban"), null);
    assert.equal(getCategoryBoardQueryParamsByLayout(pageConfig, undefined), null);
  });
});

describe("normalizeCategoryBoardQuickFilters", () => {
  test("keeps distinct, non-empty sprint names", () => {
    assert.deepEqual(normalizeCategoryBoardQuickFilters({ cycle_names: ["Sprint 1", "", "Sprint 1", 3, "Sprint 2"] }), {
      cycle_names: ["Sprint 1", "Sprint 2"],
    });
  });

  test("anything else becomes empty filters", () => {
    for (const stored of [undefined, null, "x", 1, { cycle_names: "Sprint 1" }, { type_ids: ["a"] }])
      assert.deepEqual(normalizeCategoryBoardQuickFilters(stored), { cycle_names: [] });
  });
});

describe("getCategoryBoardCycleNameParam", () => {
  test("sends the exact names as a JSON array (comma-safe, no 'None' sentinel)", () => {
    const names = ["Sprint 1, part 2", "None", "Sprint 3"];
    const param = getCategoryBoardCycleNameParam(names);
    assert.equal(param, '["Sprint 1, part 2","None","Sprint 3"]');
    assert.deepEqual(JSON.parse(param), names);
  });

  test("no selection, no param", () => {
    assert.equal(getCategoryBoardCycleNameParam([]), undefined);
  });
});

describe("getCategoryProjectIds", () => {
  const projects = [
    { id: "p1", category_id: "cat" },
    { id: "p2", category_id: "other" },
    { id: "p3", category_id: null },
    { id: "p4", category_id: "cat", archived_at: "2026-01-01" },
    { id: "p5" },
  ];

  test("uses the live project category and skips archived projects", () => {
    assert.deepEqual(getCategoryProjectIds("cat", ["p2", "p3"], projects), ["p1"]);
  });

  test("falls back to the category's project_ids when a project has no category_id field", () => {
    assert.deepEqual(getCategoryProjectIds("cat", ["p5"], projects), ["p1", "p5"]);
  });
});

describe("computeReorderedSortOrders", () => {
  const items = [
    { id: "a", sort_order: 10000 },
    { id: "b", sort_order: 20000 },
    { id: "c", sort_order: 30000 },
  ];

  test("renumbers with the gap and only returns changed items", () => {
    assert.deepEqual(computeReorderedSortOrders(items, 2, 0, 10000), [
      { id: "c", sort_order: 10000 },
      { id: "a", sort_order: 20000 },
      { id: "b", sort_order: 30000 },
    ]);
    assert.deepEqual(computeReorderedSortOrders(items, 0, 1, 10000), [
      { id: "b", sort_order: 10000 },
      { id: "a", sort_order: 20000 },
    ]);
  });

  test("no-op moves return nothing", () => {
    assert.deepEqual(computeReorderedSortOrders(items, 1, 1, 10000), []);
    assert.deepEqual(computeReorderedSortOrders(items, -1, 1, 10000), []);
    assert.deepEqual(computeReorderedSortOrders(items, 0, 3, 10000), []);
  });
});
