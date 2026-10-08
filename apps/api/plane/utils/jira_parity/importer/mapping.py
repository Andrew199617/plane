# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Pure Jira -> Plane value mappings (priorities, statuses, types, links, sprints)."""

# Python imports
import re
from datetime import timedelta

SPRINT_LENGTH_DAYS = 14

_PRIORITY_ALIASES = {
    "blocker": "highest",
    "critical": "highest",
    "urgent": "highest",
    "major": "high",
    "normal": "medium",
    "minor": "low",
    "trivial": "lowest",
    "none": "medium",
}

_STATUS_ALIASES = {
    "todo": "to do",
    "to-do": "to do",
    "open": "to do",
    "backlog": "to do",
    "selected for development": "to do",
    "reopened": "to do",
    "in development": "in progress",
    "doing": "in progress",
    "code review": "in review",
    "review": "in review",
    "in qa": "in review",
    "closed": "done",
    "resolved": "done",
    "complete": "done",
    "completed": "done",
    "won't do": "won't fix",
    "wont fix": "won't fix",
    "won’t fix": "won't fix",
    "cancelled": "won't fix",
    "canceled": "won't fix",
    "declined": "won't fix",
}

# Jira status category -> Plane state group (first state of that group is used).
_STATUS_CATEGORY_GROUPS = {
    "to do": "unstarted",
    "new": "unstarted",
    "in progress": "started",
    "indeterminate": "started",
    "done": "completed",
    "complete": "completed",
}

_ISSUE_TYPE_ALIASES = {
    "subtask": "sub-task",
    "sub task": "sub-task",
    "sub-task": "sub-task",
    "user story": "story",
    "defect": "bug",
}

# Jira link type name (inside "Inward/Outward issue link (X)") -> Plane relation type.
LINK_TYPE_MAP = {
    "blocks": "blocked_by",
    "relates": "relates_to",
    "duplicate": "duplicate",
    "cloners": "relates_to",
}
_LINK_HEADER_RE = re.compile(r"^(Inward|Outward) issue link \((.+)\)$")

_SPRINT_RE = re.compile(r"^(?P<series>.*?)\s*(?P<number>\d+)\s*$")


def map_priority(value, valid_keys, default="medium"):
    """Jira priority name -> Plane priority key (Highest/High/Medium/Low/Lowest map 1:1)."""
    key = (value or "").strip().lower()
    if not key:
        return default
    if key in valid_keys:
        return key
    alias = _PRIORITY_ALIASES.get(key)
    if alias in valid_keys:
        return alias
    return default


def normalize_status(value):
    key = re.sub(r"\s+", " ", (value or "").strip().lower())
    return _STATUS_ALIASES.get(key, key)


def status_category_group(value):
    return _STATUS_CATEGORY_GROUPS.get((value or "").strip().lower())


def normalize_issue_type(value):
    key = re.sub(r"\s+", " ", (value or "").strip().lower())
    return _ISSUE_TYPE_ALIASES.get(key, key)


def parse_link_header(header):
    """'Outward issue link (Blocks)' -> ('outward', 'blocks'); None for other headers."""
    match = _LINK_HEADER_RE.match(header.strip())
    if not match:
        return None
    return match.group(1).lower(), match.group(2).strip().lower()


def relation_for_link(direction, link_name, row_key, other_key):
    """Plane IssueRelation (issue_key, related_issue_key, relation_type) for one Jira link cell.

    Jira "Blocks": outward on A with value B means "A blocks B"  -> row(issue=B, related=A, blocked_by)
                   inward  on A with value B means "A is blocked by B" -> row(issue=A, related=B, blocked_by)
    Symmetric types (relates/duplicate/cloners/unknown) -> (A, B) sorted later by the caller.
    """
    relation_type = LINK_TYPE_MAP.get(link_name, "relates_to")
    if relation_type == "blocked_by":
        if direction == "outward":
            return other_key, row_key, relation_type
        return row_key, other_key, relation_type
    return row_key, other_key, relation_type


def parse_sprint_name(name):
    """'ABC Sprint 3' -> ('ABC Sprint', 3); names without a trailing number -> (name, None)."""
    name = (name or "").strip()
    match = _SPRINT_RE.match(name)
    if not match or not match.group("series").strip():
        return name, None
    return match.group("series").strip(), int(match.group("number"))


def plan_sprint_dates(sprint_names, today):
    """Back-to-back 2-week blocks starting `today`, per sprint series.

    Sprints of one series ("Sprint 1", "Sprint 2", ...) are laid out by number: the lowest number in
    the series starts today, number n starts (n - lowest) * 14 days later. The same name always gets
    the same dates, whichever project uses it. Sprints without a number start today.

    Returns {sprint_name: (start_date, end_date)} with end = start + 13 days (inclusive).
    """
    series_numbers = {}
    for name in sprint_names:
        series, number = parse_sprint_name(name)
        if number is not None:
            series_numbers.setdefault(series, set()).add(number)

    plan = {}
    for name in sorted(set(n.strip() for n in sprint_names if n and n.strip())):
        series, number = parse_sprint_name(name)
        offset = 0 if number is None else number - min(series_numbers[series])
        start = today + timedelta(days=SPRINT_LENGTH_DAYS * offset)
        plan[name] = (start, start + timedelta(days=SPRINT_LENGTH_DAYS - 1))
    return plan


def rank_positions(ranks):
    """Jira LexoRank strings -> ascending position index (stable; blanks last)."""
    ordered = sorted(range(len(ranks)), key=lambda i: (not ranks[i], ranks[i] or "", i))
    positions = [0] * len(ranks)
    for position, index in enumerate(ordered):
        positions[index] = position
    return positions
