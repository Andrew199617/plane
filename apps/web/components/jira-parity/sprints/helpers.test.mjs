/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Unit tests for the sprint helpers (Node's built-in runner):
//   node --test apps/web/components/jira-parity/sprints/helpers.test.mjs
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  addDaysToKey,
  daysBetweenKeys,
  DEFAULT_SPRINT_DURATION,
  getDefaultMoveTarget,
  getSprintEndDate,
  getSprintErrorMessage,
  getSprintIssueSummary,
  getSprintState,
  getStartSprintDefaults,
  inferSprintDuration,
  isActiveSprint,
  isClosedSprint,
  isFutureSprint,
  isValidSprintRange,
  normalizeDateKey,
  parseDateKey,
  sortFutureSprints,
  SPRINT_DURATION_I18N,
  SPRINT_DURATIONS,
  toDateKey,
} from "./helpers.ts";

describe("date keys", () => {
  test("format and parse local calendar days", () => {
    assert.equal(toDateKey(new Date(2026, 0, 5)), "2026-01-05");
    assert.equal(toDateKey(parseDateKey("2026-12-31")), "2026-12-31");
    assert.equal(parseDateKey("2026-02-30"), null);
    assert.equal(parseDateKey("not a date"), null);
    assert.equal(parseDateKey(""), null);
    assert.equal(parseDateKey(null), null);
    assert.equal(normalizeDateKey("2026-10-08T07:00:00Z"), "2026-10-08");
    assert.equal(normalizeDateKey(undefined), null);
  });

  test("add days across month / year / DST boundaries", () => {
    assert.equal(addDaysToKey("2026-10-08", 13), "2026-10-21");
    assert.equal(addDaysToKey("2026-12-25", 13), "2027-01-07");
    assert.equal(addDaysToKey("2026-03-01", 13), "2026-03-14");
    assert.equal(addDaysToKey("2026-03-05", 7), "2026-03-12");
    assert.equal(addDaysToKey("2026-10-30", 6), "2026-11-05");
    assert.equal(addDaysToKey("bad", 1), null);
  });

  test("days between", () => {
    assert.equal(daysBetweenKeys("2026-10-08", "2026-10-21"), 13);
    assert.equal(daysBetweenKeys("2026-10-08", "2026-10-08"), 0);
    assert.equal(daysBetweenKeys("2026-10-08", "2026-10-01"), -7);
    assert.equal(daysBetweenKeys("2026-03-01", "2026-03-15"), 14);
    assert.equal(daysBetweenKeys("x", "2026-03-15"), null);
  });
});

describe("durations", () => {
  test("options", () => {
    assert.deepEqual(SPRINT_DURATIONS, ["1w", "2w", "3w", "4w", "custom"]);
    assert.equal(DEFAULT_SPRINT_DURATION, "2w");
    for (const duration of SPRINT_DURATIONS) assert.match(SPRINT_DURATION_I18N[duration], /^jp_sprints\.duration\./);
  });

  test("end date = start + duration - 1 day", () => {
    assert.equal(getSprintEndDate("2026-10-08", "1w"), "2026-10-14");
    assert.equal(getSprintEndDate("2026-10-08", "2w"), "2026-10-21");
    assert.equal(getSprintEndDate("2026-10-08", "3w"), "2026-10-28");
    assert.equal(getSprintEndDate("2026-10-08", "4w"), "2026-11-04");
    assert.equal(getSprintEndDate("2026-10-08", "custom"), null);
    assert.equal(getSprintEndDate(null, "2w"), null);
  });

  test("infer duration from planned dates", () => {
    assert.equal(inferSprintDuration("2026-10-08", "2026-10-14"), "1w");
    assert.equal(inferSprintDuration("2026-10-08", "2026-10-21"), "2w");
    assert.equal(inferSprintDuration("2026-10-08", "2026-10-28"), "3w");
    assert.equal(inferSprintDuration("2026-10-08", "2026-11-04"), "4w");
    assert.equal(inferSprintDuration("2026-10-08", "2026-10-22"), "custom");
    assert.equal(inferSprintDuration("2026-10-08", "2026-10-08"), "custom");
    assert.equal(inferSprintDuration(null, "2026-10-08"), "2w");
  });

  test("valid range", () => {
    assert.equal(isValidSprintRange("2026-10-08", "2026-10-08"), true);
    assert.equal(isValidSprintRange("2026-10-08", "2026-10-21"), true);
    assert.equal(isValidSprintRange("2026-10-21", "2026-10-08"), false);
    assert.equal(isValidSprintRange("2026-10-08", null), false);
  });
});

