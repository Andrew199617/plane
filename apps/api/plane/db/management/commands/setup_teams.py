# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity: create/update the default workspace teams (Devs, Agents) and provision them.

    python manage.py setup_teams --workspace <slug>

Idempotent (see plane.utils.teams.seed_default_teams). Re-run after creating agent accounts to
add them to the Agents team.
"""

# Django imports
from django.core.management import BaseCommand, CommandError

# Module imports
from plane.db.models import Workspace
from plane.db.models.team import TeamMember, TeamProject
from plane.utils.teams import seed_default_teams


class Command(BaseCommand):
    help = "Create or update the default teams (Devs, Agents) of a workspace and add them to every project"

    def add_arguments(self, parser):
        parser.add_argument("--workspace", type=str, required=True, help="Workspace slug")

    def handle(self, *args, **options):
        workspace = Workspace.objects.filter(slug=options["workspace"]).first()
        if workspace is None:
            raise CommandError(f"Workspace '{options['workspace']}' not found")

        teams = seed_default_teams(workspace)
        for name, team in teams.items():
            members = TeamMember.objects.filter(team_id=team.id).count()
            projects = TeamProject.objects.filter(team_id=team.id, project__archived_at__isnull=True).count()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Team '{name}': role={team.default_project_role} auto_join={team.auto_join} "
                    f"members={members} projects={projects}"
                )
            )
