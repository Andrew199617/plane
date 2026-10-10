# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity project_categories serializers.

Add your classes here and list their names in __all__; the package __init__ re-exports __all__.

Contract: {id, name, description, sort_order, logo_props, project_ids}. `project_ids` is writable
(replace semantics over the category's non-archived projects) and read from the
`annotate_project_ids` queryset annotation.
"""

# Third party imports
from rest_framework import serializers

# Module imports
from plane.app.serializers.base import BaseSerializer
from plane.db.models import Project, ProjectCategory
from plane.utils.project_categories import set_category_projects

__all__ = ["ProjectCategorySerializer"]


class ProjectCategorySerializer(BaseSerializer):
    project_ids = serializers.ListField(child=serializers.UUIDField(), required=False)

    class Meta:
        model = ProjectCategory
        fields = ["id", "name", "description", "sort_order", "logo_props", "project_ids"]
        read_only_fields = ["id"]

    def _workspace_id(self):
        return self.context["workspace_id"]

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Category name is required.")
        duplicates = ProjectCategory.objects.filter(workspace_id=self._workspace_id(), name__iexact=name)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("A project category with this name already exists.")
        return name

    def validate_logo_props(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("logo_props must be an object.")
        return value

    def validate_project_ids(self, value):
        project_ids = list(dict.fromkeys(str(project_id) for project_id in value))
        found = set(
            str(project_id)
            for project_id in Project.objects.filter(workspace_id=self._workspace_id(), id__in=project_ids).values_list(
                "id", flat=True
            )
        )
        missing = [project_id for project_id in project_ids if project_id not in found]
        if missing:
            raise serializers.ValidationError(f"Projects not found in this workspace: {', '.join(missing)}")
        return project_ids

    def create(self, validated_data):
        project_ids = validated_data.pop("project_ids", None)
        category = ProjectCategory(workspace_id=self._workspace_id(), **validated_data)
        category.save()
        if project_ids is not None:
            set_category_projects(category, project_ids)
        return category

    def update(self, instance, validated_data):
        project_ids = validated_data.pop("project_ids", None)
        instance = super().update(instance, validated_data)
        if project_ids is not None:
            set_category_projects(instance, project_ids)
        return instance
