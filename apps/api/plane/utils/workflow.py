# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity workflow (state transition) service.

The ONE place that decides whether a state change is allowed. Every state-changing request path
calls it for the requester's effective project role:
- app   PATCH /api/workspaces/<slug>/projects/<pid>/issues/<id>/      (IssueViewSet.partial_update;
        also kanban/list drag, every state dropdown, peek, spreadsheet)
- app   PATCH .../intake-issues/<id>/                                   (IntakeIssueViewSet.partial_update)
- v1    PATCH /api/v1/workspaces/<slug>/projects/<pid>/work-items/<id>/ (IssueDetailAPIEndpoint.patch)
- v1    PATCH .../intake-issues/<id>/                                   (IntakeIssueDetailAPIEndpoint.patch)
- the Agent guard (plane.app.permissions.agent.check_issue_state_change)
CE has no bulk state-update endpoint, and cycle/module operations never change state. Creating a
work item is not a transition. QuerySet.update/bulk_update bypass this module by design (system
jobs such as the auto-close task); any future bulk path MUST call `assert_state_transition_allowed`
per work item.

Data model: db.StateTransition(project, from_state (NULL = any state), to_state,
roles: list[int] of ProjectMember.role values, exclude_epics, is_active) + Project.is_workflow_enabled.

Semantics:
1. Same state (no-op / kanban reorder) -> allowed. No actor (celery, management commands) -> allowed.
2. Admin (project role 20, or workspace admin who is a project member) -> always allowed.
3. Agent (10): never on epics (AGENT_EPIC_STATE_CHANGE_FORBIDDEN). Agents are ALWAYS restricted,
   whatever is_workflow_enabled says: by the active rules that list role 10, or - when no rule lists
   role 10 - by the built-in default To Do -> In Progress, In Progress -> In Review (state names,
   normalised so "Todo" == "To Do").
4. Member (15) / Guest (5): unrestricted unless the project's workflow is enabled AND at least one
   active rule lists that role; then only the listed (from, to) pairs are allowed. Rules with
   exclude_epics=True do not apply to epics. Moving out of the Triage state (intake) is unrestricted.
Forbidden -> HTTP 403 {"error", "code": "STATE_TRANSITION_NOT_ALLOWED" | "AGENT_EPIC_STATE_CHANGE_FORBIDDEN",
"from_state_id", "to_state_id", "allowed_state_ids"}.

Standard states (every project): To Do (unstarted, default), In Progress (started), In Review
(started), Done (completed), Won't Fix (cancelled) + the hidden Triage state. New projects get them
from db.models.state.DEFAULT_STATES; existing projects are converted by `seed_project_workflow`
(management command `apply_jira_workflow`).
"""

# Python imports
import logging
import re
import uuid

# Django imports
from django.db import transaction
from django.db.models import F, Q
from django.db.models.functions import Coalesce, Now

# Third party imports
from rest_framework import status
from rest_framework.exceptions import APIException

# Module imports
from plane.db.models import (
    DraftIssue,
    Issue,
    Project,
    ProjectMember,
    State,
    StateTransition,
    WorkspaceMember,
)
from plane.db.models.project import ROLE
from plane.db.models.state import DEFAULT_STATES, StateGroup

logger = logging.getLogger("plane.api")

ADMIN = ROLE.ADMIN.value
AGENT = ROLE.AGENT.value

STATE_TRANSITION_NOT_ALLOWED = "STATE_TRANSITION_NOT_ALLOWED"
AGENT_EPIC_STATE_CHANGE_FORBIDDEN = "AGENT_EPIC_STATE_CHANGE_FORBIDDEN"

# Roles that transition rules may list (admins always bypass the workflow).
RULE_ROLES = (ROLE.MEMBER.value, ROLE.AGENT.value, ROLE.GUEST.value)


def normalize_state_name(name):
    """'To Do' == 'Todo' == 'TODO' -> 'todo'; "Won't Fix" -> 'wontfix'."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


# Agent default transitions by normalised state name (used when no rule lists the Agent role).
AGENT_DEFAULT_TRANSITIONS = (("todo", "inprogress"), ("inprogress", "inreview"))

