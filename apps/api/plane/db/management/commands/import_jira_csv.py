# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity: import a Jira CSV export (work items, hierarchy, links, sprints) into a workspace.

    python manage.py import_jira_csv --workspace <slug> --csv <path> [--csv <path> ...]
        [--dry-run] [--rollback] [--skip-projects KEY,KEY] [--projects KEY,KEY]
        [--user <email>] [--user-map "<jira id or name>=<email>" ...] [--timezone <tz>]
        [--today YYYY-MM-DD] [--config <path>]

- --config (or $JIRA_PARITY_CONFIG) names a workspace-specific JSON file with project names,
  categories, logos, skipped projects and name replacements (see
  plane/utils/jira_parity/importer/jira_parity.example.json). Without it projects are named from
  the CSV, get no category and nothing is skipped.

- Missing projects are created like the project-create API (creator membership, default states,
  project-created hooks: work item types, workflow, agents, teams, lead defaults).
- Work items keep their Jira keys (sequence ids, gaps included); the next new item continues
  after the highest key.
- Idempotent: work items already imported (same Jira issue id) are skipped; ones deleted in Plane
  since (and their sub-work-items) are reported, not recreated. A target project that holds work
  items NOT imported from Jira is refused.
- --dry-run validates and prints the plan without writing; --rollback runs the full import in one
  transaction and rolls it back at the end (safe test against a live database).
