# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Repair installations that already applied the original Agent role migration.

0123 originally changed choices without remapping Viewer invitations. Its recorded application
time distinguishes those legacy invitations from Agent invitations created after the rollout.
Existing agent accounts keep their marker even after deactivation. Positively identified agent
accounts release any real email address they pre-registered; old human Agent tokens are revoked
rather than reinterpreted as personal tokens. This cleanup is intentionally irreversible.
"""

from django.db import migrations
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone


AGENT = 10
AGENT_BOT_TYPE = "AGENT"


def _legacy_role_cutoff(schema_editor):
    migration = (
        MigrationRecorder(schema_editor.connection).migration_qs.filter(app="db", name="0123_jp_agent_role").first()
    )
    return migration.applied if migration is not None else None


def clean_up_legacy_agents(apps, schema_editor):
    alias = schema_editor.connection.alias
    cutoff = _legacy_role_cutoff(schema_editor)
    if cutoff is not None:
        for model_name in ("WorkspaceMemberInvite", "ProjectMemberInvite"):
            apps.get_model("db", model_name).objects.using(alias).filter(role=AGENT, created_at__lt=cutoff).update(
                role=5
            )

    User = apps.get_model("db", "User")
    WorkspaceMember = apps.get_model("db", "WorkspaceMember")
    APIToken = apps.get_model("db", "APIToken")

    # The first marker migration used a broad prefix. Correct any resulting human false positives
    # before revoking legacy tokens, without changing their identity or email verification.
    User.objects.using(alias).filter(
        bot_type=AGENT_BOT_TYPE,
        username__startswith="agent_",
        is_bot=False,
    ).exclude(
        username__regex=r"^agent_[0-9a-f]{16}$",
        is_password_autoset=True,
    ).update(bot_type=None)

    # create_agent_user generated this exact username and autoset password, including for accounts
    # since deactivated or re-roled. Normal signup and profile edits cannot choose a username.
    User.objects.using(alias).filter(
        Q(bot_type__isnull=True) | Q(bot_type=""),
        username__regex=r"^agent_[0-9a-f]{16}$",
        is_bot=False,
        is_password_autoset=True,
    ).update(bot_type=AGENT_BOT_TYPE)

    legacy_accounts = User.objects.using(alias).filter(
        bot_type=AGENT_BOT_TYPE,
        username__regex=r"^agent_[0-9a-f]{16}$",
        is_bot=False,
        is_password_autoset=True,
    )
    for user in legacy_accounts.iterator():
        memberships = WorkspaceMember.objects.using(alias).filter(member_id=user.id).select_related("workspace")
        domains = [f"agents.{member.workspace.slug}.local".lower() for member in memberships]
        current_domain = (user.email or "").strip().lower().rsplit("@", 1)[-1]
        if current_domain in domains or current_domain == "agents.invalid":
            continue
        # The real email owner must be able to create their own account. The UUID-based replacement
        # cannot collide with normal provisioning; .invalid also covers agents with no membership.
        domain = domains[0] if domains else "agents.invalid"
        replacement = f"agent-{user.id.hex}@{domain}"
        suffix = 0
        while User.objects.using(alias).filter(email=replacement).exclude(pk=user.pk).exists():
            suffix += 1
            replacement = f"agent-{user.id.hex}-{suffix}@{domain}"
        User.objects.using(alias).filter(pk=user.pk).update(email=replacement, is_email_verified=False)

    now = timezone.now()
    # Before the explicit marker, an admin could mint these for a human. Their workspace role may
    # already have changed back, so revocation must not depend on their current role or description.
    APIToken.objects.using(alias).filter(
        user_type=1,
        user__is_bot=False,
        is_active=True,
    ).exclude(user__bot_type=AGENT_BOT_TYPE).update(is_active=False, updated_at=now)

    active_membership = WorkspaceMember.objects.using(alias).filter(
        member_id=OuterRef("user_id"),
        workspace_id=OuterRef("workspace_id"),
        role=AGENT,
        is_active=True,
        deleted_at__isnull=True,
    )
    APIToken.objects.using(alias).filter(
        user__bot_type=AGENT_BOT_TYPE,
        is_active=True,
    ).filter(Q(workspace__isnull=True) | ~Exists(active_membership)).update(is_active=False, updated_at=now)


def cap_stale_agent_project_roles(apps, schema_editor):
    alias = schema_editor.connection.alias
    ProjectMember = apps.get_model("db", "ProjectMember")
    WorkspaceMember = apps.get_model("db", "WorkspaceMember")
    for workspace_id, member_id in set(
        ProjectMember.objects.using(alias)
        .filter(role=AGENT, deleted_at__isnull=True)
        .values_list("workspace_id", "member_id")
    ):
        membership = (
            WorkspaceMember.objects.using(alias)
            .filter(workspace_id=workspace_id, member_id=member_id, deleted_at__isnull=True)
            .first()
        )
        rows = ProjectMember.objects.using(alias).filter(
            workspace_id=workspace_id, member_id=member_id, role=AGENT, deleted_at__isnull=True
        )
        if membership is None or not membership.is_active:
            rows.update(role=5, is_active=False, updated_at=timezone.now())
        elif membership.role != AGENT:
            rows.update(role=min(membership.role, 15), updated_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [("db", "0131_jp_agent_account_marker")]

    operations = [
        migrations.RunPython(clean_up_legacy_agents, migrations.RunPython.noop),
        migrations.RunPython(cap_stale_agent_project_roles, migrations.RunPython.noop),
    ]
