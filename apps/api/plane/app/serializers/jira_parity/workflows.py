# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity workflows serializers.

Rule JSON (packages/types/src/jira-parity/workflows.ts TStateTransitionRule):
{id, from_state_id (null = any state), to_state_id, roles: [int], exclude_epics}
"""

# Third party imports
from rest_framework import serializers

# Module imports
from plane.app.serializers.base import BaseSerializer
from plane.db.models import StateTransition
from plane.utils.workflow import RULE_ROLES

__all__ = ["StateTransitionSerializer", "StateTransitionRuleInputSerializer"]


class StateTransitionSerializer(BaseSerializer):
    from_state_id = serializers.UUIDField(read_only=True, allow_null=True)
    to_state_id = serializers.UUIDField(read_only=True)
    project_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = StateTransition
        fields = [
            "id",
            "project_id",
            "from_state_id",
            "to_state_id",
            "roles",
            "exclude_epics",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class StateTransitionRuleInputSerializer(serializers.Serializer):
    """One rule of a PUT (replace-all) body. Admins always bypass the workflow, so 20 is rejected."""

    id = serializers.UUIDField(required=False, allow_null=True)
    from_state_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    to_state_id = serializers.UUIDField()
    roles = serializers.ListField(child=serializers.IntegerField(), allow_empty=True)
    exclude_epics = serializers.BooleanField(required=False, default=False)

    def validate_roles(self, value):
        invalid = sorted({role for role in value if role not in RULE_ROLES})
        if invalid:
            raise serializers.ValidationError(
                f"Invalid roles {invalid}: rules can list Member (15), Agent (10) and Guest (5); "
                "admins can always change states."
            )
        return sorted(set(value), reverse=True)

    def validate(self, attrs):
        if attrs.get("from_state_id") and attrs["from_state_id"] == attrs["to_state_id"]:
            raise serializers.ValidationError("from_state_id and to_state_id must differ.")
        return attrs
