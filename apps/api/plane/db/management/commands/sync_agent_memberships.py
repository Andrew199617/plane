# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity: make every agent (workspace role 10) an Agent member of every non-archived project.

    python manage.py sync_agent_memberships [--workspace <slug>]

Idempotent. Run after bulk project creation (e.g. the Jira import) where the project-created hooks
did not run. Without --workspace, every workspace is synced.
"""

# Django imports
from django.core.management import BaseCommand, CommandError

# Module imports
from plane.db.models import Workspace
from plane.utils.agent import auto_join_enabled, sync_agent_memberships


class Command(BaseCommand):
    help = "Add every agent account to every non-archived project of its workspace (role Agent)"

    def add_arguments(self, parser):
        parser.add_argument("--workspace", type=str, default=None, help="Workspace slug (default: all)")

    def handle(self, *args, **options):
        if not auto_join_enabled():
            self.stdout.write(self.style.WARNING("AGENT_AUTO_JOIN_PROJECTS=0: nothing to do"))
            return
        workspaces = Workspace.objects.all()
        if options["workspace"]:
            workspaces = workspaces.filter(slug=options["workspace"])
            if not workspaces.exists():
                raise CommandError(f"Workspace '{options['workspace']}' not found")
        for workspace in workspaces:
            count = sync_agent_memberships(workspace)
            self.stdout.write(self.style.SUCCESS(f"{workspace.slug}: {count} agent project memberships ensured"))
