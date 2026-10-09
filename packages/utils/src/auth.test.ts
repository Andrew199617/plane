/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: the password criteria must classify characters exactly like the API's
// plane/utils/password_policy.py (same cases as test_character_classes_match_the_ui there).
// packages/utils has no test runner, so this file is self-contained. Run it with:
//   pnpm --filter @plane/i18n exec tsx --test <abs path to this file>
import { E_PASSWORD_STRENGTH } from "@plane/constants";
import { getPasswordCriteria, getPasswordStrength } from "./auth";

type TCase = { name: string; run: () => void };
const cases: TCase[] = [];
const test = (name: string, run: () => void) => cases.push({ name, run });

const assertEqual = <T>(actual: T, expected: T, message = "") => {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) throw new Error(`${message} expected ${e} but got ${a}`);
};
const failedCriteria = (password: string) =>
  getPasswordCriteria(password)
    .filter((criterion) => !criterion.isValid)
    .map((criterion) => criterion.key);

const CLASS_CASES: [string, string[]][] = [
  ["Abcdefg1é", ["special"]],
  ["ÀÉÎ12345!", []],
  ["Ab1!😀😀", ["length"]],
  ["Abcdefg1😀", []],
  ["Abcdefg٣!", []], // Arabic-Indic digit (Nd)
  ["Abcdefg½!", ["number"]], // vulgar fraction (No) is not a number
  ["abcdefgⅠ1!", ["uppercase"]], // Roman numeral (Nl) is not an uppercase letter
  ["Abcdefg1  ", ["special"]], // whitespace is not a symbol
];

for (const [password, failed] of CLASS_CASES) {
  test(`criteria for ${JSON.stringify(password)}`, () => assertEqual(failedCriteria(password), failed, password));
}

test("strength follows the criteria", () => {
  assertEqual(getPasswordStrength(""), E_PASSWORD_STRENGTH.EMPTY);
  assertEqual(getPasswordStrength("Ab1!😀😀"), E_PASSWORD_STRENGTH.LENGTH_NOT_VALID);
  assertEqual(getPasswordStrength("Abcdefg1é"), E_PASSWORD_STRENGTH.STRENGTH_NOT_VALID);
  assertEqual(getPasswordStrength("ÀÉÎ12345!"), E_PASSWORD_STRENGTH.STRENGTH_VALID);
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
console.log(`${cases.length - failed}/${cases.length} password criteria tests passed`);
if (failed > 0) throw new Error(`${failed} password criteria test(s) failed`);
