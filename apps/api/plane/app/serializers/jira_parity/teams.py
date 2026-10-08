# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity teams serializers.

Add your classes here and list their names in __all__; the package __init__ re-exports __all__.
"""

# Third party imports
from rest_framework import serializers

# Module imports
from plane.app.serializers.base import BaseSerializer
from plane.db.models import Team
from plane.db.models.team import TeamMember
from plane.utils.teams import allowed_project_roles

__all__ = ["TeamSerializer", "TeamMemberSerializer"]


class TeamSerializer(BaseSerializer):
    """Team JSON: {id, name, description, logo_props, default_project_role, auto_join, member_ids,
    member_count, project_ids, project_count, workspace, created_at, updated_at}.

    member_ids / project_ids are read from attributes the views attach to the instances
    (plane.app.views.jira_parity.teams.attach_team_relations); they are written through the
    dedicated member/project endpoints (or the create/patch views), never by this serializer.
    """

    member_ids = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    project_ids = serializers.SerializerMethodField()
    project_count = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = [
            "id",
            "workspace",
            "name",
            "description",
            "logo_props",
            "default_project_role",
            "auto_join",
            "member_ids",
            "member_count",
            "project_ids",
            "project_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["workspace", "created_at", "updated_at"]

    def get_member_ids(self, obj):
        return [str(member_id) for member_id in getattr(obj, "member_ids", [])]

    def get_member_count(self, obj):
        return len(getattr(obj, "member_ids", []))

    def get_project_ids(self, obj):
        return [str(project_id) for project_id in getattr(obj, "project_ids", [])]

    def get_project_count(self, obj):
        return len(getattr(obj, "project_ids", []))

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Team name is required.")
        return value

    def validate_description(self, value):
        return (value or "").strip()

    def validate_default_project_role(self, value):
        if value not in allowed_project_roles():
            raise serializers.ValidationError(
                f"Invalid role. Allowed values: {sorted(allowed_project_roles(), reverse=True)}."
            )
        return value

    def validate_logo_props(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("logo_props must be an object.")
        return value


class TeamMemberSerializer(BaseSerializer):
    class Meta:
        model = TeamMember
        fields = ["id", "team", "member", "workspace", "created_at"]
        read_only_fields = fields
