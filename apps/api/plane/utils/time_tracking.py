# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity time tracking (Issue.original_estimate / Issue.remaining_estimate, in minutes).

The estimates are plain Issue fields edited through the regular issue create/update
serializers (app + v1). This module holds the activity trackers registered in
`plane.bgtasks.issue_activities_task.update_issue_activity` and the shared helpers.

Activity rows use field "original_estimate" / "remaining_estimate", old_value/new_value as
the number of minutes (string; "" when unset), verb "updated" (value set or changed) or
"removed" (value cleared).
"""

# Module imports
from plane.db.models import IssueActivity

TIME_TRACKING_FIELDS = ("original_estimate", "remaining_estimate")


def normalize_estimate_minutes(value):
    """Coerce an estimate coming from a request / serialized instance to int minutes or None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        try:
            minutes = int(float(value))
        except (TypeError, ValueError):
            return None
    return minutes if minutes >= 0 else None


def _track_estimate(
    field,
    requested_data,
    current_instance,
    issue_id,
    project_id,
    workspace_id,
    actor_id,
    issue_activities,
    epoch,
):
    if field not in requested_data:
        return
    old_minutes = normalize_estimate_minutes((current_instance or {}).get(field))
    new_minutes = normalize_estimate_minutes(requested_data.get(field))
    if old_minutes == new_minutes:
        return
    label = field.replace("_", " ")
    issue_activities.append(
        IssueActivity(
            issue_id=issue_id,
            actor_id=actor_id,
            verb="removed" if new_minutes is None else "updated",
            old_value="" if old_minutes is None else str(old_minutes),
            new_value="" if new_minutes is None else str(new_minutes),
            field=field,
            project_id=project_id,
            workspace_id=workspace_id,
            comment=f"removed the {label}" if new_minutes is None else f"updated the {label} to ",
            epoch=epoch,
        )
    )


def track_original_estimate(
    requested_data,
    current_instance,
    issue_id,
    project_id,
    workspace_id,
    actor_id,
    issue_activities,
    epoch,
):
    _track_estimate(
        "original_estimate",
        requested_data,
        current_instance,
        issue_id,
        project_id,
        workspace_id,
        actor_id,
        issue_activities,
        epoch,
    )


def track_remaining_estimate(
    requested_data,
    current_instance,
    issue_id,
    project_id,
    workspace_id,
    actor_id,
    issue_activities,
    epoch,
):
    _track_estimate(
        "remaining_estimate",
        requested_data,
        current_instance,
        issue_id,
        project_id,
        workspace_id,
        actor_id,
        issue_activities,
        epoch,
    )
