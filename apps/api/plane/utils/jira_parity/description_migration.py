# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity: an editor "migration" save of a description is not an edit.

When the web app opens a work item whose description the rich-text editor did not write itself
(imported from Jira, created through the public API, ...), the editor only adds its node ids and
saves the result back with `skip_activity` ("uniqueIdOnlyChange"). Upstream already skips the
activity for that save, but `serializer.save()` still bumps `updated_at`/`updated_by`, so simply
viewing an imported work item once replaced Jira's "Updated" timestamp with "now".

The issue PATCH view snapshots the audit fields before such a save and restores them afterwards.
"""

# Fields the editor sends on a migration save (anything else in the payload is a real edit).
DESCRIPTION_FIELDS = frozenset({"description_html", "description_json", "description_binary", "description_stripped"})

_FALSE_VALUES = {"", "0", "false", "no", "off", "none", "null"}


def is_description_migration_update(data, skip_activity):
    """True when the request is an editor id-only description save (and nothing else).

    `data` is the request payload without `skip_activity` (the view pops it first).
    """
    if skip_activity is None or skip_activity is False:
        return False
    if isinstance(skip_activity, str) and skip_activity.strip().lower() in _FALSE_VALUES:
        return False
    try:
        keys = set(data.keys())
    except AttributeError:
        return False
    return "description_html" in keys and keys <= DESCRIPTION_FIELDS


def audit_snapshot(instance):
    """The audit fields a migration save must not change."""
    return {"updated_at": instance.updated_at, "updated_by_id": instance.updated_by_id}


def restore_audit_fields(model, pk, snapshot):
    """Put the audit fields back after save() (QuerySet.update bypasses auto_now)."""
    if snapshot:
        model._base_manager.filter(pk=pk).update(**snapshot)
