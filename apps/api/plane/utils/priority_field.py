# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""DRF serializer field for Jira-parity priorities (see ``plane.utils.priority``)."""

from rest_framework import serializers

from plane.utils.priority import PRIORITY_CHOICES, normalize_priority


class PriorityField(serializers.ChoiceField):
    """ChoiceField over the Jira priority keys that also accepts case variants and legacy keys.

    "Highest" -> "highest", "urgent" -> "highest", "none" -> "medium". Anything else is passed
    through unchanged so DRF raises its standard "is not a valid choice" error.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("choices", PRIORITY_CHOICES)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        mapped = normalize_priority(data) if isinstance(data, str) else None
        return super().to_internal_value(mapped if mapped else data)