See plane.utils.jira_parity.importer.importer for the mapping details.
"""

# Python imports
from datetime import date

# Third party imports
import pytz
from crum import impersonate

# Django imports
from django.core.management import BaseCommand, CommandError
from django.db import transaction

# Module imports
from plane.db.models import User, Workspace, WorkspaceMember
from plane.db.models.project import ROLE
from plane.utils.jira_parity.importer.config import (
    CONFIG_ENV_VAR,
    TIMEZONE_ENV_VAR,
    JiraParityConfigError,
    load_config,
    resolve_timezone,
)
from plane.utils.jira_parity.importer.csv_reader import JiraCsvError, read_jira_csv
from plane.utils.jira_parity.importer.importer import JiraCsvImporter, JiraImportError
from plane.utils.jira_parity.importer.report import format_table, totals_row


class _RollbackRequested(Exception):
    """Raised inside the import transaction to roll it back (--rollback)."""


def _split_keys(value):
    return [key.strip().upper() for key in (value or "").split(",") if key.strip()]


class Command(BaseCommand):
    help = "Import a Jira CSV export into a workspace (idempotent; --dry-run / --rollback to test)"

    def add_arguments(self, parser):
        parser.add_argument("--workspace", type=str, required=True, help="Workspace slug")
        parser.add_argument(
            "--csv", type=str, action="append", required=True, help="Jira CSV export (repeatable; later files win)"
        )
        parser.add_argument("--dry-run", action="store_true", help="Validate and print the plan; write nothing")
        parser.add_argument(
            "--rollback", action="store_true", help="Run the full import in a transaction, then roll it back"
        )
        parser.add_argument(
            "--skip-projects",
            type=str,
            default=None,
            help="Comma-separated Jira project keys to skip (default: the config's skip_projects; '' = none)",
        )
        parser.add_argument("--projects", type=str, default="", help="Only import these Jira project keys")
        parser.add_argument("--user", type=str, default="", help="Acting admin e-mail (default: workspace owner)")
        parser.add_argument(
            "--user-map",
            type=str,
            action="append",
            default=[],
            help="Map a Jira account id or display name to a workspace member: '<jira>=<email>' (repeatable)",
        )
        parser.add_argument(
            "--timezone",
            type=str,
            default="",
            help=(
                f"Timezone of the CSV timestamps (default: ${TIMEZONE_ENV_VAR}, else the config's timezone, "
                "else the acting user's timezone when it is not UTC, else UTC)"
            ),
        )
        parser.add_argument(
            "--today", type=str, default="", help="Sprint plan anchor date YYYY-MM-DD (default: today, workspace tz)"
        )
        parser.add_argument(
            "--config",
            type=str,
            default="",
            help=f"Workspace-specific JSON config (default: ${CONFIG_ENV_VAR}; none = names from the CSV)",
        )

    # ------------------------------------------------------------------ helpers

    def _resolve_inputs(self, options):
        workspace = Workspace.objects.filter(slug=options["workspace"]).first()
        if workspace is None:
            raise CommandError(f"Workspace '{options['workspace']}' not found")

        if options["user"]:
            actor = User.objects.filter(email__iexact=options["user"].strip()).first()
            if actor is None:
                raise CommandError(f"User '{options['user']}' not found")
        else:
            actor = workspace.owner
        if not WorkspaceMember.objects.filter(
            workspace_id=workspace.id, member_id=actor.id, role=ROLE.ADMIN.value, is_active=True
        ).exists():
            raise CommandError(f"{actor.email} is not an active admin of workspace '{workspace.slug}'")

        try:
            config = load_config(options["config"])
        except JiraParityConfigError as e:
            raise CommandError(str(e)) from e

        timezone_name = resolve_timezone(options["timezone"], config, actor)
        if timezone_name not in pytz.all_timezones_set:
            raise CommandError(f"Unknown timezone '{timezone_name}'")

        today = None
        if options["today"]:
            try:
                today = date.fromisoformat(options["today"].strip())
            except ValueError as e:
                raise CommandError(f"--today must be YYYY-MM-DD: {e}") from e

        user_map = {}
        for entry in options["user_map"]:
            if "=" not in entry:
                raise CommandError(f"--user-map expects '<jira>=<email>', got '{entry}'")
            jira, email = entry.split("=", 1)
            user_map[jira.strip()] = email.strip()

        rows = []
        for path in options["csv"]:
            try:
                rows.extend(read_jira_csv(path).rows)
            except FileNotFoundError as e:
                raise CommandError(f"CSV not found: {path}") from e
            except JiraCsvError as e:
                raise CommandError(str(e)) from e

        return workspace, actor, config, timezone_name, today, user_map, rows

    def _print_report(self, importer, *, mode):
        rows = importer.summary_rows()
        numeric = ["Rows", "Created", "Skipped", "Parents", "X-proj", "Relations", "In cycle", "Watchers"]
        for line in format_table([*rows, totals_row(rows, "Key", numeric)]):
            self.stdout.write(line)

        sprint_rows = importer.sprint_plan_rows()
        if sprint_rows:
            self.stdout.write("")
            self.stdout.write("Sprints -> cycles (same dates in every project):")
            for line in format_table(
                [
                    {"Cycle": name, "Start": start.isoformat(), "End": end.isoformat(), "Projects": ", ".join(keys)}
                    for name, start, end, keys in sprint_rows
                ]
            ):
                self.stdout.write(line)

        if importer.warnings:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(f"{len(importer.warnings)} note(s):"))
            for message in importer.warnings:
                self.stdout.write(self.style.WARNING(f"  - {message}"))
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(mode))

    # ------------------------------------------------------------------ entry point

    def handle(self, *args, **options):
        if options["dry_run"] and options["rollback"]:
            raise CommandError("Use either --dry-run or --rollback, not both")
        workspace, actor, config, timezone_name, today, user_map, rows = self._resolve_inputs(options)
        if options["skip_projects"] is None:
            skip_projects = list(config.skip_projects)
        else:
            skip_projects = _split_keys(options["skip_projects"])

        importer = JiraCsvImporter(
            workspace,
            actor,
            rows,
            timezone_name=timezone_name,
            today=today,
            user_map=user_map,
            skip_projects=skip_projects,
            only_projects=_split_keys(options["projects"]) or None,
            config=config,
        )
        self.stdout.write(
            f"Workspace '{workspace.slug}' as {actor.email}; {len(rows)} CSV row(s); "
            f"timestamps read as {timezone_name}; sprints anchored on {importer.today.isoformat()}; "
            f"config {config.source or '(none)'}; skipping {', '.join(skip_projects) or 'nothing'}"
        )

        try:
            if options["dry_run"]:
                importer.plan()
                self._print_report(importer, mode="DRY RUN: nothing was written.")
                return
            try:
                with transaction.atomic():
                    with impersonate(actor):
                        importer.run()
                    if options["rollback"]:
                        raise _RollbackRequested()
            except _RollbackRequested:
                self._print_report(importer, mode="ROLLBACK: the import ran completely and was rolled back.")
                return
        except JiraImportError as e:
            raise CommandError("Import refused:\n  " + "\n  ".join(e.messages)) from e

        self._print_report(importer, mode="Import committed.")
