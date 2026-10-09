/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Unit tests for the Jira-parity release helpers (Node's built-in runner):
//   node --test apps/web/components/jira-parity/releases/helpers.test.mjs
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  formatReleaseDateRangeLabel,
  getDefaultReleaseDate,
  getMoveTargetReleases,
  getReleaseErrorMessage,
  getReleaseLozengeStatus,
  getReleaseProgress,
  getUnresolvedCount,
  isReleaseOverdue,
  isReleaseReleased,
  parsePayloadDate,
  toPayloadDate,
} from "./helpers.ts";

const TODAY = new Date(2026, 9, 8); // 2026-10-08 local

const counts = (overrides = {}) => ({
  total_issues: 0,
  completed_issues: 0,
  cancelled_issues: 0,
  started_issues: 0,
  unstarted_issues: 0,
  backlog_issues: 0,
  ...overrides,
});

describe("release status", () => {
  test("released / unreleased / legacy values", () => {
    assert.equal(isReleaseReleased({ status: "released" }), true);
    assert.equal(isReleaseReleased({ status: "unreleased" }), false);
    assert.equal(isReleaseReleased({ status: "completed" }), false);
    assert.equal(isReleaseReleased({}), false);
    assert.equal(isReleaseReleased(null), false);
  });

  test("lozenge: archived wins over the status", () => {
    assert.equal(getReleaseLozengeStatus({ status: "unreleased", archived_at: null }), "unreleased");
    assert.equal(getReleaseLozengeStatus({ status: "released", archived_at: null }), "released");
    assert.equal(getReleaseLozengeStatus({ status: "released", archived_at: "2026-10-01T00:00:00Z" }), "archived");
    assert.equal(getReleaseLozengeStatus({ status: undefined, archived_at: null }), "unreleased");
  });
});

describe("overdue", () => {
  test("unreleased with a past release date", () => {
    assert.equal(isReleaseOverdue({ status: "unreleased", archived_at: null, target_date: "2026-10-07" }, TODAY), true);
  });

  test("today or later is not overdue", () => {
    assert.equal(
      isReleaseOverdue({ status: "unreleased", archived_at: null, target_date: "2026-10-08" }, TODAY),
      false
    );
    assert.equal(
      isReleaseOverdue({ status: "unreleased", archived_at: null, target_date: "2026-12-01" }, TODAY),
      false
    );
  });

  test("released, archived, or without a date is never overdue", () => {
    assert.equal(isReleaseOverdue({ status: "released", archived_at: null, target_date: "2026-01-01" }, TODAY), false);
    assert.equal(
      isReleaseOverdue({ status: "unreleased", archived_at: "2026-10-01T00:00:00Z", target_date: "2026-01-01" }, TODAY),
      false
    );
    assert.equal(isReleaseOverdue({ status: "unreleased", archived_at: null, target_date: null }, TODAY), false);
    assert.equal(isReleaseOverdue(null, TODAY), false);
  });

  test("datetime-shaped dates compare by their date part", () => {
    assert.equal(
      isReleaseOverdue({ status: "unreleased", archived_at: null, target_date: "2026-10-07T23:00:00Z" }, TODAY),
      true
    );
  });
});

describe("counts and progress", () => {
  test("unresolved = total - completed - cancelled", () => {
    assert.equal(getUnresolvedCount(counts({ total_issues: 10, completed_issues: 4, cancelled_issues: 1 })), 5);
    assert.equal(getUnresolvedCount(counts({ total_issues: 3, completed_issues: 3 })), 0);
    assert.equal(getUnresolvedCount(counts({ total_issues: 1, completed_issues: 2 })), 0);
    assert.equal(getUnresolvedCount(null), 0);
  });

  test("segments: done / in progress / to do", () => {
    const progress = getReleaseProgress(
      counts({ completed_issues: 3, cancelled_issues: 1, started_issues: 2, unstarted_issues: 1, backlog_issues: 1 })
    );
    assert.equal(progress.done, 4);
    assert.equal(progress.inProgress, 2);
    assert.equal(progress.toDo, 2);
    assert.equal(progress.total, 8);
    assert.equal(progress.donePercent, 50);
    assert.equal(progress.inProgressPercent, 25);
    assert.equal(progress.toDoPercent, 25);
  });

  test("empty release has no segments", () => {
    const progress = getReleaseProgress(counts());
    assert.deepEqual(progress, {
      done: 0,
      inProgress: 0,
      toDo: 0,
      total: 0,
      donePercent: 0,
      inProgressPercent: 0,
      toDoPercent: 0,
    });
    assert.equal(getReleaseProgress(undefined).total, 0);
  });

  test("segments add up to 100", () => {
    const progress = getReleaseProgress(counts({ completed_issues: 1, started_issues: 1, backlog_issues: 1 }));
    assert.ok(Math.abs(progress.donePercent + progress.inProgressPercent + progress.toDoPercent - 100) < 1e-9);
  });
});

