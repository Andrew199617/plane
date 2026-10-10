/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ISSUE_PRIORITIES } from "@plane/constants";
import type { TIssuePriorities } from "@plane/types";
import { PriorityIcon } from "./priority-icon";

// Jira-parity priorities: one Jira-style glyph per key, colored by its own text-priority-* token.
const EXPECTED: { key: TIssuePriorities; strokes: number }[] = [
  { key: "highest", strokes: 2 }, // double chevron up
  { key: "high", strokes: 1 }, // chevron up
  { key: "medium", strokes: 2 }, // equals
  { key: "low", strokes: 1 }, // chevron down
  { key: "lowest", strokes: 2 }, // double chevron down
];

describe("PriorityIcon", () => {
  it("covers every priority the constants expose, most important first", () => {
    expect(ISSUE_PRIORITIES.map((priority) => priority.key)).toEqual(EXPECTED.map((priority) => priority.key));
  });

  it.each(EXPECTED)("renders the $key glyph with its color token", ({ key, strokes }) => {
    const { container } = render(<PriorityIcon priority={key} className="size-4" />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute("data-priority")).toBe(key);
    expect(svg?.getAttribute("class")).toContain(`text-priority-${key}`);
    expect(svg?.getAttribute("class")).toContain("size-4");
    expect(svg?.querySelectorAll("polyline, line")).toHaveLength(strokes);
  });

  it("renders a neutral placeholder when there is no priority", () => {
    const { container } = render(<PriorityIcon priority={null} />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute("class")).toContain("text-priority-none");
  });

  it("renders nothing for an unknown (legacy) key", () => {
    const { container } = render(<PriorityIcon priority={"urgent" as unknown as TIssuePriorities} />);
    expect(container.innerHTML).toBe("");
  });
});