# Normalised names an existing state may have to be adopted as a standard state (renamed in place).
STANDARD_STATE_ALIASES = {
    "todo": ("todo",),
    "inprogress": ("inprogress",),
    "inreview": ("inreview",),
    "done": ("done",),
    "wontfix": ("wontfix", "cancelled", "canceled"),
}
# Extra normalised names whose work items are moved into the standard state, then removed.
STANDARD_STATE_MERGES = {"todo": ("backlog",)}
# Plane's previous default colors: a matched standard state still using one is recolored.
LEGACY_DEFAULT_COLORS = {"#60646c", "#f59e0b", "#46a758", "#9aa4bc"}


def standard_state_specs():
    """The standard (non-triage) states, in board order, from db.models.state.DEFAULT_STATES."""
    specs = []
    for state in DEFAULT_STATES:
        if state["group"] == StateGroup.TRIAGE.value:
            continue
        key = normalize_state_name(state["name"])
        specs.append({**state, "key": key, "aliases": STANDARD_STATE_ALIASES.get(key, (key,))})
    return specs


# ------------------------------------------------------------------ errors


class StateTransitionNotAllowed(APIException):
    """403 raised by `assert_state_transition_allowed`; DRF renders `detail` as the JSON body."""

    status_code = status.HTTP_403_FORBIDDEN
    default_code = "state_transition_not_allowed"
    default_detail = "This state change is not allowed."

    def __init__(self, *, code, message, from_state_id=None, to_state_id=None, allowed_state_ids=None):
        super().__init__()
        self.detail = {
            "error": message,
            "code": code,
            "from_state_id": str(from_state_id) if from_state_id else None,
            "to_state_id": str(to_state_id) if to_state_id else None,
            "allowed_state_ids": allowed_state_ids if allowed_state_ids is not None else [],
        }


# ------------------------------------------------------------------ roles / epics


def _role_value(role):
    if role is None:
        return None
    return int(role.value if isinstance(role, ROLE) else role)


def get_effective_project_role(user, project_id):
    """The actor's project role as allow_permission sees it: ProjectMember.role of the active
    membership, raised to Admin for an active workspace admin, pinned to Agent for a workspace agent.
    None when the user is not an active project member."""
    user_id = getattr(user, "id", user)
    if user_id is None:
        return None
    member = (
        ProjectMember.objects.filter(project_id=project_id, member_id=user_id, is_active=True)
        .values("role", "workspace_id")
        .first()
    )
    if member is None:
        return None
    workspace_role = (
        WorkspaceMember.objects.filter(workspace_id=member["workspace_id"], member_id=user_id, is_active=True)
        .values_list("role", flat=True)
        .first()
    )
    if workspace_role == ADMIN:
        return ADMIN
    if workspace_role == AGENT:
        return AGENT
    return member["role"]


def is_epic_issue(issue):
    """True when the work item's type is an epic. Uses the IssueType.is_epic flag only (never the
    type name), matching plane.utils.work_item_types and the web app's types store."""
    if issue is None or not getattr(issue, "type_id", None):
        return False
    issue_type = getattr(issue, "type", None)
    if issue_type is None:
        return False
    return bool(issue_type.is_epic)


def _is_workflow_enabled(project_id):
    return bool(Project.objects.filter(pk=project_id).values_list("is_workflow_enabled", flat=True).first())


def _is_triage_state(state_id):
    return State.all_state_objects.filter(pk=state_id, group=StateGroup.TRIAGE.value).exists()


def _valid_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


# ------------------------------------------------------------------ policy


def _active_rules(project_id, role):
    """Active rules of the project that list `role` (deleted states excluded)."""
    return list(
        StateTransition.objects.filter(
            project_id=project_id,
            is_active=True,
            roles__contains=[role],
            to_state__deleted_at__isnull=True,
        )
        .filter(Q(from_state__isnull=True) | Q(from_state__deleted_at__isnull=True))
        .values("from_state_id", "to_state_id", "exclude_epics")
    )


def _agent_fallback_pairs(project_id):
    """Built-in agent transitions resolved to this project's state ids by normalised name."""
    ids_by_name = {}
    for state_id, name in State.objects.filter(project_id=project_id).values_list("id", "name"):
        ids_by_name.setdefault(normalize_state_name(name), []).append(state_id)
    pairs = []
    for from_name, to_name in AGENT_DEFAULT_TRANSITIONS:
        for from_id in ids_by_name.get(from_name, []):
            for to_id in ids_by_name.get(to_name, []):
                pairs.append((from_id, to_id))
    return pairs


