# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Project creation with the same semantics as the project-create API endpoints.

Mirrors app ProjectViewSet.create / v1 ProjectListCreateAPIEndpoint.post minus the celery activity:
ProjectSerializer (Project + ProjectIdentifier, name/identifier/category validation) -> creator
Admin membership -> project lead Admin membership -> DEFAULT_STATES (the standard Jira states) ->
run_project_created_hooks (work item types, standard workflow, agents, teams, lead defaults).
"""

# Django imports
from django.db import transaction

# Module imports
from plane.db.models import Project, ProjectCategory, State
from plane.db.models.project import ROLE
from plane.utils.jira_parity.project_hooks import run_project_created_hooks
from plane.utils.project_membership import ensure_project_member


class ProjectCreateError(ValueError):
    def __init__(self, identifier, errors):
        self.identifier = identifier
        self.errors = errors
        super().__init__(f"Could not create project {identifier}: {errors}")


def create_default_states(project, actor):
    """Same bulk_create over DEFAULT_STATES as the project-create views (read at call time)."""
    from plane.db.models import state as state_module

    State.objects.bulk_create(
        [
            State(
                name=spec["name"],
                color=spec["color"],
                project=project,
                sequence=spec["sequence"],
                workspace=project.workspace,
                group=spec["group"],
                default=spec.get("default", False),
                created_by=actor,
            )
            for spec in state_module.DEFAULT_STATES
        ]
    )


def ensure_categories(workspace, config, *, assign_projects=False):
    """Idempotently create the project categories named by the --config file.

    Creation (and, with assign_projects=True, assigning the configured Jira projects that have no
    category yet) is delegated to the categories feature (apply_category_mapping, overwrite=False,
    so a category picked by a user is kept). Categories without a description/logo get the
    configured ones. Without a config nothing is created.

    Returns ({category name: ProjectCategory}, apply_category_mapping result dict).
    """
    from plane.utils.project_categories import apply_category_mapping

    names = config.category_names()
    mapping = {}
    if assign_projects:
        existing = set(Project.objects.filter(workspace_id=workspace.id).values_list("identifier", flat=True))
        mapping = {key: name for key, name in config.project_category_map.items() if key in existing}
    result = apply_category_mapping(workspace, categories=names, mapping=mapping, overwrite=False)
    specs = {spec.name.casefold(): spec for spec in config.categories}
    categories = {}
    for name in names:
        category = ProjectCategory.objects.filter(workspace_id=workspace.id, name__iexact=name).first()
        if category is None:  # apply_category_mapping always creates it; defensive
            continue
        spec = specs.get(name.casefold())
        updates = {}
        if spec is not None and spec.description and not category.description:
            updates["description"] = spec.description
        if spec is not None and spec.logo_props and not category.logo_props:
            updates["logo_props"] = spec.logo_props
        if updates:
            ProjectCategory.objects.filter(pk=category.pk).update(**updates)
            for field_name, value in updates.items():
                setattr(category, field_name, value)
        categories[name] = category
    return categories, result


def create_project_like_api(
    workspace,
    actor,
    *,
    name,
    identifier,
    description="",
    project_lead=None,
    logo_props=None,
    category=None,
    field_overrides=None,
):
    """Create a project exactly like the API does and return (project, hook_results).

    Raises ProjectCreateError with the serializer errors when name/identifier are invalid or taken.
    `field_overrides` are extra Project columns set right after creation (e.g. cycle_view=True,
    external_source="jira"); `category` is a ProjectCategory (or None).
    """
    from plane.app.serializers import ProjectSerializer

    data = {"name": name, "identifier": identifier, "description": description or "", "network": 2}
    if project_lead is not None:
        data["project_lead"] = str(project_lead.id)
        data["default_assignee"] = str(project_lead.id)
    if logo_props:
        data["logo_props"] = logo_props
    if category is not None:
        data["category_id"] = str(category.id)

    with transaction.atomic():
        serializer = ProjectSerializer(data=data, context={"workspace_id": workspace.id})
        if not serializer.is_valid():
            raise ProjectCreateError(identifier, serializer.errors)
        project = serializer.save()

        ensure_project_member(project, actor, ROLE.ADMIN)
        if project.project_lead_id is not None and project.project_lead_id != actor.id:
            ensure_project_member(project, project.project_lead_id, ROLE.ADMIN)

        create_default_states(project, actor)

        updates = dict(field_overrides or {})
        if category is not None and project.category_id != category.id:
            updates["category_id"] = category.id
        if updates:
            Project.objects.filter(pk=project.pk).update(**updates)
        project = Project.objects.get(pk=project.pk)

        hook_results = run_project_created_hooks(project, actor)
        project.refresh_from_db()
    return project, hook_results
