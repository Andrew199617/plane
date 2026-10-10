/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: unit tests for the estimate notification renderers.
// apps/web has no test runner, so this file is self-contained (no node/vitest imports, so it also
// type-checks under the web tsconfig). Run it with:
//   pnpm --filter @plane/i18n exec tsx --test <abs path to this file>
import { JP_TIME_TRACKING_NOTIFICATION_CONTENT_MAP } from "./notification-content";

type TCase = { name: string; run: () => void };
const cases: TCase[] = [];
const test = (name: string, run: () => void) => cases.push({ name, run });

const assertEqual = <T>(actual: T, expected: T, message = "") => {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) throw new Error(`${message} expected ${e} but got ${a}`);
};

const render = (field: "original_estimate" | "remaining_estimate", newValue: string | undefined) =>
  JP_TIME_TRACKING_NOTIFICATION_CONTENT_MAP[field]({ field, newValue, oldValue: "60", verb: "updated" });

test("a set estimate renders as a Jira duration with the 'to' connector", () => {
  assertEqual(render("original_estimate", "3630"), {
    action: "set the original estimate",
    value: "1w 2d 4h 30m",
    showConnector: true,
  });
  assertEqual(render("remaining_estimate", "480"), {
    action: "set the remaining estimate",
    value: "1d",
    showConnector: true,
  });
});

test("zero minutes is a real value, not a removal", () => {
  assertEqual(render("remaining_estimate", "0")?.value, "0m");
});

test("an empty or missing new value renders as a removal", () => {
  for (const value of ["", undefined]) {
    assertEqual(render("original_estimate", value), {
      action: "removed the original estimate",
      value: null,
      showConnector: false,
    });
  }
});

test("a non-numeric value is treated as a removal instead of rendering NaN", () => {
  assertEqual(render("remaining_estimate", "abc")?.action, "removed the remaining estimate");
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
console.log(`${cases.length - failed}/${cases.length} estimate notification tests passed`);
if (failed > 0) throw new Error(`${failed} estimate notification test(s) failed`);
