/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Unit tests for the time tracking helpers (Node's built-in runner, see duration.test.mjs):
//   node --test apps/web/components/jira-parity/time-tracking/utils.test.mjs
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { getTimeTrackingPayload, isTimeTrackingField, parseActivityMinutes, TIME_TRACKING_FIELDS } from "./utils.ts";

describe("time tracking utils", () => {
  test("fields", () => {
    assert.deepEqual(TIME_TRACKING_FIELDS, ["original_estimate", "remaining_estimate"]);
    assert.equal(isTimeTrackingField("original_estimate"), true);
    assert.equal(isTimeTrackingField("remaining_estimate"), true);
    assert.equal(isTimeTrackingField("estimate_point"), false);
    assert.equal(isTimeTrackingField(undefined), false);
  });

  test("update payloads", () => {
    assert.deepEqual(getTimeTrackingPayload("original_estimate", 90), { original_estimate: 90 });
    assert.deepEqual(getTimeTrackingPayload("remaining_estimate", null), { remaining_estimate: null });
  });

  test("activity values are minutes as strings", () => {
    assert.equal(parseActivityMinutes("150"), 150);
    assert.equal(parseActivityMinutes("0"), 0);
    assert.equal(parseActivityMinutes(""), null);
    assert.equal(parseActivityMinutes("  "), null);
    assert.equal(parseActivityMinutes(null), null);
    assert.equal(parseActivityMinutes(undefined), null);
    assert.equal(parseActivityMinutes("abc"), null);
    assert.equal(parseActivityMinutes("-5"), null);
  });
});
