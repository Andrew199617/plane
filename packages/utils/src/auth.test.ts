/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Same Unicode cases as plane/tests/unit/test_password_policy.py. Explicit escapes keep these
// fixtures intact across operating-system encodings. Run with:
//   pnpm --filter @plane/i18n exec tsx --test <abs path to this file>
import { E_PASSWORD_STRENGTH, EAuthErrorCodes } from "@plane/constants";
import { authErrorHandler, getPasswordCriteria, getPasswordPolicyFeedback, getPasswordStrength } from "./auth";

type TCase = { name: string; run: () => void };
const cases: TCase[] = [];
const test = (name: string, run: () => void) => cases.push({ name, run });

const assertEqual = <T>(actual: T, expected: T, message = "") => {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) throw new Error(message + " expected " + e + " but got " + a);
};
const failedCriteria = (password: string) =>
  getPasswordCriteria(password)
    .filter((criterion) => !criterion.isValid)
    .map((criterion) => criterion.key);

const CLASS_CASES: [string, string[]][] = [
  ["Abcdefg1\u00e9", ["special"]],
  ["\u00c0\u00c9\u00ce12345!", []],
  ["Ab1!\u{1f600}\u{1f600}", ["length"]],
  ["Abcdefg1\u{1f600}", []],
  ["Abcdefg\u0661!", []], // Arabic-Indic digit (Nd)
  ["Abcdefg\u00bd!", ["number"]], // vulgar fraction (No)
  ["abcdefg\u21671!", ["uppercase"]], // Roman numeral (Nl)
  ["Abcdefg1 \u00a0", ["special"]], // whitespace
];

for (const [password, failed] of CLASS_CASES) {
  test("criteria for " + JSON.stringify(password), () => assertEqual(failedCriteria(password), failed, password));
}

test("strength follows the criteria", () => {
  assertEqual(getPasswordStrength(""), E_PASSWORD_STRENGTH.EMPTY);
  assertEqual(getPasswordStrength("Ab1!\u{1f600}\u{1f600}"), E_PASSWORD_STRENGTH.LENGTH_NOT_VALID);
  assertEqual(getPasswordStrength("Abcdefg1\u00e9"), E_PASSWORD_STRENGTH.STRENGTH_NOT_VALID);
  assertEqual(getPasswordStrength("\u00c0\u00c9\u00ce12345!"), E_PASSWORD_STRENGTH.STRENGTH_VALID);
});

test("failed rules produce specific feedback", () => {
  assertEqual(
    getPasswordPolicyFeedback("length,uppercase,number,special"),
    "Use at least 8 characters. Use an uppercase letter. Use a number. Use a symbol."
  );
  assertEqual(
    getPasswordPolicyFeedback("strength"),
    "Choose a less predictable password. Avoid common words and patterns."
  );
  assertEqual(authErrorHandler(EAuthErrorCodes.PASSWORD_TOO_WEAK, undefined, "special")?.message, "Use a symbol.");
});

test("feedback ignores unknown keys and malformed data", () => {
  assertEqual(getPasswordPolicyFeedback("special,special,unknown"), "Use a symbol.");
  for (const rules of [undefined, null, {}, [], "", "__proto__", "constructor", "<script>alert(1)</script>"]) {
    assertEqual(getPasswordPolicyFeedback(rules), undefined);
  }
});

let failed = 0;
for (const testCase of cases) {
  try {
    testCase.run();
    console.log("ok - " + testCase.name);
  } catch (error) {
    failed += 1;
    console.error("not ok - " + testCase.name + "\n  " + (error as Error).message);
  }
}
console.log(cases.length - failed + "/" + cases.length + " password criteria tests passed");
if (failed > 0) throw new Error(failed + " password criteria test(s) failed");
