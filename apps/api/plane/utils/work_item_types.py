# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity work item types service.

Workspace-level ``IssueType`` rows are the single source of truth:
Task (default), Story, Bug, Sub-task (``is_sub_task``) and Epic (``is_epic``), with Jira-like
``logo_props``. Every project has every workspace type enabled (``ProjectIssueType`` rows) and
``Project.is_issue_type_enabled=True``; types are managed only at workspace level.

Hierarchy rules, enforced server side from the type FLAGS (never the names):
- a Sub-task work item must have a parent;
- a Sub-task cannot be the parent of any work item (so an Epic never sits under a Sub-task).

Public helpers:
- ensure_workspace_work_item_types(workspace) -> [IssueType]   create/repair the 5 standard types
- seed_project_work_item_types(project)                          ProjectIssueType rows + flag
- sync_workspace_work_item_types(workspace) -> dict              setup-command one-stop (+ backfill)
- get_default_type(workspace) -> IssueType | None                the workspace default (Task)
- set_default_work_item_type(issue_type)                         move the default atomically
- validate_issue_type_and_parent(attrs, instance=, workspace_id=) serializer-level rules
- check_issue_type_hierarchy(issue_type, parent, ...)            low-level rule check
- validate_parent_can_have_children(parent_issue)                sub-issue add endpoints
- is_epic_issue(issue) / is_sub_task_issue(issue)
- track_work_item_type(...)                                      issue activity (field "type")
"""

# Python imports
import logging
import uuid

# Django imports
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce

# Third party imports
from rest_framework import serializers

# Module imports
from plane.db.models import DraftIssue, Issue, IssueActivity, IssueType, Project, ProjectIssueType, ProjectMember
from plane.utils.exception_logger import log_exception

logger = logging.getLogger("plane.api")

# ---------------------------------------------------------------- standard types

TASK = "task"
STORY = "story"
BUG = "bug"
SUB_TASK = "sub_task"
EPIC = "epic"

# Hierarchy levels (Jira hierarchyLevel): Epic 1, standard 0, Sub-task -1.
LEVEL_EPIC = 1
LEVEL_STANDARD = 0
LEVEL_SUB_TASK = -1


def _icon(name, color):
    # Material Symbols ligature + Jira brand color; same shape the web settings modal saves
    # (components/jira-parity/work-item-types/rules.ts buildWorkItemTypeLogoProps).
    return {"in_use": "icon", "icon": {"name": name, "color": color, "background_color": color}}


STANDARD_WORK_ITEM_TYPES = (
    {
        "key": TASK,
        "name": "Task",
        "description": "A small, distinct piece of work.",
        "is_default": True,
        "is_epic": False,
        "is_sub_task": False,
        "logo_props": _icon("check_box", "#4BADE8"),
    },
    {
        "key": STORY,
        "name": "Story",
        "description": "A feature or functionality expressed as a user goal.",
        "is_default": False,
        "is_epic": False,
        "is_sub_task": False,
        "logo_props": _icon("priority", "#E97F33"),
    },
    {
        "key": BUG,
        "name": "Bug",
        "description": "A problem or error.",
        "is_default": False,
        "is_epic": False,
        "is_sub_task": False,
        "logo_props": _icon("bug_report", "#E5493A"),
    },
    {
        "key": SUB_TASK,
        "name": "Sub-task",
        "description": "A smaller piece of work that is part of a larger work item.",
        "is_default": False,
        "is_epic": False,
        "is_sub_task": True,
        "logo_props": _icon("subdirectory_arrow_right", "#4BADE8"),
    },
    {
        "key": EPIC,
        "name": "Epic",
        "description": "A large body of work that groups related work items.",
        "is_default": False,
        "is_epic": True,
        "is_sub_task": False,
        "logo_props": _icon("bolt", "#904EE2"),
    },
)


def type_level(is_epic, is_sub_task):
    """Hierarchy level derived from the flags (IssueType.level is kept consistent with them)."""
    if is_epic:
        return LEVEL_EPIC
    if is_sub_task:
        return LEVEL_SUB_TASK
    return LEVEL_STANDARD


def _workspace_id(workspace):
    return getattr(workspace, "pk", workspace)


def _match_by_flag(spec, candidates, used_ids):
    for issue_type in candidates:
        if issue_type.id in used_ids:
            continue
        if spec["is_epic"] and issue_type.is_epic:
            return issue_type
        if spec["is_sub_task"] and issue_type.is_sub_task:
            return issue_type
        if spec["is_default"] and issue_type.is_default and not (issue_type.is_epic or issue_type.is_sub_task):
            return issue_type
    return None


def _create_standard_type(workspace_id, spec):
    try:
        with transaction.atomic():
            return IssueType.objects.create(
                workspace_id=workspace_id,
                name=spec["name"],
                description=spec["description"],
                logo_props=spec["logo_props"],
                is_epic=spec["is_epic"],
                is_sub_task=spec["is_sub_task"],
                is_default=False,  # the single default is settled by _ensure_single_default
                is_active=True,
                level=type_level(spec["is_epic"], spec["is_sub_task"]),
            )
    except IntegrityError:
        # Created concurrently (unique live name per workspace): adopt the winner.
        existing = IssueType.objects.filter(workspace_id=workspace_id, name__iexact=spec["name"]).first()
        if existing is None:
            raise
        return existing


def _repair_flags(issue_type, spec):
    """Standard types keep their semantic flags; names, descriptions, logos and is_active are
    user-editable and never overwritten."""
    expected = {
        "is_epic": spec["is_epic"],
        "is_sub_task": spec["is_sub_task"],
        "level": type_level(spec["is_epic"], spec["is_sub_task"]),
    }
    if spec["is_epic"] or spec["is_sub_task"]:
        expected["is_default"] = False
    changed = [field for field, value in expected.items() if getattr(issue_type, field) != value]
    if changed:
        for field in changed:
            setattr(issue_type, field, expected[field])
        issue_type.save(update_fields=changed + ["updated_at"])


def _sync_project_type_defaults(workspace_id, default_type_id):
    ProjectIssueType.objects.filter(workspace_id=workspace_id, is_default=True).exclude(
        issue_type_id=default_type_id
    ).update(is_default=False)
    ProjectIssueType.objects.filter(workspace_id=workspace_id, issue_type_id=default_type_id).update(is_default=True)


def _ensure_single_default(workspace_id, preferred):
    """Exactly one live, active, standard-level default type per workspace (prefer an existing
    valid default, else `preferred` = Task). Returns the default type."""
    defaults = list(IssueType.objects.filter(workspace_id=workspace_id, is_default=True).order_by("created_at"))
    valid = [t for t in defaults if t.is_active and not t.is_epic and not t.is_sub_task]
    keep = valid[0] if valid else preferred
    stale = [t.id for t in defaults if t.id != keep.id]
    changed = bool(stale)
    if stale:
        IssueType.objects.filter(id__in=stale).update(is_default=False)
    if not keep.is_default or not keep.is_active:
        IssueType.objects.filter(pk=keep.pk).update(is_default=True, is_active=True)
        keep.is_default = True
        keep.is_active = True
        changed = True
    if changed:
        _sync_project_type_defaults(workspace_id, keep.id)
    return keep


def ensure_workspace_work_item_types(workspace):
    """Idempotently create/repair the 5 standard workspace-level IssueType rows; return them
    (list, in STANDARD_WORK_ITEM_TYPES order: Task, Story, Bug, Sub-task, Epic).

    Matching: live type with the same name (case-insensitive) first, then by flag (Epic ->
    is_epic, Sub-task -> is_sub_task, Task -> the current standard default), else create.
    Semantic flags of matched rows are repaired; user edits (name, description, logo, active)
    are kept. Guarantees exactly one active default (Task unless another valid default exists).
    """
    workspace_id = _workspace_id(workspace)
    live = list(IssueType.objects.filter(workspace_id=workspace_id).order_by("created_at"))
    by_name = {}
    for issue_type in live:
        by_name.setdefault(issue_type.name.strip().lower(), issue_type)

    used_ids = set()
    matched = {}
    # pass 1: by name
    for spec in STANDARD_WORK_ITEM_TYPES:
        issue_type = by_name.get(spec["name"].lower())
        if issue_type is not None and issue_type.id not in used_ids:
            matched[spec["key"]] = issue_type
            used_ids.add(issue_type.id)
    # pass 2: by flag, then create
    for spec in STANDARD_WORK_ITEM_TYPES:
        if spec["key"] in matched:
            continue
        issue_type = _match_by_flag(spec, live, used_ids) or _create_standard_type(workspace_id, spec)
        matched[spec["key"]] = issue_type
        used_ids.add(issue_type.id)

    result = []
    for spec in STANDARD_WORK_ITEM_TYPES:
        issue_type = matched[spec["key"]]
        _repair_flags(issue_type, spec)
        result.append(issue_type)

    default_type = _ensure_single_default(workspace_id, preferred=matched[TASK])
    for issue_type in result:
        issue_type.is_default = issue_type.id == default_type.id
    return result


def link_work_item_types_to_projects(issue_types, projects):
    """Create the missing ProjectIssueType rows for every (project, type) pair."""
    issue_types = list(issue_types)
    projects = list(projects)
    if not issue_types or not projects:
        return 0
    existing = set(
        ProjectIssueType.objects.filter(
            project_id__in=[p.id for p in projects], issue_type_id__in=[t.id for t in issue_types]
        ).values_list("project_id", "issue_type_id")
    )
    rows = [
        ProjectIssueType(
            project_id=project.id,
            workspace_id=project.workspace_id,
            issue_type_id=issue_type.id,
            level=max(int(issue_type.level or 0), 0),
            is_default=issue_type.is_default,
        )
        for project in projects
        for issue_type in issue_types
        if (project.id, issue_type.id) not in existing
    ]
    if rows:
        ProjectIssueType.objects.bulk_create(rows, batch_size=500, ignore_conflicts=True)
    return len(rows)


def seed_project_work_item_types(project):
    """Enable every workspace work item type on `project` (ProjectIssueType rows) and set
    project.is_issue_type_enabled=True. Called by run_project_created_hooks.

    The standard types are only (re)created here when the workspace has no live type at all,
    so a type an admin deleted is not resurrected by every new project.
    """
    workspace_id = project.workspace_id
    if not IssueType.objects.filter(workspace_id=workspace_id).exists():
        ensure_workspace_work_item_types(workspace_id)
    link_work_item_types_to_projects(IssueType.objects.filter(workspace_id=workspace_id), [project])
    if not project.is_issue_type_enabled:
        Project.objects.filter(pk=project.pk).update(is_issue_type_enabled=True)
        project.is_issue_type_enabled = True


def seed_new_workspace_work_item_types(workspace):
    """Workspace-create hook: seed the standard types; never blocks workspace creation."""
    try:
        with transaction.atomic():
            ensure_workspace_work_item_types(workspace)
    except Exception as e:  # noqa: BLE001
        logger.warning("Jira-parity: seeding work item types failed for workspace %s: %s", workspace, e)
        log_exception(e)


def backfill_issue_types(workspace):
    """Give every work item / draft without a type the workspace default type. Returns counts."""
    default_type = get_default_type(workspace)
    if default_type is None:
        return {"issues": 0, "draft_issues": 0}
    workspace_id = _workspace_id(workspace)
    issues = Issue.all_objects.filter(workspace_id=workspace_id, type__isnull=True).update(type=default_type)
    drafts = DraftIssue.all_objects.filter(workspace_id=workspace_id, type__isnull=True).update(type=default_type)
    return {"issues": issues, "draft_issues": drafts}


def sync_workspace_work_item_types(workspace, backfill=True):
    """One-stop idempotent setup for a workspace (used by setup commands): standard types,
    ProjectIssueType rows + is_issue_type_enabled for every project, and (optionally) a backfill
    of work items without a type. Returns a summary dict."""
    workspace_id = _workspace_id(workspace)
    types = ensure_workspace_work_item_types(workspace_id)
    projects = list(Project.objects.filter(workspace_id=workspace_id))
    linked = link_work_item_types_to_projects(IssueType.objects.filter(workspace_id=workspace_id), projects)
    enabled = Project.objects.filter(workspace_id=workspace_id, is_issue_type_enabled=False).update(
        is_issue_type_enabled=True
    )
    summary = {
        "types": [t.name for t in types],
        "project_links_created": linked,
        "projects_enabled": enabled,
    }
    if backfill:
        summary["backfilled"] = backfill_issue_types(workspace_id)
    return summary


def get_default_type(workspace, seed=True):
    """The workspace default work item type (Task). Seeds the standard types lazily when the
    workspace has none. Falls back to the oldest active standard-level type."""
    workspace_id = _workspace_id(workspace)
    if workspace_id is None:
        return None
    active = IssueType.objects.filter(workspace_id=workspace_id, is_active=True)
    default_type = active.filter(is_default=True).order_by("created_at").first()
    if default_type is not None:
        return default_type
    if seed and not IssueType.objects.filter(workspace_id=workspace_id).exists():
        try:
            with transaction.atomic():
                types = ensure_workspace_work_item_types(workspace_id)
            return next((t for t in types if t.is_default), None)
        except Exception as e:  # noqa: BLE001 - never block work item creation
            log_exception(e)
            return None
    return active.filter(is_epic=False, is_sub_task=False).order_by("created_at").first()


def set_default_work_item_type(issue_type):
    """Make `issue_type` the single workspace default (and mirror it on ProjectIssueType)."""
    with transaction.atomic():
        IssueType.objects.filter(workspace_id=issue_type.workspace_id, is_default=True).exclude(
            pk=issue_type.pk
        ).update(is_default=False)
        if not issue_type.is_default:
            IssueType.objects.filter(pk=issue_type.pk).update(is_default=True)
            issue_type.is_default = True
        _sync_project_type_defaults(issue_type.workspace_id, issue_type.id)
    return issue_type


def visible_issues_q(user):
    """Work items `user` can see: active project memberships; guests of projects without
    guest_view_all_features only their own work items (same rule as the issue lists)."""
    memberships = ProjectMember.objects.filter(member=user, is_active=True, project__deleted_at__isnull=True)
    full_access = memberships.filter(Q(role__gt=5) | Q(role=5, project__guest_view_all_features=True))
    own_only = memberships.filter(role=5, project__guest_view_all_features=False)
    return Q(project_id__in=full_access.values("project_id")) | Q(
        project_id__in=own_only.values("project_id"), created_by=user
    )


def annotate_issue_count(queryset, user=None):
    """Annotate `issue_count` = live (not deleted) work items of each type, incl. archived/drafts.

    With `user`, only the work items that user can see are counted (visible_issues_q).
    """
    issues = Issue.all_objects.filter(type_id=OuterRef("id"), deleted_at__isnull=True)
    if user is not None:
        issues = issues.filter(visible_issues_q(user))
    count_subquery = issues.order_by().values("type_id").annotate(count=Count("id")).values("count")
    return queryset.annotate(issue_count=Coalesce(Subquery(count_subquery, output_field=IntegerField()), Value(0)))


# ---------------------------------------------------------------- issue rules

INVALID_WORK_ITEM_TYPE = "INVALID_WORK_ITEM_TYPE"
WORK_ITEM_TYPE_INACTIVE = "WORK_ITEM_TYPE_INACTIVE"
SUB_TASK_REQUIRES_PARENT = "SUB_TASK_REQUIRES_PARENT"
SUB_TASK_CANNOT_BE_PARENT = "SUB_TASK_CANNOT_BE_PARENT"

MSG_INVALID_TYPE = "Invalid work item type."
MSG_INACTIVE_TYPE = "This work item type is inactive."
MSG_SUB_TASK_REQUIRES_PARENT = "A Sub-task must have a parent work item."
MSG_SUB_TASK_CANNOT_BE_PARENT = "A Sub-task cannot be the parent of other work items."
MSG_SUB_TASK_HAS_CHILDREN = "A work item that has sub-work items cannot become a Sub-task."


class WorkItemTypeRuleError(ValidationError):
    """A Django ValidationError (so DRF serializers turn it into a 400 with field errors and
    Issue-level callers can catch it) that also carries a stable code for plain responses."""

    def __init__(self, field, message, code):
        self.field = field
        self.rule_message = message
        self.rule_code = code
        super().__init__({field: message, "error": message, "code": code})

    def as_response_data(self):
        return {"error": self.rule_message, "code": self.rule_code, self.field: self.rule_message}


def is_epic_issue(issue):
    """True when the work item's type is an Epic (flag based)."""
    return bool(issue is not None and issue.type_id and issue.type.is_epic)


