# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity importer: CSV reader, date parsing and pure value mappings."""

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
import pytz

from plane.utils.jira_parity.importer.config import (
    CONFIG_ENV_VAR,
    TIMEZONE_ENV_VAR,
    JiraParityConfig,
    JiraParityConfigError,
    load_config,
    parse_config,
    resolve_timezone,
)
from plane.utils.jira_parity.importer.csv_reader import (
    JiraCsvError,
    parse_jira_date,
    parse_jira_datetime,
    parse_seconds_as_minutes,
    read_jira_csv,
)
from plane.utils.jira_parity.importer.mapping import (
    map_priority,
    normalize_issue_type,
    normalize_status,
    parse_link_header,
    parse_sprint_name,
    plan_sprint_dates,
    rank_positions,
    relation_for_link,
    status_category_group,
)
from plane.utils.jira_parity.importer.report import format_table

HEADERS = [
    "Summary",
    "Issue key",
    "Issue id",
    "Sprint",
    "Sprint",
    "Watchers",
    "Watchers",
    "Description",
    "Σ Original Estimate",
    "Outward issue link (Blocks)",
]


def _write(path, rows, headers=HEADERS):
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    return path


@pytest.mark.unit
class TestReader:
    def test_duplicate_headers_bom_and_multiline(self, tmp_path):
        path = _write(
            tmp_path / "jira.csv",
            [
                [
                    "First",
                    "ABC-1",
                    "10001",
                    "Sprint 1",
                    "Sprint 2",
                    "Jane Doe",
                    "",
                    "line 1\n   - nested",
                    "3600",
                    "ABC-2",
                ],
                ["", "", "", "", "", "", "", "", "", ""],
            ],
        )
        export = read_jira_csv(path)
        assert len(export.rows) == 1  # blank rows are skipped
        row = export.rows[0]
        assert row.key == "ABC-1" and row.project_key == "ABC" and row.number == 1
        assert row.issue_id == "10001"
        assert row.get("Sprint") == "Sprint 1"
        assert row.get_all("Sprint") == ["Sprint 1", "Sprint 2"]
        assert row.get_all("Watchers") == ["Jane Doe"]
        assert row.get("Σ Original Estimate") == "3600"
        assert row.get_raw("Description") == "line 1\n   - nested"
        assert row.items_with_prefix("Outward issue link") == [("Outward issue link (Blocks)", "ABC-2")]
        assert row.get("Missing column", "x") == "x"

    def test_missing_required_column(self, tmp_path):
        path = _write(tmp_path / "bad.csv", [["x"]], headers=["Summary"])
        with pytest.raises(JiraCsvError):
            read_jira_csv(path)

    def test_empty_file(self, tmp_path):
        path = tmp_path / "empty.csv"
        path.write_text("", encoding="utf-8")
        with pytest.raises(JiraCsvError):
            read_jira_csv(path)


@pytest.mark.unit
class TestDates:
    def test_jira_datetime_in_export_timezone(self):
        value = parse_jira_datetime("01/Nov/24 12:59 PM", "America/New_York")
        assert value == pytz.timezone("America/New_York").localize(datetime(2024, 11, 1, 12, 59))
        assert value.utcoffset() == timedelta(hours=-4)

    def test_midnight_and_noon(self):
        assert parse_jira_datetime("23/Aug/25 12:05 AM").hour == 0
        assert parse_jira_datetime("23/Aug/25 12:05 PM").hour == 12
        assert parse_jira_datetime("23/Aug/2025 9:48 pm").hour == 21

    def test_iso_fallback_and_blank(self):
        assert parse_jira_datetime("2025-01-02T03:04:05Z") == datetime(2025, 1, 2, 3, 4, 5, tzinfo=pytz.utc)
        assert parse_jira_datetime("") is None
        assert parse_jira_datetime(None) is None

    @pytest.mark.parametrize("value", ["32/Jan/25 1:00 PM", "01/Foo/25", "yesterday", "01/Jan/25 13:00 PM"])
    def test_invalid(self, value):
        with pytest.raises(JiraCsvError):
            parse_jira_datetime(value)

    def test_date(self):
        assert parse_jira_date("27/Sep/24 12:00 AM") == date(2024, 9, 27)
        assert parse_jira_date("2024-09-27") == date(2024, 9, 27)
        assert parse_jira_date("") is None

    def test_seconds_to_minutes(self):
        assert parse_seconds_as_minutes("14400") == 240
        assert parse_seconds_as_minutes("0") == 0
        assert parse_seconds_as_minutes("") is None
        with pytest.raises(JiraCsvError):
            parse_seconds_as_minutes("2h")


