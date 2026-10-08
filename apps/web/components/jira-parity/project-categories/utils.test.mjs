/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: unit tests for the project-categories UI helpers (Node's built-in runner; Node >= 23.6 strips the
// TypeScript types of utils.ts natively):
//   node --test components/jira-parity/project-categories/utils.test.mjs   (from apps/web)
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { getProjectCategoryErrorMessage, groupProjectIdsByCategory } from "./utils.ts";

describe("getProjectCategoryErrorMessage", () => {
  test("reads {error} and {detail}", () => {
    assert.equal(
      getProjectCategoryErrorMessage({ error: "Project category not found." }, "fallback"),
      "Project category not found."
    );
    assert.equal(getProjectCategoryErrorMessage({ detail: "Forbidden" }, "fallback"), "Forbidden");
  });

  test("reads the first DRF field error", () => {
    assert.equal(
      getProjectCategoryErrorMessage({ name: ["A project category with this name already exists."] }, "fallback"),
      "A project category with this name already exists."
    );
  });

  test("plain strings are returned as is", () => {
    assert.equal(getProjectCategoryErrorMessage("Bad request", "fallback"), "Bad request");
  });

  test("falls back for empty or unknown shapes", () => {
    for (const error of [undefined, null, "", "  ", 42, {}, { name: [] }, { error: "" }])
      assert.equal(getProjectCategoryErrorMessage(error, "fallback"), "fallback");
  });
});

describe("groupProjectIdsByCategory", () => {
  const categories = [
    { id: "game", name: "Game" },
    { id: "web", name: "Website" },
    { id: "empty", name: "Testing" },
  ];
  const projectCategory = { p1: "web", p2: "game", p3: null, p4: "game", p5: "deleted-category" };

  test("one group per category with projects (category order), then uncategorized", () => {
    const groups = groupProjectIdsByCategory(["p1", "p2", "p3", "p4", "p5"], categories, (id) => projectCategory[id]);
    assert.deepEqual(
      groups.map((group) => [group.category?.id ?? null, group.projectIds]),
      [
        ["game", ["p2", "p4"]],
        ["web", ["p1"]],
        [null, ["p3", "p5"]],
      ]
    );
  });

  test("no uncategorized group when every project has a known category", () => {
    const groups = groupProjectIdsByCategory(["p2", "p1"], categories, (id) => projectCategory[id]);
    assert.deepEqual(
      groups.map((group) => group.category?.id ?? null),
      ["game", "web"]
    );
  });

  test("empty input yields no groups", () => {
    assert.deepEqual(
      groupProjectIdsByCategory([], categories, () => null),
      []
    );
  });
});
