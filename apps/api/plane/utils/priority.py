# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity work item priorities: the single source of truth for priority keys.

Keys (most -> least important): ``highest``, ``high``, ``medium`` (default), ``low``, ``lowest``.
Plane's legacy keys are accepted on input and mapped: ``urgent`` -> ``highest``, ``none`` -> ``medium``.

This module is imported by ``plane.db.models.issue`` so it must stay free of model imports.
The DRF field lives in ``plane.utils.priority_field`` to keep this module import-light.
"""

PRIORITY_HIGHEST = "highest"
PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"
PRIORITY_LOWEST = "lowest"

PRIORITY_CHOICES = (
    (PRIORITY_HIGHEST, "Highest"),
    (PRIORITY_HIGH, "High"),
    (PRIORITY_MEDIUM, "Medium"),
    (PRIORITY_LOW, "Low"),
    (PRIORITY_LOWEST, "Lowest"),
)

# Most -> least important. Index 0 sorts first for "-priority".
PRIORITY_VALUES = [key for key, _ in PRIORITY_CHOICES]
PRIORITY_ORDER = PRIORITY_VALUES
# Least -> most important (legacy analytics sort order).
PRIORITY_ASCENDING = list(reversed(PRIORITY_VALUES))

DEFAULT_PRIORITY = PRIORITY_MEDIUM

# Plane's pre-Jira keys that external clients (MCP server, mobile, old scripts, saved URLs) may still send.
LEGACY_PRIORITY_MAP = {"urgent": PRIORITY_HIGHEST, "none": PRIORITY_MEDIUM}

PRIORITY_FILTER_KEYS = frozenset({"priority", "priority__in", "priority__exact"})


def normalize_priority(value, default=None):
    """Return the canonical priority key for ``value`` or ``default`` when it is empty/unknown.

    Accepts any case and surrounding whitespace (Jira CSV exports use "Highest"), and maps the
    legacy Plane keys ("urgent", "none").
    """
    if value is None:
        return default
    key = str(value).strip().lower()
    if not key:
        return default
    key = LEGACY_PRIORITY_MAP.get(key, key)
    return key if key in PRIORITY_VALUES else default


def resolve_request_priority(value, default=DEFAULT_PRIORITY):
    """Priority for a create request: missing/blank -> ``default``, known keys normalized, invalid -> None."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    return normalize_priority(value)


PRIORITY_LABELS = dict(PRIORITY_CHOICES)


def sort_priority_chart_rows(rows):
    """Order analytics rows keyed by priority most -> least important and label them ("Highest")."""
    position = {key: index for index, key in enumerate(PRIORITY_VALUES)}
    ordered = sorted(rows, key=lambda row: position.get(row.get("key"), len(position)))
    return [
        {**row, "name": PRIORITY_LABELS[row["key"]]} if row.get("key") in PRIORITY_LABELS else row for row in ordered
    ]


def _dedupe(values):
    seen = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def remap_priority_tokens(value):
    """Map legacy keys inside a comma-separated string or a list; keeps the input type and order."""
    if isinstance(value, str):
        return ",".join(_dedupe([LEGACY_PRIORITY_MAP.get(part, part) for part in value.split(",")]))
    if isinstance(value, (list, tuple)):
        return _dedupe([LEGACY_PRIORITY_MAP.get(v, v) if isinstance(v, str) else v for v in value])
    return value


def remap_priority_filter_tree(node):
    """Return a copy of a (legacy or rich) filter tree with legacy priority keys remapped.

    Walks dicts and lists, including nested and/or/not groups; only values under the keys
    ``priority``, ``priority__in`` and ``priority__exact`` change.
    """
    if isinstance(node, dict):
        return {
            key: (remap_priority_tokens(value) if key in PRIORITY_FILTER_KEYS else remap_priority_filter_tree(value))
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [remap_priority_filter_tree(item) for item in node]
    return node