def is_sub_task_issue(issue):
    """True when the work item's type is a Sub-task (flag based)."""
    return bool(issue is not None and issue.type_id and issue.type.is_sub_task)


def check_issue_type_hierarchy(issue_type, parent, instance=None, check_children=False):
    """Raise WorkItemTypeRuleError when (issue_type, parent) breaks the Jira-parity rules.

    - Sub-task requires a parent;
    - the parent cannot be a Sub-task (covers "Epic cannot have a Sub-task parent");
    - with check_children, a work item that has children cannot become a Sub-task.
    A missing type (legacy rows) is treated as a standard type.
    """
    if issue_type is not None and issue_type.is_sub_task and parent is None:
        raise WorkItemTypeRuleError("parent_id", MSG_SUB_TASK_REQUIRES_PARENT, SUB_TASK_REQUIRES_PARENT)
    if parent is not None and is_sub_task_issue(parent):
        raise WorkItemTypeRuleError("parent_id", MSG_SUB_TASK_CANNOT_BE_PARENT, SUB_TASK_CANNOT_BE_PARENT)
    if (
        check_children
        and instance is not None
        and instance.pk
        and issue_type is not None
        and issue_type.is_sub_task
        and Issue.all_objects.filter(parent_id=instance.pk, deleted_at__isnull=True).exists()
    ):
        raise WorkItemTypeRuleError("type_id", MSG_SUB_TASK_HAS_CHILDREN, SUB_TASK_CANNOT_BE_PARENT)


