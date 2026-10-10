# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity work_item_types serializers.

Contract JSON: {id, name, description, logo_props, is_epic, is_sub_task, is_default, is_active, level,
workspace_id} (+ issue_count, created_at, updated_at). `level` is derived from the flags
(Epic 1, standard 0, Sub-task -1).
"""

# Third party imports
from rest_framework import serializers

# Module imports
from plane.app.serializers.base import BaseSerializer
from plane.db.models import Issue, IssueType
from plane.utils.work_item_types import type_level

__all__ = ["WorkItemTypeSerializer"]


class WorkItemTypeSerializer(BaseSerializer):
    workspace_id = serializers.UUIDField(read_only=True)
    issue_count = serializers.SerializerMethodField()
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    logo_props = serializers.JSONField(required=False)

    class Meta:
        model = IssueType
        fields = [
            "id",
            "name",
            "description",
            "logo_props",
            "is_epic",
            "is_sub_task",
            "is_default",
            "is_active",
            "level",
            "workspace_id",
            "issue_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "level", "workspace_id", "issue_count", "created_at", "updated_at"]

    def get_issue_count(self, obj):
        count = getattr(obj, "issue_count", None)
        if count is None and obj.pk:
            count = Issue.all_objects.filter(type_id=obj.pk, deleted_at__isnull=True).count()
        return count or 0

    def _workspace_id(self):
        if self.instance is not None:
            return self.instance.workspace_id
        return self.context.get("workspace_id")

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Name is required.")
        duplicates = IssueType.objects.filter(workspace_id=self._workspace_id(), name__iexact=name)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("A work item type with this name already exists.")
        return name

    def validate_description(self, value):
        return value or ""

    def validate_logo_props(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("logo_props must be an object.")
        return value

    def validate(self, attrs):
        instance = self.instance

        def current(field, default):
            if field in attrs:
                return attrs[field]
            return getattr(instance, field) if instance is not None else default

        if instance is None and "name" not in attrs:
            raise serializers.ValidationError({"name": "Name is required."})

        is_epic = current("is_epic", False)
        is_sub_task = current("is_sub_task", False)
        is_default = current("is_default", False)
        is_active = current("is_active", True)

        if is_epic and is_sub_task:
            raise serializers.ValidationError(
                {"is_sub_task": "A work item type cannot be both an Epic and a Sub-task."}
            )
        if is_default and (is_epic or is_sub_task):
            raise serializers.ValidationError(
                {"is_default": "An Epic or Sub-task type cannot be the default work item type."}
            )
        if instance is not None and instance.is_default and attrs.get("is_default") is False:
            raise serializers.ValidationError({"is_default": "Mark another work item type as the default instead."})
        if is_default and not is_active:
            raise serializers.ValidationError({"is_active": "The default work item type cannot be deactivated."})
        if (
            instance is not None
            and "is_sub_task" in attrs
            and attrs["is_sub_task"] != instance.is_sub_task
            and self.get_issue_count(instance) > 0
        ):
            raise serializers.ValidationError(
                {"is_sub_task": "The Sub-task flag cannot change while work items use this type."}
            )

        attrs["level"] = type_level(is_epic, is_sub_task)
        return attrs
