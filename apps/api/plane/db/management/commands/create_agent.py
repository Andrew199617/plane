# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity: create an agent account (workspace role Agent = 10) and print its API token.

    python manage.py create_agent --workspace <slug> --name "Claude Dev" [--email x] [--token-label y] [--no-token]

The agent joins every non-archived project as Agent and authenticates to /api/v1 with the printed
X-Api-Key token (shown only once). If an active agent with that display name already exists in the
workspace, no new account is created; a new token is minted unless --no-token is given.

Operator-only: unlike the agents API (agents.<slug>.local addresses only), --email accepts any
address; it is left unverified and its owner can no longer sign up with it, so prefer the default.
"""

# Django imports
from django.core.management import BaseCommand, CommandError

# Module imports
from plane.db.models import ProjectMember, Workspace, WorkspaceMember
from plane.utils.agent import (
    AGENT,
    AGENT_BOT_TYPE,
    AgentProvisioningError,
    create_agent_token,
    create_agent_user,
    sync_agent_memberships,
)


class Command(BaseCommand):
    help = "Create an agent account (role Agent) in a workspace and print its API token"

    def add_arguments(self, parser):
        parser.add_argument("--workspace", type=str, required=True, help="Workspace slug")
        parser.add_argument("--name", type=str, required=True, help="Agent display name")
        parser.add_argument(
            "--email",
            type=str,
            default=None,
            help="Email (default <name>@agents.<slug>.local); any other address is accepted but left unverified",
        )
        parser.add_argument("--token-label", type=str, default=None, help="Label of the API token")
        parser.add_argument("--no-token", action="store_true", help="Do not mint an API token")

    def handle(self, *args, **options):
        workspace = Workspace.objects.filter(slug=options["workspace"]).first()
        if workspace is None:
            raise CommandError(f"Workspace '{options['workspace']}' not found")

        name = (options["name"] or "").strip()
        workspace_member = (
            WorkspaceMember.objects.filter(
                workspace=workspace,
                role=AGENT,
                is_active=True,
                member__display_name=name,
                member__bot_type=AGENT_BOT_TYPE,
            )
            .select_related("member")
            .first()
        )
        if workspace_member is not None:
            sync_agent_memberships(workspace, users=[workspace_member.member_id])
            self.stdout.write(self.style.WARNING(f"Agent '{name}' already exists; reusing it"))
        else:
            try:
                workspace_member = create_agent_user(workspace, name, email=options["email"], allow_custom_email=True)
            except AgentProvisioningError as e:
                raise CommandError(str(e))
            self.stdout.write(self.style.SUCCESS(f"Created agent '{name}'"))

        user = workspace_member.member
        projects = ProjectMember.objects.filter(
            workspace=workspace, member=user, is_active=True, role=AGENT, project__archived_at__isnull=True
        ).count()
        self.stdout.write(f"user_id={user.id}")
        self.stdout.write(f"email={user.email}")
        self.stdout.write(f"projects={projects}")
        if not options["no_token"]:
            token = create_agent_token(user, workspace, label=options["token_label"])
            self.stdout.write(f"token={token.token}")
            self.stdout.write(self.style.WARNING("Store this token now: it is not shown again."))
