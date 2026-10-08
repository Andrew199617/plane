/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Unit tests for the project lead / default assignee helpers (Node's built-in runner; apps/web has
// no test runner):
//   node --test apps/web/components/jira-parity/project-defaults/utils.test.mjs
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { getPrefillAssigneeId, getProjectUserId } from "./utils.ts";

describe("getProjectUserId", () => {
  test("ids and user objects", () => {
    assert.equal(getProjectUserId("user-1"), "user-1");
    assert.equal(getProjectUserId({ id: "user-2", display_name: "x" }), "user-2");
  });

  test("empty values", () => {
    assert.equal(getProjectUserId(null), null);
    assert.equal(getProjectUserId(undefined), null);
    assert.equal(getProjectUserId(""), null);
    assert.equal(getProjectUserId({}), null);
    assert.equal(getProjectUserId({ id: "" }), null);
    assert.equal(getProjectUserId(42), null);
  });
});

describe("getPrefillAssigneeId", () => {
  test("members not loaded yet trusts the server", () => {
    assert.equal(getPrefillAssigneeId("user-1", null), "user-1");
  });

  test("default assignee must be an assignable project member", () => {
    assert.equal(getPrefillAssigneeId("user-1", ["user-0", "user-1"]), "user-1");
    assert.equal(getPrefillAssigneeId({ id: "user-1" }, ["user-1"]), "user-1");
    assert.equal(getPrefillAssigneeId("user-9", ["user-1"]), null);
  });

  test("no default assignee", () => {
    assert.equal(getPrefillAssigneeId(null, ["user-1"]), null);
    assert.equal(getPrefillAssigneeId(undefined, null), null);
  });
});
