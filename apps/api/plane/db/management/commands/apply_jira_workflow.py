# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity: convert projects to the standard workflow.

    python manage.py apply_jira_workflow --workspace <slug> [--project IDENT ...] [--no-enable]
        [--merge-existing-states] [--dry-run]

Per project (plane.utils.workflow.seed_project_workflow, idempotent):
- standard states To Do (default) / In Progress / In Review / Done / Won't Fix: "Todo" is renamed to
  "To Do", "Cancelled" to "Won't Fix"; Backlog and duplicate states are preserved by default
- --merge-existing-states moves Backlog/duplicate-state items into the standard states and removes
  those states; state-id filters are updated, but filters for the removed Backlog group become empty
- the Agent transition rules To Do -> In Progress and In Progress -> In Review
- Project.is_workflow_enabled = True (unless --no-enable)
"""

# Django imports
from django.core.management import BaseCommand, CommandError
from django.db import transaction

# Module imports
from plane.db.models import Project, Workspace
from plane.utils.workflow import seed_project_workflow


class _DryRun(Exception):
    pass


class Command(BaseCommand):
    help = "Apply the standard Jira-like states and agent transition rules to the projects of a workspace"

    def add_arguments(self, parser):
        parser.add_argument("--workspace", type=str, required=True, help="Workspace slug")
        parser.add_argument(
            "--project", action="append", default=None, help="Project identifier (repeatable; default: all)"
        )
        parser.add_argument("--no-enable", action="store_true", help="Do not set is_workflow_enabled")
        parser.add_argument(
            "--merge-existing-states",
            action="store_true",
            help="Merge Backlog and duplicate states (saved Backlog group filters may become empty)",
        )
        parser.add_argument("--dry-run", action="store_true", help="Report the changes and roll them back")

    def handle(self, *args, **options):
        workspace = Workspace.objects.filter(slug=options["workspace"]).first()
        if workspace is None:
            raise CommandError(f"Workspace '{options['workspace']}' not found")

        projects = Project.objects.filter(workspace=workspace).order_by("identifier")
        if options["project"]:
            identifiers = [identifier.upper() for identifier in options["project"]]
            projects = projects.filter(identifier__in=identifiers)
            missing = sorted(set(identifiers) - set(projects.values_list("identifier", flat=True)))
            if missing:
                raise CommandError(f"Projects not found: {', '.join(missing)}")

        summaries = {}
        try:
            with transaction.atomic():
                for project in projects:
                    summaries[project.identifier] = seed_project_workflow(
                        project,
                        enable=not options["no_enable"],
                        merge_existing_states=options["merge_existing_states"],
                    )
                if options["dry_run"]:
                    raise _DryRun()
        except _DryRun:
            self.stdout.write(self.style.WARNING("Dry run: no changes were saved"))

        for identifier, summary in summaries.items():
            changes = []
            if summary.get("created"):
                changes.append(f"created {', '.join(summary['created'])}")
            if summary.get("renamed"):
                changes.append(f"renamed {', '.join(summary['renamed'])}")
            if summary.get("updated"):
                changes.append(f"updated {', '.join(summary['updated'])}")
            for name, moved in (summary.get("merged") or {}).items():
                changes.append(f"merged '{name}' ({moved} work items)")
            if summary.get("rules_changed"):
                changes.append(f"{summary['rules_changed']} agent rules")
            if summary.get("workflow_enabled"):
                changes.append("workflow enabled")
            self.stdout.write(f"{identifier}: {'; '.join(changes) if changes else 'already standard'}")
        self.stdout.write(self.style.SUCCESS(f"{len(summaries)} projects processed"))