describe("dates", () => {
  test("payload date formatting and parsing", () => {
    assert.equal(toPayloadDate(new Date(2026, 0, 5)), "2026-01-05");
    const parsed = parsePayloadDate("2026-10-08");
    assert.ok(parsed);
    assert.equal(toPayloadDate(parsed), "2026-10-08");
    assert.equal(parsePayloadDate(null), null);
    assert.equal(parsePayloadDate("not a date"), null);
  });

  test("default release date: target date, else today", () => {
    assert.equal(getDefaultReleaseDate({ target_date: "2026-11-30" }, TODAY), "2026-11-30");
    assert.equal(getDefaultReleaseDate({ target_date: null }, TODAY), "2026-10-08");
    assert.equal(getDefaultReleaseDate(undefined, TODAY), "2026-10-08");
  });

  test("range label marks the missing end", () => {
    assert.equal(formatReleaseDateRangeLabel({ from: "", to: "" }), "");
    assert.equal(formatReleaseDateRangeLabel({ from: "", to: "Oct 15, 2026" }), "… - Oct 15, 2026");
    assert.equal(formatReleaseDateRangeLabel({ from: "Oct 01, 2026", to: "" }), "Oct 01, 2026 - …");
    assert.equal(
      formatReleaseDateRangeLabel({ from: "Oct 01, 2026", to: "Oct 15, 2026" }),
      "Oct 01, 2026 - Oct 15, 2026"
    );
  });
});

describe("move targets", () => {
  test("other unreleased, non-archived releases of the same project, in order", () => {
    const current = { id: "a", project_id: "p", status: "unreleased", archived_at: null };
    const releases = [
      current,
      { id: "b", project_id: "p", status: "unreleased", archived_at: null },
      { id: "c", project_id: "p", status: "released", archived_at: null },
      { id: "d", project_id: "p", status: "unreleased", archived_at: "2026-10-01T00:00:00Z" },
      { id: "e", project_id: "other", status: "unreleased", archived_at: null },
      null,
      { id: "f", project_id: "p", status: undefined, archived_at: null },
    ];
    assert.deepEqual(
      getMoveTargetReleases(releases, current).map((release) => release.id),
      ["b", "f"]
    );
  });
});

const translate = (key) => `t:${key}`;

describe("error messages", () => {
  test("known codes are translated", () => {
    assert.equal(
      getReleaseErrorMessage({ error: "Already released", code: "RELEASE_ALREADY_RELEASED" }, translate, "fallback"),
      "t:jp_releases.errors.already_released"
    );
    assert.equal(
      getReleaseErrorMessage({ code: "INVALID_TARGET" }, translate, "fallback"),
      "t:jp_releases.errors.invalid_target"
    );
  });

  test("unknown codes use the server message, then the fallback", () => {
    assert.equal(getReleaseErrorMessage({ error: "Nope", code: "SOMETHING" }, translate, "fallback"), "Nope");
    assert.equal(getReleaseErrorMessage({ detail: "Forbidden" }, translate, "fallback"), "Forbidden");
    assert.equal(getReleaseErrorMessage({}, translate, "fallback"), "fallback");
    assert.equal(getReleaseErrorMessage(undefined, translate, "fallback"), "fallback");
    assert.equal(getReleaseErrorMessage("boom", translate, "fallback"), "fallback");
  });
});