def validate_parent_can_have_children(parent_issue):
    """For endpoints that attach existing work items under `parent_issue` (sub-issue add)."""
    if is_sub_task_issue(parent_issue):
        raise WorkItemTypeRuleError("parent_id", MSG_SUB_TASK_CANNOT_BE_PARENT, SUB_TASK_CANNOT_BE_PARENT)


def _resolve_workspace_id(instance, workspace_id, project_id):
    if workspace_id:
        return workspace_id
    if instance is not None and getattr(instance, "workspace_id", None):
        return instance.workspace_id
    if project_id:
        return Project.objects.filter(pk=project_id).values_list("workspace_id", flat=True).first()
    return None


def validate_issue_type_and_parent(attrs, instance=None, workspace_id=None, project_id=None):
    """Serializer-level work item type rules for app and v1 issue serializers. Returns attrs.

    - optional ``type_name`` (v1): resolved case-insensitively within the workspace;
    - ``type`` must belong to the issue's workspace; an inactive type can be kept but not newly set;
    - ``type: null`` is ignored on update (types cannot be cleared) and means "default" on create;
    - on create without a type, the workspace default type (Task) is used;
    - when creating, or when the type or the parent changes: check_issue_type_hierarchy.
    Raises WorkItemTypeRuleError (a Django ValidationError -> HTTP 400 through DRF).
    """
    creating = instance is None
    ws_id = _resolve_workspace_id(instance, workspace_id, project_id)

    type_name = attrs.pop("type_name", None) if hasattr(attrs, "pop") else None
    if isinstance(type_name, str) and type_name.strip():
        named_type = IssueType.objects.filter(workspace_id=ws_id, name__iexact=type_name.strip()).first()
        if named_type is None:
            raise WorkItemTypeRuleError(
                "type_name", f"Unknown work item type '{type_name.strip()}'.", INVALID_WORK_ITEM_TYPE
            )
        attrs["type"] = named_type

    if "type" in attrs:
        issue_type = attrs["type"]
        if issue_type is None:
            attrs.pop("type")
        else:
            if ws_id is None or str(issue_type.workspace_id) != str(ws_id) or issue_type.deleted_at is not None:
                raise WorkItemTypeRuleError("type_id", MSG_INVALID_TYPE, INVALID_WORK_ITEM_TYPE)
            if not issue_type.is_active and (creating or instance.type_id != issue_type.id):
                raise WorkItemTypeRuleError("type_id", MSG_INACTIVE_TYPE, WORK_ITEM_TYPE_INACTIVE)

    if creating and "type" not in attrs:
        default_type = get_default_type(ws_id)
        if default_type is not None:
            attrs["type"] = default_type

    type_changed = "type" in attrs and (creating or attrs["type"].id != instance.type_id)
    parent_changed = "parent" in attrs and (
        creating or (attrs["parent"].id if attrs["parent"] is not None else None) != instance.parent_id
    )
    if creating or type_changed or parent_changed:
        effective_type = attrs["type"] if "type" in attrs else (instance.type if instance is not None else None)
        effective_parent = attrs["parent"] if "parent" in attrs else (instance.parent if instance is not None else None)
        check_issue_type_hierarchy(
            effective_type,
            effective_parent,
            instance=instance,
            check_children=type_changed and not creating,
        )
    return attrs