describe("start sprint defaults", () => {
  test("no planned dates: today + 2 weeks", () => {
    assert.deepEqual(
      getStartSprintDefaults({ name: "LGD Sprint 5", description: "", start_date: null, end_date: null }, "2026-10-08"),
      { name: "LGD Sprint 5", description: "", duration: "2w", start_date: "2026-10-08", end_date: "2026-10-21" }
    );
  });

  test("planned dates prefill (past dates allowed) and infer the duration", () => {
    assert.deepEqual(
      getStartSprintDefaults(
        { name: "Sprint 1", description: "Ship it", start_date: "2026-09-01", end_date: "2026-09-07" },
        "2026-10-08"
      ),
      { name: "Sprint 1", description: "Ship it", duration: "1w", start_date: "2026-09-01", end_date: "2026-09-07" }
    );
    assert.equal(
      getStartSprintDefaults({ name: "S", description: "", start_date: "2026-10-01", end_date: "2026-10-10" }, "x")
        .duration,
      "custom"
    );
  });

  test("start only / invalid range fall back to the default duration", () => {
    assert.deepEqual(
      getStartSprintDefaults({ name: "S", description: null, start_date: "2026-11-02", end_date: null }, "2026-10-08"),
      { name: "S", description: "", duration: "2w", start_date: "2026-11-02", end_date: "2026-11-15" }
    );
    assert.deepEqual(
      getStartSprintDefaults({ name: "S", description: "", start_date: "2026-11-02", end_date: "2026-11-01" }, "x"),
      { name: "S", description: "", duration: "2w", start_date: "2026-11-02", end_date: "2026-11-15" }
    );
    assert.equal(getStartSprintDefaults(undefined, "2026-10-08").start_date, "2026-10-08");
  });
});

describe("sprint state", () => {
  test("state comes from the server status, never from dates", () => {
    assert.equal(getSprintState({ status: "COMPLETED", archived_at: null }), "closed");
    assert.equal(getSprintState({ status: "CURRENT", archived_at: null }), "active");
    assert.equal(getSprintState({ status: "UPCOMING", archived_at: null }), "future");
    assert.equal(getSprintState({ status: "DRAFT", archived_at: null }), "future");
    assert.equal(getSprintState({ status: undefined, archived_at: null }), "future");
    assert.equal(
      getSprintState({ status: undefined, archived_at: null, started_at: "2026-10-01T00:00:00Z" }),
      "active"
    );
    assert.equal(
      getSprintState({ status: undefined, archived_at: null, started_at: "x", completed_at: "2026-10-01T00:00:00Z" }),
      "closed"
    );
    assert.equal(getSprintState(null), "future");
  });

  test("predicates", () => {
    assert.equal(isFutureSprint({ status: "UPCOMING", archived_at: null }), true);
    assert.equal(isFutureSprint({ status: "UPCOMING", archived_at: "2026-10-01" }), false);
    assert.equal(isActiveSprint({ status: "CURRENT", archived_at: null }), true);
    assert.equal(isActiveSprint({ status: "COMPLETED", archived_at: null }), false);
    assert.equal(isClosedSprint({ status: "COMPLETED", archived_at: "2026-10-01" }), true);
    assert.equal(isClosedSprint(undefined), false);
  });
});

describe("complete sprint", () => {
  test("future sprints in backlog order", () => {
    const sprints = [
      { id: "c", name: "Sprint 7", sort_order: 300, start_date: null },
      { id: "b", name: "Sprint 6", sort_order: 200, start_date: "2026-11-01" },
      { id: "a", name: "Sprint 5", sort_order: 200, start_date: "2026-10-20" },
      { id: "d", name: "Sprint 4", sort_order: 200, start_date: null },
      { id: "e", name: "Sprint 3", sort_order: 100, start_date: null },
    ];
    assert.deepEqual(
      sortFutureSprints(sprints).map((s) => s.id),
      ["e", "a", "b", "d", "c"]
    );
    assert.equal(sprints[0].id, "c", "does not mutate the input");
  });

  test("default move target", () => {
    assert.equal(getDefaultMoveTarget(["s1", "s2"]), "s1");
    assert.equal(getDefaultMoveTarget([]), "new");
  });

  test("done vs open summary", () => {
    assert.deepEqual(
      getSprintIssueSummary({
        total_issues: 10,
        completed_issues: 4,
        cancelled_issues: 1,
        backlog_issues: 1,
        unstarted_issues: 2,
        started_issues: 2,
      }),
      { done: 5, open: 5 }
    );
    assert.deepEqual(getSprintIssueSummary({ total_issues: 6, completed_issues: 2, cancelled_issues: 1 }), {
      done: 3,
      open: 3,
    });
    assert.deepEqual(getSprintIssueSummary(undefined), { done: 0, open: 0 });
  });
});

describe("error messages", () => {
  test("prefers the server message", () => {
    assert.equal(
      getSprintErrorMessage({ error: "Sprint 4 is already active.", code: "ACTIVE_SPRINT_EXISTS" }, "fallback"),
      "Sprint 4 is already active."
    );
    assert.equal(getSprintErrorMessage({ detail: "Not found." }, "fallback"), "Not found.");
    assert.equal(getSprintErrorMessage({ end_date: ["Invalid date."] }, "fallback"), "Invalid date.");
    assert.equal(getSprintErrorMessage({ error: "  " }, "fallback"), "fallback");
    assert.equal(getSprintErrorMessage(undefined, "fallback"), "fallback");
    assert.equal(getSprintErrorMessage("<html>", "fallback"), "fallback");
  });
});
