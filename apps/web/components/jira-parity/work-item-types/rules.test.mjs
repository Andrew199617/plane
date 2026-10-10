/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: unit tests for the pure work item type rules.
// Run (from apps/web): node --test components/jira-parity/work-item-types/rules.test.mjs
// Node >= 23.6 strips the TypeScript types of rules.ts natively.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  buildWorkItemTypeLogoProps,
  getSuggestedWorkItemTypeForParent,
  getWorkItemTypeColor,
  getWorkItemTypeHierarchyError,
  getWorkItemTypeIconKey,
  isWorkItemTypeSelectable,
  sortWorkItemTypes,
  sortWorkItemsByTypeName,
} from "./rules.ts";

const makeType = (overrides) => ({
  id: overrides.name.toLowerCase(),
  description: "",
  logo_props: { in_use: "icon", icon: {} },
  is_epic: false,
  is_sub_task: false,
  is_default: false,
  is_active: true,
  level: 0,
  workspace_id: "ws",
  ...overrides,
});

const TASK = makeType({ name: "Task", is_default: true });
const STORY = makeType({ name: "Story" });
const BUG = makeType({ name: "Bug" });
const SUB_TASK = makeType({ name: "Sub-task", is_sub_task: true, level: -1 });
const EPIC = makeType({ name: "Epic", is_epic: true, level: 1 });
const ALL_TYPES = [EPIC, SUB_TASK, BUG, STORY, TASK];

describe("sortWorkItemsByTypeName", () => {
  const items = [
    { id: "task", type_id: TASK.id },
    { id: "none", type_id: null },
    { id: "story", type_id: STORY.id },
    { id: "bug", type_id: BUG.id },
    { id: "bug-again", type_id: BUG.id },
  ];
  const getName = (id) => ALL_TYPES.find((type) => type.id === id)?.name;
  test("ascending and descending sorts keep untyped items last and ties stable", () => {
    assert.deepEqual(
      sortWorkItemsByTypeName(items, getName)?.map((item) => item.id),
      ["bug", "bug-again", "story", "task", "none"]
    );
    assert.deepEqual(
      sortWorkItemsByTypeName(items, getName, true)?.map((item) => item.id),
      ["task", "story", "bug", "bug-again", "none"]
    );
    assert.equal(items[0].id, "task");
  });
  test("an unloaded type leaves the incoming API order intact", () => {
    assert.equal(
      sortWorkItemsByTypeName(items, () => undefined),
      undefined
    );
    assert.equal(
      sortWorkItemsByTypeName(items, (id) => (id === BUG.id ? undefined : getName(id))),
      undefined
    );
  });
});

describe("getWorkItemTypeIconKey", () => {
  test("uses the logo icon name first (material ligatures and plain keys)", () => {
    assert.equal(
      getWorkItemTypeIconKey({ ...TASK, logo_props: { in_use: "icon", icon: { name: "bug_report" } } }),
      "bug"
    );
    assert.equal(getWorkItemTypeIconKey({ ...TASK, logo_props: { in_use: "icon", icon: { name: "BOLT" } } }), "epic");
    assert.equal(
      getWorkItemTypeIconKey({ ...TASK, logo_props: { in_use: "icon", icon: { name: "bookmark" } } }),
      "story"
    );
    assert.equal(
      getWorkItemTypeIconKey({ ...TASK, logo_props: { in_use: "icon", icon: { name: "sub_task" } } }),
      "sub_task"
    );
    // ligatures seeded by the backend (plane/utils/work_item_types.py STANDARD_WORK_ITEM_TYPES)
    assert.equal(
      getWorkItemTypeIconKey({ ...TASK, logo_props: { in_use: "icon", icon: { name: "priority" } } }),
      "story"
    );
    assert.equal(
      getWorkItemTypeIconKey({ ...TASK, logo_props: { in_use: "icon", icon: { name: "subdirectory_arrow_right" } } }),
      "sub_task"
    );
    assert.equal(
      getWorkItemTypeIconKey({ ...TASK, logo_props: { in_use: "icon", icon: { name: "check_box" } } }),
      "task"
    );
  });

  test("falls back to the type flags, then the type name", () => {
    assert.equal(getWorkItemTypeIconKey(EPIC), "epic");
    assert.equal(getWorkItemTypeIconKey(SUB_TASK), "sub_task");
    assert.equal(getWorkItemTypeIconKey(makeType({ name: "Subtask" })), "sub_task");
    assert.equal(getWorkItemTypeIconKey(STORY), "story");
    assert.equal(getWorkItemTypeIconKey(BUG), "bug");
    assert.equal(getWorkItemTypeIconKey(TASK), "task");
  });

  test("unknown or missing types draw the task glyph", () => {
    assert.equal(getWorkItemTypeIconKey(makeType({ name: "Incident" })), "task");
    assert.equal(getWorkItemTypeIconKey(undefined), "task");
    assert.equal(
      getWorkItemTypeIconKey({ ...TASK, logo_props: { in_use: "icon", icon: { name: "rocket_launch" } } }),
      "task"
    );
  });
});

