# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity priorities: constants, normalization, filter remapping and the shared lists that use them."""

import ast
import importlib

import pytest
from rest_framework import serializers

from plane.db.models import DraftIssue, Issue, IssueVersion
from plane.utils import priority as priority_utils
from plane.utils.priority import (
    DEFAULT_PRIORITY,
    LEGACY_PRIORITY_MAP,
    PRIORITY_ASCENDING,
    PRIORITY_CHOICES,
    PRIORITY_ORDER,
    PRIORITY_VALUES,
    normalize_priority,
    remap_priority_filter_tree,
    remap_priority_tokens,
    resolve_request_priority,
)
from plane.utils.priority_field import PriorityField

JIRA_KEYS = ["highest", "high", "medium", "low", "lowest"]


@pytest.mark.unit
class TestPriorityConstants:
    def test_keys_and_default(self):
        assert PRIORITY_VALUES == JIRA_KEYS
        assert PRIORITY_ORDER == JIRA_KEYS
        assert PRIORITY_ASCENDING == list(reversed(JIRA_KEYS))
        assert DEFAULT_PRIORITY == "medium"
        assert dict(PRIORITY_CHOICES) == {
            "highest": "Highest",
            "high": "High",
            "medium": "Medium",
            "low": "Low",
            "lowest": "Lowest",
        }
        assert LEGACY_PRIORITY_MAP == {"urgent": "highest", "none": "medium"}

    def test_models_use_single_source(self):
        from plane.db.models import issue as issue_models

        assert issue_models.PRIORITY_CHOICES is PRIORITY_CHOICES
        assert issue_models.DEFAULT_PRIORITY == DEFAULT_PRIORITY
        for model in (Issue, DraftIssue, IssueVersion):
            field = model._meta.get_field("priority")
            assert [key for key, _ in field.choices] == JIRA_KEYS
            assert field.default == DEFAULT_PRIORITY

    def test_migration_maps_match_utils(self):
        migration = importlib.import_module("plane.db.migrations.0124_jp_priorities")
        assert migration.FORWARD_MAP == LEGACY_PRIORITY_MAP
        assert [key for key, _ in migration.PRIORITY_CHOICES] == JIRA_KEYS

    def test_module_has_no_model_imports(self):
        # plane.db.models.issue imports this module, so it must not import models itself.
        source = importlib.util.find_spec("plane.utils.priority").origin
        with open(source, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        imported = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        assert imported == []
        assert priority_utils.PRIORITY_HIGHEST == "highest"


@pytest.mark.unit
class TestNormalizePriority:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("highest", "highest"),
            ("Highest", "highest"),
            (" HIGH ", "high"),
            ("Medium", "medium"),
            ("low", "low"),
            ("Lowest", "lowest"),
            ("urgent", "highest"),
            ("Urgent", "highest"),
            ("none", "medium"),
            ("None", "medium"),
        ],
    )
    def test_known_values(self, value, expected):
        assert normalize_priority(value) == expected

    @pytest.mark.parametrize("value", ["bogus", "critical", "", "   ", None, 3])
    def test_unknown_values_use_default(self, value):
        assert normalize_priority(value) is None
        assert normalize_priority(value, "medium") == "medium"

    def test_resolve_request_priority(self):
        assert resolve_request_priority(None) == "medium"
        assert resolve_request_priority("") == "medium"
        assert resolve_request_priority("  ") == "medium"
        assert resolve_request_priority("Lowest") == "lowest"
        assert resolve_request_priority("urgent") == "highest"
        assert resolve_request_priority("none") == "medium"
        assert resolve_request_priority("bogus") is None
        assert resolve_request_priority(None, default="low") == "low"


@pytest.mark.unit
class TestRemapPriority:
    def test_tokens_string_and_list(self):
        assert remap_priority_tokens("urgent,high") == "highest,high"
        assert remap_priority_tokens("none,medium") == "medium"
        assert remap_priority_tokens(["none", "urgent"]) == ["medium", "highest"]
        assert remap_priority_tokens(["highest", "lowest"]) == ["highest", "lowest"]
        assert remap_priority_tokens(None) is None

    def test_rich_filter_tree(self):
        tree = {"and": [{"priority__in": "urgent,high"}, {"state_id__in": "x"}]}
        assert remap_priority_filter_tree(tree) == {"and": [{"priority__in": "highest,high"}, {"state_id__in": "x"}]}

    def test_legacy_filter_and_nested_groups(self):
        tree = {
            "priority": ["none", "urgent"],
            "or": [{"not": {"priority__exact": "urgent"}}],
            "display_filters": {"group_by": "priority"},
        }
        out = remap_priority_filter_tree(tree)
        assert out["priority"] == ["medium", "highest"]
        assert out["or"][0]["not"]["priority__exact"] == "highest"
        assert out["display_filters"] == {"group_by": "priority"}
        # input is not mutated
        assert tree["priority"] == ["none", "urgent"]