def _resolve_policy(project_id, role, epic):
    """None = unrestricted; otherwise the list of allowed (from_state_id | None, to_state_id) pairs."""
    role = _role_value(role)
    if role is None:
        return []
    if role >= ADMIN:
        return None
    is_agent = role == AGENT
    if is_agent and epic:
        return []
    if not is_agent and not _is_workflow_enabled(project_id):
        return None
    rules = _active_rules(project_id, role)
    if rules:
        return [(r["from_state_id"], r["to_state_id"]) for r in rules if not (epic and r["exclude_epics"])]
    if is_agent:
        return _agent_fallback_pairs(project_id)
    return None


def _targets(pairs, from_state_id):
    source = str(from_state_id) if from_state_id else None
    return sorted({str(to_id) for from_id, to_id in pairs if from_id is None or str(from_id) == source} - {source})


def allowed_target_state_ids(project_id, from_state_id, role, epic=False):
    """State ids (str) `role` may move a work item to from `from_state_id`, or None when the role is
    unrestricted. The current state itself is never listed (staying put is always allowed)."""
    pairs = _resolve_policy(project_id, role, epic)
    if pairs is None:
        return None
    return _targets(pairs, from_state_id)


def is_transition_allowed(*, project_id, issue, to_state_id, role=None, user=None):
    """Return (allowed, error_code) for moving `issue` to `to_state_id`.

    `role` is the actor's effective project role (int or ROLE); when omitted it is derived from
    `user`. With neither (system jobs) the move is allowed.
    """
    from_state_id = getattr(issue, "state_id", None)
    if not to_state_id or (from_state_id is not None and str(from_state_id) == str(to_state_id)):
        return True, None
    role = _role_value(role)
    if role is None:
        if user is None or getattr(user, "is_anonymous", False):
            return True, None
        role = get_effective_project_role(user, project_id)
        if role is None:
            return False, STATE_TRANSITION_NOT_ALLOWED
    if role >= ADMIN:
        return True, None
    epic = is_epic_issue(issue)
    if role == AGENT and epic:
        return False, AGENT_EPIC_STATE_CHANGE_FORBIDDEN
    if role != AGENT and from_state_id is not None and _is_triage_state(from_state_id):
        return True, None
    allowed = allowed_target_state_ids(project_id, from_state_id, role, epic=epic)
    if allowed is None or str(to_state_id) in allowed:
        return True, None
    return False, STATE_TRANSITION_NOT_ALLOWED


def assert_state_transition_allowed(*, issue, to_state_id, user=None, role=None, project_id=None):
    """Raise StateTransitionNotAllowed (HTTP 403) unless the move is allowed. No-op when the payload
    does not change the state or carries an invalid id (the serializer reports that as a 400).

    `to_state_id` may be a State instance (e.g. `serializer.validated_data.get("state")`), so views
    call this between `serializer.is_valid()` and `serializer.save()` whatever key carried the state.
    """
    to_state_id = getattr(to_state_id, "pk", to_state_id)
    if to_state_id in (None, "") or _valid_uuid(to_state_id) is None:
        return
    project_id = project_id or issue.project_id
    allowed, code = is_transition_allowed(
        project_id=project_id, issue=issue, to_state_id=to_state_id, role=role, user=user
    )
    if allowed:
        return
    from_state_id = getattr(issue, "state_id", None)
    if code == AGENT_EPIC_STATE_CHANGE_FORBIDDEN:
        raise StateTransitionNotAllowed(
            code=code,
            message="Agents can't change the state of an epic.",
            from_state_id=from_state_id,
            to_state_id=to_state_id,
        )
    names = dict(
        State.all_state_objects.filter(pk__in=[s for s in (from_state_id, to_state_id) if s]).values_list("id", "name")
    )
    from_name = names.get(_valid_uuid(from_state_id), "this state") if from_state_id else "no state"
    to_name = names.get(_valid_uuid(to_state_id), "that state")
    effective_role = _role_value(role) if role is not None else get_effective_project_role(user, project_id)
    allowed_ids = allowed_target_state_ids(project_id, from_state_id, effective_role, epic=is_epic_issue(issue))
    raise StateTransitionNotAllowed(
        code=code,
        message=f"You can't move this work item from '{from_name}' to '{to_name}'.",
        from_state_id=from_state_id,
        to_state_id=to_state_id,
        allowed_state_ids=allowed_ids or [],
    )