describe("getWorkItemTypeColor", () => {
  test("prefers the logo background color, then the logo color, ignoring white", () => {
    assert.equal(
      getWorkItemTypeColor({
        ...TASK,
        logo_props: { in_use: "icon", icon: { background_color: "#123456", color: "#FFFFFF" } },
      }),
      "#123456"
    );
    assert.equal(
      getWorkItemTypeColor({
        ...TASK,
        logo_props: { in_use: "icon", icon: { background_color: "#FFFFFF", color: "#abcdef" } },
      }),
      "#abcdef"
    );
  });

  test("falls back to the Jira color of the type name, then the glyph default", () => {
    assert.equal(getWorkItemTypeColor(BUG), "#E5493A");
    assert.equal(getWorkItemTypeColor(STORY), "#E97F33");
    assert.equal(getWorkItemTypeColor(EPIC), "#904EE2");
    assert.equal(getWorkItemTypeColor(makeType({ name: "Defect" })), "#E5493A");
    assert.equal(getWorkItemTypeColor(makeType({ name: "Incident" })), "#4BADE8");
    assert.equal(getWorkItemTypeColor(undefined), "#4BADE8");
  });

  test("ignores invalid colors", () => {
    assert.equal(
      getWorkItemTypeColor({
        ...BUG,
        logo_props: { in_use: "icon", icon: { background_color: "red", color: "var(--x)" } },
      }),
      "#E5493A"
    );
  });
});

describe("buildWorkItemTypeLogoProps", () => {
  test("stores the material ligature and the brand color on both icon colors", () => {
    assert.deepEqual(buildWorkItemTypeLogoProps("story", "#E97F33"), {
      in_use: "icon",
      icon: { name: "priority_high", color: "#E97F33", background_color: "#E97F33" },
    });
  });

  test("round-trips through the icon and color resolvers", () => {
    const logo = buildWorkItemTypeLogoProps("epic", "#00B8D9");
    const type = makeType({ name: "Feature", logo_props: logo });
    assert.equal(getWorkItemTypeIconKey(type), "epic");
    assert.equal(getWorkItemTypeColor(type), "#00B8D9");
  });

  test("an invalid color falls back to the glyph default", () => {
    assert.equal(buildWorkItemTypeLogoProps("bug", "nope").icon.background_color, "#E5493A");
  });
});

describe("sortWorkItemTypes", () => {
  test("default first, standard types by name, then Epic, then Sub-task", () => {
    assert.deepEqual(
      sortWorkItemTypes(ALL_TYPES).map((type) => type.name),
      ["Task", "Bug", "Story", "Epic", "Sub-task"]
    );
  });

  test("does not mutate its input", () => {
    const input = [...ALL_TYPES];
    sortWorkItemTypes(input);
    assert.deepEqual(input, ALL_TYPES);
  });
});

describe("getWorkItemTypeHierarchyError", () => {
  test("a Sub-task requires a parent", () => {
    assert.equal(getWorkItemTypeHierarchyError(SUB_TASK, { hasParent: false }), "sub_task_requires_parent");
    assert.equal(getWorkItemTypeHierarchyError(SUB_TASK, { hasParent: true, parentType: STORY }), undefined);
  });

  test("a Sub-task cannot be a parent", () => {
    assert.equal(getWorkItemTypeHierarchyError(TASK, { hasParent: true, parentType: SUB_TASK }), "parent_is_sub_task");
    assert.equal(getWorkItemTypeHierarchyError(EPIC, { hasParent: true, parentType: SUB_TASK }), "parent_is_sub_task");
    assert.equal(
      getWorkItemTypeHierarchyError(SUB_TASK, { hasParent: true, parentType: STORY, hasChildren: true }),
      "sub_task_cannot_have_children"
    );
  });

  test("standard types and Epics are valid with or without a parent", () => {
    for (const type of [TASK, STORY, BUG, EPIC]) {
      assert.equal(getWorkItemTypeHierarchyError(type, { hasParent: false }), undefined);
      assert.equal(getWorkItemTypeHierarchyError(type, { hasParent: true, parentType: EPIC }), undefined);
    }
  });

  test("an unknown parent type does not block", () => {
    assert.equal(getWorkItemTypeHierarchyError(SUB_TASK, { hasParent: true, parentType: undefined }), undefined);
  });
});

describe("isWorkItemTypeSelectable", () => {
  test("Sub-task is only selectable for a work item with a parent and no children", () => {
    assert.equal(isWorkItemTypeSelectable(SUB_TASK, { hasParent: false }), false);
    assert.equal(isWorkItemTypeSelectable(SUB_TASK, { hasParent: true, hasChildren: true }), false);
    assert.equal(isWorkItemTypeSelectable(SUB_TASK, { hasParent: true, hasChildren: false }), true);
    assert.equal(isWorkItemTypeSelectable(TASK, { hasParent: false, hasChildren: true }), true);
  });
});

describe("getSuggestedWorkItemTypeForParent", () => {
  test("suggests Sub-task under a standard work item", () => {
    for (const parent of [TASK, STORY, BUG]) {
      assert.equal(getSuggestedWorkItemTypeForParent(ALL_TYPES, parent)?.name, "Sub-task");
    }
  });

  test("suggests the default type under an Epic or without a parent", () => {
    assert.equal(getSuggestedWorkItemTypeForParent(ALL_TYPES, EPIC)?.name, "Task");
    assert.equal(getSuggestedWorkItemTypeForParent(ALL_TYPES, undefined)?.name, "Task");
  });

  test("skips inactive types", () => {
    const inactiveSubTask = makeType({ name: "Sub-task", is_sub_task: true, level: -1, is_active: false });
    const types = [EPIC, inactiveSubTask, BUG, STORY, TASK];
    assert.equal(getSuggestedWorkItemTypeForParent(types, STORY)?.name, "Task");
  });
});
