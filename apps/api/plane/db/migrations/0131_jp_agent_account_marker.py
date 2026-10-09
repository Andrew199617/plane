# Jira-parity: mark existing agent accounts with User.bot_type = "AGENT" (plane.utils.agent).
# Agent accounts are the users create_agent_user made: username "agent_<hex>" and an active
# workspace membership with the Agent role (10). Data-only; the reverse is a no-op.

from django.db import migrations
from django.db.models import Q


AGENT_BOT_TYPE = "AGENT"


def mark_agent_accounts(apps, schema_editor):
    User = apps.get_model("db", "User")
    WorkspaceMember = apps.get_model("db", "WorkspaceMember")
    agent_ids = WorkspaceMember.objects.filter(
        role=10, is_active=True, deleted_at__isnull=True, member__username__startswith="agent_"
    ).values_list("member_id", flat=True)
    User.objects.filter(Q(bot_type__isnull=True) | Q(bot_type=""), id__in=agent_ids, is_bot=False).update(
        bot_type=AGENT_BOT_TYPE
    )


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0130_jp_team_provisioned_members"),
    ]

    operations = [
        migrations.RunPython(mark_agent_accounts, migrations.RunPython.noop),
    ]
