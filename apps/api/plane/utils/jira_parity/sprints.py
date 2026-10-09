# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-style sprint lifecycle for cycles.

A cycle is a sprint that moves through explicit states instead of being driven by its dates:
- future: not started (status UPCOMING when it has planned dates, DRAFT otherwise)
- active: started_at is set (status CURRENT); at most one per project
- closed: completed_at is set (status COMPLETED); read-only, open work items were moved out

Every place that used to derive a cycle's status from start_date/end_date goes through this module.
"""

# Python imports
import json
import re
import uuid

import pytz

# Django imports
from django.db import transaction
from django.db.models import Case, CharField, Q, Value, When
from django.utils import timezone

# Module imports
from plane.bgtasks.issue_activities_task import issue_activity
from plane.db.models import Cycle, CycleIssue, Project
from plane.utils.cycle_transfer_issues import transfer_cycle_issues
from plane.utils.host import base_host

# Values returned by `.values(...)` in cycle payloads, next to the upstream fields.
SPRINT_FIELDS = ("started_at", "completed_at")

# State groups of work items that are still open when a sprint is completed.
OPEN_STATE_GROUPS = ("backlog", "unstarted", "started")

MOVE_TO_BACKLOG = "backlog"
MOVE_TO_NEW_SPRINT = "new"

_SPRINT_NAME_RE = re.compile(r"^(?P<series>.*\bsprint)\s*(?P<number>\d+)\s*$", re.IGNORECASE)


class SprintError(Exception):
    """A lifecycle rule was broken; rendered as a 400 `{error, code, **extra}`."""

    def __init__(self, code, message, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra

    def as_response_data(self):
        return {"error": self.message, "code": self.code, **self.extra}


def _field(prefix, name):
    return f"{prefix}{name}"


def sprint_status_case(prefix=""):
    """Annotation for the upper-case cycle status (COMPLETED / CURRENT / UPCOMING / DRAFT)."""
    return Case(
        When(**{_field(prefix, "completed_at__isnull"): False}, then=Value("COMPLETED")),
        When(**{_field(prefix, "started_at__isnull"): False}, then=Value("CURRENT")),
        When(
            **{_field(prefix, "start_date__isnull"): False, _field(prefix, "end_date__isnull"): False},
            then=Value("UPCOMING"),
        ),
        default=Value("DRAFT"),
        output_field=CharField(),
    )


def active_sprint_q(prefix=""):
    return Q(**{_field(prefix, "started_at__isnull"): False, _field(prefix, "completed_at__isnull"): True})


def closed_sprint_q(prefix=""):
    return Q(**{_field(prefix, "completed_at__isnull"): False})


def future_sprint_q(prefix=""):
    return Q(**{_field(prefix, "started_at__isnull"): True, _field(prefix, "completed_at__isnull"): True})


def sprint_status(cycle):
    if cycle.completed_at is not None:
        return "COMPLETED"
    if cycle.started_at is not None:
        return "CURRENT"
    if cycle.start_date is not None and cycle.end_date is not None:
        return "UPCOMING"
    return "DRAFT"


def is_sprint_closed(cycle):
    return cycle is not None and cycle.completed_at is not None


def is_sprint_active(cycle):
    return cycle is not None and cycle.started_at is not None and cycle.completed_at is None


def get_active_sprint(project_id, exclude_id=None):
    queryset = Cycle.objects.filter(project_id=project_id, archived_at__isnull=True).filter(active_sprint_q())
    if exclude_id is not None:
        queryset = queryset.exclude(pk=exclude_id)
    return queryset.order_by("started_at").first()


def parse_sprint_name(name):
    """'LGD Sprint 4' -> ('LGD Sprint', 4); names without a trailing sprint number -> (name, None)."""
    name = (name or "").strip()
    match = _SPRINT_NAME_RE.match(name)
    if not match:
        return name, None
    return match.group("series").strip(), int(match.group("number"))


def next_sprint_name(project):
    """Continue the project's newest numbered sprint series ("LGD Sprint 4" -> "LGD Sprint 5").

    Archived and deleted sprints count, so numbers are never reused. Projects without numbered sprints start
    at "<IDENTIFIER> Sprint 1".
    """
    best = None
    names = Cycle.all_objects.filter(project_id=project.id).order_by("created_at").values_list("name", flat=True)
    for name in names:
        series, number = parse_sprint_name(name)
        if number is None:
            continue
        # Highest number wins; ties go to the newest series name.
        if best is None or number >= best[1]:
            best = (series, number)
    if best is None:
        return f"{project.identifier} Sprint 1"
    return f"{best[0]} {best[1] + 1}"


def validate_sprint_update(cycle, data):
    """Rules for PATCHing a cycle outside the start/complete actions. Returns the data to save."""
    if is_sprint_closed(cycle):
        if "sort_order" in data:
            return {"sort_order": data.get("sort_order", cycle.sort_order)}
        raise SprintError("SPRINT_COMPLETED", "This sprint is completed, so it can't be edited.")
    if is_sprint_active(cycle):
        for field in ("start_date", "end_date"):
            if field in data and not data.get(field):
                raise SprintError("INVALID_DATES", "An active sprint needs a start date and an end date.")
    return data


def _write_serializer(cycle, data):
    # Imported lazily: plane.app.serializers imports views-level modules.
    from plane.app.serializers import CycleWriteSerializer

    return CycleWriteSerializer(cycle, data=data, partial=True, context={"project_id": cycle.project_id})


def start_sprint(cycle, data):
    """Start a future sprint. `data` may carry name, description (the sprint goal), start_date and end_date."""
    if cycle.archived_at is not None:
        raise SprintError("SPRINT_ARCHIVED", "Archived sprints can't be started.")
    if is_sprint_closed(cycle):
        raise SprintError("SPRINT_COMPLETED", "This sprint is already completed.")
    if is_sprint_active(cycle):
        raise SprintError("SPRINT_ALREADY_STARTED", "This sprint has already started.")

    payload = {key: data[key] for key in ("name", "description", "start_date", "end_date") if key in data}
    # The write serializer only converts dates to the project's day boundaries when both are sent.
    project_tz = Project.objects.filter(pk=cycle.project_id).values_list("timezone", flat=True).first()
    payload.setdefault("start_date", _local_date(cycle.start_date, project_tz))
    payload.setdefault("end_date", _local_date(cycle.end_date, project_tz))
    if not payload.get("start_date") or not payload.get("end_date"):
        raise SprintError("INVALID_DATES", "Choose a start date and an end date to start the sprint.")

    serializer = _write_serializer(cycle, payload)
    if not serializer.is_valid():
        errors = serializer.errors
        messages = [msg for msgs in errors.values() for msg in (msgs if isinstance(msgs, list) else [msgs])]
        message = "; ".join(str(msg) for msg in messages)
        raise SprintError("INVALID_DATES", message or "Invalid sprint details.", errors=errors)

    with transaction.atomic():
        # Lock the project's cycles so two concurrent starts can't both pass the one-active check.
        list(Cycle.objects.select_for_update().filter(project_id=cycle.project_id).values_list("id", flat=True))
        active = get_active_sprint(cycle.project_id, exclude_id=cycle.id)
        if active is not None:
            raise SprintError(
                "ACTIVE_SPRINT_EXISTS",
                f"Complete {active.name} before starting another sprint.",
                active_sprint={"id": str(active.id), "name": active.name},
            )
        cycle = serializer.save()
        cycle.started_at = timezone.now()
        cycle.save(update_fields=["started_at", "updated_at"])
    return cycle


def _remove_open_issues_from_sprint(cycle, request, user_id):
    """Move the sprint's open work items to the backlog (no sprint). Returns the number moved."""
    cycle_issues = CycleIssue.objects.filter(
        cycle_id=cycle.id,
        issue__archived_at__isnull=True,
        issue__is_draft=False,
        issue__state__group__in=OPEN_STATE_GROUPS,
    )
    issue_ids = [str(issue_id) for issue_id in cycle_issues.values_list("issue_id", flat=True)]
    if not issue_ids:
        return 0
    epoch = int(timezone.now().timestamp())
    origin = base_host(request=request, is_app=True)
    for issue_id in issue_ids:
        issue_activity.delay(
            type="cycle.activity.deleted",
            requested_data=json.dumps({"cycle_id": str(cycle.id), "cycle_name": cycle.name, "issues": [issue_id]}),
            actor_id=str(user_id),
            issue_id=issue_id,
            project_id=str(cycle.project_id),
            current_instance=None,
            epoch=epoch,
            notification=True,
            origin=origin,
        )
    CycleIssue.objects.filter(cycle_id=cycle.id, issue_id__in=issue_ids).delete()
    return len(issue_ids)


