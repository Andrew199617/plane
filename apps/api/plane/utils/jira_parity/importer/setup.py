# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Idempotent Jira-parity workspace configuration (management command `setup_jira_parity`).

Steps: instance sign-up off; admin, workspace (and default-UTC project) timezone; workspace work
item types (+ backfill of untyped work items); the project categories of the --config file (+ the
configured category of projects that have none); Devs/Agents teams; and for every project: Admin
membership for the admin, project lead = admin (the default assignee follows), the standard
workflow (states + agent rules), then the project-created hooks (types, workflow, agents, teams,
lead defaults); finally a workspace-wide agent sync.

Feature behaviour is delegated to the feature services. Every step runs in its own savepoint: a
failing step is reported (SetupReport.warnings) and the others still run.
"""

# Python imports
import importlib
import logging
from dataclasses import dataclass, field

# Django imports
from django.core.cache import cache
from django.db import transaction

# Module imports
from plane.db.models import Project, User, Workspace
from plane.db.models.project import ROLE
from plane.db.models.team import TeamMember, TeamProject
from plane.utils.exception_logger import log_exception
from plane.utils.jira_parity.project_hooks import run_project_created_hooks
from plane.utils.project_membership import ensure_project_member

from .config import JiraParityConfig
from .constants import DEFAULT_TIMEZONE
from .projects import ensure_categories

logger = logging.getLogger("plane.api")
_DEFAULT_PROJECT_TIMEZONE = "UTC"

_INSTANCE_CACHE_KEYS = ("/api/instances/", "/api/instances/configurations/")


@dataclass
class SetupReport:
    lines: list = field(default_factory=list)
    projects: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def add(self, section, message):
        self.lines.append((section, message))

    def warn(self, message):
        self.warnings.append(message)


def _call_feature(module_name, function_name, *args, **kwargs):
    module = importlib.import_module(module_name)
    return getattr(module, function_name)(*args, **kwargs)


def _step(report, section, func, *args, **kwargs):
    """Run one setup step in a savepoint; a failure is reported and returns None."""
    try:
        with transaction.atomic():
            return func(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 - one failing feature must not stop the setup
        report.warn(f"{section}: {type(e).__name__}: {e}")
        logger.warning("setup_jira_parity step '%s' failed: %s", section, e)
        log_exception(e)
        return None


def disable_public_signup(report):
    from plane.license.models import InstanceConfiguration

    config = InstanceConfiguration.objects.filter(key="ENABLE_SIGNUP").first()
    if config is None:
        InstanceConfiguration.objects.create(
            key="ENABLE_SIGNUP", value="0", category="AUTHENTICATION", is_encrypted=False
        )
        report.add("instance", "ENABLE_SIGNUP created = 0")
    elif config.value != "0":
        InstanceConfiguration.objects.filter(pk=config.pk).update(value="0")
        report.add("instance", f"ENABLE_SIGNUP {config.value!r} -> '0'")
    else:
        report.add("instance", "ENABLE_SIGNUP already 0")

    def _clear_cache():
        try:
            cache.delete_many(list(_INSTANCE_CACHE_KEYS))
        except Exception:  # noqa: BLE001 - cache outages must not fail the setup
            logger.warning("setup_jira_parity: could not clear instance config cache")

    transaction.on_commit(_clear_cache)


def set_timezones(workspace, admin, timezone_name, report):
    if admin.user_timezone != timezone_name:
        User.objects.filter(pk=admin.pk).update(user_timezone=timezone_name)
        report.add("timezone", f"{admin.email}: {admin.user_timezone} -> {timezone_name}")
        admin.user_timezone = timezone_name
    else:
        report.add("timezone", f"{admin.email}: already {timezone_name}")
    if workspace.timezone != timezone_name:
        Workspace.objects.filter(pk=workspace.pk).update(timezone=timezone_name)
        report.add("timezone", f"workspace {workspace.slug}: {workspace.timezone} -> {timezone_name}")
        workspace.timezone = timezone_name
    else:
        report.add("timezone", f"workspace {workspace.slug}: already {timezone_name}")
    # Projects copy the workspace timezone when created; ones still on the model default follow it
    # (cycle dates are stored/displayed in the project timezone).
    moved = Project.objects.filter(workspace_id=workspace.id, timezone=_DEFAULT_PROJECT_TIMEZONE).exclude(
        timezone=timezone_name
    )
    count = moved.update(timezone=timezone_name)
    if count:
        report.add("timezone", f"{count} project(s): {_DEFAULT_PROJECT_TIMEZONE} -> {timezone_name}")


def ensure_work_item_types(workspace, report):
    types = _call_feature("plane.utils.work_item_types", "ensure_workspace_work_item_types", workspace) or []
    report.add("types", ", ".join(issue_type.name for issue_type in types) or "(none: feature not implemented)")
    module = importlib.import_module("plane.utils.work_item_types")
    if hasattr(module, "backfill_issue_types"):
        backfilled = module.backfill_issue_types(workspace)
        if any(backfilled.values()):
            report.add("types", f"untyped work items set to the default type: {backfilled}")
    return types


def ensure_project_categories(workspace, config, report):
    categories, result = ensure_categories(workspace, config, assign_projects=True)
    if not categories:
        report.add("categories", "none configured (see --config)")
        return categories
    report.add(
        "categories",
        f"{', '.join(categories)} (created: {', '.join(result['created']) or '-'}; "
        f"assigned: {', '.join(f'{k}={v}' for k, v in sorted(result['assigned'].items())) or '-'})",
    )
    return categories


def ensure_teams(workspace, report):
    teams = _call_feature("plane.utils.teams", "seed_default_teams", workspace) or {}
    for name, team in teams.items():
        members = TeamMember.objects.filter(team_id=team.id).count()
        projects = TeamProject.objects.filter(team_id=team.id, project__archived_at__isnull=True).count()
        report.add(
            "teams",
            f"{name}: role {team.default_project_role}, auto_join {team.auto_join}, "
            f"{members} member(s), {projects} project(s)",
        )
    return teams


def _set_project_lead(project, admin):
    """Project lead = admin; the default assignee follows when it was the old lead or unset."""
    if project.project_lead_id == admin.id:
        return []
    old_lead_id, old_default_id = project.project_lead_id, project.default_assignee_id
    Project.objects.filter(pk=project.pk).update(project_lead_id=admin.id)
    project.project_lead_id = admin.id
    changed = ["lead"]
    follow = _call_feature(
        "plane.utils.project_defaults",
        "apply_project_lead_change",
        project,
        old_lead_id=old_lead_id,
        old_default_assignee_id=old_default_id,
    )
    if follow and "default_assignee_id" in follow:
        changed.append("default_assignee")
    return changed


def _describe_workflow(summary):
    parts = []
    if summary.get("created"):
        parts.append("+" + "/".join(summary["created"]))
    if summary.get("renamed"):
        parts.append(", ".join(summary["renamed"]))
    if summary.get("merged"):
        parts.append(", ".join(f"{name}=>({count})" for name, count in summary["merged"].items()))
    if summary.get("updated"):
        parts.append("~" + "/".join(summary["updated"]))
    if summary.get("rules_changed"):
        parts.append(f"{summary['rules_changed']} agent rule(s)")
    if summary.get("workflow_enabled"):
        parts.append("workflow on")
    return " ".join(parts)


def configure_project(project, admin, report):
    """Per-project configuration (each part in its own savepoint); returns a summary row."""
    row = {"identifier": project.identifier, "name": project.name, "changes": []}

    _step(report, f"{project.identifier} membership", ensure_project_member, project, admin, ROLE.ADMIN)
    lead_changes = _step(report, f"{project.identifier} lead", _set_project_lead, project, admin)
    row["changes"].extend(lead_changes or [])

    workflow = _step(
        report,
        f"{project.identifier} workflow",
        _call_feature,
        "plane.utils.workflow",
        "seed_project_workflow",
        project,
    )
    if isinstance(workflow, dict) and _describe_workflow(workflow):
        row["changes"].append("states " + _describe_workflow(workflow))

    project.refresh_from_db()
    row["hooks"] = run_project_created_hooks(project, admin)
    failed = [name for name, ok in row["hooks"].items() if not ok]
    if failed:
        report.warn(f"{project.identifier}: project hooks failed: {', '.join(failed)} (see plane.api log)")
    project.refresh_from_db()
    row["lead"] = project.project_lead_id == admin.id
    row["default_assignee"] = project.default_assignee_id == admin.id
    row["category"] = project.category.name if project.category_id else ""
    report.projects.append(row)
    return row


def run_setup(workspace, admin, *, timezone_name=DEFAULT_TIMEZONE, config=None):
    """Run every setup step inside the caller's transaction and return a SetupReport.

    `config` is the loaded --config file (JiraParityConfig); without one no categories are created.
    """
    config = config if config is not None else JiraParityConfig()
    report = SetupReport()
    _step(report, "instance", disable_public_signup, report)
    _step(report, "timezone", set_timezones, workspace, admin, timezone_name, report)
    _step(report, "work item types", ensure_work_item_types, workspace, report)
    _step(report, "categories", ensure_project_categories, workspace, config, report)
    _step(report, "teams", ensure_teams, workspace, report)

    projects = Project.objects.filter(workspace_id=workspace.id, archived_at__isnull=True).order_by("identifier")
    for project in projects:
        configure_project(project, admin, report)

    count = _step(report, "agents", _call_feature, "plane.utils.agent", "sync_agent_memberships", workspace)
    if count is not None:
        report.add("agents", f"sync_agent_memberships: {count} (agent, project) membership(s) ensured")
    return report