@pytest.mark.unit
class TestMapping:
    VALID = {"highest", "high", "medium", "low", "lowest"}

    @pytest.mark.parametrize(
        "jira,expected",
        [
            ("Highest", "highest"),
            ("High", "high"),
            ("Medium", "medium"),
            ("Low", "low"),
            ("Lowest", "lowest"),
            ("", "medium"),
            ("Blocker", "highest"),
            ("Trivial", "lowest"),
            ("Weird", "medium"),
        ],
    )
    def test_priority(self, jira, expected):
        assert map_priority(jira, self.VALID) == expected

    def test_status_and_type_normalisation(self):
        assert normalize_status("To Do") == "to do"
        assert normalize_status("TODO") == "to do"
        assert normalize_status("Won't Fix") == "won't fix"
        assert normalize_status("Closed") == "done"
        assert status_category_group("In Progress") == "started"
        assert status_category_group("Done") == "completed"
        assert normalize_issue_type("Subtask") == "sub-task"
        assert normalize_issue_type("Sub-task") == "sub-task"
        assert normalize_issue_type("Epic") == "epic"

    def test_link_headers_and_relation_direction(self):
        assert parse_link_header("Outward issue link (Blocks)") == ("outward", "blocks")
        assert parse_link_header("Inward issue link (Relates)") == ("inward", "relates")
        assert parse_link_header("Sprint") is None
        # ABC-15 "Outward (Blocks)" ABC-5 => ABC-5 is blocked by ABC-15
        assert relation_for_link("outward", "blocks", "ABC-15", "ABC-5") == ("ABC-5", "ABC-15", "blocked_by")
        # ABC-5 "Inward (Blocks)" ABC-15 => the same relation
        assert relation_for_link("inward", "blocks", "ABC-5", "ABC-15") == ("ABC-5", "ABC-15", "blocked_by")
        assert relation_for_link("outward", "relates", "XYZ-6", "XYZ-5")[2] == "relates_to"
        assert relation_for_link("outward", "duplicate", "A-1", "A-2")[2] == "duplicate"

    def test_sprint_names(self):
        assert parse_sprint_name("ABC Sprint 3") == ("ABC Sprint", 3)
        assert parse_sprint_name("Sprint 1") == ("Sprint", 1)
        assert parse_sprint_name("Hardening") == ("Hardening", None)

    def test_sprint_plan_back_to_back_from_today(self):
        today = date(2026, 10, 7)
        plan = plan_sprint_dates(["Sprint 2", "Sprint 1", "Sprint 3", "ABC Sprint 2", "ABC Sprint 1", "Spike"], today)
        assert plan["Sprint 1"] == (today, today + timedelta(days=13))
        assert plan["Sprint 2"] == (today + timedelta(days=14), today + timedelta(days=27))
        assert plan["Sprint 3"][0] == today + timedelta(days=28)
        assert plan["ABC Sprint 1"] == plan["Sprint 1"]
        assert plan["ABC Sprint 2"] == plan["Sprint 2"]
        assert plan["Spike"] == (today, today + timedelta(days=13))

    def test_rank_positions(self):
        assert rank_positions(["0|i0002:", "0|i0001:", "", "0|i0003:"]) == [1, 0, 3, 2]

    def test_format_table(self):
        lines = format_table([{"A": "x", "Bee": 10}, {"A": "long", "Bee": 2}])
        assert lines[0] == "A     Bee"
        assert lines[2] == "x     10"
        assert len(lines) == 4