def _count_open_issues(cycle):
    return CycleIssue.objects.filter(
        cycle_id=cycle.id,
        issue__archived_at__isnull=True,
        issue__is_draft=False,
        issue__state__group__in=OPEN_STATE_GROUPS,
    ).count()


def complete_sprint(cycle, move_to, request, user):
    """Complete an active sprint, moving its open work items to the backlog, a new sprint or a future sprint.

    Returns {"cycle": Cycle, "moved_issues": int, "moved_to": Cycle | None, "new_sprint": Cycle | None}.
    """
    if not is_sprint_active(cycle):
        if is_sprint_closed(cycle):
            raise SprintError("SPRINT_COMPLETED", "This sprint is already completed.")
        raise SprintError("SPRINT_NOT_STARTED", "Start this sprint before completing it.")

    move_to = str(move_to or MOVE_TO_BACKLOG)
    target = None
    if move_to not in (MOVE_TO_BACKLOG, MOVE_TO_NEW_SPRINT):
        if _is_uuid(move_to):
            target = (
                Cycle.objects.filter(project_id=cycle.project_id, pk=move_to, archived_at__isnull=True)
                .exclude(pk=cycle.pk)
                .first()
            )
        if target is None or target.started_at is not None or target.completed_at is not None:
            raise SprintError("INVALID_TARGET", "Open work items can only move to a future sprint of this project.")

    new_sprint = None
    with transaction.atomic():
        open_issues = _count_open_issues(cycle)
        if open_issues and move_to == MOVE_TO_NEW_SPRINT:
            project = Project.objects.get(pk=cycle.project_id)
            new_sprint = Cycle.objects.create(
                name=next_sprint_name(project),
                project_id=cycle.project_id,
                workspace_id=cycle.workspace_id,
                owned_by=user,
                timezone=cycle.timezone,
            )
            target = new_sprint
        if not open_issues or move_to == MOVE_TO_BACKLOG:
            target = None

        # Writes the progress snapshot (frozen burndown and stats); with a target it also moves the open work
        # items there. Without one it only snapshots and the open work items go back to the backlog below.
        result = transfer_cycle_issues(
            slug=cycle.workspace.slug,
            project_id=cycle.project_id,
            cycle_id=cycle.id,
            new_cycle_id=target.id if target is not None else None,
            request=request,
            user_id=user.id,
        )
        if not result.get("success"):
            raise SprintError("INVALID_TARGET", result.get("error") or "Couldn't move the open work items.")
        moved_issues = open_issues if target is not None else _remove_open_issues_from_sprint(cycle, request, user.id)

        cycle.refresh_from_db()
        cycle.completed_at = timezone.now()
        cycle.save(update_fields=["completed_at", "updated_at"])

    return {"cycle": cycle, "moved_issues": moved_issues, "moved_to": target, "new_sprint": new_sprint}


def _local_date(value, tz_name):
    """ISO date of a stored UTC datetime in the project's timezone (None stays None)."""
    if value is None:
        return None
    return value.astimezone(pytz.timezone(tz_name or "UTC")).date().isoformat()


def _is_uuid(value):
    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True
