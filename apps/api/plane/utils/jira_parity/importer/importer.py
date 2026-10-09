# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira CSV -> Plane importer (management command `import_jira_csv`).

Pure ORM, no celery. `JiraCsvImporter.plan()` validates everything without writing; `run()` writes
and must be called inside a transaction with crum impersonating the acting admin (the command does
both). Identity of an imported work item = (project, external_source="jira", external_id=Jira
"Issue id"); re-running skips existing items, items deleted in Plane since an earlier import are not
recreated (nor are their sub-work-items), and a project holding non-Jira work items is refused.

Passes:
  0. workspace work item types, categories, projects (API create semantics + project-created
     hooks), memberships, cycles (one global date plan: same sprint name = same dates everywhere)
  1. work items in hierarchy order (parents first, so parent_id is set at creation; cross-project
     parents allowed), Jira number forced onto sequence_id + IssueSequence
  2. relations (+ relates_to for cross-project parents), cycle items, assignees, watchers, labels,
     comments, activity
  3. Rank -> sort_order and historical timestamps (QuerySet.update, after every save())
"""

# Python imports
import importlib
import logging
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, time

# Third party imports
import pytz

# Django imports
from django.db import connection, transaction
from django.db.models import F, Max, Q
from django.utils import timezone

# Module imports
from plane.db.models import (
    Cycle,
    CycleIssue,
    Issue,
    IssueActivity,
    IssueAssignee,
    IssueComment,
    IssueLabel,
    IssueRelation,
    IssueSequence,
    IssueSubscriber,
    IssueType,
    Label,
    Project,
    State,
    User,
    WorkspaceMember,
)
from plane.db.models.issue import PRIORITY_CHOICES
from plane.db.models.project import ROLE
from plane.utils.project_membership import ensure_project_member
from plane.utils.uuid import convert_uuid_to_integer

from ..wiki_markup import description_fields, jira_wiki_to_html
from .config import JiraParityConfig
from .constants import IMPORTED_PROJECT_FLAGS, JIRA_EXTERNAL_SOURCE
from .csv_reader import (
    ISSUE_KEY_RE,
    JiraCsvError,
    parse_jira_date,
    parse_jira_datetime,
    parse_seconds_as_minutes,
)
from .mapping import (
    map_priority,
    normalize_issue_type,
    normalize_status,
    parse_link_header,
    plan_sprint_dates,
    rank_positions,
    relation_for_link,
    status_category_group,
)
from .projects import ProjectCreateError, create_project_like_api, ensure_categories

logger = logging.getLogger("plane.api")

SORT_ORDER_START = 65535
SORT_ORDER_STEP = 10000
SYMMETRIC_RELATIONS = {"relates_to", "duplicate"}

# Workspace work item types the importer can fall back to creating when the work-item-types
# feature has not provisioned any (only happens before that feature is deployed).
_FALLBACK_TYPES = (
    {"name": "Task", "is_default": True},
    {"name": "Story"},
    {"name": "Bug"},
    {"name": "Sub-task", "is_sub_task": True},
    {"name": "Epic", "is_epic": True},
)


class JiraImportError(Exception):
    """Validation/plan failure; nothing has been written when raised from plan()."""

    def __init__(self, messages):
        self.messages = messages if isinstance(messages, list) else [messages]
        super().__init__("\n".join(self.messages))


@dataclass
class ProjectPlan:
    key: str
    rows: list
    name: str = ""
    description: str = ""
    category_name: str = ""
    logo_props: dict = field(default_factory=dict)
    lead: object = None
    project: object = None
    created: bool = False
    existing_issues: dict = field(default_factory=dict)  # Jira key -> Issue (already imported)
    deleted_issues: dict = field(default_factory=dict)  # Jira key -> Issue (imported, then deleted in Plane)
    rows_to_create: list = field(default_factory=list)
    sprints: set = field(default_factory=set)
    stats: Counter = field(default_factory=Counter)

    @property
    def exists(self):
        return self.project is not None and not self.created


class PersonResolver:
    """Jira person (account id / display name) -> Plane User.

    Order: explicit --user-map (account id, then name) -> workspace member whose full name, display
    name or e-mail matches -> the default user (recorded as unmapped). Only active workspace members
    are ever returned (a mapped e-mail outside the workspace counts as unmapped).
    """

    def __init__(self, workspace, default_user, user_map=None):
        self.default_user = default_user
        self.user_map = {str(k).strip().lower(): v for k, v in (user_map or {}).items()}
        self.unmapped = Counter()
        self._cache = {}
        members = (
            User.objects.filter(
                member_workspace__workspace_id=workspace.id,
                member_workspace__is_active=True,
                member_workspace__deleted_at__isnull=True,
                is_active=True,
            )
            .distinct()
            .order_by("date_joined")
        )
        self._members = list(members)
        self.workspace_roles = dict(
            WorkspaceMember.objects.filter(workspace_id=workspace.id, is_active=True).values_list("member_id", "role")
        )

    def _from_map(self, token):
        email = self.user_map.get((token or "").strip().lower())
        if not email:
            return None
        return next((u for u in self._members if u.email.lower() == str(email).strip().lower()), None)

    def _match_member(self, name):
        name = (name or "").strip().lower()
        if not name:
            return None
        for user in self._members:
            full_name = f"{user.first_name} {user.last_name}".strip().lower()
            if name in (full_name, (user.display_name or "").lower(), user.email.lower()):
                return user
        return None

    def resolve(self, name, account_id=None, *, default=True):
        cache_key = ((name or "").strip(), (account_id or "").strip())
        if cache_key in self._cache:
            user = self._cache[cache_key]
        else:
            user = self._from_map(account_id) or self._from_map(name) or self._match_member(name)
            self._cache[cache_key] = user
        if user is None and (name or account_id):
            self.unmapped[name or account_id] += 1
            return self.default_user if default else None
        if user is None:
            return self.default_user if default else None
        return user

    def mention(self, identifier):
        """wiki_markup mention resolver: 'accountid:XYZ' or 'username' -> (user_id, display_name)."""
        token = identifier.split(":", 1)[1] if identifier.lower().startswith("accountid:") else identifier
        user = self._from_map(token) or self._match_member(token)
        if user is None:
            return None
        return str(user.id), user.display_name


class JiraCsvImporter:
    def __init__(
        self,
        workspace,
        actor,
        rows,
        *,
        timezone_name="UTC",
        today=None,
        user_map=None,
        skip_projects=(),
        only_projects=None,
        config=None,
    ):
        self.workspace = workspace
        # Workspace-specific project names/categories/logos and name replacements (--config).
        self.config = config if config is not None else JiraParityConfig()
        self.actor = actor
        self.all_rows = rows
        self.timezone_name = timezone_name or "UTC"
        self.tz = pytz.timezone(self.timezone_name)
        # Sprint plan anchor: today in the user's timezone (the one the CSV timestamps are read in).
        self.today = today or timezone.now().astimezone(self.tz).date()
        self.skip_projects = {key.strip().upper() for key in skip_projects if key and key.strip()}
        self.only_projects = {key.strip().upper() for key in only_projects} if only_projects else None
        self.people = PersonResolver(workspace, actor, user_map)

        self.plans = OrderedDict()
        self.rows_by_key = {}
        self.issues_by_key = {}
        self.created_keys = set()
        self.sprint_dates = {}
        self.warnings = []
        self.type_map = {}
        self.cycles = {}
        self.stats = Counter()
        self._planned = False
        self._has_run = False

    # ================================================================ planning (read-only)

    def _warn(self, message):
        self.warnings.append(message)

    def _selected_rows(self):
        rows_by_id = OrderedDict()
        errors = []
        for row in self.all_rows:
            key = row.key
            if not ISSUE_KEY_RE.match(key or ""):
                errors.append(f"{row.source}:{row.line}: invalid Issue key {key!r}")
                continue
            project_column = row.get("Project key").upper()
            if project_column and project_column != row.project_key:
                self._warn(f"{key}: Project key column {project_column!r} differs from the issue key; using the key")
            identity = row.issue_id or key
            if identity in rows_by_id:
                self._warn(f"{key}: duplicate row (Issue id {identity}); the last one wins")
            rows_by_id[identity] = row
        if errors:
            raise JiraImportError(errors)

        selected = []
        seen_keys = {}
        for row in rows_by_id.values():
            if row.key in seen_keys:
                raise JiraImportError(f"{row.key}: two different Jira issue ids use this key")
            seen_keys[row.key] = row
            if row.project_key in self.skip_projects:
                continue
            if self.only_projects is not None and row.project_key not in self.only_projects:
                continue
            selected.append(row)
        return selected

    def plan(self):
        if self._planned:
            return self.plans
        selected = self._selected_rows()
        if not selected:
            raise JiraImportError("No Jira rows left to import (check --skip-projects/--projects).")

        sprint_names = {name for row in self.all_rows for name in row.get_all("Sprint")}
        self.sprint_dates = plan_sprint_dates(sprint_names, self.today)

        by_project = OrderedDict()
        for row in sorted(selected, key=lambda r: (r.project_key, r.number)):
            by_project.setdefault(row.project_key, []).append(row)
            self.rows_by_key[row.key] = row

        errors = []
        for key, rows in by_project.items():
            plan = self._plan_project(key, rows, errors)
            self.plans[key] = plan
        if errors:
            raise JiraImportError(errors)

        self._select_rows_to_create()
        self._validate_values()
        self._planned = True
        return self.plans

    def _plan_project(self, key, rows, errors):
        first = rows[0]
        spec = self.config.projects.get(key)
        plan = ProjectPlan(key=key, rows=rows)
        plan.name = (spec.name if spec else "") or self.config.rename(first.get("Project name") or key)
        plan.description = self.config.rename(
            next((r.get("Project description") for r in rows if r.get("Project description")), "")
        )
        plan.category_name = spec.category if spec else ""
        plan.logo_props = spec.logo_props if spec else {}
        plan.lead = self.people.resolve(first.get("Project lead"), first.get("Project lead id"))

        project = Project.objects.filter(workspace_id=self.workspace.id, identifier=key).first()
        if project is not None:
            if project.archived_at is not None:
                errors.append(f"{key}: project is archived; unarchive it before importing")
            foreign_error = self._foreign_issues_error(key, project)
            if foreign_error:
                errors.append(foreign_error)
            plan.project = project
            # soft-deleted items too (their number stays taken); live ones win over deleted duplicates
            existing = Issue.all_objects.filter(project_id=project.id, external_source=JIRA_EXTERNAL_SOURCE).order_by(
                F("deleted_at").desc(nulls_last=True)
            )
            by_external, by_sequence = {}, {}
            for issue in existing:
                by_external[issue.external_id] = issue
                by_sequence[issue.sequence_id] = issue
            for row in rows:
                issue = by_external.get(row.issue_id) or by_sequence.get(row.number)
                if issue is None:
                    continue
                if issue.deleted_at is not None:
                    plan.deleted_issues[row.key] = issue
                else:
                    plan.existing_issues[row.key] = issue
                    self.issues_by_key[row.key] = issue
        elif Project.objects.filter(workspace_id=self.workspace.id, name=plan.name).exists():
            errors.append(f"{key}: a project named {plan.name!r} already exists with another identifier")
        return plan

    def _foreign_issues_error(self, key, project):
        foreign = Issue.objects.filter(project_id=project.id).exclude(external_source=JIRA_EXTERNAL_SOURCE)
        foreign_count = foreign.count()
        if not foreign_count:
            return None
        sample = ", ".join(
            f"{key}-{seq}" for seq in foreign.order_by("sequence_id").values_list("sequence_id", flat=True)[:5]
        )
        return (
            f"{key}: project already has {foreign_count} work item(s) not imported from Jira ({sample}); "
            "refusing to import into it"
        )

    def _select_rows_to_create(self):
        """Rows not imported yet. Items deleted in Plane after an earlier import are not recreated, and
        neither are their sub-work-items (deleting a work item in Plane deletes its sub-work-items)."""
        for plan in self.plans.values():
            plan.rows_to_create = []
            for row in plan.rows:
                if row.key in plan.existing_issues:
                    continue
                if row.key in plan.deleted_issues:
                    self._warn(f"{row.key}: deleted in Plane after an earlier import; not recreated")
                    continue
                deleted_ancestor = self._deleted_ancestor(row)
                if deleted_ancestor:
                    self._warn(
                        f"{row.key}: not imported, {deleted_ancestor} (its parent or an ancestor) was deleted in Plane"
                    )
                    continue
                plan.rows_to_create.append(row)
            for row in plan.rows_to_create:
                sprints = row.get_all("Sprint")
                if sprints:
                    plan.sprints.add(sprints[-1])

    def _deleted_ancestor(self, row):
        """Key of the nearest ancestor of `row` deleted in Plane after an earlier import (looking past
        ancestors that are still to be imported), or ""."""
        trail = {row.key}
        parent_key = self._parent_key(row)
        while parent_key and parent_key not in trail:
            if self._is_deleted_in_plane(parent_key):
                return parent_key
            parent_row = self.rows_by_key.get(parent_key)
            if parent_row is None or parent_key in self.issues_by_key:
                return ""
            trail.add(parent_key)
            parent_key = self._parent_key(parent_row)
        return ""

    def _is_deleted_in_plane(self, key):
        row = self.rows_by_key.get(key)
        if row is not None:
            plan = self.plans.get(row.project_key)
            return plan is not None and key in plan.deleted_issues
        match = ISSUE_KEY_RE.match(key or "")
        if not match or self._find_existing_issue(key) is not None:
            return False
        return Issue.all_objects.filter(
            workspace_id=self.workspace.id,
            project__identifier=match.group(1),
            sequence_id=int(match.group(2)),
            external_source=JIRA_EXTERNAL_SOURCE,
            deleted_at__isnull=False,
        ).exists()

    def _validate_values(self):
        errors = []
        for plan in self.plans.values():
            for row in plan.rows_to_create:
                for column in ("Created", "Updated", "Resolved", "Status category changed"):
                    try:
                        parse_jira_datetime(row.get(column), self.timezone_name)
                    except JiraCsvError as e:
                        errors.append(f"{row.key}: {column}: {e}")
                for column in ("Due date", "Custom field (Start date)"):
                    try:
                        parse_jira_date(row.get(column))
                    except (JiraCsvError, ValueError) as e:
                        errors.append(f"{row.key}: {column}: {e}")
                for column in ("Original estimate", "Remaining Estimate"):
                    try:
                        parse_seconds_as_minutes(row.get(column))
                    except JiraCsvError as e:
                        errors.append(f"{row.key}: {column}: {e}")
                parent_key = self._parent_key(row)
                if parent_key and parent_key not in self.rows_by_key and not self._find_existing_issue(parent_key):
                    self._warn(f"{row.key}: parent {parent_key} is not part of this import; parent left empty")
        if errors:
            raise JiraImportError(errors)

    # ================================================================ helpers

    def _parent_key(self, row):
        parent_key = row.get("Parent key")
        if parent_key:
            return parent_key
        parent_id = row.get("Parent")
        if parent_id:
            for candidate in self.all_rows:
                if candidate.issue_id == parent_id:
                    return candidate.key
        return ""

    def _find_existing_issue(self, key):
        if key in self.issues_by_key:
            return self.issues_by_key[key]
        match = ISSUE_KEY_RE.match(key or "")
        if not match:
            return None
        issue = (
            Issue.objects.filter(
                workspace_id=self.workspace.id,
                project__identifier=match.group(1),
                sequence_id=int(match.group(2)),
            )
            .order_by("created_at")
            .first()
        )
        if issue is not None:
            self.issues_by_key[key] = issue
        return issue

    def _dt(self, row, column):
        return parse_jira_datetime(row.get(column), self.timezone_name)

    def _hierarchy_depths(self):
        depths = {}

        def depth(key, trail=()):
            if key in depths:
                return depths[key]
            if key in trail:
                self._warn(f"{key}: circular parent chain; parent ignored")
                return 0
            row = self.rows_by_key.get(key)
            parent_key = self._parent_key(row) if row else ""
            value = depth(parent_key, trail + (key,)) + 1 if parent_key in self.rows_by_key else 0
            depths[key] = value
            return value

        for key in self.rows_by_key:
            depth(key)
        return depths

    # ================================================================ pass 0

    def _ensure_types(self):
        try:
            with transaction.atomic():
                module = importlib.import_module("plane.utils.work_item_types")
                module.ensure_workspace_work_item_types(self.workspace)
        except Exception as e:  # noqa: BLE001 - fall back to existing/fallback types below
            self._warn(f"ensure_workspace_work_item_types failed: {e}")

        types = list(IssueType.objects.filter(workspace_id=self.workspace.id))
        if not types:
            self._warn("No workspace work item types found; created fallback Task/Story/Bug/Sub-task/Epic types")
            for spec in _FALLBACK_TYPES:
                issue_type = IssueType(
                    workspace_id=self.workspace.id,
                    name=spec["name"],
                    is_default=spec.get("is_default", False),
                    is_epic=spec.get("is_epic", False),
                    is_sub_task=spec.get("is_sub_task", False),
                    external_source=JIRA_EXTERNAL_SOURCE,
                )
                issue_type.save(created_by_id=self.actor.id)
                types.append(issue_type)

        self.type_map = {issue_type.name.strip().lower(): issue_type for issue_type in types}
        self.default_type = next((t for t in types if t.is_default), None) or self.type_map.get("task")
        self.epic_type = next((t for t in types if t.is_epic), None)
        self.sub_task_type = next((t for t in types if getattr(t, "is_sub_task", False)), None)

    def _resolve_type(self, jira_type):
        name = normalize_issue_type(jira_type)
        issue_type = self.type_map.get(name)
        if issue_type is None and name == "epic":
            issue_type = self.epic_type
        if issue_type is None and name == "sub-task":
            issue_type = self.sub_task_type
        if issue_type is None:
            self.stats[f"type fallback: {jira_type or '(blank)'}"] += 1
            issue_type = self.default_type
        return issue_type

    def _ensure_projects(self):
        categories = {}
        if any(plan.project is None and plan.category_name for plan in self.plans.values()):
            created, _ = ensure_categories(self.workspace, self.config)
            categories = {name.casefold(): category for name, category in created.items()}
        for plan in self.plans.values():
            if plan.project is None:
                category = categories.get(plan.category_name.casefold()) if plan.category_name else None
                try:
                    project, hooks = create_project_like_api(
                        self.workspace,
                        self.actor,
                        name=plan.name,
                        identifier=plan.key,
                        description=plan.description,
                        project_lead=plan.lead,
                        logo_props=plan.logo_props,
                        category=category,
                        field_overrides={
                            **IMPORTED_PROJECT_FLAGS,
                            "external_source": JIRA_EXTERNAL_SOURCE,
                            "external_id": plan.key,
                        },
                    )
                except ProjectCreateError as e:
                    raise JiraImportError(str(e)) from e
                failed = [name for name, ok in hooks.items() if not ok]
                if failed:
                    self._warn(f"{plan.key}: project-created hooks failed: {', '.join(failed)}")
                plan.project = project
                plan.created = True
            else:
                self._ensure_standard_states(plan)
                if plan.sprints and not plan.project.cycle_view:
                    Project.objects.filter(pk=plan.project.pk).update(cycle_view=True)

            users = {plan.lead.id} if plan.lead else set()
            for row in plan.rows_to_create:
                for user in self._row_people(row):
                    users.add(user.id)
            for user_id in users:
                ensure_project_member(plan.project, user_id, self._project_role(plan, user_id), update_role=False)
            plan.state_map = {state.name.strip().lower(): state for state in State.objects.filter(project=plan.project)}
            plan.default_state = next((s for s in plan.state_map.values() if s.default), None)
            if plan.default_state is None and plan.state_map:
                plan.default_state = sorted(plan.state_map.values(), key=lambda s: s.sequence)[0]

    def _ensure_standard_states(self, plan):
        """Existing project: make sure it has the standard Jira states (workflow feature service)."""
        try:
            with transaction.atomic():
                module = importlib.import_module("plane.utils.workflow")
                module.ensure_standard_states(plan.project)
        except Exception as e:  # noqa: BLE001 - statuses then fall back to state groups
            self._warn(f"{plan.key}: could not ensure the standard states: {e}")

    def _project_role(self, plan, user_id):
        """Project lead -> Admin; others -> Member, capped by their workspace role (Agent/Guest)."""
        if plan.lead is not None and user_id == plan.lead.id:
            return ROLE.ADMIN.value
        workspace_role = self.people.workspace_roles.get(user_id, ROLE.MEMBER.value)
        return min(ROLE.MEMBER.value, workspace_role)

    def _row_people(self, row):
        people = []
        assignee = self._assignee(row)
        if assignee:
            people.append(assignee)
        people.extend(self._watchers(row))
        people.append(self._reporter(row))
        return people

    def _assignee(self, row):
        if not (row.get("Assignee") or row.get("Assignee Id")):
            return None
        return self.people.resolve(row.get("Assignee"), row.get("Assignee Id"))

    def _reporter(self, row):
        name = row.get("Reporter") or row.get("Creator")
        account = row.get("Reporter Id") or row.get("Creator Id")
        if not (name or account):
            return self.actor
        return self.people.resolve(name, account)

    def _watchers(self, row):
        names = row.get_all("Watchers")
        ids = row.get_all("Watchers Id")
        users = []
        for index in range(max(len(names), len(ids))):
            user = self.people.resolve(
                names[index] if index < len(names) else "", ids[index] if index < len(ids) else ""
            )
            if user and user not in users:
                users.append(user)
        return users

    def _resolve_state(self, plan, row):
        status = normalize_status(row.get("Status"))
        state = plan.state_map.get(status)
        if state is None:
            group = status_category_group(row.get("Status category"))
            candidates = [s for s in plan.state_map.values() if group and s.group == group]
            if group == "unstarted" and plan.default_state is not None:
                state = plan.default_state
            elif candidates:
                state = sorted(candidates, key=lambda s: s.sequence)[0]
            else:
                state = plan.default_state
            self.stats[f"status fallback: {row.get('Status') or '(blank)'} -> {state.name if state else '?'}"] += 1
        return state

    def _ensure_cycles(self):
        """One cycle per (project, sprint name) used by the imported rows.

        Dates come from the global plan, stored like the cycle API does (CycleWriteSerializer ->
        convert_to_utc): start = local 00:00:01, end = local 23:59 in the project timezone, so a
        sprint name has the same dates in every project of the same timezone.
        """
        for plan in self.plans.values():
            tz = pytz.timezone(plan.project.timezone or self.workspace.timezone or "UTC")
            for name in sorted(plan.sprints, key=lambda n: (self.sprint_dates[n][0], n)):
                cycle = (
                    Cycle.objects.filter(project_id=plan.project.id)
                    .filter(Q(external_source=JIRA_EXTERNAL_SOURCE, external_id=f"sprint:{name}") | Q(name=name))
                    .order_by("created_at")
                    .first()
                )
                if cycle is None:
                    start, end = self.sprint_dates[name]
                    cycle = Cycle(
                        name=name,
                        project=plan.project,
                        workspace_id=plan.project.workspace_id,
                        owned_by=plan.lead or self.actor,
                        start_date=tz.localize(datetime.combine(start, time(0, 0, 1))).astimezone(pytz.utc),
                        end_date=tz.localize(datetime.combine(end, time(23, 59))).astimezone(pytz.utc),
                        timezone=tz.zone,
                        external_source=JIRA_EXTERNAL_SOURCE,
                        external_id=f"sprint:{name}",
                    )
                    cycle.save(created_by_id=(plan.lead or self.actor).id)
                    plan.stats["cycles created"] += 1
                self.cycles[(plan.key, name)] = cycle

    # ================================================================ pass 1: work items

    def _lock_sequences(self):
        """Take each existing project's work item sequence lock (the advisory lock Issue.save takes,
        held until the import transaction ends) and re-check for non-Jira work items created since
        plan(): the forced Jira numbers must not collide with them."""
        errors = []
        for plan in self.plans.values():
            if not plan.rows_to_create or plan.created:
                continue
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [convert_uuid_to_integer(plan.project.id)])
            foreign_error = self._foreign_issues_error(plan.key, plan.project)
            if foreign_error:
                errors.append(foreign_error)
        if errors:
            raise JiraImportError(errors)

    def _create_issues(self):
        self._lock_sequences()
        depths = self._hierarchy_depths()
        pending = [
            (depths.get(row.key, 0), plan.key, row.number, plan, row)
            for plan in self.plans.values()
            for row in plan.rows_to_create
        ]
        valid_priorities = {key for key, _ in PRIORITY_CHOICES}
        for _, _, number, plan, row in sorted(pending, key=lambda item: item[:3]):
            reporter = self._reporter(row)
            parent_key = self._parent_key(row)
            parent = self._find_existing_issue(parent_key) if parent_key else None
            if parent_key and parent is None:
                plan.stats["parents missing"] += 1

            description = row.get_raw("Description")
            environment = row.get("Environment")
            if environment:
                description = f"{description}\n\nh3. Environment\n{environment}"

            start_date = parse_jira_date(row.get("Custom field (Start date)"))
            target_date = parse_jira_date(row.get("Due date"))
            if start_date and target_date and start_date > target_date:
                start_date = None

            priority = map_priority(row.get("Priority"), valid_priorities)
            if row.get("Priority") and priority != row.get("Priority").strip().lower():
                self.stats[f"priority fallback: {row.get('Priority')} -> {priority}"] += 1

            issue = Issue(
                project=plan.project,
                workspace_id=plan.project.workspace_id,
                name=(row.get("Summary") or row.key)[:255],
                state=self._resolve_state(plan, row),
                priority=priority,
                type=self._resolve_type(row.get("Issue Type")),
                parent=parent,
                start_date=start_date,
                target_date=target_date,
                original_estimate=parse_seconds_as_minutes(row.get("Original estimate")),
                remaining_estimate=parse_seconds_as_minutes(row.get("Remaining Estimate")),
                external_source=JIRA_EXTERNAL_SOURCE,
                external_id=row.issue_id or row.key,
                **description_fields(description, mention_resolver=self.people.mention),
            )
            issue.save(created_by_id=reporter.id)
            if issue.sequence_id != number:
                Issue.objects.filter(pk=issue.pk).update(sequence_id=number)
                IssueSequence.objects.filter(issue_id=issue.pk).update(sequence=number)
                issue.sequence_id = number
            self.issues_by_key[row.key] = issue
            self.created_keys.add(row.key)
            plan.stats["created"] += 1
            if parent is not None:
                plan.stats["parents"] += 1
                if parent.project_id != plan.project.id:
                    plan.stats["cross-project parents"] += 1
            self._check_type_rules(row, issue, parent)

    def _check_type_rules(self, row, issue, parent):
        """Jira data is kept as exported, but work-item-type rules the API enforces are reported."""
        issue_type = issue.type
        if getattr(issue_type, "is_sub_task", False) and parent is None:
            self._warn(f"{row.key}: Sub-task without a parent (the API requires one)")
        if parent is not None and getattr(parent.type, "is_sub_task", False):
            self._warn(f"{row.key}: parent {parent.project.identifier}-{parent.sequence_id} is a Sub-task")

    # ================================================================ pass 2: links

    def _create_links(self):
        relations = OrderedDict()
        for plan in self.plans.values():
            for row in plan.rows:
                for header, value in row.items_with_prefix(""):
                    parsed = parse_link_header(header)
                    if not parsed:
                        continue
                    direction, link_name = parsed
                    for other_key in [v.strip() for v in value.split(",") if v.strip()]:
                        issue_key, related_key, relation_type = relation_for_link(
                            direction, link_name, row.key, other_key
                        )
                        if relation_type in SYMMETRIC_RELATIONS:
                            issue_key, related_key = sorted((issue_key, related_key))
                        relations.setdefault((issue_key, related_key), relation_type)

        # Cross-project parents (e.g. ABC-12 -> XYZ-3) keep parent_id, but CE lists sub-work-items
        # per project only, so the pair is also related (visible from both sides).
        for plan in self.plans.values():
            for row in plan.rows_to_create:
                issue = self.issues_by_key[row.key]
                parent_key = self._parent_key(row)
                if parent_key and issue.parent_id and issue.parent.project_id != issue.project_id:
                    pair = tuple(sorted((row.key, parent_key)))
                    relations.setdefault(pair, "relates_to")

        for (issue_key, related_key), relation_type in relations.items():
            if issue_key not in self.created_keys and related_key not in self.created_keys:
                continue
            issue = self._find_existing_issue(issue_key)
            related = self._find_existing_issue(related_key)
            if issue is None or related is None or issue.pk == related.pk:
                self._warn(f"relation {issue_key} {relation_type} {related_key}: work item missing; skipped")
                continue
            exists = IssueRelation.objects.filter(
                Q(issue_id=issue.pk, related_issue_id=related.pk) | Q(issue_id=related.pk, related_issue_id=issue.pk)
            ).exists()
            if exists:
                continue
            relation = IssueRelation(
                issue=issue,
                related_issue=related,
                relation_type=relation_type,
                project_id=issue.project_id,
                workspace_id=issue.workspace_id,
            )
            relation.save(created_by_id=self.actor.id)
            plan = self.plans.get(self.rows_by_key[issue_key].project_key) if issue_key in self.rows_by_key else None
            if plan is not None:
                plan.stats["relations"] += 1
            created = [
                self._dt(self.rows_by_key[k], "Created") for k in (issue_key, related_key) if k in self.rows_by_key
            ]
            if created:
                IssueRelation.objects.filter(pk=relation.pk).update(created_at=max(created), updated_at=max(created))

        for plan in self.plans.values():
            for row in plan.rows_to_create:
                self._link_row(plan, row)

    def _link_row(self, plan, row):
        issue = self.issues_by_key[row.key]
        created_at = self._dt(row, "Created") or timezone.now()
        common = {"project_id": plan.project.id, "workspace_id": plan.project.workspace_id}

        sprints = row.get_all("Sprint")
        cycle = None
        if sprints:
            cycle = self.cycles.get((plan.key, sprints[-1]))
            if cycle is not None and not CycleIssue.objects.filter(issue_id=issue.pk).exists():
                CycleIssue.objects.bulk_create(
                    [CycleIssue(cycle=cycle, issue=issue, created_by_id=self.actor.id, **common)]
                )
                plan.stats["cycle items"] += 1
            else:
                cycle = None

        assignee = self._assignee(row)
        if assignee is not None:
            IssueAssignee.objects.bulk_create(
                [IssueAssignee(issue=issue, assignee=assignee, created_by_id=self.actor.id, **common)]
            )
            plan.stats["assignees"] += 1

        watchers = self._watchers(row)
        if watchers:
            IssueSubscriber.objects.bulk_create(
                [
                    IssueSubscriber(issue=issue, subscriber=user, created_by_id=self.actor.id, **common)
                    for user in watchers
                ]
            )
            plan.stats["watchers"] += len(watchers)

        for label_name in row.get_all("Labels"):
            label = Label.objects.filter(project_id=plan.project.id, name=label_name).first()
            if label is None:
                label = Label(name=label_name, project=plan.project, workspace_id=plan.project.workspace_id)
                label.save(created_by_id=self.actor.id)
            IssueLabel.objects.bulk_create(
                [IssueLabel(issue=issue, label=label, created_by_id=self.actor.id, **common)]
            )
            plan.stats["labels"] += 1

        for raw_comment in row.get_all("Comment"):
            self._create_comment(plan, issue, raw_comment, common)

        self._create_activity(plan, row, issue, created_at, common, cycle=cycle)

    def _create_comment(self, plan, issue, raw_comment, common):
        parts = raw_comment.split(";", 2)
        when, author, body = (parts + ["", "", ""])[:3] if len(parts) == 3 else ("", "", raw_comment)
        try:
            commented_at = parse_jira_datetime(when, self.timezone_name)
        except JiraCsvError:
            commented_at, body = None, raw_comment
        author_user = self.people.resolve("", author) if author else self.actor
        comment = IssueComment(
            issue=issue,
            actor=author_user,
            comment_html=jira_wiki_to_html(body, mention_resolver=self.people.mention),
            external_source=JIRA_EXTERNAL_SOURCE,
            **common,
        )
        comment.save(created_by_id=author_user.id)
        if commented_at:
            IssueComment.objects.filter(pk=comment.pk).update(created_at=commented_at, updated_at=commented_at)
            if comment.description_id:
                from plane.db.models import Description

                Description.objects.filter(pk=comment.description_id).update(
                    created_at=commented_at, updated_at=commented_at
                )
        plan.stats["comments"] += 1

    def _create_activity(self, plan, row, issue, created_at, common, cycle=None):
        """History rows in the formats of bgtasks/issue_activities_task (no celery, no notifications):
        'created the issue', the state change to a non-default state, and 'added cycle'."""
        reporter = self._reporter(row)
        activities = [
            (
                IssueActivity(
                    issue=issue,
                    verb="created",
                    comment="created the issue",
                    actor=reporter,
                    epoch=created_at.timestamp(),
                    **common,
                ),
                created_at,
            )
        ]
        state = issue.state
        default_state = plan.default_state
        if state is not None and default_state is not None and state.pk != default_state.pk:
            changed_at = self._dt(row, "Resolved") or self._dt(row, "Status category changed") or created_at
            activities.append(
                (
                    IssueActivity(
                        issue=issue,
                        verb="updated",
                        field="state",
                        old_value=default_state.name,
                        new_value=state.name,
                        old_identifier=default_state.id,
                        new_identifier=state.id,
                        comment="updated the state to",
                        actor=reporter,
                        epoch=changed_at.timestamp(),
                        **common,
                    ),
                    changed_at,
                )
            )
        if cycle is not None:
            activities.append(
                (
                    IssueActivity(
                        issue=issue,
                        verb="created",
                        field="cycles",
                        old_value="",
                        new_value=cycle.name,
                        new_identifier=cycle.id,
                        comment=f"added cycle {cycle.name}",
                        actor=reporter,
                        epoch=created_at.timestamp(),
                        **common,
                    ),
                    created_at,
                )
            )
        for activity, _ in activities:
            activity.created_by_id = reporter.id
        IssueActivity.objects.bulk_create([activity for activity, _ in activities])
        for activity, at in activities:
            IssueActivity.objects.filter(pk=activity.pk).update(created_at=at, updated_at=at)

    # ================================================================ pass 3: order + timestamps

    def _finalize(self):
        for plan in self.plans.values():
            positions = rank_positions([row.get("Custom field (Rank)") for row in plan.rows])
            sort_orders = {
                row.key: SORT_ORDER_START + position * SORT_ORDER_STEP for row, position in zip(plan.rows, positions)
            }
            for row in plan.rows_to_create:
                issue = self.issues_by_key[row.key]
                created_at = self._dt(row, "Created") or issue.created_at
                updated_at = self._dt(row, "Updated") or created_at
                completed_at = None
                if issue.state is not None and issue.state.group == "completed":
                    completed_at = self._dt(row, "Resolved") or self._dt(row, "Status category changed") or updated_at
                Issue.objects.filter(pk=issue.pk).update(
                    created_at=created_at,
                    updated_at=max(updated_at, created_at),
                    completed_at=completed_at,
                    sort_order=sort_orders[row.key],
                    created_by_id=self._reporter(row).id,
                )
                for model in (IssueAssignee, IssueSubscriber, CycleIssue, IssueLabel):
                    model.objects.filter(issue_id=issue.pk).update(created_at=created_at, updated_at=created_at)
                IssueSequence.objects.filter(issue_id=issue.pk).update(created_at=created_at, updated_at=created_at)

            max_sequence = IssueSequence.objects.filter(project_id=plan.project.id).aggregate(largest=Max("sequence"))[
                "largest"
            ]
            plan.stats["next sequence"] = (max_sequence or 0) + 1

    # ================================================================ entry point

    def run(self):
        """Write everything. Call inside transaction.atomic() with crum impersonating the actor."""
        self.plan()
        self._ensure_types()
        self._ensure_projects()
        self._ensure_cycles()
        self._create_issues()
        self._create_links()
        self._finalize()
        self._has_run = True
        unmapped = dict(self.people.unmapped)
        if unmapped:
            self._warn(
                "People not matched to a Plane user (imported as "
                f"{self.actor.email}): " + ", ".join(f"{name} x{count}" for name, count in unmapped.items())
            )
        for message, count in sorted(self.stats.items()):
            self._warn(f"{message} (x{count})")
        return self.plans

    # ================================================================ reporting

    def summary_rows(self):
        rows = []
        for plan in self.plans.values():
            stats = plan.stats
            rows.append(
                OrderedDict(
                    [
                        ("Key", plan.key),
                        ("Name", plan.project.name if plan.project else plan.name),
                        ("Category", plan.category_name or "-"),
                        ("Project", "created" if plan.created else ("exists" if plan.project else "new")),
                        ("Rows", len(plan.rows)),
                        ("Created", stats.get("created", 0) if self._ran else len(plan.rows_to_create)),
                        ("Skipped", len(plan.rows) - len(plan.rows_to_create)),
                        ("Parents", stats.get("parents", 0)),
                        ("X-proj", stats.get("cross-project parents", 0)),
                        ("Relations", stats.get("relations", 0)),
                        ("Cycles", ", ".join(sorted(plan.sprints)) or "-"),
                        ("In cycle", stats.get("cycle items", 0)),
                        ("Watchers", stats.get("watchers", 0)),
                        ("Next key", f"{plan.key}-{stats['next sequence']}" if stats.get("next sequence") else "-"),
                    ]
                )
            )
        return rows

    @property
    def _ran(self):
        return self._has_run

    def sprint_plan_rows(self):
        """[(sprint name, start date, end date, [project keys])] for the cycles this run uses."""
        used = {}
        for plan in self.plans.values():
            for name in plan.sprints:
                used.setdefault(name, []).append(plan.key)
        return [
            (name, self.sprint_dates[name][0], self.sprint_dates[name][1], sorted(keys))
            for name, keys in sorted(used.items(), key=lambda item: (self.sprint_dates[item[0]][0], item[0]))
        ]