def validate_draft_work_item_type(attrs, instance=None, workspace_id=None):
    """Draft work items: a given type must belong to the draft's workspace (drafts may clear it).
    Hierarchy rules run when the draft becomes a work item (IssueCreateSerializer)."""
    issue_type = attrs.get("type") if hasattr(attrs, "get") else None
    if issue_type is None:
        return attrs
    ws_id = workspace_id or getattr(instance, "workspace_id", None)
    if ws_id is None or str(issue_type.workspace_id) != str(ws_id) or issue_type.deleted_at is not None:
        raise WorkItemTypeRuleError("type_id", MSG_INVALID_TYPE, INVALID_WORK_ITEM_TYPE)
    return attrs


# ---------------------------------------------------------------- serializer helpers


def work_item_type_id_field():
    """`type_id` write/read field (source="type"); workspace scoping happens in
    validate_issue_type_and_parent."""
    return serializers.PrimaryKeyRelatedField(
        source="type", queryset=IssueType.objects.all(), required=False, allow_null=True
    )


def normalize_type_name_input(data):
    """v1: accept ``"type": "<type name>"`` as an alias of ``type_name`` (a UUID stays a pk)."""
    if not hasattr(data, "get"):
        return data
    value = data.get("type")
    if not isinstance(value, str) or not value.strip():
        return data
    try:
        uuid.UUID(value)
        return data
    except ValueError:
        pass
    data = data.dict() if hasattr(data, "dict") else dict(data)
    data.pop("type", None)
    data.setdefault("type_name", value)
    return data


