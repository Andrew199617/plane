/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";

const locales = new URL("../src/locales/", import.meta.url);
const read = (locale, file) => JSON.parse(readFileSync(new URL(`${locale}/${file}.json`, locales), "utf8"));
const english = read("en", "jp-priorities").jp_priorities;
for (const locale of readdirSync(locales)) {
  test(`${locale} priorities retain existing translations and localize the new extremes`, () => {
    const priorities = read(locale, "jp-priorities").jp_priorities;
    const previous = read(locale, "work-item").issue.priority;
    assert.deepEqual(Object.keys(priorities).toSorted(), ["high", "highest", "low", "lowest", "medium"]);
    for (const key of ["high", "medium", "low"]) assert.equal(priorities[key], previous[key]);
    for (const key of ["highest", "lowest"]) {
      assert.ok(priorities[key].trim());
      if (locale !== "en") assert.notEqual(priorities[key], english[key]);
    }
  });
}
