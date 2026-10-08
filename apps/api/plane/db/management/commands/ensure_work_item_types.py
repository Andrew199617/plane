# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity: idempotently seed/repair work item types.

    python manage.py ensure_work_item_types [--workspace <slug>] [--no-backfill]

For every (or one) workspace: the 5 standard types (Task default, Story, Bug, Sub-task, Epic),
ProjectIssueType rows + is_issue_type_enabled for every project, and a backfill of work items /
drafts without a type to the default type (bulk inserts bypass Issue.save).
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from plane.db.models import Workspace
from plane.utils.work_item_types import sync_workspace_work_item_types


class Command(BaseCommand):
    help = "Seed/repair the Jira-parity work item types for workspaces (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument("--workspace", type=str, help="Workspace slug (default: all workspaces)")
        parser.add_argument(
            "--no-backfill", action="store_true", help="Do not assign the default type to untyped work items"
        )

    def handle(self, *args, **options):
        workspaces = Workspace.objects.all().order_by("created_at")
        if options.get("workspace"):
            workspaces = workspaces.filter(slug=options["workspace"])
            if not workspaces.exists():
                raise CommandError(f"Workspace '{options['workspace']}' not found")

        for workspace in workspaces:
            with transaction.atomic():
                summary = sync_workspace_work_item_types(workspace, backfill=not options.get("no_backfill"))
            self.stdout.write(self.style.SUCCESS(f"{workspace.slug}: {summary}"))