EXAMPLE_CONFIG = Path(__file__).resolve().parents[3] / "utils" / "jira_parity" / "importer" / "jira_parity.example.json"


@pytest.mark.unit
class TestConfig:
    def test_default_is_empty(self, monkeypatch):
        monkeypatch.delenv(CONFIG_ENV_VAR, raising=False)
        config = load_config()
        assert config.categories == () and config.projects == {} and config.skip_projects == ()
        assert config.source == "" and config.project_category_map == {}
        assert config.rename("Draft plan") == "Draft plan"

    def test_example_file_loads(self):
        config = load_config(str(EXAMPLE_CONFIG))
        assert [spec.name for spec in config.categories] == ["Product", "Platform"]
        assert config.projects["ABC"].name == "Example App"
        assert config.project_category_map == {"ABC": "Product", "XYZ": "Platform"}
        assert config.skip_projects == ("IDEA",)

    def test_env_var_names_the_file(self, monkeypatch):
        monkeypatch.setenv(CONFIG_ENV_VAR, str(EXAMPLE_CONFIG))
        assert load_config().source == str(EXAMPLE_CONFIG)
        assert load_config(use_env=False).source == ""

    def test_parse_projects_categories_and_emoji(self):
        config = parse_config(
            {
                "categories": ["Alpha", {"name": "Beta", "description": "Second.", "emoji": 128640}],
                "projects": {"abc": {"name": "Example App", "category": "Gamma", "emoji": "127462-127464"}},
                "skip_projects": ["idea"],
            }
        )
        assert config.categories[1].logo_props == {"in_use": "emoji", "emoji": {"value": "128640"}}
        assert config.categories[0].logo_props == {}
        assert config.projects["ABC"].logo_props["emoji"]["value"] == "127462-127464"
        assert config.category_names() == ["Alpha", "Beta", "Gamma"]
        assert config.skip_projects == ("IDEA",)
        assert parse_config({"projects": {"ABC": {"emoji": "\u2699"}}}).projects["ABC"].emoji == "9881"

    def test_name_replacements_are_whole_words(self):
        config = JiraParityConfig(name_replacements={"Draft": "Final"})
        assert config.rename("Draft project containing Drafts") == "Final project containing Drafts"
        assert config.rename(None) == ""

    def test_invalid_config(self, tmp_path):
        with pytest.raises(JiraParityConfigError, match="unknown key"):
            parse_config({"project": {}})
        with pytest.raises(JiraParityConfigError, match="name is required"):
            parse_config({"categories": [{"description": "x"}]})
        with pytest.raises(JiraParityConfigError, match="not found"):
            load_config(str(tmp_path / "missing.json"))
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(JiraParityConfigError, match="Could not read"):
            load_config(str(bad))
        listed = tmp_path / "list.json"
        listed.write_text(json.dumps([1, 2]), encoding="utf-8")
        with pytest.raises(JiraParityConfigError, match="JSON object"):
            load_config(str(listed))

    def test_resolve_timezone(self, monkeypatch):
        class _User:
            user_timezone = "Asia/Tokyo"

        monkeypatch.delenv(TIMEZONE_ENV_VAR, raising=False)
        config = JiraParityConfig(timezone="Europe/Berlin")
        assert resolve_timezone("America/New_York", config, _User()) == "America/New_York"
        assert resolve_timezone("", config, _User()) == "Europe/Berlin"
        assert resolve_timezone("", JiraParityConfig(), _User()) == "Asia/Tokyo"
        assert resolve_timezone("", JiraParityConfig(), None) == "UTC"
        monkeypatch.setenv(TIMEZONE_ENV_VAR, "Australia/Sydney")
        assert resolve_timezone("", config, _User()) == "Australia/Sydney"
