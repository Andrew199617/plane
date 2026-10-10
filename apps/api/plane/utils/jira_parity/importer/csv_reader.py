# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira CSV export reader.

Jira repeats a header when a field has several values ("Sprint", "Watchers", "Labels", "Comment",
...) and some custom-field headers appear twice, so rows are read positionally and values are looked
up by header name (`JiraRow.get` = first non-empty value, `JiraRow.get_all` = every non-empty value).
"""

# Python imports
import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime

# Third party imports
import pytz

ISSUE_KEY_RE = re.compile(r"^([A-Z][A-Z0-9_]*)-(\d+)$")
# Index entry holding the ordered (stripped) header list; cannot clash with a CSV header.
_HEADERS_KEY = "\x00headers"

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
# 23/Aug/25 11:48 AM | 23/Aug/2025 11:48 | 27/Sep/24
_JIRA_DATETIME_RE = re.compile(
    r"^(?P<day>\d{1,2})/(?P<month>[A-Za-z]{3})/(?P<year>\d{2}|\d{4})"
    r"(?:\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?\s*(?P<ampm>[AaPp][Mm])?)?$"
)


class JiraCsvError(ValueError):
    """Raised for unreadable CSV content (bad dates, missing columns, ...)."""


@dataclass
class JiraCsv:
    path: str
    headers: list
    rows: list = field(default_factory=list)


class JiraRow:
    __slots__ = ("_values", "_index", "line", "source")

    def __init__(self, values, index, line, source=""):
        self._values = values
        self._index = index
        self.line = line
        self.source = source

    def _columns(self, name):
        columns = self._index.get(name)
        if columns is None:
            columns = self._index.get(name.lower().strip(), [])
        return columns

    def get(self, name, default=""):
        """First non-empty value of the column(s) called `name` (stripped)."""
        for column in self._columns(name):
            if column < len(self._values):
                value = self._values[column].strip()
                if value:
                    return value
        return default

    def get_raw(self, name, default=""):
        """Like get() but keeps surrounding whitespace (descriptions keep their indentation)."""
        for column in self._columns(name):
            if column < len(self._values) and self._values[column].strip():
                return self._values[column]
        return default

    def get_all(self, name):
        """Every non-empty value of the repeated column `name`, in file order."""
        values = []
        for column in self._columns(name):
            if column < len(self._values):
                value = self._values[column].strip()
                if value:
                    values.append(value)
        return values

    def items_with_prefix(self, prefix):
        """[(header, value)] for every non-empty column whose header starts with `prefix`."""
        result = []
        for column, header in enumerate(self._index.get(_HEADERS_KEY, [])):
            if header.startswith(prefix) and column < len(self._values) and self._values[column].strip():
                result.append((header, self._values[column].strip()))
        return result

    # Convenience accessors -------------------------------------------------

    @property
    def key(self):
        return self.get("Issue key")

    @property
    def issue_id(self):
        return self.get("Issue id")

    @property
    def project_key(self):
        match = ISSUE_KEY_RE.match(self.key)
        if match:
            return match.group(1)
        return self.get("Project key").upper()

    @property
    def number(self):
        match = ISSUE_KEY_RE.match(self.key)
        return int(match.group(2)) if match else None

    def __repr__(self):
        return f"<JiraRow {self.key or '?'} line {self.line}>"


def _build_index(headers):
    index = {_HEADERS_KEY: [header.strip() for header in headers]}
    for position, header in enumerate(headers):
        name = header.strip()
        index.setdefault(name, []).append(position)
        lowered = name.lower()
        if lowered != name:
            index.setdefault(lowered, []).append(position)
    return index


def read_jira_csv(path):
    """Read a Jira CSV export (utf-8, optional BOM). Returns a JiraCsv with JiraRow rows."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            headers = next(reader)
        except StopIteration as e:
            raise JiraCsvError(f"{path}: empty file") from e
        index = _build_index(headers)
        for required in ("Issue key", "Summary"):
            if required not in index:
                raise JiraCsvError(f"{path}: missing required column '{required}'")
        rows = []
        for values in reader:
            if not any(value.strip() for value in values):
                continue
            rows.append(JiraRow(values, index, reader.line_num, source=str(path)))
    return JiraCsv(path=str(path), headers=headers, rows=rows)


def parse_jira_datetime(value, tz_name="UTC"):
    """Parse a Jira export timestamp ('23/Aug/25 11:48 AM', also ISO) as an aware datetime.

    Jira exports timestamps in the exporting user's profile timezone (`tz_name`). English month
    abbreviations are mapped explicitly so parsing does not depend on the process locale.
    Returns None for blank values; raises JiraCsvError when the value cannot be parsed.
    """
    if value is None or not str(value).strip():
        return None
    value = str(value).strip()
    tz = pytz.timezone(tz_name or "UTC")
    match = _JIRA_DATETIME_RE.match(value)
    if match:
        month = _MONTHS.get(match.group("month").lower())
        if month is None:
            raise JiraCsvError(f"Unknown month in Jira date '{value}'")
        year = int(match.group("year"))
        if year < 100:
            year += 2000
        hour = int(match.group("hour") or 0)
        minute = int(match.group("minute") or 0)
        second = int(match.group("second") or 0)
        ampm = (match.group("ampm") or "").lower()
        if ampm:
            if not 1 <= hour <= 12:
                raise JiraCsvError(f"Invalid hour in Jira date '{value}'")
            hour = hour % 12 + (12 if ampm == "pm" else 0)
        try:
            naive = datetime(year, month, int(match.group("day")), hour, minute, second)
        except ValueError as e:
            raise JiraCsvError(f"Invalid Jira date '{value}': {e}") from e
        return tz.localize(naive)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise JiraCsvError(f"Unrecognised Jira date '{value}'") from e
    if parsed.tzinfo is None:
        parsed = tz.localize(parsed)
    return parsed


def parse_jira_date(value):
    """Parse a Jira date or timestamp ('27/Sep/24 12:00 AM', '2024-09-27') into a date (or None)."""
    if value is None or not str(value).strip():
        return None
    value = str(value).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return date.fromisoformat(value)
    parsed = parse_jira_datetime(value, "UTC")
    return parsed.date() if parsed else None


def parse_seconds_as_minutes(value):
    """Jira time tracking value in seconds -> whole minutes (None for blank; 0 stays 0)."""
    if value is None or not str(value).strip():
        return None
    try:
        seconds = int(float(str(value).strip()))
    except ValueError as e:
        raise JiraCsvError(f"Invalid time tracking value '{value}'") from e
    return max(seconds, 0) // 60