def get_my_transitions(project_id, user):
    """Payload of GET .../state-transitions/me/ for `user` (UI gating of dropdowns and kanban).

    {"restricted": false} or {"restricted": true, "role", "epic_locked", "transitions":
    {from_state_id: [to_state_id, ...]}, "epic_transitions": {...}} where `transitions` applies to
    work items and `epic_transitions` to epics (empty lists when epic_locked).
    """
    role = get_effective_project_role(user, project_id)
    if role is None or role >= ADMIN:
        return {"restricted": False}
    pairs = _resolve_policy(project_id, role, epic=False)
    epic_pairs = _resolve_policy(project_id, role, epic=True)
    if pairs is None and epic_pairs is None:
        return {"restricted": False}
    state_ids = [str(state_id) for state_id in State.objects.filter(project_id=project_id).values_list("id", flat=True)]

    def build(policy):
        if policy is None:
            return {state_id: [other for other in state_ids if other != state_id] for state_id in state_ids}
        return {state_id: _targets(policy, state_id) for state_id in state_ids}

    return {
        "restricted": True,
        "role": role,
        "epic_locked": role == AGENT,
        "transitions": build(pairs),
        "epic_transitions": build(epic_pairs),
    }


# ------------------------------------------------------------------ standard states + seeding


def _repoint_state(source, target):
    """Move every work item / draft from `source` to `target`; returns the moved work-item count."""
    issues = Issue.all_objects.filter(state_id=source.id)
    if target.group == StateGroup.COMPLETED.value:
        moved = issues.update(state_id=target.id, completed_at=Coalesce(F("completed_at"), Now()))
    else:
        moved = issues.update(state_id=target.id, completed_at=None)
    DraftIssue.all_objects.filter(state_id=source.id).update(state_id=target.id)
    Project.all_objects.filter(default_state_id=source.id).update(default_state_id=target.id)
    return moved


def _remove_state(source):
    """Drop rules that reference `source`, then soft-delete it (queryset delete: no celery cascade,
    nothing points at it any more)."""
    StateTransition.all_objects.filter(Q(from_state_id=source.id) | Q(to_state_id=source.id)).delete()
    State.all_state_objects.filter(pk=source.pk).update(deleted_at=Now())


def ensure_standard_states(project):
    """Make the project's (non-triage) states the standard set, idempotently.

    - an existing state named exactly like a standard state, else one whose normalised name is an
      alias ("Todo" -> "To Do", "Cancelled" -> "Won't Fix"), is adopted and renamed in place (keeps
      its id, so work items and activity stay valid); missing ones are created
    - Backlog (and duplicate aliases) are merged: their work items move to To Do / the matching
      standard state, then the empty state is removed
    - To Do becomes the only default state; standard states get the standard group/order
    - any other custom state is left untouched
    Returns (states_by_key, summary).
    """
    summary = {"created": [], "renamed": [], "updated": [], "merged": {}}
    states = list(State.objects.filter(project_id=project.id).order_by("sequence", "created_at"))
    used = set()
    by_key = {}

    for spec in standard_state_specs():
        state = next((s for s in states if s.id not in used and s.name == spec["name"]), None)
        if state is None:
            state = next(
                (s for s in states if s.id not in used and normalize_state_name(s.name) in spec["aliases"]),
                None,
            )
        if state is None:
            state = State.objects.create(
                project=project,
                workspace_id=project.workspace_id,
                name=spec["name"],
                color=spec["color"],
                group=spec["group"],
                default=False,
            )
            State.all_state_objects.filter(pk=state.pk).update(sequence=spec["sequence"])
            state.sequence = spec["sequence"]
            summary["created"].append(spec["name"])
        else:
            fields = []
            if state.name != spec["name"]:
                summary["renamed"].append(f"{state.name} -> {spec['name']}")
                state.name = spec["name"]
                fields += ["name", "slug"]
                if state.color != spec["color"]:
                    state.color = spec["color"]
                    fields.append("color")
            elif (state.color or "").lower() in LEGACY_DEFAULT_COLORS and state.color != spec["color"]:
                state.color = spec["color"]
                fields.append("color")
            if state.group != spec["group"]:
                state.group = spec["group"]
                fields.append("group")
            if state.sequence != spec["sequence"]:
                state.sequence = spec["sequence"]
                fields.append("sequence")
            if fields:
                state.save(update_fields=[*fields, "updated_at"])
                if fields != ["sequence"]:
                    summary["updated"].append(spec["name"])
        used.add(state.id)
        by_key[spec["key"]] = state

    merge_into = {}
    for key, aliases in STANDARD_STATE_ALIASES.items():
        for alias in (*aliases, *STANDARD_STATE_MERGES.get(key, ())):
            merge_into.setdefault(alias, key)
    for state in states:
        if state.id in used:
            continue
        key = merge_into.get(normalize_state_name(state.name))
        if key is None or key not in by_key:
            continue
        summary["merged"][state.name] = _repoint_state(state, by_key[key])
        _remove_state(state)

    todo = by_key.get("todo")
    if todo is not None:
        State.objects.filter(project_id=project.id, default=True).exclude(pk=todo.pk).update(default=False)
        if not todo.default:
            State.all_state_objects.filter(pk=todo.pk).update(default=True)
            todo.default = True
    return by_key, summary


