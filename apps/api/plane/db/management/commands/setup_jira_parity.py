# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity: idempotent workspace configuration.

    python manage.py setup_jira_parity --workspace <slug> [--admin <email>] [--timezone <tz>]
        [--config <path>] [--rollback]

Instance sign-up off (ENABLE_SIGNUP=0); admin + workspace timezone; standard work item types;
the project categories and project -> category mapping of the --config file (see
plane/utils/jira_parity/importer/jira_parity.example.json); teams Devs (Admin, auto-join) and
Agents (Agent, auto-join); for every project: admin membership,
project lead = admin (default assignee follows), standard states + agent transition rules, and
the project-created hooks (types, workflow, agents, teams, lead defaults); workspace agent sync.
Safe to re-run. --rollback runs everything and rolls it back (prints what would change).
See plane.utils.jira_parity.importer.setup.
"""

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
from plane.utils.jira_parity.importer.report import format_table
from plane.utils.jira_parity.importer.setup import run_setup


class _RollbackRequested(Exception):
    """Raised inside the setup transaction to roll it back (--rollback)."""


class Command(BaseCommand):
    help = (
        "Configure a workspace for Jira parity (idempotent): sign-up off, timezone, types, categories, teams, workflows"
    )

    def add_arguments(self, parser):
        parser.add_argument("--workspace", type=str, required=True, help="Workspace slug")
        parser.add_argument("--admin", type=str, default="", help="Admin e-mail (default: workspace owner)")
        parser.add_argument(
            "--timezone",
            type=str,
            default="",
            help=(
                f"Workspace timezone (default: ${TIMEZONE_ENV_VAR}, else the config's timezone, else the "
                "admin's timezone when it is not UTC, else UTC)"
            ),
        )
        parser.add_argument(
            "--config",
            type=str,
            default="",
            help=f"Workspace-specific JSON config (default: ${CONFIG_ENV_VAR}; none = no categories)",
        )
        parser.add_argument("--rollback", action="store_true", help="Run everything, then roll it back")

    def handle(self, *args, **options):
        workspace = Workspace.objects.filter(slug=options["workspace"]).first()
        if workspace is None:
            raise CommandError(f"Workspace '{options['workspace']}' not found")
        if options["admin"]:
            admin = User.objects.filter(email__iexact=options["admin"].strip()).first()
            if admin is None:
                raise CommandError(f"User '{options['admin']}' not found")
        else:
            admin = workspace.owner
        if not WorkspaceMember.objects.filter(
            workspace_id=workspace.id, member_id=admin.id, role=ROLE.ADMIN.value, is_active=True
        ).exists():
            raise CommandError(f"{admin.email} is not an active admin of workspace '{workspace.slug}'")
        try:
            config = load_config(options["config"])
        except JiraParityConfigError as e:
            raise CommandError(str(e)) from e
        timezone_name = resolve_timezone(options["timezone"], config, admin)
        if timezone_name not in pytz.all_timezones_set:
            raise CommandError(f"Unknown timezone '{timezone_name}'")

        report = None
        try:
            with transaction.atomic():
                with impersonate(admin):
                    report = run_setup(workspace, admin, timezone_name=timezone_name, config=config)
                if options["rollback"]:
                    raise _RollbackRequested()
        except _RollbackRequested:
            self._print(report, workspace, admin, config)
            self.stdout.write(self.style.SUCCESS("ROLLBACK: the setup ran completely and was rolled back."))
            return
        self._print(report, workspace, admin, config)
        self.stdout.write(self.style.SUCCESS("Setup committed."))

    def _print(self, report, workspace, admin, config):
        self.stdout.write(f"Workspace '{workspace.slug}' ({workspace.name}), admin {admin.email}")
        self.stdout.write(f"Config: {config.source or '(none)'}")
        for section, message in report.lines:
            self.stdout.write(f"[{section}] {message}")
        if report.projects:
            self.stdout.write("")
            rows = [
                {
                    "Project": row["identifier"],
                    "Name": row["name"],
                    "Category": row.get("category") or "-",
                    "Lead": "yes" if row.get("lead") else "NO",
                    "Default assignee": "yes" if row.get("default_assignee") else "NO",
                    "Hooks": "ok"
                    if all(row.get("hooks", {}).values())
                    else "failed: " + ",".join(k for k, ok in row.get("hooks", {}).items() if not ok),
                    "Changes": "; ".join(row["changes"]) or "-",
                }
                for row in report.projects
            ]
            for line in format_table(rows):
                self.stdout.write(line)
        else:
            self.stdout.write("(no projects yet: run import_jira_csv, then re-run this command if needed)")
        if report.warnings:
            self.stdout.write("")
            for message in report.warnings:
                self.stdout.write(self.style.WARNING(f"WARNING: {message}"))
