/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Unit tests for the Jira-style duration helpers. apps/web has no test runner, so these use
// Node's built-in runner (Node >= 22.18 strips the TypeScript types of the imported module):
//   node --test apps/web/components/jira-parity/time-tracking/duration.test.mjs
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { formatDuration, parseDuration, MAX_ESTIMATE_MINUTES } from "./duration.ts";

describe("formatDuration", () => {
  test("formats with 8h days and 5d weeks", () => {
    assert.equal(formatDuration(2400 + 960 + 240 + 30), "1w 2d 4h 30m");
    assert.equal(formatDuration(480), "1d");
    assert.equal(formatDuration(2400), "1w");
    assert.equal(formatDuration(90), "1h 30m");
    assert.equal(formatDuration(45), "45m");
    assert.equal(formatDuration(600), "1d 2h");
  });

  test("zero and empty values", () => {
    assert.equal(formatDuration(0), "0m");
    assert.equal(formatDuration(null), "");
    assert.equal(formatDuration(undefined), "");
    assert.equal(formatDuration(-1), "");
    assert.equal(formatDuration(Number.NaN), "");
  });

  test("honours a custom config", () => {
    assert.equal(formatDuration(1440, { hoursPerDay: 24, daysPerWeek: 7 }), "1d");
    assert.equal(formatDuration(480, { hoursPerDay: 24, daysPerWeek: 7 }), "8h");
  });
});

describe("parseDuration", () => {
  const minutes = (input) => {
    const result = parseDuration(input);
    assert.equal(result.ok, true, `expected "${input}" to parse`);
    return result.minutes;
  };

  test("Jira tokens", () => {
    assert.equal(minutes("1w 2d 4h 30m"), 3630);
    assert.equal(minutes("4h30m"), 270);
    assert.equal(minutes("2d"), 960);
    assert.equal(minutes("1W 1D"), 2880);
    assert.equal(minutes("  3h  "), 180);
    assert.equal(minutes("2 days, 3 hours"), 1140);
    assert.equal(minutes("1 week 15 mins"), 2415);
  });

  test("decimals round to the minute", () => {
    assert.equal(minutes("1.5h"), 90);
    assert.equal(minutes("0,5d"), 240);
    assert.equal(minutes("0.01h"), 1);
  });

  test("bare numbers are minutes", () => {
    assert.equal(minutes("90"), 90);
    assert.equal(minutes("0"), 0);
  });

  test("empty clears", () => {
    assert.equal(minutes(""), null);
    assert.equal(minutes("   "), null);
    assert.equal(minutes(null), null);
  });

  test("rejects invalid input", () => {
    for (const input of ["abc", "1x", "h", "1h foo", "foo 1h", "-1h", "1h-2m", "1..5h"]) {
      assert.equal(parseDuration(input).ok, false, `expected "${input}" to be rejected`);
    }
    assert.equal(parseDuration(`${MAX_ESTIMATE_MINUTES + 1}`).ok, false);
  });

  test("round-trips formatted values", () => {
    for (const value of [1, 59, 60, 61, 479, 480, 2399, 2400, 3630, 123456]) {
      assert.equal(minutes(formatDuration(value)), value);
    }
  });
});