@pytest.mark.unit
class TestPriorityField:
    def test_accepts_canonical_case_and_legacy(self):
        field = PriorityField()
        assert field.to_internal_value("lowest") == "lowest"
        assert field.to_internal_value("Highest") == "highest"
        assert field.to_internal_value("urgent") == "highest"
        assert field.to_internal_value("none") == "medium"

    def test_rejects_unknown(self):
        field = PriorityField()
        with pytest.raises(serializers.ValidationError):
            field.to_internal_value("bogus")
        with pytest.raises(serializers.ValidationError):
            field.to_internal_value(5)

    def test_serializers_declare_priority_field(self):
        from plane.api.serializers.intake import IssueDataSerializer
        from plane.api.serializers.issue import IssueSerializer
        from plane.app.serializers.draft import DraftIssueCreateSerializer
        from plane.app.serializers.issue import IssueCreateSerializer

        for serializer_class in (IssueSerializer, IssueCreateSerializer, DraftIssueCreateSerializer):
            field = serializer_class().fields["priority"]
            assert isinstance(field, PriorityField)
            assert field.required is False
        intake_field = IssueDataSerializer().fields["priority"]
        assert isinstance(intake_field, PriorityField)
        assert intake_field.default == "medium"


@pytest.mark.unit
class TestSharedPriorityLists:
    def test_order_queryset_uses_jira_order(self):
        from plane.utils.order_queryset import PRIORITY_ORDER as ORDER

        assert ORDER == JIRA_KEYS

    def test_group_values(self):
        from plane.space.utils.grouper import issue_group_values as space_group_values
        from plane.utils.grouper import issue_group_values

        assert sorted(issue_group_values("priority", "any-slug")) == sorted(JIRA_KEYS)
        assert sorted(space_group_values("priority", "any-slug")) == sorted(JIRA_KEYS)

    def test_analytics_sort(self):
        from plane.utils.analytics_plot import sort_data

        data = {key: [] for key in ["medium", "highest", "lowest", "high", "low"]}
        assert list(sort_data(data, "priority")) == ["lowest", "low", "medium", "high", "highest"]

    def test_chart_rows_sorted_and_labelled(self):
        from plane.utils.priority import sort_priority_chart_rows

        rows = [
            {"key": "low", "name": "low", "count": 1},
            {"key": "None", "name": "None", "count": 9},
            {"key": "highest", "name": "highest", "count": 2, "extra": 3},
            {"key": "medium", "name": "medium", "count": 4},
        ]
        out = sort_priority_chart_rows(rows)
        assert [row["key"] for row in out] == ["highest", "medium", "low", "None"]
        assert [row["name"] for row in out] == ["Highest", "Medium", "Low", "None"]
        assert out[0]["extra"] == 3
        # input rows are not mutated
        assert rows[0]["name"] == "low"

    def test_legacy_filter_converter_accepts_new_and_legacy_keys(self):
        from plane.utils.filters.converters import LegacyToRichFiltersConverter

        converter = LegacyToRichFiltersConverter()
        assert set(converter.VALID_CHOICES["priority"]) >= set(JIRA_KEYS) | {"urgent", "none"}
        rich = converter.convert({"priority": ["highest", "lowest", "bogus"]})
        assert rich == {"priority__in": "highest,lowest"}

    def test_issue_filters_map_legacy_tokens(self):
        from plane.utils.issue_filters import filter_priority

        assert filter_priority({"priority": "urgent,high"}, {}, "GET") == {"priority__in": ["highest", "high"]}
        assert filter_priority({"priority": "lowest"}, {}, "GET") == {"priority__in": ["lowest"]}
        assert filter_priority({"priority": ["none"]}, {}, "POST") == {"priority__in": ["medium"]}