def filter_issues_by_work_item_type(queryset, params):
    """v1 list filter: ``?type_id=<uuid>[,..]``, ``?type=<name or uuid>[,..]`` or ``?type_name=``
    (names are case-insensitive). Returns the queryset unchanged when no such param is given."""
    values = []
    for key in ("type_id", "type", "type_name"):
        raw = params.get(key)
        if raw:
            values.extend(value.strip() for value in str(raw).split(",") if value.strip())
    if not values:
        return queryset
    type_ids, names = [], []
    for value in values:
        try:
            type_ids.append(uuid.UUID(value))
        except ValueError:
            names.append(value)
    query = Q(type_id__in=type_ids) if type_ids else Q()
    for name in names:
        query |= Q(type__name__iexact=name, type__deleted_at__isnull=True)
    return queryset.filter(query)


def work_item_type_name(issue, serializer=None):
    """Name of the work item's type, cached per serializer to avoid N+1 in v1 lists."""
    type_id = getattr(issue, "type_id", None)
    if type_id is None:
        return None
    cached_type = issue._state.fields_cache.get("type")
    if cached_type is not None:
        return cached_type.name
    cache = None
    if serializer is not None:
        cache = serializer.__dict__.setdefault("_jp_type_name_cache", {})
        if type_id in cache:
            return cache[type_id]
    name = IssueType.all_objects.filter(pk=type_id).values_list("name", flat=True).first()
    if cache is not None:
        cache[type_id] = name
    return name


