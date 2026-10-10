# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Plain-text tables for the Jira-parity management command summaries."""


def format_table(rows, columns=None):
    """Render a list of dict rows as an aligned text table (returns a list of lines)."""
    rows = list(rows)
    if not rows:
        return []
    columns = list(columns or rows[0].keys())
    cells = [[str(row.get(column, "")) for column in columns] for row in rows]
    widths = [max(len(column), *(len(line[index]) for line in cells)) for index, column in enumerate(columns)]

    def render(values):
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(values)).rstrip()

    lines = [render(columns), render(["-" * width for width in widths])]
    lines.extend(render(line) for line in cells)
    return lines


def totals_row(rows, label_column, numeric_columns, label="TOTAL"):
    """A totals row summing `numeric_columns` (non-numbers count as 0)."""
    total = {label_column: label}
    for column in numeric_columns:
        total[column] = sum(row.get(column, 0) for row in rows if isinstance(row.get(column, 0), int))
    return total
