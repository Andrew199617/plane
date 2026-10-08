# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity project categories / master boards service.

Models: db.ProjectCategory (workspace, name, description, sort_order, logo_props,
external_source, external_id), Project.category (FK, SET_NULL, related_name "projects"),
IssueView.category (FK, CASCADE, related_name "board_views"; optional master-board view).
Helpers: category project scoping and group values for /project-categories/<id>/issues/
(including the cross-project "state__name" grouping), distinct cycles by name across the
category's projects, replacing a category's projects, apply_category_mapping(...) for the setup
command and a workspace-scoped `category_id` serializer field for the project serializers.
"""

# Python imports
import logging
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

# Django imports
from django.contrib.postgres.aggregates import ArrayAgg
from django.contrib.postgres.fields import ArrayField
from django.db import transaction
from django.db.models import F, Max, Min, Q, QuerySet, UUIDField, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

# Third party imports
from rest_framework import serializers

# Module imports
from plane.db.models import Cycle, IssueView, Label, Module, Project, ProjectCategory, ProjectMember, State

logger = logging.getLogger("plane.api")

# Group-by key of the master boards: one column per state *name* across the category's projects.
STATE_NAME_GROUP_BY = "state__name"
# Standard Jira-parity states, in board column order; any other state name follows them.
STANDARD_STATE_ORDER = ("To Do", "In Progress", "In Review", "Done", "Won't Fix")
STATE_GROUP_ORDER = ("backlog", "unstarted", "started", "completed", "cancelled")


def _normalize_state_name(name: str) -> str:
    return " ".join((name or "").replace("’", "'").split()).casefold()


_STANDARD_STATE_RANK = {_normalize_state_name(name): index for index, name in enumerate(STANDARD_STATE_ORDER)}


def category_group_by_allowlist() -> frozenset:
    """group_by / sub_group_by values accepted by the category issues endpoint.

    The shared issue allowlist (read at call time so other features' additions apply) plus
    "state__name" and "type_id" (work item type; group values come from the shared grouper).
    Every value reaches F()/values()/Window partition_by, so nothing else may pass.
    """
    from plane.utils.order_queryset import ISSUE_GROUP_BY_ALLOWLIST

    return frozenset(ISSUE_GROUP_BY_ALLOWLIST) | {STATE_NAME_GROUP_BY, "type_id"}


def order_state_names(rows: Iterable[Sequence[Any]]) -> List[str]:
    """Distinct state names from (name, group, sequence) rows, in board column order.

    Standard names first (To Do, In Progress, In Review, Done, Won't Fix; matched ignoring case,
    extra spaces and curly apostrophes), then the others by state group (backlog -> cancelled),
    lowest sequence and name. Names stay exact because issues are grouped by the exact value.
    """
    best: Dict[str, tuple] = {}
    for name, group, sequence in rows:
        if not name:
            continue
        key = (
            _STANDARD_STATE_RANK.get(_normalize_state_name(name), len(_STANDARD_STATE_RANK)),
            STATE_GROUP_ORDER.index(group) if group in STATE_GROUP_ORDER else len(STATE_GROUP_ORDER),
            sequence if sequence is not None else float("inf"),
            name.casefold(),
            name,
        )
        if name not in best or key < best[name]:
            best[name] = key
    return sorted(best, key=lambda state_name: best[state_name])


def state_name_group_values(
    *,
    slug: str,
    project_id: Optional[str] = None,
    project_ids: Optional[Iterable[Any]] = None,
    filters: Optional[Mapping[str, Any]] = None,
) -> List[str]:
    """Group values for group_by "state__name" (non-triage states of the scoped projects).

    Scope: `project_id`, else `project_ids`, else the legacy filters `project__in` /
    `project__category_id__in`, else every project of the workspace.
    """
    states = State.objects.filter(
        workspace__slug=slug,
        is_triage=False,
        project__deleted_at__isnull=True,
    )
    if project_id:
        states = states.filter(project_id=project_id)
    elif project_ids is not None:
        states = states.filter(project_id__in=list(project_ids))
    else:
        filters = filters or {}
        if filters.get("project__in"):
            states = states.filter(project_id__in=filters["project__in"])
        if filters.get("project__category_id__in"):
            states = states.filter(project__category_id__in=filters["project__category_id__in"])
    return order_state_names(states.values_list("name", "group", "sequence"))


def category_project_ids(category_id: Any, *, include_archived: bool = False) -> List[Any]:
    """Ids of the (non-deleted) projects of a category; archived projects only when asked."""
    projects = Project.objects.filter(category_id=category_id)
    if not include_archived:
        projects = projects.filter(archived_at__isnull=True)
    return list(projects.values_list("id", flat=True))


def member_project_ids(project_ids: Iterable[Any], user: Any) -> List[Any]:
    """The subset of `project_ids` where `user` is an active project member."""
    return list(
        ProjectMember.objects.filter(project_id__in=list(project_ids), member=user, is_active=True)
        .values_list("project_id", flat=True)
        .distinct()
    )


def annotate_project_ids(queryset: QuerySet) -> QuerySet:
    """Annotate ProjectCategory rows with `project_ids` (non-deleted, non-archived projects)."""
    return queryset.annotate(
        project_ids=Coalesce(
            ArrayAgg(
                "projects__id",
                distinct=True,
                # projects__id__isnull=False: the LEFT JOIN row of a category without projects
                filter=Q(
                    projects__id__isnull=False,
                    projects__deleted_at__isnull=True,
                    projects__archived_at__isnull=True,
                ),
            ),
            Value([], output_field=ArrayField(UUIDField())),
        )
    )


def category_group_values(
    *,
    field: str,
    slug: str,
    project_ids: Iterable[Any],
    filters: Optional[Mapping[str, Any]] = None,
    queryset: Optional[QuerySet] = None,
) -> List[Any]:
    """issue_group_values() for a category board: project-bound groups are limited to the
    category's projects (no empty columns for the rest of the workspace); every other field is
    delegated to the shared plane.utils.grouper.issue_group_values."""
    from plane.utils.grouper import issue_group_values

    project_ids = list(project_ids)
    if field == STATE_NAME_GROUP_BY:
        return state_name_group_values(slug=slug, project_ids=project_ids)
    if field == "project_id":
        return list(Project.objects.filter(id__in=project_ids).order_by("name").values_list("id", flat=True))
    if field == "state_id":
        return list(State.objects.filter(project_id__in=project_ids, is_triage=False).values_list("id", flat=True))
    if field == "cycle_id":
        return list(Cycle.objects.filter(project_id__in=project_ids).values_list("id", flat=True)) + ["None"]
    if field == "issue_module__module_id":
        return list(Module.objects.filter(project_id__in=project_ids).values_list("id", flat=True)) + ["None"]
    if field == "labels__id":
        labels = Label.objects.filter(workspace__slug=slug).filter(
            Q(project_id__in=project_ids) | Q(project__isnull=True)
        )
        return list(labels.values_list("id", flat=True)) + ["None"]
    return issue_group_values(field=field, slug=slug, filters=dict(filters or {}), queryset=queryset)


def category_cycles(project_ids: Iterable[Any]) -> List[Dict[str, Any]]:
    """Cycles (sprints) of the given projects, distinct by name.

    Each row: {name, start_date (earliest), end_date (latest), project_ids}, ordered by start date
    (undated last) then name. Archived cycles are included so finished sprints stay filterable.
    """
    rows = (
        Cycle.objects.filter(project_id__in=list(project_ids), project__archived_at__isnull=True)
        .exclude(name__isnull=True)
        .exclude(name="")
        .order_by()
        .values("name")
        .annotate(
            first_start=Min("start_date"),
            last_end=Max("end_date"),
            cycle_project_ids=ArrayAgg("project_id", distinct=True),
        )
        .order_by(F("first_start").asc(nulls_last=True), "name")
    )
    return [
        {
            "name": row["name"],
            "start_date": row["first_start"],
            "end_date": row["last_end"],
            "project_ids": sorted(str(project_id) for project_id in row["cycle_project_ids"]),
        }
        for row in rows
    ]


def set_category_projects(category: ProjectCategory, project_ids: Iterable[Any]) -> None:
    """Make the category's active (non-archived) projects exactly `project_ids`.

    Projects dropped from the list become uncategorized; archived projects keep their category.
    Callers validate that the ids belong to the category's workspace.
    """
    target = {str(project_id) for project_id in project_ids}
    now = timezone.now()
    with transaction.atomic():
        Project.objects.filter(category_id=category.id, archived_at__isnull=True).exclude(id__in=target).update(
            category=None, updated_at=now
        )
        if target:
            Project.objects.filter(workspace_id=category.workspace_id, id__in=target).exclude(
                category_id=category.id
            ).update(category=category, updated_at=now)


def delete_category(category: ProjectCategory) -> None:
    """Delete a category synchronously: uncategorize its projects (archived ones too), soft-delete
    its master-board views, then soft-delete the category (no reliance on the async cascade)."""
    with transaction.atomic():
        Project.objects.filter(category_id=category.id).update(category=None, updated_at=timezone.now())
        for view in IssueView.objects.filter(category_id=category.id):
            view.delete()
        category.delete()


def apply_category_mapping(
    workspace: Any,
    categories: Optional[Sequence[str]] = None,
    mapping: Optional[Mapping[str, str]] = None,
    *,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """Idempotently create `categories` (matched by name, ignoring case; new ones get a sort order
    following the list order) and assign projects by identifier (`mapping` identifier -> category
    name). Categories named only in `mapping` are created too. With overwrite=False projects that
    already have a category keep it. Both default to empty (nothing is created or assigned); the
    setup command passes the categories and mapping of its --config file.

    Returns {"created": [names], "categories": {name: id}, "assigned": {identifier: name},
    "unchanged": [identifiers], "unknown_identifiers": [identifiers]}.
    """
    categories = list(categories or ())
    mapping = dict(mapping or {})
    names = list(dict.fromkeys(name.strip() for name in [*categories, *mapping.values()] if name and name.strip()))

    created: List[str] = []
    by_name: Dict[str, ProjectCategory] = {}
    assigned: Dict[str, str] = {}
    unchanged: List[str] = []
    unknown: List[str] = []
    now = timezone.now()

    with transaction.atomic():
        existing = {
            category.name.casefold(): category for category in ProjectCategory.objects.filter(workspace_id=workspace.id)
        }
        for index, name in enumerate(names):
            category = existing.get(name.casefold())
            if category is None:
                category = ProjectCategory(workspace_id=workspace.id, name=name, sort_order=(index + 1) * 10000)
                category.save()
                existing[name.casefold()] = category
                created.append(name)
            by_name[name.casefold()] = category

        projects = {
            project.identifier.upper(): project for project in Project.objects.filter(workspace_id=workspace.id)
        }
        for identifier, category_name in mapping.items():
            project = projects.get(str(identifier).strip().upper())
            if project is None:
                unknown.append(identifier)
                continue
            category = by_name[category_name.strip().casefold()]
            if project.category_id == category.id or (project.category_id and not overwrite):
                unchanged.append(project.identifier)
                continue
            Project.objects.filter(pk=project.pk).update(category=category, updated_at=now)
            assigned[project.identifier] = category.name

    if unknown:
        logger.warning("apply_category_mapping: unknown project identifiers %s", ", ".join(unknown))

    return {
        "created": created,
        "categories": {category.name: str(category.id) for category in by_name.values()},
        "assigned": assigned,
        "unchanged": unchanged,
        "unknown_identifiers": unknown,
    }


class ProjectCategoryIdField(serializers.PrimaryKeyRelatedField):
    """Writable project category reference for the project serializers (app + v1).

    Only categories of the serializer context's `workspace_id` resolve; anything else is a 400.
    Declare it as `category_id = ProjectCategoryIdField(source="category")`.
    """

    default_error_messages = {
        **serializers.PrimaryKeyRelatedField.default_error_messages,
        "does_not_exist": "Project category not found in this workspace.",
    }

    def __init__(self, **kwargs):
        if not kwargs.get("read_only"):
            kwargs.setdefault("required", False)
            kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)

    def get_queryset(self):
        context = self.context if isinstance(self.context, dict) else {}
        workspace_id = context.get("workspace_id")
        if workspace_id is None:
            return ProjectCategory.objects.none()
        return ProjectCategory.objects.filter(workspace_id=workspace_id)