# ---------------------------------------------------------------- activity

# Request keys that can change the type: app/v1 `type_id`, v1 `type` (pk or name), v1 `type_name`
TYPE_REQUEST_KEYS = ("type_id", "type", "type_name")


def _requested_work_item_type(requested_data, workspace_id):
    """The IssueType a PATCH payload asks for, or None (absent / null / unknown)."""
    for key in TYPE_REQUEST_KEYS:
        value = requested_data.get(key)
        if isinstance(value, dict):
            value = value.get("id")
        if value is None or not str(value).strip():
            continue
        value = str(value).strip()
        try:
            uuid.UUID(value)
        except ValueError:
            return IssueType.all_objects.filter(workspace_id=workspace_id, name__iexact=value).first()
        return IssueType.all_objects.filter(pk=value).first()
    return None


def track_work_item_type(
    requested_data,
    current_instance,
    issue_id,
    project_id,
    workspace_id,
    actor_id,
    issue_activities,
    epoch,
):
    """ISSUE_ACTIVITY_MAPPER tracker: records field "type" (names as values, ids as identifiers),
    rendered by the web WorkItemTypeActivity. Runs once per payload even when it carries several
    type keys."""
    if any(activity.field == "type" for activity in issue_activities):
        return
    new_type = _requested_work_item_type(requested_data or {}, workspace_id)
    if new_type is None:
        return
    current_instance = current_instance or {}
    old_type_id = current_instance.get("type_id") or current_instance.get("type")
    if old_type_id and str(old_type_id) == str(new_type.id):
        return
    old_type = IssueType.all_objects.filter(pk=old_type_id).first() if old_type_id else None
    issue_activities.append(
        IssueActivity(
            issue_id=issue_id,
            actor_id=actor_id,
            verb="updated",
            old_value=old_type.name if old_type is not None else None,
            new_value=new_type.name,
            field="type",
            project_id=project_id,
            workspace_id=workspace_id,
            comment="updated the work item type to",
            old_identifier=old_type.id if old_type is not None else None,
            new_identifier=new_type.id,
            epoch=epoch,
        )
    )