def seed_agent_transition_rules(project, states_by_key):
    """Idempotently make sure the Agent role (10) has the default rules To Do -> In Progress and
    In Progress -> In Review (exclude_epics=True). Returns the number of rules created or changed."""
    changed = 0
    for from_key, to_key in AGENT_DEFAULT_TRANSITIONS:
        from_state, to_state = states_by_key.get(from_key), states_by_key.get(to_key)
        if from_state is None or to_state is None:
            continue
        rule = StateTransition.objects.filter(
            project_id=project.id, from_state_id=from_state.id, to_state_id=to_state.id, exclude_epics=True
        ).first()
        if rule is None:
            StateTransition.objects.create(
                project=project,
                workspace_id=project.workspace_id,
                from_state=from_state,
                to_state=to_state,
                roles=[AGENT],
                exclude_epics=True,
            )
            changed += 1
            continue
        fields = []
        if AGENT not in (rule.roles or []):
            rule.roles = sorted({*(rule.roles or []), AGENT}, reverse=True)
            fields.append("roles")
        if not rule.is_active:
            rule.is_active = True
            fields.append("is_active")
        if fields:
            rule.save(update_fields=[*fields, "updated_at"])
            changed += 1
    return changed


def seed_project_workflow(project, *, enable=True):
    """Standard states + agent transition rules + Project.is_workflow_enabled for `project`.

    Called by run_project_created_hooks for every new project (states already standard there) and by
    the `apply_jira_workflow` / setup commands for existing projects. Idempotent. Returns a summary.
    """
    with transaction.atomic():
        states_by_key, summary = ensure_standard_states(project)
        summary["rules_changed"] = seed_agent_transition_rules(project, states_by_key)
        if enable and not project.is_workflow_enabled:
            Project.all_objects.filter(pk=project.pk).update(is_workflow_enabled=True)
            project.is_workflow_enabled = True
            summary["workflow_enabled"] = True
    return summary


# ------------------------------------------------------------------ rule replacement (settings page)


def replace_project_transitions(project, rules):
    """Replace all rules of `project` with `rules` (validated dicts: from_state_id | None,
    to_state_id, roles: list[int], exclude_epics: bool). Rules with the same (from, to, exclude_epics)
    are merged; rules without roles are dropped. Existing rows are updated in place (ids kept)."""
    merged = {}
    for rule in rules:
        roles = sorted({_role_value(r) for r in rule.get("roles") or []}, reverse=True)
        if not roles:
            continue
        key = (
            str(rule["from_state_id"]) if rule.get("from_state_id") else None,
            str(rule["to_state_id"]),
            bool(rule.get("exclude_epics", False)),
        )
        merged[key] = sorted({*merged.get(key, []), *roles}, reverse=True)

    with transaction.atomic():
        existing = {
            (str(r.from_state_id) if r.from_state_id else None, str(r.to_state_id), r.exclude_epics): r
            for r in StateTransition.objects.filter(project_id=project.id)
        }
        for key, rule in existing.items():
            if key not in merged:
                rule.delete(soft=False)
        for key, roles in merged.items():
            from_state_id, to_state_id, exclude_epics = key
            rule = existing.get(key)
            if rule is None:
                StateTransition.objects.create(
                    project=project,
                    workspace_id=project.workspace_id,
                    from_state_id=from_state_id,
                    to_state_id=to_state_id,
                    roles=roles,
                    exclude_epics=exclude_epics,
                    is_active=True,
                )
            elif rule.roles != roles or not rule.is_active:
                rule.roles = roles
                rule.is_active = True
                rule.save(update_fields=["roles", "is_active", "updated_at"])
    return list(StateTransition.objects.filter(project_id=project.id).order_by("created_at"))
