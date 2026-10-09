# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-style releases (fix versions) for modules.

A module is a release: Unreleased until someone releases it (status "released"), with target_date as the release
date. Archiving is independent of the status. Releasing can move the release's unresolved work items to another
unreleased release, like Jira's "Release version" dialog.
"""

# Python imports
import datetime
import json
import uuid

import pytz

# Django imports
from django.db import transaction
from django.utils import timezone

# Module imports
from plane.bgtasks.issue_activities_task import issue_activity
from plane.db.models import Module, ModuleIssue
from plane.utils.host import base_host

RELEASE_UNRELEASED = "unreleased"
RELEASE_RELEASED = "released"

# State groups of work items that are still unresolved when a release ships.
UNRESOLVED_STATE_GROUPS = ("backlog", "unstarted", "started")


class ReleaseError(Exception):
    """A release rule was broken; rendered as a 400 `{error, code}`."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message

    def as_response_data(self):
        return {"error": self.message, "code": self.code}


def _parse_release_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError as error:
        raise ReleaseError("INVALID_DATE", "Release date must be a date (YYYY-MM-DD).") from error


def _project_today(module):
    tz_name = getattr(module.project, "timezone", None) or "UTC"
    return timezone.now().astimezone(pytz.timezone(tz_name)).date()


def _unresolved_module_issues(module):
    return ModuleIssue.objects.filter(
        module_id=module.id,
        issue__archived_at__isnull=True,
        issue__is_draft=False,
        issue__deleted_at__isnull=True,
        issue__state__group__in=UNRESOLVED_STATE_GROUPS,
    )


def _move_unresolved_issues(module, target, request, user):
    """Move the release's unresolved work items to `target`, logging the module activity. Returns the count."""
    issue_ids = [str(issue_id) for issue_id in _unresolved_module_issues(module).values_list("issue_id", flat=True)]
    if not issue_ids:
        return 0

    ModuleIssue.objects.bulk_create(
        [
            ModuleIssue(
                issue_id=issue_id,
                module_id=target.id,
                project_id=module.project_id,
                workspace_id=module.workspace_id,
                created_by=user,
                updated_by=user,
            )
            for issue_id in issue_ids
        ],
        batch_size=100,
        ignore_conflicts=True,
    )
    ModuleIssue.objects.filter(module_id=module.id, issue_id__in=issue_ids).delete()

    epoch = int(timezone.now().timestamp())
    origin = base_host(request=request, is_app=True)
    for issue_id in issue_ids:
        issue_activity.delay(
            type="module.activity.deleted",
            requested_data=json.dumps({"module_id": str(module.id)}),
            actor_id=str(user.id),
            issue_id=issue_id,
            project_id=str(module.project_id),
            current_instance=json.dumps({"module_name": module.name}),
            epoch=epoch,
            notification=True,
            origin=origin,
        )
        issue_activity.delay(
            type="module.activity.created",
            requested_data=json.dumps({"module_id": str(target.id)}),
            actor_id=str(user.id),
            issue_id=issue_id,
            project_id=str(module.project_id),
            current_instance=None,
            epoch=epoch,
            notification=True,
            origin=origin,
        )
    return len(issue_ids)


def release_module(module, release_date=None, move_to=None, request=None, user=None):
    """Mark the release as released. Returns the number of unresolved work items moved to `move_to`."""
    if module.archived_at is not None:
        raise ReleaseError("RELEASE_ARCHIVED", "Archived releases can't be released.")
    if module.status == RELEASE_RELEASED:
        raise ReleaseError("RELEASE_ALREADY_RELEASED", "This release is already released.")

    date = _parse_release_date(release_date) or module.target_date or _project_today(module)
    if module.start_date is not None and date < module.start_date:
        raise ReleaseError("INVALID_DATE", "The release date can't be before the start date.")

    target = None
    if move_to:
        if _is_uuid(move_to):
            target = (
                Module.objects.filter(project_id=module.project_id, pk=move_to, archived_at__isnull=True)
                .exclude(pk=module.pk)
                .first()
            )
        if target is None or target.status == RELEASE_RELEASED:
            raise ReleaseError(
                "INVALID_TARGET", "Unresolved work items can only move to another unreleased release of this project."
            )

    with transaction.atomic():
        moved = _move_unresolved_issues(module, target, request, user) if target is not None else 0
        module.status = RELEASE_RELEASED
        module.target_date = date
        module.save(update_fields=["status", "target_date", "updated_at"])
    return moved


def unrelease_module(module):
    if module.archived_at is not None:
        raise ReleaseError("RELEASE_ARCHIVED", "Restore this release before changing it.")
    if module.status != RELEASE_RELEASED:
        raise ReleaseError("RELEASE_NOT_RELEASED", "This release isn't released.")
    module.status = RELEASE_UNRELEASED
    module.save(update_fields=["status", "updated_at"])


def _is_uuid(value):
    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True
