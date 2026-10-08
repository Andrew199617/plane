# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Project-created hook (Jira-parity scaffold).

`run_project_created_hooks(project, actor)` is called by BOTH project-create code paths
(app ProjectViewSet.create and v1 ProjectListCreateAPIEndpoint.post) after the creator's
ProjectMember row, the project-lead ProjectMember row and the default states exist, and before
the response is built.

Each feature hook runs in its own savepoint and its own try/except: a failing feature is logged
and skipped so it can never block project creation (and never poisons the v1 outer transaction).
Feature modules are imported lazily so a broken feature module only disables its own hook.
"""

# Python imports
import importlib
import logging

# Django imports
from django.db import transaction

# Module imports
from plane.utils.exception_logger import log_exception

logger = logging.getLogger("plane.api")


def _seed_work_item_types(project, actor):
    module = importlib.import_module("plane.utils.work_item_types")
    module.seed_project_work_item_types(project)


def _seed_workflow(project, actor):
    module = importlib.import_module("plane.utils.workflow")
    module.seed_project_workflow(project)


def _sync_agents(project, actor):
    module = importlib.import_module("plane.utils.agent")
    module.sync_agent_memberships(project.workspace, projects=[project])


def _auto_join_teams(project, actor):
    module = importlib.import_module("plane.utils.teams")
    module.apply_auto_join_teams(project)


def _project_lead_defaults(project, actor):
    module = importlib.import_module("plane.utils.project_defaults")
    module.apply_project_lead_defaults(project, actor)


# Order matters: types and workflow need the default states; memberships come before the
# lead/default-assignee defaults so the lead is already a member when defaults are applied.
PROJECT_CREATED_HOOKS = (
    ("work_item_types", _seed_work_item_types),
    ("workflow", _seed_workflow),
    ("agents", _sync_agents),
    ("teams", _auto_join_teams),
    ("project_defaults", _project_lead_defaults),
)


def run_project_created_hooks(project, actor):
    """Run every Jira-parity feature hook for a newly created project.

    Args:
        project: the freshly created db.Project instance.
        actor: the requesting user (request.user); may be None for system callers.

    Returns:
        dict {hook_name: True | False} telling which hooks succeeded (useful in tests/commands).
    """
    results = {}
    for name, hook in PROJECT_CREATED_HOOKS:
        try:
            with transaction.atomic():
                hook(project, actor)
            results[name] = True
        except Exception as e:  # noqa: BLE001 - one feature must never block project creation
            results[name] = False
            logger.warning(
                "Jira-parity project-created hook '%s' failed for project %s: %s",
                name,
                getattr(project, "id", None),
                e,
            )
            log_exception(e)
    return results
